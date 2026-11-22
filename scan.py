"""Scan OCR du HUD -> timeline.json (modes cup / ranked_reload / ranked_br)

  python 2_scan.py               scan complet (décodage NVDEC + EasyOCR GPU), puis analyse
  python 2_scan.py --reanalyze   refait UNIQUEMENT l'analyse depuis work/scan_raw.jsonl
                                 (quelques secondes : pratique pour ajuster les seuils de config.json)
"""
import argparse
import json
import os
import queue
import re
import statistics
import subprocess
import threading
import time
from collections import Counter

import cv2
import numpy as np

from common import (HERE, HudOCR, crop, ffprobe_info, fmt_tc, load_config, need, video_path,
                    work_dir)

TEXT_ROIS = ("lobby", "spectate")
RAW_NAME = "scan_raw_v3.jsonl"
PTS_RE = re.compile(rb"pts_time:\s*([-0-9.]+)")


# --------------------------------------------------------------------------- scan
def frame_reader(video, w, h, fps=None, keyframes=False, start=0.0, duration=None, hw=None):
    """Décode la vidéo (NVDEC) et renvoie (timestamp, image BGR).
    keyframes=True : seules les images clés sont décodées (-skip_frame nokey) -> des dizaines de fois plus rapide."""
    cmd = [need("ffmpeg"), "-hide_banner", "-loglevel", "info", "-nostats"]
    if hw is None:
        from common import detect_encoder
        hw = os.environ.get("MONTAGE_NO_CUDA") != "1" and detect_encoder() == "nvenc"
    if hw:
        cmd += ["-hwaccel", "cuda"]
    if keyframes:
        cmd += ["-skip_frame", "nokey"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(video)]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    vf = (f"fps={fps}," if fps and not keyframes else "") + f"scale={w}:{h},showinfo"
    cmd += ["-an", "-vf", vf, "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=w * h * 3 * 4)
    pts_q = queue.Queue()

    def read_stderr():
        for line in iter(proc.stderr.readline, b""):
            m = PTS_RE.search(line)
            if m and b"Parsed_showinfo" in line:
                pts_q.put(float(m.group(1)))
        pts_q.put(None)

    threading.Thread(target=read_stderr, daemon=True).start()
    size = w * h * 3
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            t = pts_q.get(timeout=60)
            if t is None:
                break
            yield start + t, np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()


def keyframe_interval(video, probe_s=60):
    """Écart moyen entre images clés sur la première minute (lecture des paquets, sans décodage)."""
    out = subprocess.run([need("ffprobe"), "-v", "error", "-select_streams", "v:0",
                          "-read_intervals", f"%+{probe_s}", "-show_entries", "packet=pts_time,flags",
                          "-of", "csv=p=0", str(video)], capture_output=True, text=True).stdout
    ts = [float(l.split(",")[0]) for l in out.splitlines()
          if "K" in l.split(",")[-1] and l.split(",")[0] not in ("", "N/A")]
    if len(ts) < 2:
        return None
    return (ts[-1] - ts[0]) / (len(ts) - 1)


def scan(cfg):
    sc, rois = cfg["scan"], cfg["rois"]
    if "hud" not in rois:
        raise SystemExit("[ERREUR] zone 'hud' absente de config.json (lance 1_calibrate.py)")
    video, wd = video_path(cfg), work_dir(cfg)
    info = ffprobe_info(video)
    w, h = sc["analysis_width"], sc["analysis_height"]

    keyframes = sc["mode"] == "keyframes"
    ki = None
    if keyframes:
        ki = keyframe_interval(video)
        if ki is None or ki > sc["max_keyframe_interval_s"]:
            print(f"[SCAN] images clés trop espacées ({ki}) -> mode {sc['fps']} img/s")
            keyframes = False
        else:
            print(f"[SCAN] mode images clés : 1 image toutes les {ki:.2f} s")
    step = ki if keyframes else 1 / sc["fps"]
    sc["_step"] = step
    total = int(info["duration"] / step)
    print(f"[SCAN] {video.name} : {fmt_tc(info['duration'])[:8]}, ~{total} images à analyser")

    print(">> Chargement du moteur de lecture d'écran (OCR)...", flush=True)
    ocr = HudOCR(sc)
    print(">> Scan des images...", flush=True)
    ranked = cfg.get("mode_rank", cfg["mode"].startswith("ranked"))
    box = cfg.get("mode_kind") == "box"
    lobby_n = 0
    raw_path = wd / RAW_NAME
    tmp_path = wd / (RAW_NAME + ".partiel")
    diag = wd / "diagnostic"
    diag.mkdir(exist_ok=True)
    diag_at = {int(total * f) for f in (0.15, 0.3, 0.45, 0.6, 0.75, 0.9)}
    stats = {"hud": 0, "rank": 0, "score": 0, "lobby": 0}
    t0 = time.time()
    n = 0
    with tmp_path.open("w", encoding="utf-8") as out:
        out.write(json.dumps({"_meta": {"step": step}}) + "\n")
        for t, frame in frame_reader(video, w, h, fps=sc["fps"], keyframes=keyframes):
            players, kills = ocr.read_hud_column(crop(frame, rois["hud"]))
            rec = {"t": round(t, 3), "players": players, "kills": kills}
            if box:
                band = crop(frame, rois["score"])
                sc_ = parse_score(ocr.reader.readtext(band, detail=1, paragraph=False), band.shape[1])
                if sc_:
                    rec["score"] = sc_
                elif ranked:
                    lobby_n += 1
                    if lobby_n % sc["rank_lobby_every"] == 0:
                        rk = parse_rank(ocr.reader.readtext(frame, detail=1, paragraph=False), w)
                        if rk:
                            rec["rank"] = rk
            elif players is None and ranked:
                lobby_n += 1
                if lobby_n % sc["rank_lobby_every"] == 0:
                    rk = parse_rank(ocr.reader.readtext(frame, detail=1, paragraph=False), w)
                    if rk:
                        rec["rank"] = rk
            elif players is None and "lobby" in rois:
                # pas de cache ici : deux écrans de salon différents se ressemblent trop
                rec["lobby"] = ocr.read_text(crop(frame, rois["lobby"]))
            elif players is not None:
                if "spectate" in rois:
                    rec["spec"] = has_kw(ocr.read_text(crop(frame, rois["spectate"])), sc["spectate_keywords"])
                if "top" in rois:
                    txt = ocr.read_text(crop(frame, rois["top"]))
                    m = TOP_RE.search(txt)
                    if m:
                        rec["top"] = int(m.group(1))
                    elif txt:
                        rec["top_txt"] = txt[:40]       # pour diagnostic
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            stats["hud"] += players is not None
            stats["rank"] += "rank" in rec
            stats["score"] += "score" in rec
            stats["lobby"] += bool(rec.get("lobby"))
            if n in diag_at:     # images pour comprendre ce que le scan voit
                small = cv2.resize(frame, (960, 540))
                x, y, rw, rh = rois["hud"]
                cv2.rectangle(small, (int(x * 960), int(y * 540)), (int((x + rw) * 960), int((y + rh) * 540)),
                              (0, 255, 255), 2)
                cv2.putText(small, f"{fmt_tc(t)[:8]} joueurs={players} kills={kills}", (10, 520),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.imwrite(str(diag / f"{fmt_tc(t)[:8].replace(':', '-')}.jpg"), small)
            n += 1
            if n % 50 == 0:
                el = time.time() - t0
                eta = el / n * max(0, total - n)
                print(f"  {fmt_tc(t)[:8]}  {n}/{total}  {n / el:5.1f} img/s  reste ~{eta / 60:4.1f} min"
                      f"  | joueurs={players} kills={kills} score={rec.get('score')}")
                out.flush()
    if n == 0 and keyframes:
        print("[SCAN] décodage des images clés impossible avec ce codec -> mode 1 img/s")
        cfg["scan"]["mode"] = "fps"
        return scan(cfg)
    if n == 0:
        tmp_path.unlink(missing_ok=True)
        raise SystemExit("[ERREUR] aucune image décodée (vidéo illisible ?)")
    with tmp_path.open("a", encoding="utf-8") as out:
        out.write(json.dumps({"_end": n}) + "\n")
    tmp_path.replace(raw_path)          # le scan n'est "fait" que s'il est allé jusqu'au bout
    print(f"[SCAN] terminé en {(time.time() - t0) / 60:.1f} min : {n} images, HUD lu sur {stats['hud']}, "
          f"rang lu {stats['rank']} fois, score lu {stats['score']} fois")
    if stats["hud"] < n * 0.05 and cfg.get("mode_kind") != "box":
        print("[ATTENTION] le HUD (kills / joueurs restants) n'a presque jamais été lu : mauvaise catégorie,\n"
              "            HUD Fortnite masqué/déplacé, ou rec qui n'est pas du Battle Royale.\n"
              f"            Images de contrôle : {diag}")
    return raw_path


# ----------------------------------------------------------------------- analyse
PARTIE_RE = re.compile(r"partie\s*(\d{1,2})(?!\d)")
TOTAL_RE = re.compile(r"\bsur\s*(\d{1,2})(?!\d)")
PTS_RE_TXT = re.compile(r"(\d{1,4})\s*pts")
TOP_RE = re.compile(r"top\s*(\d{1,2})")

# ------------------------------------------------------------------ rang (ranked)
TIERS = [("BRONZE", ("bronze",)), ("ARGENT", ("argent", "silver")), ("OR", ("or", "gold")),
         ("PLATINE", ("platine", "platinum")), ("DIAMANT", ("diamant", "diamond"))]
TOP_TIERS = [("ÉLITE", ("elite",)), ("CHAMPION", ("champion",)), ("UNREAL", ("unreal", "irreel"))]
ROMAN = ["I", "II", "III"]
PCT_RE = re.compile(r"(\d{1,3})\s*%")


def _norm(t):
    import unicodedata
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _division(tok):
    tok = tok.strip().lower()
    if tok in ("1", "2", "3"):
        return int(tok)
    if tok and all(c in "il|1" for c in tok) and len(tok) <= 3:
        return len(tok)
    return None


def rank_name(level):
    if level is None:
        return None
    if level < 15:
        return f"{TIERS[level // 3][0]} {ROMAN[level % 3]}"
    return TOP_TIERS[min(level - 15, 2)][0]


def parse_rank(results, W):
    """Cherche un rang Fortnite (Bronze I ... Unreal) + le % de progression le plus proche."""
    boxes = []
    for box, txt, conf in results:
        if conf < 0.3:
            continue
        cx = (box[0][0] + box[2][0]) / 2
        cy = (box[0][1] + box[2][1]) / 2
        boxes.append((cx, cy, _norm(txt), box))
    found = None
    for i, (cx, cy, txt, box) in enumerate(boxes):
        words = re.findall(r"[a-z]+|\d+|\|", txt)
        for j, wd in enumerate(words):
            for ti, (_, keys) in enumerate(TIERS):
                if wd in keys:
                    nxt = words[j + 1] if j + 1 < len(words) else None
                    if nxt is None and i + 1 < len(boxes) and abs(boxes[i + 1][1] - cy) < 30 \
                            and 0 < boxes[i + 1][0] - cx < 300:
                        nxt = boxes[i + 1][2].split()[0] if boxes[i + 1][2].split() else None
                    div = _division(nxt) if nxt else None
                    if div:
                        found = (ti * 3 + div - 1, cx, cy)
            for ti, (_, keys) in enumerate(TOP_TIERS):
                if wd in keys and len(txt) <= 20:
                    found = (15 + ti, cx, cy)
        if found:
            break
    if not found:
        return None
    level, rx, ry = found
    pct, best = None, 0.25 * W
    for cx, cy, txt, _ in boxes:
        m = PCT_RE.search(txt)
        if m and int(m.group(1)) <= 100:
            d = ((cx - rx) ** 2 + (cy - ry) ** 2) ** 0.5
            if d < best:
                pct, best = int(m.group(1)), d
    return [level, pct]


# ------------------------------------------------------------------ score (box fight / 1v1)
SCORE_RE = re.compile(r"(?<![\d:])(\d{1,2})\s*[-–—|]\s*(\d{1,2})(?![\d:])")


def parse_score(results, W):
    """Score des manches dans le bandeau du haut : 'A - B', ou deux nombres de part et d'autre du centre."""
    items = []
    for box, txt, conf in results:
        if conf < 0.35:
            continue
        cx = (box[0][0] + box[2][0]) / 2
        cy = (box[0][1] + box[2][1]) / 2
        h = abs(box[2][1] - box[0][1])
        items.append((cx, cy, h, txt.strip()))
    for cx, cy, h, txt in items:
        m = SCORE_RE.search(txt)
        if m and int(m.group(1)) <= 40 and int(m.group(2)) <= 40:
            return [int(m.group(1)), int(m.group(2))]
    nums = [(cx, cy, h, int(t)) for cx, cy, h, t in items if t.isdigit() and len(t) <= 2 and int(t) <= 40]
    best = None
    for a in nums:
        for b in nums:
            if a[0] < W / 2 < b[0] and abs(a[1] - b[1]) < max(a[2], b[2]) * 0.6 \
                    and abs((W / 2 - a[0]) - (b[0] - W / 2)) < W * 0.08 and abs(a[2] - b[2]) < max(a[2], b[2]) * 0.4:
                d = b[0] - a[0]
                if best is None or d < best[0]:
                    best = (d, [a[3], b[3]])
    return best[1] if best else None


def analyze_box(samples, cfg):
    """Box fight / 1v1 : un 'match' = une suite de scores qui montent ; nouveau match quand le score
    repart à 0, quand un salon (rang) apparaît, ou après un long trou sans score."""
    sc = cfg["scan"]
    reads = []
    for i, s in enumerate(samples):
        v = s.get("score")
        if not v:
            continue
        nxt = [tuple(x["score"]) for x in samples[i:i + 3] if x.get("score")]
        if nxt.count(tuple(v)) >= 2 or (reads and tuple(v) == reads[-1][1]):
            reads.append((s["t"], tuple(v)))
    rank_t = [s["t"] for s in samples if s.get("rank")]
    matches = []
    for t, v in reads:
        if matches:
            pt, pv = matches[-1][-1]
            reset = v[0] < pv[0] or v[1] < pv[1]
            if reset or t - pt > sc["split_gap_s"] or any(pt < x < t for x in rank_t):
                matches.append([(t, v)])
                continue
            matches[-1].append((t, v))
        else:
            matches.append([(t, v)])
    games, prev_end = [], 0.0
    bounds = [m[0][0] for m in matches] + [float("inf")]
    for gi, m in enumerate(matches):
        if len(m) < 2 and m[-1][1] == (0, 0):
            continue
        start, end = max(prev_end, m[0][0] - 20), m[-1][0] + 8
        rounds, last = [], m[0][1]
        for t, v in m[1:]:
            if v != last:
                rounds.append({"t": t, "score": list(v), "win": v[0] > last[0]})
                last = v
        g = {"start": start, "end": end, "kills": [r["t"] for r in rounds if r["win"]],
             "tops": [{"t": r["t"], "reached": "manche perdue"} for r in rounds if not r["win"]],
             "final_spectate": None, "rounds": rounds, "score": list(m[-1][1])}
        if cfg.get("mode_rank"):
            g["rank_before"] = rank_state([s for s in samples if prev_end <= s["t"] < m[0][0]])
            g["rank_after"] = rank_state([s for s in samples if m[-1][0] < s["t"] < bounds[gi + 1]])
        games.append(g)
        prev_end = end
    if not games and samples:
        # aucun score lisible : on garde tout le rec en un seul bloc (à ajuster dans le studio)
        g = {"start": samples[0]["t"], "end": samples[-1]["t"], "kills": [], "tops": [], "final_spectate": None,
             "rounds": [], "score": None, "no_score": True}
        if cfg.get("mode_rank"):
            g["rank_before"] = rank_state(samples[: len(samples) // 10 or 1])
            g["rank_after"] = rank_state(samples[-(len(samples) // 10 or 1):])
        games.append(g)
    return games


# ------------------------------------------------------------------ analyse
def has_kw(text, kws):
    text = (text or "").lower()
    return any(k in text for k in kws)


def lobby_markers(samples):
    """Cup : lectures du salon contenant 'Partie X' -> (t, partie, total, pts)."""
    out = []
    for s in samples:
        txt = (s.get("lobby") or "").lower().replace("|", "1")
        m = PARTIE_RE.search(txt)
        if not m or not 1 <= int(m.group(1)) <= 30:
            continue
        tm = TOTAL_RE.search(txt[m.end():m.end() + 12])
        pm = PTS_RE_TXT.search(txt[m.end():])
        out.append((s["t"], int(m.group(1)), int(tm.group(1)) if tm else None,
                    int(pm.group(1)) if pm else None))
    return out


def mode(values):
    values = [v for v in values if v is not None]
    return Counter(values).most_common(1)[0][0] if values else None


def clean_players(reads):
    out = []
    for i, (t, p) in enumerate(reads):
        win = [q for _, q in reads[max(0, i - 2):i + 3]]
        med = statistics.median(win)
        if abs(p - med) <= 12 or len(win) < 3:
            out.append((t, p))
    return out


def find_games(samples, sc, marker_times):
    reads = clean_players([(s["t"], s["players"]) for s in samples
                           if isinstance(s.get("players"), int) and 1 <= s["players"] <= 100])
    clusters = []
    for i, (t, p) in enumerate(reads):
        new = not clusters
        if clusters:
            pt, pp = clusters[-1][-1]
            if any(pt < x < t for x in marker_times) or t - pt > sc["split_gap_s"]:
                new = True
            elif p - pp >= sc["new_game_jump"]:
                nxt = [q for _, q in reads[i:i + 3]]
                if len(nxt) >= 2 and all(q - pp >= sc["new_game_jump"] for q in nxt):
                    new = True
        if new:
            clusters.append([(t, p)])
        else:
            clusters[-1].append((t, p))
    return [c for c in clusters
            if len(c) >= sc["min_game_reads"] and c[-1][0] - c[0][0] >= sc["min_game_s"]]


def game_events(c, in_game, cfg):
    sc = cfg["scan"]
    kreads = [(s["t"], s["kills"]) for s in in_game if isinstance(s.get("kills"), int)]
    kv, kills = None, []
    for i, (t, k) in enumerate(kreads):
        nxt = [q for _, q in kreads[i:i + 3]]
        if nxt.count(k) < sc["kill_confirm"]:
            continue
        if kv is None:
            kv = k
        elif 0 < k - kv <= sc["max_kill_jump"]:
            kills += [t] * (k - kv)
            kv = k
    treads = [(s["t"], s["top"]) for s in in_game if isinstance(s.get("top"), int)]
    tops, cur = [], None
    for i, (t, v) in enumerate(treads):
        if [q for _, q in treads[i:i + 3]].count(v) < 2:
            continue
        if cur is not None and v < cur:
            tops.append({"t": t, "reached": f"top {cur}"})
        cur = v
    if not tops:   # paliers approximés par les joueurs restants (fraction du lobby)
        maxp = max(p for _, p in c)
        for fr in cfg["edit"]["top_players_fractions"]:
            th = max(2, round(maxp * fr))
            hit = next((t for t, p in c if p <= th), None)
            if hit is not None and c[0][1] > th:
                tops.append({"t": hit, "reached": f"<= {th} joueurs"})
        tops.sort(key=lambda x: x["t"])
    spec_start, misses = None, 0
    for s in reversed(in_game):
        if s.get("spec"):
            spec_start, misses = s["t"], 0
        elif s.get("players") is not None:
            misses += 1
            if misses > 2:
                break
    if spec_start is not None and c[-1][0] - spec_start < 5:
        spec_start = None
    return kills, tops, spec_start


def rank_state(samples):
    """Rang affiché dans un salon : lecture majoritaire sur la 2e moitié du salon (après MAJ)."""
    rs = [tuple(s["rank"]) for s in samples if s.get("rank")]
    if not rs:
        return None
    tail = rs[len(rs) // 2:] or rs
    level = mode([r[0] for r in tail])
    pct = mode([r[1] for r in tail if r[0] == level])
    return {"level": level, "name": rank_name(level), "pct": pct}


def score(st):
    if not st or st.get("pct") is None or st["level"] >= 17:
        return None
    return st["level"] * 100 + st["pct"]


def analyze(samples, cfg, duration):
    sc = cfg["scan"]
    if cfg.get("mode_kind") == "box":
        return analyze_box(samples, cfg), None
    cup = cfg["mode"] == "cup"
    lobbies = lobby_markers(samples) if cup else []
    markers = [l[0] for l in lobbies] if cup else [s["t"] for s in samples if s.get("rank")]
    clusters = find_games(samples, sc, markers)

    games, prev_end, last_partie, last_pts = [], 0.0, 0, 0
    bounds = [c[0][0] for c in clusters] + [float("inf")]
    for gi, c in enumerate(clusters):
        start, end = c[0][0], c[-1][0]
        in_game = [s for s in samples if start <= s["t"] <= end]
        kills, tops, spec = game_events(c, in_game, cfg)
        g = {"start": start, "end": end, "kills": kills, "tops": tops, "final_spectate": spec}
        if cup:
            before = [l for l in lobbies if prev_end <= l[0] < start and l[1] > last_partie]
            partie = mode([l[1] for l in before])
            pts = mode([l[3] for l in before if l[1] == partie and l[3] is not None and l[3] >= last_pts])
            last_partie = partie or last_partie
            last_pts = pts if pts is not None else last_pts
            g.update(lobby_partie=partie, lobby_points=pts,
                     cup_total=mode([l[2] for l in lobbies if l[2] and 2 <= l[2] <= 30]))
        else:
            g["rank_before"] = rank_state([s for s in samples if prev_end <= s["t"] < start])
            g["rank_after"] = rank_state([s for s in samples if end < s["t"] < bounds[gi + 1]])
        games.append(g)
        prev_end = end

    final_pts = None
    if cup:
        after = [l for l in lobbies if l[0] > (clusters[-1][-1][0] if clusters else 0)]
        final_pts = mode([l[3] for l in after if l[3] is not None and l[3] >= last_pts])
    return games, final_pts


def write_timeline(cfg, games, final_pts, duration):
    cup = cfg["mode"] == "cup"
    out = {"video": str(cfg["video"]), "mode": cfg["mode"], "duration": duration,
           "final_points": final_pts, "games": []}
    last_num = 0
    for g in games:
        lp = g.get("lobby_partie")
        num = lp if lp and lp > last_num else last_num + 1
        last_num = num
        e = {"game": num, "start": round(g["start"], 2), "end": round(g["end"], 2),
             "start_tc": fmt_tc(g["start"]), "end_tc": fmt_tc(g["end"]),
             "kills": [{"t": round(t, 2), "tc": fmt_tc(t)} for t in g["kills"]],
             "tops": [{"t": round(x["t"], 2), "tc": fmt_tc(x["t"]), "reached": x["reached"]} for x in g["tops"]],
             "final_spectate": g["final_spectate"]}
        if "rounds" in g:
            e.update(rounds=[dict(r, tc=fmt_tc(r["t"])) for r in g["rounds"]], score=g["score"],
                     no_score=g.get("no_score", False))
        if cup:
            e.update(cup_games=g["cup_total"], points_before=g["lobby_points"])
        else:
            rb, ra = g.get("rank_before"), g.get("rank_after")
            e.update(rank_before=rb, rank_after=ra,
                     gain=(score(ra) - score(rb)) if score(ra) is not None and score(rb) is not None else None)
        out["games"].append(e)
    gs = out["games"]
    if cup:
        for i, g in enumerate(gs):
            nxt = gs[i + 1]["points_before"] if i + 1 < len(gs) else final_pts
            pb = g["points_before"]
            g["points_gained"] = (nxt - pb) if (nxt is not None and pb is not None and nxt >= pb) else None
    path = work_dir(cfg) / "timeline.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] {path.name} : {len(gs)} game(s)")
    for g in gs:
        info = (f"pts avant={g['points_before']} gagnés={g['points_gained']}" if cup else
                f"score {g.get('score')} " * ("score" in g) +
                f"rang {((g['rank_before'] or {}).get('name'))} {((g['rank_before'] or {}).get('pct'))}% "
                f"-> gain {g['gain']}")
        print(f"  GAME {g['game']:2d}  {g['start_tc'][:8]} -> {g['end_tc'][:8]}  kills={len(g['kills'])}  {info}")
    return path


def scan_complete(raw):
    """Un scan interrompu (app fermée, plantage) ne doit jamais être réutilisé."""
    try:
        lines = raw.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return False
    if len(lines) < 3:
        return False
    if '"_end"' in lines[-1]:
        return True
    # anciens scans (sans marqueur de fin) : acceptés s'ils couvrent quasiment toute la vidéo
    try:
        last_t = json.loads(lines[-1]).get("t", 0)
        return last_t >= 0.9 * ffprobe_info(video_path_of(raw))["duration"]
    except Exception:
        return len(lines) > 50


def video_path_of(raw):
    return _CURRENT_VIDEO.get("path")


_CURRENT_VIDEO = {}


def run(cfg, rescan=False):
    wd = work_dir(cfg)
    raw = wd / RAW_NAME
    _CURRENT_VIDEO["path"] = cfg["video"]
    if not rescan and raw.exists() and not scan_complete(raw):
        print("[SCAN] scan précédent incomplet (interrompu) -> on recommence")
        rescan = True
    if rescan or not raw.exists():
        raw = scan(cfg)
    else:
        print(f"[SCAN] déjà fait ({raw.name}) -> réanalyse")
    samples = [json.loads(l) for l in raw.read_text(encoding="utf-8").splitlines() if l.strip()]
    samples = [s for s in samples if "_end" not in s]
    if samples and "_meta" in samples[0]:
        cfg["scan"]["_step"] = samples.pop(0)["_meta"]["step"]
    duration = samples[-1]["t"] if samples else 0
    games, final_pts = analyze(samples, cfg, duration)
    if not games:
        hud = sum(1 for s in samples if s.get("players") is not None)
        print(f"[ATTENTION] 0 game détectée ({hud} lectures du HUD sur {len(samples)} images).")
    return write_timeline(cfg, games, final_pts, duration)

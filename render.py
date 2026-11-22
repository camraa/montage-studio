"""Rendu FFmpeg (h264_nvenc) : edit_plan.json -> montage

  python 4_render.py           rendu complet sur GPU
  python 4_render.py --cpu     libx264 (si NVENC indisponible / pour tester)
  python 4_render.py --dry     affiche les commandes sans rien encoder
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageDraw, ImageFont

from common import ffprobe_info, fmt_tc, need, resolve, video_path, work_dir

DRY = False


def run(cmd, duration=None, label="", progress=None):
    """Lance ffmpeg ; si duration est donnée, affiche une barre de progression
    (ou appelle progress(secondes_faites) quand plusieurs encodages tournent en parallèle)."""
    if DRY:
        print(" ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd))
        return
    cmd = [str(c) for c in cmd]
    if duration:
        cmd = cmd[:1] + ["-progress", "pipe:1", "-nostats"] + cmd[1:]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="replace")
    err = []
    import threading
    threading.Thread(target=lambda: err.extend(p.stderr.readlines()), daemon=True).start()
    t0 = time.time()
    for line in p.stdout:
        if duration and line.startswith("out_time_us="):
            try:
                done = max(0.0, int(line.split("=")[1]) / 1e6)
            except ValueError:
                continue
            if progress:
                progress(done)
                continue
            pct = min(100.0, done / duration * 100)
            el = time.time() - t0
            eta = max(0.0, el / max(done, 0.01) * (duration - done))
            bar = "#" * int(pct / 4)
            print(f"\r    {label} [{bar:<25}] {pct:5.1f}%  x{done / max(el, 0.01):4.1f}  "
                  f"reste {int(eta // 60)}:{int(eta % 60):02d}   ", end="", flush=True)
    p.wait()
    if duration and not progress:
        print()
    if p.returncode:
        print("".join(err)[-3000:])
        sys.exit(f"[ERREUR] ffmpeg a échoué (code {p.returncode})")


def video_args(rc, kind):
    common = ["-g", str(rc["fps"] * 2), "-video_track_timescale", "60000"]
    br, mx = rc["bitrate"], rc["maxrate"]
    if kind == "nvenc":
        return ["-c:v", "h264_nvenc", "-preset", rc["preset"], "-tune", "hq", "-rc", "vbr",
                "-cq", str(rc["cq"]), "-b:v", br, "-maxrate", mx, "-bufsize", mx,
                "-profile:v", "high", "-bf", "2", *common]
    if kind == "amf":
        return ["-c:v", "h264_amf", "-quality", "quality", "-rc", "vbr_peak", "-b:v", br, "-maxrate", mx,
                "-profile:v", "high", *common]
    if kind == "qsv":
        return ["-c:v", "h264_qsv", "-preset", "slow", "-b:v", br, "-maxrate", mx, "-profile:v", "high", *common]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-maxrate", mx, "-bufsize", mx,
            "-pix_fmt", "yuv420p", "-profile:v", "high", *common]


def pix_fmt(kind):
    return "nv12" if kind == "qsv" else "yuv420p"


AUDIO = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


ACCENT = (255, 205, 40)          # or "légendaire"
GREEN, RED = (90, 235, 110), (255, 80, 80)
WHITE, GREY = (255, 255, 255), (190, 210, 255)
from common import ASSET_DIR, DATA_DIR
FONT_DIR = ASSET_DIR / "polices"
_FONTS = {"title": "LuckiestGuy-Regular.ttf", "label": "Anton-Regular.ttf"}


def _font(rc, size, kind="title"):
    for f in (FONT_DIR / _FONTS[kind], rc.get("font"), "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(str(f), size)
        except (OSError, TypeError):
            continue
    return ImageFont.load_default()


def _background(W, H):
    """Fond bleu façon salon Fortnite : dégradé radial + rayons lumineux."""
    import numpy as np
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2, H * 0.42
    r = np.sqrt(((x - cx) / W) ** 2 + ((y - cy) / H) ** 2)
    inner, outer = np.array([45, 120, 235]), np.array([8, 22, 70])
    k = np.clip(r / 0.75, 0, 1)[..., None]
    img = inner * (1 - k) + outer * k
    ang = np.arctan2(y - cy, x - cx)
    rays = (np.sin(ang * 14) > 0.55).astype(np.float32) * np.clip(1 - r * 1.4, 0, 1) * 18
    img = np.clip(img + rays[..., None], 0, 255)
    return Image.fromarray(img.astype("uint8"), "RGB")


def _center(d, text, font, y, W, fill, stroke=None, shadow=True):
    """Texte centré ; style Fortnite : contour sombre + ombre portée."""
    sw = stroke if stroke is not None else max(2, font.size // 16)
    box = d.textbbox((0, 0), text, font=font, stroke_width=sw)
    x = (W - (box[2] - box[0])) // 2 - box[0]
    yy = y - box[1]
    if shadow:
        off = max(3, font.size // 18)
        d.text((x + off, yy + off), text, font=font, fill=(0, 0, 0, 150), stroke_width=sw,
               stroke_fill=(0, 0, 0, 150))
    d.text((x, yy), text, font=font, fill=fill, stroke_width=sw, stroke_fill=(10, 15, 40))
    return y + (box[3] - box[1])


def _prev_line(p):
    if not p:
        return None
    parts = [f"PARTIE {p['partie']}"]
    if p.get("gained") is not None:
        parts.append(f"+{p['gained']} PTS")
    parts.append(f"{p['kills']} KILL{'S' if p['kills'] > 1 else ''}")
    return "   •   ".join(parts)


def _bar(d, W, y, u, pct, color=ACCENT, width=900):
    bw, hb = int(width * u), int(22 * u)
    x0 = (W - bw) // 2
    rad = hb // 2
    d.rounded_rectangle([x0 - 4, y - 4, x0 + bw + 4, y + hb + 4], rad + 4, fill=(10, 15, 40))
    d.rounded_rectangle([x0, y, x0 + bw, y + hb], rad, fill=(40, 60, 120))
    if pct:
        d.rounded_rectangle([x0, y, x0 + max(hb, int(bw * min(100, pct) / 100)), y + hb], rad, fill=color)
    return y + hb


def _card_cup(rc, card, final, d, u, W, H):
    label, mid, big = _font(rc, int(50 * u), "label"), _font(rc, int(72 * u)), _font(rc, int(150 * u))
    n = card.get("cup_games") or 10
    if final:
        y = _center(d, "FIN DE LA CUP", label, int(250 * u), W, GREY)
        y = _center(d, f"{card['points']} PTS" if card.get("points") is not None else "GG", big,
                    y + int(50 * u), W, ACCENT)
        y = _center(d, f"{card['parties']} PARTIE{'S' if card['parties'] > 1 else ''} JOUÉE"
                       f"{'S' if card['parties'] > 1 else ''}", mid, y + int(60 * u), W, WHITE)
        done, current = (card.get("last") or {}).get("partie", card["parties"]), None
        line = _prev_line(card.get("last"))
    else:
        y = _center(d, "RÉCAP DE LA CUP", label, int(200 * u), W, GREY)
        y = _center(d, f"PARTIE {card['partie']} / {n}", big, y + int(40 * u), W, WHITE)
        if card.get("points") is not None:
            y = _center(d, f"{card['points']} PTS", mid, y + int(50 * u), W, ACCENT)
        done, current = card["partie"] - 1, card["partie"]
        line = _prev_line(card.get("prev"))
    hist = [h for h in (card.get("history") or []) if h.get("gained") is not None or h.get("total") is not None]
    if final and len(hist) >= 2:
        _cup_chart(rc, d, hist, y + int(60 * u), u, W)
        return
    gap, bw = int(12 * u), int(1100 * u)
    cw = (bw - gap * (n - 1)) / n
    x0, yb, hb = (W - bw) / 2, y + int(70 * u), int(22 * u)
    for i in range(n):
        x = x0 + i * (cw + gap)
        col = WHITE if i < done else ACCENT if current == i + 1 else (40, 60, 120)
        d.rounded_rectangle([x - 3, yb - 3, x + cw + 3, yb + hb + 3], 6, fill=(10, 15, 40))
        d.rounded_rectangle([x, yb, x + cw, yb + hb], 5, fill=col)
    if line:
        _center(d, line, label, yb + hb + int(55 * u), W, GREY, stroke=2)


def _cup_chart(rc, d, hist, top, u, W):
    """Carton de fin de Cup : points gagnés par partie (barres) + total cumulé (courbe)."""
    small = _font(rc, int(30 * u), "label")
    tiny = _font(rc, int(26 * u), "label")
    bw, bh = int(1200 * u), int(300 * u)
    x0, y0 = (W - bw) / 2, top + int(30 * u)
    n = len(hist)
    gained = [max(0, h.get("gained") or 0) for h in hist]
    totals, acc = [], 0
    for h, g in zip(hist, gained):
        acc = h["total"] if h.get("total") is not None else acc + g
        totals.append(acc)
    gmax, tmax = max(gained) or 1, max(totals) or 1
    d.rounded_rectangle([x0 - 30 * u, y0 - 40 * u, x0 + bw + 30 * u, y0 + bh + 60 * u], int(24 * u), fill=(8, 14, 44, 200))
    slot = bw / n
    bar_w = slot * 0.5
    pts = []
    for i, (h, g, t) in enumerate(zip(hist, gained, totals)):
        cx = x0 + slot * (i + 0.5)
        hgt = bh * 0.40 * g / gmax
        d.rounded_rectangle([cx - bar_w / 2, y0 + bh - hgt, cx + bar_w / 2, y0 + bh], int(8 * u), fill=ACCENT)
        if g:
            d.text((cx, y0 + bh - hgt - 8 * u), f"+{g}", font=tiny, fill=ACCENT, anchor="md")
        d.text((cx, y0 + bh + 28 * u), f"P{h['partie']}", font=tiny, fill=WHITE, anchor="mm")
        pts.append((cx, y0 + bh * 0.46 - bh * 0.42 * t / tmax))
    d.line(pts, fill=WHITE, width=max(3, int(6 * u)), joint="curve")
    for i, (px, py) in enumerate(pts):
        r = int(9 * u)
        d.ellipse([px - r, py - r, px + r, py + r], fill=WHITE, outline=(8, 14, 44), width=max(2, int(3 * u)))
    lx, ly = pts[-1]
    d.text((lx, ly - 22 * u), f"{totals[-1]} PTS", font=small, fill=WHITE, anchor="md", stroke_width=3, stroke_fill=(8, 14, 44))


def _rank_txt(r):
    if not r or not r.get("name"):
        return None
    return r["name"] + (f"  •  {r['pct']} %" if r.get("pct") is not None else "")


def _gain_txt(g):
    return (f"+{g} %" if g >= 0 else f"-{abs(g)} %"), (GREEN if g >= 0 else RED)


def _card_ranked(rc, card, final, d, u, W, H):
    label, mid, big, huge = (_font(rc, int(50 * u), "label"), _font(rc, int(72 * u)),
                             _font(rc, int(150 * u)), _font(rc, int(230 * u)))
    tag = card.get("label", "RANKED").upper()
    if final:
        y = _center(d, f"FIN DE SESSION  •  {tag}", label, int(200 * u), W, GREY)
        g = card.get("session_gain")
        txt, col = _gain_txt(g) if g is not None else ("GG", WHITE)
        y = _center(d, txt, huge, y + int(40 * u), W, col)
        rs, re_ = card.get("rank_start"), card.get("rank_end")
        if rs and re_ and rs.get("name") and re_.get("name"):
            y = _center(d, f"{_rank_txt(rs)}   >   {_rank_txt(re_)}", mid, y + int(50 * u), W, ACCENT)
        elif re_ and re_.get("name"):
            y = _center(d, _rank_txt(re_), mid, y + int(50 * u), W, ACCENT)
        if re_ and re_.get("pct") is not None:
            y = _bar(d, W, y + int(40 * u), u, re_["pct"])
        n = card.get("games", 0)
        line = f"{n} GAME{'S' if n > 1 else ''}"
        last = card.get("last") or {}
        if last.get("kills") is not None:
            line += f"   •   DERNIÈRE GAME : {last['kills']} KILL{'S' if last['kills'] > 1 else ''}"
        _center(d, line, label, y + int(50 * u), W, GREY, stroke=2)
        return
    y = _center(d, f"{tag}  •  GAME {card['game']}", label, int(200 * u), W, GREY)
    prev = card.get("prev")
    if prev and prev.get("gain") is not None:
        txt, col = _gain_txt(prev["gain"])
        y = _center(d, txt, huge, y + int(40 * u), W, col)
        y = _center(d, f"GAME {prev['game']}  •  {prev['kills']} KILL{'S' if prev['kills'] > 1 else ''}",
                    label, y + int(35 * u), W, WHITE, stroke=2)
    else:
        y = _center(d, f"GAME {card['game']}", big, y + int(40 * u), W, WHITE)
        if prev:
            y = _center(d, f"GAME {prev['game']} : {prev['kills']} KILL{'S' if prev['kills'] > 1 else ''}",
                        label, y + int(35 * u), W, GREY, stroke=2)
    r = card.get("rank")
    if r and r.get("name"):
        y = _center(d, _rank_txt(r), mid, y + int(60 * u), W, ACCENT)
        if r.get("pct") is not None:
            _bar(d, W, y + int(35 * u), u, r["pct"])


def _card_box(rc, card, final, d, u, W, H):
    label, mid, big, huge = (_font(rc, int(50 * u), "label"), _font(rc, int(72 * u)),
                             _font(rc, int(150 * u)), _font(rc, int(200 * u)))
    tag = card.get("label", "BOX FIGHT").upper()
    if final:
        y = _center(d, f"BILAN DE LA SESSION  •  {tag}", label, int(200 * u), W, GREY)
        w_, l_ = card.get("wins", 0), card.get("losses", 0)
        y = _center(d, f"{w_}V - {l_}D", huge, y + int(40 * u), W, GREEN if w_ >= l_ else RED)
        r = card.get("rounds") or [0, 0]
        y = _center(d, f"MANCHES  {r[0]} - {r[1]}", mid, y + int(50 * u), W, WHITE)
        g = card.get("session_gain")
        if g is not None:
            txt, col = _gain_txt(g)
            y = _center(d, f"ELO {txt}", mid, y + int(40 * u), W, col)
        rs, re_ = card.get("rank_start"), card.get("rank_end")
        if re_ and re_.get("name"):
            line = f"{_rank_txt(rs)}   >   {_rank_txt(re_)}" if rs and rs.get("name") else _rank_txt(re_)
            y = _center(d, line, mid, y + int(40 * u), W, ACCENT)
            if re_.get("pct") is not None:
                _bar(d, W, y + int(35 * u), u, re_["pct"])
        return
    y = _center(d, f"{tag}  •  MATCH {card['game']}", label, int(200 * u), W, GREY)
    prev = card.get("prev")
    sc = prev.get("score") if prev else None
    if sc:
        win = sc[0] > sc[1]
        y = _center(d, f"{'VICTOIRE' if win else 'DÉFAITE' if sc[0] < sc[1] else 'ÉGALITÉ'}  {sc[0]}-{sc[1]}", big,
                    y + int(40 * u), W, GREEN if win else RED if sc[0] < sc[1] else WHITE)
        if prev.get("gain") is not None:
            txt, col = _gain_txt(prev["gain"])
            y = _center(d, f"ELO {txt}", mid, y + int(30 * u), W, col)
    else:
        y = _center(d, f"MATCH {card['game']}", big, y + int(40 * u), W, WHITE)
    r = card.get("rank")
    if r and r.get("name"):
        y = _center(d, _rank_txt(r), mid, y + int(55 * u), W, ACCENT)
        if r.get("pct") is not None:
            _bar(d, W, y + int(35 * u), u, r["pct"])


def make_card(rc, card, path, final=False):
    W, H = rc["width"], rc["height"]
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    u = H / 1080
    if card.get("type") == "ranked":
        _card_ranked(rc, card, final, d, u, W, H)
    elif card.get("type") == "box":
        _card_box(rc, card, final, d, u, W, H)
    else:
        _card_cup(rc, card, final, d, u, W, H)
    img = _background(W, H).convert("RGBA")
    bbox = layer.getbbox()
    if bbox:   # centrage vertical du bloc de texte
        block = layer.crop((0, bbox[1], W, bbox[3]))
        img.alpha_composite(block, (0, (H - block.height) // 2))
    img.convert("RGB").save(path)


def render_card(rc, card, out, kind, final=False):
    png = out.with_suffix(".png")
    make_card(rc, card, png, final)
    d = rc["card_duration_s"]
    run([need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
         "-loop", "1", "-framerate", rc["fps"], "-i", png,
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-t", f"{d:.3f}", "-map", "0:v", "-map", "1:a",
         "-vf", f"fade=t=in:st=0:d=0.25,fade=t=out:st={d - 0.25:.3f}:d=0.25,format={pix_fmt(kind)}",
         *video_args(rc, kind), *AUDIO, "-shortest", out])


def render_segment(rc, video, info, seg, out, kind, progress=None):
    s, d = seg["start"], seg["end"] - seg["start"]
    cmd = [need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y"]
    same_size = (info["width"], info["height"]) == (rc["width"], rc["height"])
    if kind != "nvenc":
        vf = f"scale={rc['width']}:{rc['height']}:flags=lanczos,fps={rc['fps']},format={pix_fmt(kind)}"
    else:
        cmd += ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
        vf = ("" if same_size else f"scale_cuda={rc['width']}:{rc['height']}:interp_algo=lanczos,") + f"fps={rc['fps']}"
    cmd += ["-ss", f"{s:.3f}", "-i", video]
    if not info["has_audio"]:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd += ["-t", f"{d:.3f}", "-map", "0:v:0",
            "-map", f"0:a:{rc['audio_stream']}" if info["has_audio"] else "1:a",
            "-vf", vf, *video_args(rc, kind), *AUDIO, out]
    run(cmd, duration=d, label=out.stem, progress=progress)


MUSIC_EXT = (".mp3", ".wav", ".ogg", ".m4a", ".flac")


def _decode(path, sr, ch, start=0.0, dur=None, concat=False, loop=False):
    import numpy as np
    cmd = [need("ffmpeg"), "-hide_banner", "-loglevel", "error"]
    if loop:
        cmd += ["-stream_loop", "-1"]
    if concat:
        cmd += ["-f", "concat", "-safe", "0"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path)]
    if dur:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-vn", "-ac", str(ch), "-ar", str(sr), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    return x.reshape(-1, ch) if ch > 1 else x


def duck_gain(key, sr_key, n_out, rc):
    """Courbe de volume pour la musique : baisse quand le son d'origine (voix/jeu) est présent."""
    import numpy as np
    hop = int(sr_key * 0.02)
    nfr = max(1, len(key) // hop)
    fr = key[: nfr * hop].reshape(nfr, hop) if len(key) >= hop else np.zeros((1, hop))
    lvl = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-6)
    red = np.clip((lvl - rc["duck_threshold_db"]) * rc["duck_slope"], 0, rc["duck_max_db"])
    att, rel = 1 - np.exp(-0.02 / 0.03), 1 - np.exp(-0.02 / (rc["duck_release_ms"] / 1000))
    sm, cur = np.empty_like(red), 0.0
    for i, r in enumerate(red):
        cur += (r - cur) * (att if r > cur else rel)
        sm[i] = cur
    g = 10 ** (-sm / 20)
    return np.interp(np.arange(n_out) / n_out * nfr, np.arange(nfr), g)


def music_bed(cfg, clips, total, cmd, plan=None):
    """Musique sur les cartons (intro / entre les games / outro) qui déborde un peu sur le début
    du gameplay puis s'efface. Elle baisse automatiquement dès qu'il y a du son d'origine
    (ta voix, les tirs...) et remonte quand c'est calme."""
    import random
    import numpy as np
    rc = cfg["render"]
    intro, outro = resolve(cfg, rc["intro"]), resolve(cfg, rc["outro"])
    pool = sorted(p for d in (ASSET_DIR / "musiques", DATA_DIR / "musiques") if d.exists()
                  for p in d.glob("*") if p.suffix.lower() in MUSIC_EXT)
    if not pool:
        pool = [p for p in (intro, outro) if p.exists()]
    if not pool:
        print("[INFO] aucune musique trouvée -> son d'origine uniquement")
        return [], 1
    rng = random.Random(Path(cfg["video"]).stem)
    order = pool[:]
    rng.shuffle(order)
    lst = clips[0].parent / "concat.txt"
    starts, t = [], 0.0
    for c in clips:
        d = duration_of(c)
        starts.append((c, t, d))
        t += d
    cards = [(c, st, d) for c, st, d in starts if "_card" in c.name]
    choices = [g["card"].get("music") for g in (plan or {}).get("games", [])]
    if (plan or {}).get("final"):
        choices.append(plan["final"].get("music"))
    by_name = {p.name: p for p in pool + [intro, outro] if p.exists()}

    SR, KSR = 48000, 8000
    vol, fade = rc["music_volume"], rc["music_fade_s"]
    pieces, idx, k = [], 1, 0
    for i, (c, st, d) in enumerate(cards):
        if c.name.startswith("99_final"):
            src = outro if outro.exists() else order[k % len(order)]
            L = min(rc["outro_s"], total)
            st = max(0.0, total - L)
        elif i == 0:
            src = intro if intro.exists() else order[k % len(order)]
            L = rc["intro_s"]
        else:
            src = order[k % len(order)]
            k += 1
            L = d + rc["music_tail_s"]
        choice = choices[i] if i < len(choices) else None
        if choice == "aucune":
            continue
        if choice and choice != "auto" and choice in by_name:
            src = by_name[choice]
        L = min(L, total - st)
        if L <= 1:
            continue
        m = _decode(src, SR, 2, dur=L, loop=True)
        if len(m) == 0:
            continue
        n = len(m)
        tt = np.arange(n) / SR
        envl = np.minimum(1, tt / 0.4) * np.clip((L - tt) / min(fade, L), 0, 1)
        key = _decode(lst, KSR, 1, start=st, dur=L, concat=True)
        g = duck_gain(key, KSR, n, rc) if len(key) else np.ones(n)
        m = m * (vol * envl * g)[:, None]
        wav = clips[0].parent / f"music_{idx:02d}.wav"
        import wave
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((np.clip(m, -1, 1) * 32767).astype("<i2").tobytes())
        ms = int(st * 1000)
        cmd += ["-i", wav]
        pieces.append(f"[{idx}:a]adelay={ms}|{ms}[m{idx}]")
        idx += 1
    # ---- musique de fin de zone (Cup) : ambiance stressante sur les dernières minutes de chaque partie
    tension = sorted(p for d in (ASSET_DIR / "musiques" / "fin_de_zone", DATA_DIR / "musiques" / "fin_de_zone")
                     if d.exists() for p in d.glob("*") if p.suffix.lower() in MUSIC_EXT)
    if (plan or {}).get("mode") == "cup" and rc.get("endgame_music", True) and tension:
        rng.shuffle(tension)
        games_end = {}
        for c, st, d in starts:
            if "_partie" in c.name:
                gi = c.name[:2]
                g0, _, kept = games_end.get(gi, (st, 0, 0.0))
                games_end[gi] = (g0, st + d, kept + d)
        L0 = float(rc.get("endgame_music_s", 120))
        rc_e = dict(rc, duck_max_db=rc.get("endgame_duck_db", 9))
        for k_, (gi, (g0, end, kept)) in enumerate(sorted(games_end.items())):
            if kept < L0 + 30:                     # partie trop courte (élimination rapide) : pas de stress
                continue
            st = end - L0
            m = _decode(tension[k_ % len(tension)], SR, 2, dur=L0, loop=True)
            if len(m) == 0:
                continue
            n = len(m)
            tt = np.arange(n) / SR
            envl = np.minimum(1, tt / 4.0) * np.clip((L0 - tt) / 1.5, 0, 1)
            key = _decode(lst, KSR, 1, start=st, dur=L0, concat=True)
            g = duck_gain(key, KSR, n, rc_e) if len(key) else np.ones(n)
            m = m * (rc.get("endgame_volume", 0.35) * envl * g)[:, None]
            wav = clips[0].parent / f"music_{idx:02d}.wav"
            import wave
            with wave.open(str(wav), "wb") as w:
                w.setnchannels(2)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes((np.clip(m, -1, 1) * 32767).astype("<i2").tobytes())
            ms = int(st * 1000)
            cmd += ["-i", wav]
            pieces.append(f"[{idx}:a]adelay={ms}|{ms}[m{idx}]")
            idx += 1
            print(f"[MUSIQUE] fin de zone : partie {int(gi)} ({tension[k_ % len(tension)].stem})")
    if not pieces:
        return [], 1
    labels = "[0:a]" + "".join(f"[m{j}]" for j in range(1, idx))
    pieces.append(f"{labels}amix=inputs={idx}:duration=first:dropout_transition=0:normalize=0,"
                  "alimiter=limit=0.95[a]")
    print(f"[MUSIQUE] {idx - 1} passage(s) musicaux - baisse auto quand tu parles / quand le jeu fait du bruit")
    return pieces, idx


def write_chapters(cfg, plan, clips, out):
    """Description YouTube prête à coller : titre proposé + chapitres (une ligne par game)."""
    t, lines = 0.0, []
    cup = plan.get("mode") == "cup"
    games = iter(plan["games"])
    for c in clips:
        if "_card" in c.name and not c.name.startswith("99_"):
            g = next(games)
            m, s_ = divmod(int(t), 60)
            h, m = divmod(m, 60)
            stamp = f"{h}:{m:02d}:{s_:02d}" if h else f"{m:02d}:{s_:02d}"
            if len(lines) == 0:
                stamp = "00:00"
            word = "Partie" if cup else "Match" if g["card"].get("type") == "box" else "Game"
            sc = (g["card"].get("prev") or {}).get("score")
            lines.append(f"{stamp} {word} {g['game']}")
        t += duration_of(c)
    fin = plan.get("final") or {}
    if fin.get("type") == "box":
        title = (f"{fin.get('wins', 0)} VICTOIRES EN {plan.get('label', 'BOX FIGHT').upper()}"
                 + (f" (+{fin['session_gain']}%)" if (fin.get("session_gain") or 0) > 0 else ""))
    elif cup:
        title = f"MA CUP FORTNITE : {fin.get('points') or '?'} POINTS en {fin.get('parties', len(plan['games']))} parties"
    else:
        g = fin.get("session_gain")
        rk = (fin.get("rank_end") or {}).get("name")
        title = (f"+{g}% EN UNE SESSION {plan.get('label', 'RANKED').upper()}" if g and g > 0
                 else f"SESSION {plan.get('label', 'RANKED').upper()}") + (f" ({rk})" if rk else "")
    txt = (f"TITRE PROPOSÉ :\n{title}\n\nDESCRIPTION :\n"
           f"Session {plan.get('label', '')} Fortnite, toutes les games en long format.\n\n"
           "CHAPITRES :\n" + "\n".join(lines) + "\n")
    p = Path(str(out)).with_suffix(".txt")
    p.write_text(txt, encoding="utf-8")
    print(f"[YOUTUBE] titre + chapitres -> {p.name}")


def duration_of(path):
    return 0.0 if DRY else ffprobe_info(path)["duration"]


def render(cfg, cpu=False, reencode_final=False):
    from common import detect_encoder
    kind = "x264" if cpu else detect_encoder()
    rc = cfg["render"]
    plan = json.loads((work_dir(cfg) / "edit_plan.json").read_text(encoding="utf-8"))
    plan["games"] = [g for g in plan["games"] if not g.get("disabled") and g.get("segments")]
    if not plan["games"]:
        raise SystemExit("[ERREUR] Aucune game détectée dans ce rec -> rien à monter.\n"
                         "  Vérifie la catégorie choisie, puis regarde work/<rec>/diagnostic (images du HUD lu).")
    video = video_path(cfg)
    info = ffprobe_info(video)
    print(f"[RENDU] source {info['width']}x{info['height']} @ {info['fps']:.0f} fps -> "
          f"sortie {rc['width']}x{rc['height']} @ {rc['fps']} fps, {rc['bitrate']}b/s, encodeur {kind}")
    clips_dir = work_dir(cfg) / "clips"
    clips_dir.mkdir(exist_ok=True)
    for old in list(clips_dir.glob("*.mp4")) + list(clips_dir.glob("*.wav")):
        old.unlink()

    clips, jobs = [], []
    for gi, g in enumerate(plan["games"]):
        card = clips_dir / f"{gi:02d}_card.mp4"
        render_card(rc, g["card"], card, kind)
        clips.append(card)
        for j, seg in enumerate(g["segments"]):
            out = clips_dir / f"{gi:02d}_partie{g['game']:02d}_s{j:02d}.mp4"
            jobs.append((seg, out))
            clips.append(out)
    if plan.get("final"):
        fc = clips_dir / "99_final_card.mp4"
        render_card(rc, plan["final"], fc, kind, final=True)
        clips.append(fc)

    # encodage des segments en parallèle : 1 encodage par puce NVENC (la 5070 Ti en a 2)
    workers = max(1, int(rc.get("parallel_encodes", 2))) if kind == "nvenc" else 1
    total_s = sum(seg["end"] - seg["start"] for seg, _ in jobs)
    prog, lock = {}, threading.Lock()
    t0, last = time.time(), [0.0]

    def show(force=False):
        now = time.time()
        if not force and now - last[0] < 0.5:
            return
        last[0] = now
        done_s = sum(prog.values())
        el = now - t0
        pct = min(100.0, done_s / max(total_s, 0.01) * 100)
        eta = max(0.0, el / max(done_s, 0.01) * (total_s - done_s))
        bar = "#" * int(pct / 4)
        print(f"\r    [{bar:<25}] {pct:5.1f}%  x{done_s / max(el, 0.01):4.1f}  "
              f"reste {int(eta // 3600)}:{int(eta % 3600 // 60):02d}:{int(eta % 60):02d}  "
              f"({len(jobs)} morceaux, {workers} en parallèle)   ", end="", flush=True)

    def job(seg, out):
        def cb(done):
            with lock:
                prog[out] = min(done, seg["end"] - seg["start"])
                show()
        render_segment(rc, video, info, seg, out, kind, progress=cb)
        with lock:
            prog[out] = seg["end"] - seg["start"]
            show(force=True)

    print(f"[RENDU] {len(jobs)} morceaux de gameplay ({fmt_tc(total_s)[:8]}) - {workers} encodages en parallèle")
    order = sorted(jobs, key=lambda j: j[0]["start"] - j[0]["end"])   # les plus longs d'abord
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(job, seg, out) for seg, out in order]
        for f in futures:
            f.result()          # remonte une éventuelle erreur ffmpeg
    print()

    lst = clips_dir / "concat.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    total = sum(duration_of(c) for c in clips)
    print(f"[CONCAT] {len(clips)} clips, durée {fmt_tc(total)[:8]}")

    out = resolve(cfg, rc["output"])
    cmd = [need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
           "-f", "concat", "-safe", "0", "-i", lst]
    mix, idx = music_bed(cfg, clips, total, cmd, plan)
    vcodec = video_args(rc, kind) if reencode_final else ["-c:v", "copy"]
    if mix:
        cmd += ["-filter_complex", ";".join(mix), "-map", "0:v", "-map", "[a]", *vcodec, *AUDIO]
    else:
        cmd += ["-map", "0:v", "-map", "0:a", *vcodec, "-c:a", "copy"]
    cmd += ["-movflags", "+faststart", out]
    print("[FINAL] assemblage + musique...")
    run(cmd, duration=total, label="final")
    write_chapters(cfg, plan, clips, out)
    print(f"\n[OK] Montage terminé : {out}  ({fmt_tc(total)[:8]})")
    print(f"[OUTPUT] {out}")
    for old in list(clips_dir.glob("*.mp4")) + list(clips_dir.glob("*.wav")):
        old.unlink()          # libère la place (les clips intermédiaires sont énormes)
    return out

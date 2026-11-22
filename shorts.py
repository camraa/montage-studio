"""Shorts TikTok / YouTube automatiques : les meilleurs fights du rec en vidéos verticales 9:16.

  python job.py shorts <mode> <vidéo>

- repère les enchaînements de kills (timeline du scan), garde les N meilleurs, sans chevauchement
- format vertical 1080x1920 : gameplay agrandi au centre, fond flouté, gros titre en haut
- sous-titres animés de ta voix (mot par mot, le mot prononcé en jaune), via transcribe.py
- sortie : Vidéos/Shorts/[SHORT] <rec> - 01.mp4 ...
"""
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from common import ASSET_DIR, RAW_DIR_NAME, detect_encoder, need, work_dir

W, H = 1080, 1920
FONT_DIR = ASSET_DIR / "polices"
YELLOW, WHITE, DARK = (255, 214, 40), (255, 255, 255), (12, 14, 34)


def font(size, kind="title"):
    f = FONT_DIR / ("LuckiestGuy-Regular.ttf" if kind == "title" else "Anton-Regular.ttf")
    try:
        return ImageFont.truetype(str(f), size)
    except OSError:
        return ImageFont.load_default()


# ------------------------------------------------------------------ choix des moments
def moments(timeline, n=3, min_len=18, max_len=58):
    """Enchaînements de kills (écart <= 22 s) notés : kills, rapidité, fin de partie."""
    cands = []
    for g in timeline.get("games", []):
        ks = sorted(k["t"] for k in g.get("kills", []))
        if not ks:
            continue
        groups, cur = [], [ks[0]]
        for t in ks[1:]:
            if t - cur[-1] <= 22:
                cur.append(t)
            else:
                groups.append(cur)
                cur = [t]
        groups.append(cur)
        for grp in groups:
            span = grp[-1] - grp[0]
            late = max(0.0, 1 - (g["end"] - grp[-1]) / 300)          # bonus fin de partie (zones finales)
            score = len(grp) * 3 + (4 if len(grp) >= 2 and span <= 10 else 0) + late * 3
            s, e = grp[0] - 9, grp[-1] + 5
            if e - s < min_len:
                pad = (min_len - (e - s)) / 2
                s, e = s - pad, e + pad
            if e - s > max_len:
                s = e - max_len
            s, e = max(g["start"], s), min(g["end"] + 5, e)
            cands.append({"start": s, "end": e, "kills": len(grp), "span": span, "score": score,
                          "game": g.get("game"), "late": late > 0.5})
    cands.sort(key=lambda c: -c["score"])
    out = []
    for c in cands:
        if all(c["end"] < o["start"] - 2 or c["start"] > o["end"] + 2 for o in out):
            out.append(c)
        if len(out) >= n:
            break
    return sorted(out, key=lambda c: c["start"])


def headline(m):
    k = m["kills"]
    if k >= 4:
        return f"{k} KILLS EN {max(1, round(m['span']))} SEC"
    if k == 3:
        return "TRIPLE KILL"
    if k == 2:
        return "DOUBLE KILL" if m["span"] <= 8 else "2 KILLS PROPRES"
    return "LE KILL DE LA GAME" if m["late"] else "CLEAN"


# ------------------------------------------------------------------ images (titre + sous-titres)
def _text_block(d, text, y, size, fill, max_w=W - 120, stroke=10):
    f = font(size)
    while d.textlength(text, font=f) > max_w and size > 40:
        size -= 6
        f = font(size)
    d.text((W // 2, y), text, font=f, fill=fill, anchor="mm", stroke_width=stroke, stroke_fill=DARK)


def title_png(text, sub, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds = ImageDraw.Draw(sh)
    _text_block(ds, text, 270, 112, (0, 0, 0, 180), stroke=18)
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(img)
    _text_block(d, text, 262, 112, WHITE)
    if sub:
        _text_block(d, sub, 392, 58, YELLOW, stroke=7)
    img.save(path)


def caption_png(words, active, path):
    """Une phrase de sous-titre (2-3 mots), le mot en cours en jaune, sur 1 ou 2 lignes."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font(92)
    toks = [w.upper().strip(" ,") for w in words]
    space = d.textlength(" ", font=f)
    lines, cur, cur_w = [], [], 0.0
    for i, t in enumerate(toks):
        wdt = d.textlength(t, font=f)
        if cur and cur_w + space + wdt > W - 140:
            lines.append(cur)
            cur, cur_w = [], 0.0
        cur.append((i, t, wdt))
        cur_w += (space if len(cur) > 1 else 0) + wdt
    if cur:
        lines.append(cur)
    y = 1430 - (len(lines) - 1) * 55
    for ln in lines:
        total = sum(w for _, _, w in ln) + space * (len(ln) - 1)
        x = (W - total) / 2
        for i, t, wdt in ln:
            d.text((x, y), t, font=f, fill=YELLOW if i == active else WHITE, anchor="lm",
                   stroke_width=11, stroke_fill=DARK)
            x += wdt + space
        y += 110
    img.save(path)


def captions_stream(ws, dur, folder):
    """Fichier concat ffmpeg : une image transparente par mot prononcé, vide entre les phrases."""
    import transcribe
    blank = folder / "blank.png"
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank)
    entries, t = [], 0.0
    k = 0
    for ch in transcribe.chunks(ws, max_words=3):
        txt = [w[2] for w in ch]
        for j, (s, e, _) in enumerate(ch):
            s = max(s, t)
            end = ch[j + 1][0] if j + 1 < len(ch) else e + 0.25
            end = min(max(end, s + 0.08), dur)
            if s >= dur:
                break
            if s - t > 0.01:
                entries.append((blank, s - t))
            p = folder / f"cap_{k:04d}.png"
            caption_png(txt, j, p)
            entries.append((p, end - s))
            t, k = end, k + 1
    if dur - t > 0.01:
        entries.append((blank, dur - t))
    lst = folder / "captions.txt"
    lines = []
    for p, d in entries:
        lines += [f"file '{p.as_posix()}'", f"duration {d:.3f}"]
    lines.append(f"file '{entries[-1][0].as_posix()}'" if entries else f"file '{blank.as_posix()}'")
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lst


# ------------------------------------------------------------------ rendu
def encoder_args():
    kind = detect_encoder()
    if kind == "nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "12M", "-maxrate", "18M",
                "-bufsize", "18M", "-profile:v", "high"]
    if kind == "amf":
        return ["-c:v", "h264_amf", "-quality", "quality", "-rc", "vbr_peak", "-b:v", "12M", "-maxrate", "18M"]
    if kind == "qsv":
        return ["-c:v", "h264_qsv", "-preset", "slow", "-b:v", "12M", "-maxrate", "18M"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def render_short(video, m, out, folder, layout="cadre", captions=True, sub=None):
    folder.mkdir(parents=True, exist_ok=True)
    dur = m["end"] - m["start"]
    title_png(headline(m), sub, folder / "title.png")
    cap = None
    if captions:
        try:
            import transcribe
            ws = transcribe.words(transcribe.load_audio(video, m["start"], dur))
            cap = captions_stream(ws, dur, folder) if ws else None
            print(f"[SHORT] {len(ws)} mot(s) sous-titré(s)", flush=True)
        except Exception as e:                       # pas de transcription : le Short sort quand même
            print(f"[SHORT] sous-titres impossibles ({type(e).__name__}: {e}) -> Short sans sous-titres", flush=True)
    if layout == "plein":        # gameplay en plein écran (centre de l'image), bords coupés
        base = "[0:v]scale=-2:1920,crop=1080:1920[v1]"
    else:                        # gameplay agrandi au centre + fond flouté
        base = ("[0:v]split=2[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                "boxblur=24:2,eq=brightness=-0.18:saturation=1.2[bg];[b]crop=iw*0.82:ih,scale=1080:-2[fg];"
                "[bg][fg]overlay=0:(H-h)/2-10[v1]")
    fc = base + ";[v1][1:v]overlay=0:0[v2]"
    inputs = ["-ss", f"{m['start']:.3f}", "-t", f"{dur:.3f}", "-i", str(video), "-loop", "1", "-t", f"{dur:.3f}",
              "-i", str(folder / "title.png")]
    if cap:
        inputs += ["-f", "concat", "-safe", "0", "-i", str(cap)]
        fc += ";[2:v]fps=30,format=rgba[c];[v2][c]overlay=0:0:eof_action=pass,format=yuv420p[v]"
    else:
        fc += ";[v2]format=yuv420p[v]"
    cmd = [need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", fc,
           "-map", "[v]", "-map", "0:a:0?", "-r", "60", *encoder_args(),
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", f"{dur:.3f}",
           "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 and "nvenc" in " ".join(cmd):
        cmd = [c for c in cmd]                       # repli processeur si l'encodeur matériel refuse
        i = cmd.index("-c:v")
        j = cmd.index("-c:a")
        cmd[i:j] = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
        r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-600:])
    return out


def run(cfg):
    rc = cfg["render"]
    wd = work_dir(cfg)
    tl_p = wd / "timeline.json"
    if not tl_p.exists():
        raise SystemExit("[ERREUR] analyse d'abord le rec (scan), les Shorts utilisent les kills détectés")
    tl = json.loads(tl_p.read_text(encoding="utf-8"))
    ms = moments(tl, n=int(rc.get("shorts_count", 3)))
    if not ms:
        raise SystemExit("[ERREUR] aucun kill détecté dans ce rec : pas de moment fort pour un Short")
    video = Path(cfg["video"])
    base = video.parent.parent if video.parent.name == RAW_DIR_NAME else video.parent
    out_dir = base / "Shorts"
    out_dir.mkdir(exist_ok=True)
    sub = None
    if cfg["mode"] == "cup":
        sub = "EN CUP"
    elif cfg.get("mode_label"):
        sub = str(cfg["mode_label"]).upper()
    outs = []
    for i, m in enumerate(ms, 1):
        print(f"[SHORT] {i}/{len(ms)} : {headline(m)} ({m['end'] - m['start']:.0f} s)", flush=True)
        print(f"[SHORTS] {(i - 1) / len(ms) * 100:.1f}%", flush=True)
        out = out_dir / f"[SHORT] {video.stem} - {i:02d}.mp4"
        render_short(video, m, out, wd / "shorts" / f"{i:02d}", rc.get("shorts_layout", "cadre"),
                     rc.get("shorts_captions", True), sub)
        outs.append(out)
        print(f"[OUTPUT] {out}", flush=True)
    print(f"[OK] {len(outs)} Short(s) dans {out_dir}")
    return outs

"""Miniatures YouTube automatiques (1280x720, < 2 Mo) pensées pour le clic :
image du plus gros fight boostée (couleurs/contraste/netteté), 2 à 4 mots ÉNORMES,
contraste maximal, couleurs vives, style Fortnite (Luckiest Guy).

4 variantes générées -> tu choisis (ou tu les testes avec "Tester et comparer" de YouTube Studio).
"""
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from common import ASSET_DIR, need, video_path, work_dir

W, H = 1280, 720
FONT_DIR = ASSET_DIR / "polices"
YELLOW, GREEN, RED, WHITE, BLUE = (255, 214, 0), (70, 240, 90), (255, 60, 60), (255, 255, 255), (30, 110, 255)


def font(size, kind="title"):
    f = FONT_DIR / ("LuckiestGuy-Regular.ttf" if kind == "title" else "Anton-Regular.ttf")
    try:
        return ImageFont.truetype(str(f), size)
    except OSError:
        return ImageFont.load_default()


# ------------------------------------------------------------------ choix des moments
def best_moments(timeline, plan, n=4):
    """Moments les plus 'chauds' : là où il y a le plus de kills en 25 s (dans les passages gardés)."""
    kept = [(s["start"], s["end"]) for g in plan.get("games", []) for s in g["segments"]]

    def is_kept(t):
        return any(a <= t <= b for a, b in kept) if kept else True

    kills = sorted(k["t"] for g in timeline.get("games", []) for k in g.get("kills", []))
    scored = []
    for t in kills:
        c = sum(1 for k in kills if t - 25 <= k <= t)
        if is_kept(t):
            scored.append((c, t))
    scored.sort(reverse=True)
    out = []
    for c, t in scored:
        if all(abs(t - o) > 40 for o in out):
            out.append(t)
        if len(out) >= n:
            break
    # complément : milieu des passages gardés
    for a, b in sorted(kept, key=lambda s: s[0] - s[1]):
        if len(out) >= n:
            break
        m = (a + b) / 2
        if all(abs(m - o) > 40 for o in out):
            out.append(m)
    return out[:n] or [60.0]


def grab(video, t):
    raw = subprocess.run([need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-ss", f"{max(0, t):.2f}",
                          "-i", str(video), "-frames:v", "1", "-vf", f"scale={W}:{H}",
                          "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
    from io import BytesIO
    try:
        return Image.open(BytesIO(raw)).convert("RGB")
    except Exception:
        return Image.new("RGB", (W, H), (20, 40, 90))


def good_frame(video, t):
    """Évite les écrans noirs / menus / 'DÉFAITE' : essaie quelques secondes autour."""
    import numpy as np
    best, best_score = None, -1
    for dt in (0, -2, -4, 2, -7, -10, 5):
        img = grab(video, t + dt)
        a = np.asarray(img.resize((160, 90))).astype(np.float32)
        mean, std = a.mean(), a.std()
        dark = (a.max(axis=2) < 40).mean()
        score = std * (1 - dark) * (mean > 45)
        if score > best_score:
            best, best_score = img, score
        if mean > 60 and std > 45 and dark < 0.25:
            return img
    return best


def punch(img, zoom=1.12):
    """Zoom sur l'action + couleurs saturées + contraste + netteté : ce qui ressort sur YouTube."""
    if zoom > 1:
        cw, ch = int(W / zoom), int(H / zoom)
        x0, y0 = (W - cw) // 2, int((H - ch) * 0.45)
        img = img.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.LANCZOS)
    img = ImageEnhance.Color(img).enhance(1.55)
    img = ImageEnhance.Contrast(img).enhance(1.22)
    img = ImageEnhance.Brightness(img).enhance(1.06)
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=3))
    return img


def vignette(img, strength=0.55):
    import numpy as np
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2)
    m = np.clip(1 - strength * np.clip(r - 0.45, 0, 1) ** 1.4, 0, 1)
    a = np.asarray(img).astype(np.float32) * m[..., None]
    return Image.fromarray(a.clip(0, 255).astype("uint8"))


def side_shade(img, side="left", width=0.6, alpha=200):
    import numpy as np
    g = np.zeros((H, W), np.float32)
    ramp = np.clip(1 - np.linspace(0, 1, int(W * width)), 0, 1) ** 1.3
    if side == "left":
        g[:, :len(ramp)] = ramp
    elif side == "bottom":
        rv = np.clip(np.linspace(0, 1, H) - (1 - width), 0, 1) / width
        g[:] = (rv ** 1.2)[:, None]
    shade = Image.fromarray((g * alpha).astype("uint8"))
    black = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(black, img, shade)


def big_text(d, xy, text, size, fill, anchor="la", stroke=None, glow=None, layer=None):
    f = font(size)
    sw = stroke or max(6, size // 11)
    if glow and layer is not None:
        gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(gl).text(xy, text, font=f, fill=glow + (255,), anchor=anchor, stroke_width=sw + 10,
                                stroke_fill=glow + (255,))
        layer.alpha_composite(gl.filter(ImageFilter.GaussianBlur(18)))
        d = ImageDraw.Draw(layer)
    off = max(5, size // 14)
    d.text((xy[0] + off, xy[1] + off), text, font=f, fill=(0, 0, 0, 200), anchor=anchor, stroke_width=sw,
           stroke_fill=(0, 0, 0, 200))
    d.text(xy, text, font=f, fill=fill, anchor=anchor, stroke_width=sw, stroke_fill=(0, 0, 0))
    return d.textbbox(xy, text, font=f, anchor=anchor, stroke_width=sw)


def fit_size(text, max_w, start, kind="title"):
    s = start
    while s > 40:
        f = font(s, kind)
        b = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), text, font=f, stroke_width=s // 11)
        if b[2] - b[0] <= max_w:
            return s
        s -= 6
    return s


def arrow(d, tip, color=RED, size=110, angle=-35):
    import math
    a = math.radians(angle)
    ux, uy = math.cos(a), math.sin(a)
    px, py = -uy, ux
    tx, ty = tip
    L, hw, sw = size * 1.8, size * 0.55, size * 0.22
    base = (tx - ux * size, ty - uy * size)
    tail = (tx - ux * L, ty - uy * L)
    pts = [tip, (base[0] + px * hw, base[1] + py * hw), (base[0] + px * sw, base[1] + py * sw),
           (tail[0] + px * sw, tail[1] + py * sw), (tail[0] - px * sw, tail[1] - py * sw),
           (base[0] - px * sw, base[1] - py * sw), (base[0] - px * hw, base[1] - py * hw)]
    d.polygon(pts, fill=(0, 0, 0))
    inner = [(x + (tx - x) * 0.0, y) for x, y in pts]
    d.polygon([(x - ux * 6, y - uy * 6) for x, y in inner], fill=color)


# ------------------------------------------------------------------ textes auto
def auto_texts(timeline, plan):
    games = timeline.get("games", [])
    kills = [len(g.get("kills", [])) for g in games]
    tot, best = sum(kills), max(kills) if kills else 0
    mode = timeline.get("mode", "cup")
    if mode in ("box_arena", "creative_1v1"):
        fin = plan.get("final") or {}
        w_, l_ = fin.get("wins", 0), fin.get("losses", 0)
        best = max((g.get("score") or [0, 0] for g in games), key=lambda s: s[0] - s[1], default=None)
        gain = fin.get("session_gain")
        if mode == "box_arena":
            main = f"+{gain}%" if gain and gain > 0 else (f"{w_} WINS" if w_ else "BOX FIGHT")
            sub = (fin.get("rank_end") or {}).get("name") or "ARÈNE BOX FIGHT"
        else:
            main = f"{best[0]}-{best[1]}" if best and best[0] > best[1] else (f"{w_} WINS" if w_ else "1V1")
            sub = "1V1 BOX FIGHT"
        alt = f"{w_}V - {l_}D" if (w_ or l_) else sub
        return {"main": main, "sub": sub, "alt": alt}
    if mode == "cup":
        pts = timeline.get("final_points") or max([g.get("points_before") or 0 for g in games] or [0])
        main = f"{pts} PTS" if pts else f"{tot} KILLS"
        sub = "EN CUP !"
        alt = f"{best} KILLS EN 1 GAME" if best else "LA CUP"
    else:
        fin = plan.get("final") or {}
        gain = fin.get("session_gain")
        rank = (fin.get("rank_end") or {}).get("name")
        main = f"+{gain}%" if gain and gain > 0 else f"{tot} KILLS"
        sub = rank or ("RANKED RELOAD" if "reload" in mode else "RANKED")
        alt = f"{best} KILLS EN 1 GAME" if best else "RANKED"
    return {"main": main, "sub": sub, "alt": alt}


# ------------------------------------------------------------------ mises en page
def layout_impact(bg, main, sub, accent):
    """Gros chiffre à gauche + sous-titre jaune, fond assombri à gauche."""
    img = side_shade(vignette(punch(bg)), "left", 0.62, 215).convert("RGBA")
    d = ImageDraw.Draw(img)
    s = fit_size(main, 700, 230)
    big_text(d, (60, 120), main, s, accent, glow=accent, layer=img)
    d = ImageDraw.Draw(img)
    s2 = fit_size(sub, 680, 120)
    big_text(d, (64, 140 + s + 20), sub, s2, YELLOW)
    return img


def layout_banner(bg, main, sub, accent):
    """Texte énorme en bas sur bandeau, sous-titre en étiquette jaune en haut."""
    img = side_shade(vignette(punch(bg), 0.4), "bottom", 0.55, 230).convert("RGBA")
    d = ImageDraw.Draw(img)
    s = fit_size(main, 1180, 220)
    big_text(d, (W // 2, H - 40), main, s, WHITE, anchor="ms", glow=accent, layer=img)
    d = ImageDraw.Draw(img)
    f = font(fit_size(sub, 900, 90))
    tb = d.textbbox((0, 0), sub, font=f)
    pad = 22
    x0, y0 = 40, 36
    d.rounded_rectangle([x0, y0, x0 + tb[2] - tb[0] + pad * 2, y0 + tb[3] - tb[1] + pad * 2], 18, fill=YELLOW,
                        outline=(0, 0, 0), width=6)
    d.text((x0 + pad - tb[0], y0 + pad - tb[1]), sub, font=f, fill=(0, 0, 0))
    return img


def layout_split(bg, main, sub, accent):
    """Panneau bleu Fortnite à gauche avec le stat, gameplay à droite + flèche."""
    img = punch(bg).convert("RGBA")
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.polygon([(0, 0), (560, 0), (440, H), (0, H)], fill=BLUE + (240,))
    pd.polygon([(560, 0), (590, 0), (470, H), (440, H)], fill=YELLOW + (255,))
    img.alpha_composite(panel)
    d = ImageDraw.Draw(img)
    s = fit_size(main, 440, 200)
    big_text(d, (40, 170), main, s, accent, glow=(0, 0, 0), layer=img)
    d = ImageDraw.Draw(img)
    big_text(d, (44, 190 + s), sub, fit_size(sub, 400, 100), WHITE)
    arrow(d, (830, 400), RED, 100, -150)
    return img


def layout_center(bg, main, sub, accent):
    """Mot-choc centré géant, légèrement incliné (effet 'MrBeast'), sous-titre dessous."""
    img = vignette(punch(bg), 0.7).convert("RGBA")
    txt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    td = ImageDraw.Draw(txt)
    s = fit_size(main, 1100, 260)
    big_text(td, (W // 2, H // 2 - 20), main, s, accent, anchor="mm", glow=accent, layer=txt)
    td = ImageDraw.Draw(txt)
    big_text(td, (W // 2, H // 2 + s // 2 + 40), sub, fit_size(sub, 1000, 110), WHITE, anchor="mm")
    img.alpha_composite(txt.rotate(4, resample=Image.BICUBIC, center=(W // 2, H // 2)))
    return img


LAYOUTS = [("impact", layout_impact), ("bandeau", layout_banner), ("split", layout_split), ("centre", layout_center)]


def accent_for(main):
    import re
    m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", main)
    if m:
        return GREEN if int(m.group(1)) > int(m.group(2)) else RED
    if main.strip().startswith("+"):
        return GREEN
    if main.strip().startswith("-"):
        return RED
    return YELLOW if "PTS" in main else WHITE


def save_jpg(img, path):
    from license import watermark
    img = watermark(img.convert("RGB"))
    q = 92
    while True:
        img.save(path, "JPEG", quality=q, optimize=True, progressive=True)
        if Path(path).stat().st_size < 1_900_000 or q <= 60:   # limite YouTube : 2 Mo
            return
        q -= 6


def generate(cfg, main=None, sub=None, times=None, out_dir=None):
    wd = work_dir(cfg)
    tl = json.loads((wd / "timeline.json").read_text(encoding="utf-8"))
    plan_p = wd / "edit_plan.json"
    plan = json.loads(plan_p.read_text(encoding="utf-8")) if plan_p.exists() else {}
    auto = auto_texts(tl, plan)
    main = (main or auto["main"]).upper()
    sub = (sub or auto["sub"]).upper()
    times = times or best_moments(tl, plan, 4)
    out_dir = Path(out_dir or wd / "miniatures")
    out_dir.mkdir(parents=True, exist_ok=True)
    video = video_path(cfg)
    accent = accent_for(main)
    files = []
    for i, (name, fn) in enumerate(LAYOUTS):
        bg = good_frame(video, times[i % len(times)])
        img = fn(bg, main, sub if i != 3 else (auto["alt"].upper() if not sub else sub), accent)
        p = out_dir / f"miniature_{i + 1}_{name}.jpg"
        save_jpg(img, p)
        files.append(p)
    return files, {"main": main, "sub": sub, "auto": auto, "times": times}

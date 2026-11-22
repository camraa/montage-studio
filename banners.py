"""Studio de bannières : miniatures Cup / Ranked dans le style des chaînes Fortnite compétitives.

Les visuels Epic (icônes de cups, de rangs, skins) ne sont pas fournis : l'utilisateur dépose
ses propres PNG dans assets/ (rangs/, cups/, skins/). Sans eux, des badges et un trophée
originaux aux couleurs des paliers sont dessinés à la place.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:
    from common import ASSET_DIR, DATA_DIR
except Exception:                       # utilisation hors de l'app
    ASSET_DIR = DATA_DIR = Path(__file__).resolve().parent

S = 2                                   # rendu en 2x puis réduction = bords lisses
W, H = 1280, 720
FONT_DIR = ASSET_DIR / "polices"
USER_ASSETS = DATA_DIR / "assets"

RANKS = [  # nom, couleur claire, couleur foncée
    ("BRONZE", (222, 150, 96), (122, 66, 32)),
    ("ARGENT", (214, 224, 236), (112, 126, 146)),
    ("OR", (255, 214, 72), (176, 112, 10)),
    ("PLATINE", (120, 236, 228), (24, 120, 140)),
    ("DIAMANT", (110, 170, 255), (34, 62, 186)),
    ("ÉLITE", (196, 206, 222), (52, 58, 74)),
    ("CHAMPION", (255, 138, 72), (170, 40, 20)),
    ("UNREAL", (226, 150, 255), (98, 30, 170)),
]
THEMES = {
    "cup":    {"bg": ((18, 66, 190), (6, 18, 70)), "ray": (90, 160, 255), "accent": (255, 206, 40)},
    "reload": {"bg": ((20, 150, 120), (4, 40, 40)), "ray": (110, 255, 200), "accent": (255, 220, 60)},
    "ranked": {"bg": ((150, 40, 230), (30, 6, 70)), "ray": (220, 120, 255), "accent": (120, 255, 150)},
}


def F(size, kind="anton"):
    name = {"anton": "Anton-Regular.ttf", "lucky": "LuckiestGuy-Regular.ttf"}[kind]
    try:
        return ImageFont.truetype(str(FONT_DIR / name), int(size * S))
    except OSError:
        return ImageFont.load_default()


def P(*v):
    return tuple(int(x * S) for x in v)


# ------------------------------------------------------------------ fonds
def background(theme, frame=None):
    w, h = W * S, H * S
    c1, c2 = THEMES[theme]["bg"]
    if frame is not None:                      # image du rec floutée en fond
        bg = frame.convert("RGB").resize((w, h)).filter(ImageFilter.GaussianBlur(10 * S))
        tint = Image.new("RGB", (w, h), c2)
        bg = Image.blend(bg, tint, 0.45)
    else:
        bg = Image.new("RGB", (w, h), c2)
        grad = Image.radial_gradient("L").resize((w * 2, h * 2)).crop((w // 2, h // 3, w // 2 + w, h // 3 + h))
        bg = Image.composite(Image.new("RGB", (w, h), c2), Image.new("RGB", (w, h), c1), grad)
    # rayons de lumière
    rays = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(rays)
    cx, cy = w * 0.62, h * 0.45
    for i in range(18):
        a0 = i * (2 * math.pi / 18)
        a1 = a0 + math.pi / 30
        r = w * 1.5
        d.polygon([(cx, cy), (cx + r * math.cos(a0), cy + r * math.sin(a0)), (cx + r * math.cos(a1), cy + r * math.sin(a1))], fill=34)
    rays = rays.filter(ImageFilter.GaussianBlur(6 * S))
    bg = Image.composite(Image.new("RGB", (w, h), THEMES[theme]["ray"]), bg, rays)
    # vignette
    vig = Image.radial_gradient("L").resize((w, h)).point(lambda v: max(0, v - 90) * 1.6)
    bg = Image.composite(Image.new("RGB", (w, h), (0, 0, 0)), bg, vig.point(lambda v: min(150, v)))
    return bg.convert("RGBA")


# ------------------------------------------------------------------ texte façon Fortnite
def title(img, text, xy, size, fill=(255, 255, 255), anchor="mm", skew=0.18, stroke=7, shadow=(0, 0, 0)):
    """Texte gras penché, gros contour sombre et ombre portée (style miniature Fortnite)."""
    font = F(size)
    pad = int(size * S * 0.6)
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    l, t, r, b = tmp.textbbox((0, 0), text, font=font, stroke_width=stroke * S)
    tw, th = r - l + pad * 2, b - t + pad * 2
    lay = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    dl = ImageDraw.Draw(lay)
    org = (pad - l, pad - t)
    sh = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((org[0] + 6 * S, org[1] + 8 * S), text, font=font, fill=shadow + (170,), stroke_width=stroke * S, stroke_fill=shadow + (170,))
    sh = sh.filter(ImageFilter.GaussianBlur(4 * S))
    lay.alpha_composite(sh)
    dl.text(org, text, font=font, fill=fill, stroke_width=stroke * S, stroke_fill=(14, 16, 40))
    if skew:
        lay = lay.transform((tw + int(th * skew), th), Image.AFFINE, (1, skew, -th * skew, 0, 1, 0), Image.BICUBIC)
    x, y = P(*xy)
    lw, lh = lay.size
    ox = {"l": 0, "m": lw // 2, "r": lw}[anchor[0]] - (pad if anchor[0] == "l" else -pad if anchor[0] == "r" else 0)
    oy = {"t": 0, "m": lh // 2, "b": lh}[anchor[1]] - (pad if anchor[1] == "t" else -pad if anchor[1] == "b" else 0)
    img.alpha_composite(lay, (int(x - ox), int(y - oy)))


def rounded(img, box, r, fill, outline=None, width=0, shadow=True):
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        b = P(*box)
        ImageDraw.Draw(sh).rounded_rectangle((b[0] + 8 * S, b[1] + 12 * S, b[2] + 8 * S, b[3] + 12 * S), r * S, fill=(0, 0, 0, 120))
        img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10 * S)))
    ImageDraw.Draw(img).rounded_rectangle(P(*box), r * S, fill=fill, outline=outline, width=width * S)


def vgrad(size, top, bottom):
    w, h = size
    g = Image.linear_gradient("L").resize((w, h))
    return Image.composite(Image.new("RGBA", (w, h), bottom), Image.new("RGBA", (w, h), top), g)


def globe(img, cx, cy, r, color=(70, 200, 120)):
    d = ImageDraw.Draw(img)
    c = P(cx, cy)
    R = r * S
    d.ellipse((c[0] - R, c[1] - R, c[0] + R, c[1] + R), fill=(40, 120, 220), outline=(255, 255, 255), width=2 * S)
    for k in (-0.55, 0, 0.55):
        rx = R * (1 - abs(k)) if k else R * 0.45
        d.ellipse((c[0] - rx, c[1] - R, c[0] + rx, c[1] + R), outline=(255, 255, 255, 170), width=max(1, S))
    d.line((c[0] - R, c[1], c[0] + R, c[1]), fill=(255, 255, 255, 170), width=max(1, S))
    d.pieslice((c[0] - R * .7, c[1] - R * .8, c[0] + R * .3, c[1] + R * .4), 180, 320, fill=color)


def trophy(img, cx, cy, h):
    """Trophée générique (dessin original)."""
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    x, y, k = cx * S, cy * S, h * S / 100
    gold, dark = (255, 205, 50), (190, 120, 10)
    d.ellipse((x - 46 * k, y - 38 * k, x - 12 * k, y + 2 * k), outline=dark, width=int(9 * k))
    d.ellipse((x + 12 * k, y - 38 * k, x + 46 * k, y + 2 * k), outline=dark, width=int(9 * k))
    d.pieslice((x - 36 * k, y - 80 * k, x + 36 * k, y + 20 * k), 0, 180, fill=gold)
    d.rectangle((x - 36 * k, y - 50 * k, x + 36 * k, y - 30 * k), fill=gold)
    d.rectangle((x - 7 * k, y + 18 * k, x + 7 * k, y + 36 * k), fill=dark)
    d.rounded_rectangle((x - 28 * k, y + 34 * k, x + 28 * k, y + 50 * k), int(4 * k), fill=gold)
    d.polygon([(x - 14 * k, y - 46 * k), (x - 4 * k, y - 46 * k), (x - 18 * k, y + 8 * k)], fill=(255, 245, 190, 200))
    sh = lay.filter(ImageFilter.GaussianBlur(14 * S))
    img.alpha_composite(Image.composite(Image.new("RGBA", img.size, (255, 200, 60, 140)), Image.new("RGBA", img.size, (0, 0, 0, 0)), sh.split()[3]))
    img.alpha_composite(lay)


def rank_badge(img, cx, cy, size, idx, user_icon=None):
    """Icône de rang : PNG de l'utilisateur si présent, sinon badge original aux couleurs du palier."""
    if user_icon and Path(user_icon).exists():
        ic = Image.open(user_icon).convert("RGBA")
        ic.thumbnail((size * S, size * S))
        img.alpha_composite(ic, (int(cx * S - ic.width / 2), int(cy * S - ic.height / 2)))
        return
    name, light, dark = RANKS[idx]
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    r = size * S / 2
    x, y = cx * S, cy * S
    hexa = [(x + r * math.cos(math.radians(a)), y + r * math.sin(math.radians(a))) for a in range(-90, 270, 60)]
    inner = [(x + r * .72 * math.cos(math.radians(a)), y + r * .72 * math.sin(math.radians(a))) for a in range(-90, 270, 60)]
    d.polygon(hexa, fill=dark)
    d.polygon(inner, fill=light)
    pips = min(idx + 1, 5)
    for i in range(pips):                      # chevrons = niveau du palier
        yy = y + r * .32 - i * r * .2
        d.line([(x - r * .32, yy), (x, yy - r * .16), (x + r * .32, yy)], fill=dark, width=max(2, int(r * .09)), joint="curve")
    img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(0.4 * S)))


def skin(img, path, box):
    """Skin détouré de l'utilisateur ; sinon une silhouette repère."""
    x0, y0, x1, y1 = P(*box)
    if path and Path(path).exists():
        sk = Image.open(path).convert("RGBA")
        sk.thumbnail((x1 - x0, y1 - y0))
        px, py = x0 + (x1 - x0 - sk.width) // 2, y1 - sk.height
        glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        glow.alpha_composite(sk, (px, py))
        a = glow.split()[3].filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(6 * S))
        img.alpha_composite(Image.composite(Image.new("RGBA", img.size, (255, 255, 255, 230)), Image.new("RGBA", img.size, (0, 0, 0, 0)), a))
        img.alpha_composite(sk, (px, py))
        return
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    cx, w, h = (x0 + x1) / 2, x1 - x0, y1 - y0
    col = (255, 255, 255, 55)
    d.ellipse((cx - w * .16, y0 + h * .06, cx + w * .16, y0 + h * .3), fill=col)
    d.rounded_rectangle((cx - w * .36, y0 + h * .33, cx + w * .36, y1 + 40 * S), int(w * .16), fill=col)
    img.alpha_composite(lay)
    dd = ImageDraw.Draw(img)
    dd.text((cx, y0 + h * .62), "TON SKIN", font=F(30), fill=(255, 255, 255, 200), anchor="mm")
    dd.text((cx, y0 + h * .69), "détouré depuis ton rec", font=F(17), fill=(255, 255, 255, 150), anchor="mm")


def finish(img):
    return img.resize((W, H), Image.LANCZOS).convert("RGB")


# ------------------------------------------------------------------ modèles
def cup_leaderboard(pseudo="Camra", points=351, place=1, cup="SOLO CASH CUP", others=None,
                    top_pct="Top 1%", theme="cup", skin_path=None, frame=None):
    img = background(theme, frame)
    others = others or [("Vexo", 297), ("Kuzz", 254), ("Ralyx", 210), ("Mertz", 195), ("Okami", 189)]
    skin(img, skin_path, (20, 120, 430, 720))
    title(img, cup, (820, 74), 82)
    # panneau du classement
    px0, py0, px1 = 470, 140, 1240
    rounded(img, (px0, py0, px1, 660), 18, (10, 22, 70, 205), outline=(120, 170, 255, 120), width=2)
    # ligne mise en avant
    row = vgrad(P(px1 - px0 + 24, 104)[0:2], (255, 255, 255, 255), (214, 230, 255, 255))
    mask = Image.new("L", row.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, row.width - 1, row.height - 1), 14 * S, fill=255)
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(P(px0 - 4, py0 + 14, px1 + 26, py0 + 128), 14 * S, fill=(0, 0, 0, 150))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10 * S)))
    img.paste(row, P(px0 - 12, py0 + 6), mask)
    d = ImageDraw.Draw(img)
    badge = (px0 + 4, py0 + 14, px0 + 136, py0 + 102)
    d.rounded_rectangle(P(*badge), 12 * S, fill=(255, 204, 0))
    title(img, f"#{place}", ((badge[0] + badge[2]) / 2, (badge[1] + badge[3]) / 2 + 2), 62, fill=(255, 255, 255), skew=0.12, stroke=5)
    d.text(P(px0 + 160, py0 + 58), pseudo, font=F(52), fill=(14, 24, 60), anchor="lm")
    d.text(P(px1 - 70, py0 + 58), str(points), font=F(64), fill=(14, 24, 60), anchor="rm")
    globe(img, px1 - 30, py0 + 58, 20)
    # autres lignes
    y = py0 + 142
    for i, (name, pts) in enumerate(others):
        d.text(P(px0 + 40, y), f"#{place + i + 1}", font=F(28), fill=(255, 255, 255), anchor="lm")
        d.text(P(px0 + 120, y), name, font=F(28), fill=(220, 232, 255), anchor="lm")
        d.text(P(px1 - 70, y), str(pts), font=F(30), fill=(255, 255, 255), anchor="rm")
        globe(img, px1 - 32, y, 13)
        d.line(P(px0 + 30, y + 30, px1 - 20, y + 30), fill=(255, 255, 255, 40), width=S)
        y += 62
    d.text(P(px0 + 40, 625), "TOI :", font=F(30), fill=(200, 215, 255), anchor="lm")
    d.text(P(px0 + 120, 625), f"{points} PTS", font=F(40), fill=(255, 255, 255), anchor="lm")
    d.text(P(px0 + 290, 627), f"({top_pct})", font=F(26), fill=(200, 215, 255), anchor="lm")
    trophy(img, 1185, 72, 92)
    return finish(img)


def ranked_grind(pseudo="Camra", start=2, current=4, target=7, progress=0.45, elo_gain="+65%",
                 day=12, theme="ranked", skin_path=None, frame=None, icons=None):
    img = background(theme, frame)
    icons = icons or {}
    skin(img, skin_path, (870, 110, 1270, 720))
    title(img, f"OBJECTIF {RANKS[target][0]}", (460, 86), 84)
    title(img, f"JOUR {day} DU GRIND", (460, 176), 44, fill=THEMES[theme]["accent"], skew=0.15, stroke=5)
    # barre de progression par paliers
    n = target - start + 1
    bx0, bx1, by = 70, 850, 420
    step = (bx1 - bx0) / (n - 1)
    d = ImageDraw.Draw(img)
    rounded(img, (bx0 - 20, by - 18, bx1 + 20, by + 18), 18, (20, 6, 50, 230), outline=(255, 255, 255, 60), width=2)
    fill_to = bx0 + step * ((current - start) + progress)
    bar = vgrad(P(fill_to - bx0 + 10, 24)[0:2], (140, 255, 170, 255), (40, 190, 90, 255))
    m = Image.new("L", bar.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, bar.width - 1, bar.height - 1), 12 * S, fill=255)
    img.paste(bar, P(bx0 - 10, by - 12), m)
    for i in range(n):
        idx = start + i
        x = bx0 + step * i
        big = idx in (current, target)
        size = 120 if big else 84
        rank_badge(img, x, by - (14 if big else 0), size, idx, icons.get(idx))
        col = (255, 255, 255) if idx <= current else (190, 170, 230)
        d.text(P(x, by + (82 if big else 64)), RANKS[idx][0], font=F(24 if big else 20), fill=col, anchor="mm")
    # repère "tu es ici"
    d.polygon([P(fill_to - 12, by - 56), P(fill_to + 12, by - 56), P(fill_to, by - 38)], fill=(255, 255, 255))
    d.text(P(fill_to, by - 74), "TU ES ICI", font=F(22), fill=(255, 255, 255), anchor="mm")
    # stats
    title(img, f"{elo_gain} ELO", (300, 600), 96, fill=THEMES[theme]["accent"])
    d.text(P(610, 584), "aujourd'hui", font=F(28), fill=(235, 220, 255), anchor="lm")
    d.text(P(610, 622), pseudo.upper(), font=F(28), fill=(255, 255, 255), anchor="lm")
    return finish(img)


TEMPLATES = {"cup_leaderboard": cup_leaderboard, "ranked_grind": ranked_grind}

if __name__ == "__main__":
    out = Path("apercu_bannieres")
    out.mkdir(exist_ok=True)
    cup_leaderboard().save(out / "cup_leaderboard.jpg", quality=92)
    ranked_grind().save(out / "ranked_grind.jpg", quality=92)
    print("ok", out.resolve())

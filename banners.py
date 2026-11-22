"""Studio de bannières : miniatures, bannière de chaîne, écran de fin, bandeau de stream, bannière X.

Style des chaînes Fortnite compétitives (titres penchés à gros contour, classement, progression de rang).
Les visuels Epic (icônes de cups, de rangs, skins) ne sont PAS fournis : l'utilisateur dépose ses propres
PNG dans <données>/assets/ (rangs/, cups/, skins/). Sans eux, on dessine des badges et un trophée originaux.
"""
import math
import re
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

try:
    from common import ASSET_DIR, DATA_DIR
except Exception:                       # utilisation hors de l'app
    ASSET_DIR = DATA_DIR = Path(__file__).resolve().parent

S = 2                                   # rendu en 2x puis réduction = bords lisses
FONT_DIR = ASSET_DIR / "polices"
USER_ASSETS = DATA_DIR / "assets"
SKIN_DIR = USER_ASSETS / "skins"
RANK_DIR = USER_ASSETS / "rangs"
CUP_DIR = USER_ASSETS / "cups"

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
RANK_NAMES = [r[0] for r in RANKS]
THEMES = {
    "cup":    {"label": "Cup (bleu)", "bg": ((18, 66, 190), (6, 18, 70)), "ray": (90, 160, 255), "accent": (255, 206, 40)},
    "reload": {"label": "Reload (vert)", "bg": ((20, 150, 120), (4, 40, 40)), "ray": (110, 255, 200), "accent": (255, 220, 60)},
    "ranked": {"label": "Ranked (violet)", "bg": ((150, 40, 230), (30, 6, 70)), "ray": (220, 120, 255), "accent": (120, 255, 150)},
    "rouge":  {"label": "Rouge", "bg": ((210, 40, 50), (60, 6, 16)), "ray": (255, 120, 110), "accent": (255, 220, 60)},
}
DARK = (14, 16, 40)


def F(size, kind="anton"):
    name = {"anton": "Anton-Regular.ttf", "lucky": "LuckiestGuy-Regular.ttf"}[kind]
    try:
        return ImageFont.truetype(str(FONT_DIR / name), int(size * S))
    except OSError:
        return ImageFont.load_default()


def P(*v):
    return tuple(int(x * S) for x in v)


def rank_index(name):
    """'DIAMANT II' / 'Diamond' / 4 -> indice de palier (0 = Bronze ... 7 = Unreal)."""
    if isinstance(name, int):
        return max(0, min(7, name))
    n = (name or "").upper().replace("É", "E")
    for i, r in enumerate(RANK_NAMES):
        if r.replace("É", "E") in n:
            return i
    for i, key in enumerate(("BRONZE", "SILVER", "GOLD", "PLATINUM", "DIAMOND", "ELITE", "CHAMPION", "UNREAL")):
        if key in n:
            return i
    return 0


# ------------------------------------------------------------------ fonds
def background(theme, w, h, frame=None):
    w, h = w * S, h * S
    th = THEMES.get(theme, THEMES["cup"])
    c1, c2 = th["bg"]
    if frame is not None:                      # image du rec floutée et teintée en fond
        bg = ImageOps.fit(frame.convert("RGB"), (w, h)).filter(ImageFilter.GaussianBlur(6 * S))
        bg = Image.blend(bg, Image.new("RGB", (w, h), c2), 0.5)
    else:
        grad = Image.radial_gradient("L").resize((w * 2, h * 2)).crop((w // 2, h // 3, w // 2 + w, h // 3 + h))
        bg = Image.composite(Image.new("RGB", (w, h), c2), Image.new("RGB", (w, h), c1), grad)
    rays = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(rays)
    cx, cy = w * 0.62, h * 0.45
    r = max(w, h) * 1.5
    for i in range(18):
        a0 = i * (2 * math.pi / 18)
        a1 = a0 + math.pi / 30
        d.polygon([(cx, cy), (cx + r * math.cos(a0), cy + r * math.sin(a0)), (cx + r * math.cos(a1), cy + r * math.sin(a1))], fill=34)
    rays = rays.filter(ImageFilter.GaussianBlur(6 * S))
    bg = Image.composite(Image.new("RGB", (w, h), th["ray"]), bg, rays)
    vig = Image.radial_gradient("L").resize((w, h)).point(lambda v: min(150, max(0, v - 90) * 1.6))
    bg = Image.composite(Image.new("RGB", (w, h), (0, 0, 0)), bg, vig)
    return bg.convert("RGBA")


def finish(img, w, h):
    return img.resize((w, h), Image.LANCZOS)


# ------------------------------------------------------------------ éléments
def title(img, text, xy, size, fill=(255, 255, 255), anchor="mm", skew=0.18, stroke=7, kind="anton", max_w=None):
    """Texte gras penché, gros contour sombre et ombre portée (style miniature Fortnite)."""
    text = str(text)
    if max_w:                                   # réduit la taille si le texte est trop large
        while size > 12:
            l, _, r, _ = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=F(size, kind), stroke_width=stroke * S)
            if (r - l) / S <= max_w:
                break
            size -= 2
    font = F(size, kind)
    pad = int(size * S * 0.6)
    l, t, r, b = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=font, stroke_width=stroke * S)
    tw, th = r - l + pad * 2, b - t + pad * 2
    lay = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    org = (pad - l, pad - t)
    sh = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((org[0] + 6 * S, org[1] + 8 * S), text, font=font, fill=(0, 0, 0, 170),
                            stroke_width=stroke * S, stroke_fill=(0, 0, 0, 170))
    lay.alpha_composite(sh.filter(ImageFilter.GaussianBlur(4 * S)))
    ImageDraw.Draw(lay).text(org, text, font=font, fill=fill, stroke_width=stroke * S, stroke_fill=DARK)
    if skew:
        lay = lay.transform((tw + int(th * skew), th), Image.AFFINE, (1, skew, -th * skew, 0, 1, 0), Image.BICUBIC)
    x, y = P(*xy)
    lw, lh = lay.size
    ox = {"l": pad, "m": lw // 2, "r": lw - pad}[anchor[0]]
    oy = {"t": pad, "m": lh // 2, "b": lh - pad}[anchor[1]]
    img.alpha_composite(lay, (int(x - ox), int(y - oy)))


def shadow_box(img, box, r, blur=10, off=(8, 12), alpha=120):
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    b = P(*box)
    ImageDraw.Draw(sh).rounded_rectangle((b[0] + off[0] * S, b[1] + off[1] * S, b[2] + off[0] * S, b[3] + off[1] * S),
                                         r * S, fill=(0, 0, 0, alpha))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur * S)))


def rounded(img, box, r, fill, outline=None, width=0, shadow=True):
    if shadow:
        shadow_box(img, box, r)
    ImageDraw.Draw(img).rounded_rectangle(P(*box), r * S, fill=fill, outline=outline, width=width * S)


def vgrad(size, top, bottom):
    w, h = size
    g = Image.linear_gradient("L").resize((w, h))
    return Image.composite(Image.new("RGBA", (w, h), bottom), Image.new("RGBA", (w, h), top), g)


def paste_rounded(img, tile, xy, r):
    m = Image.new("L", tile.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, tile.width - 1, tile.height - 1), r * S, fill=255)
    img.paste(tile, P(*xy), m)


def globe(img, cx, cy, r):
    d = ImageDraw.Draw(img)
    c = P(cx, cy)
    R = r * S
    d.ellipse((c[0] - R, c[1] - R, c[0] + R, c[1] + R), fill=(40, 120, 220), outline=(255, 255, 255), width=2 * S)
    for k in (-0.55, 0.55):
        rx = R * (1 - abs(k))
        d.ellipse((c[0] - rx, c[1] - R, c[0] + rx, c[1] + R), outline=(255, 255, 255, 170), width=max(1, S))
    d.line((c[0] - R, c[1], c[0] + R, c[1]), fill=(255, 255, 255, 170), width=max(1, S))
    d.pieslice((c[0] - R * .7, c[1] - R * .8, c[0] + R * .3, c[1] + R * .4), 180, 320, fill=(70, 200, 120))


def _user_png(folder, name=None):
    if not folder.exists():
        return None
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".png", ".webp"))
    if name:
        key = re.sub(r"[^a-z]", "", name.lower().replace("é", "e"))
        files = [p for p in files if key and key in re.sub(r"[^a-z]", "", p.stem.lower().replace("é", "e"))]
    return files[0] if files else None


def place_png(img, path, cx, cy, size):
    ic = Image.open(path).convert("RGBA")
    ic.thumbnail((size * S, size * S), Image.LANCZOS)
    img.alpha_composite(ic, (int(cx * S - ic.width / 2), int(cy * S - ic.height / 2)))


def trophy(img, cx, cy, h):
    """Icône de cup de l'utilisateur (assets/cups) sinon trophée générique (dessin original)."""
    user = _user_png(CUP_DIR)
    if user:
        return place_png(img, user, cx, cy, h * 1.3)
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
    glow = lay.split()[3].filter(ImageFilter.GaussianBlur(14 * S))
    img.alpha_composite(Image.composite(Image.new("RGBA", img.size, (255, 200, 60, 140)),
                                        Image.new("RGBA", img.size, (0, 0, 0, 0)), glow))
    img.alpha_composite(lay)


def rank_badge(img, cx, cy, size, idx):
    """Icône de rang : PNG de l'utilisateur (assets/rangs/<nom>.png) sinon badge original aux couleurs du palier."""
    user = _user_png(RANK_DIR, RANKS[idx][0])
    if user:
        return place_png(img, user, cx, cy, size)
    _, light, dark = RANKS[idx]
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    r = size * S / 2
    x, y = cx * S, cy * S
    hexa = [(x + r * math.cos(math.radians(a)), y + r * math.sin(math.radians(a))) for a in range(-90, 270, 60)]
    inner = [(x + r * .72 * math.cos(math.radians(a)), y + r * .72 * math.sin(math.radians(a))) for a in range(-90, 270, 60)]
    d.polygon(hexa, fill=dark)
    d.polygon(inner, fill=light)
    for i in range(min(idx + 1, 5)):            # chevrons = niveau du palier
        yy = y + r * .32 - i * r * .2
        d.line([(x - r * .32, yy), (x, yy - r * .16), (x + r * .32, yy)], fill=dark, width=max(2, int(r * .09)), joint="curve")
    img.alpha_composite(lay)


def skin(img, path, box, flip=False, label=True):
    """Skin détouré de l'utilisateur, avec contour blanc ; sinon une silhouette repère."""
    x0, y0, x1, y1 = P(*box)
    if path and Path(path).exists():
        sk = Image.open(path).convert("RGBA")
        bb = sk.getbbox()
        if bb:
            sk = sk.crop(bb)
        if flip:
            sk = ImageOps.mirror(sk)
        k = min((x1 - x0) / sk.width, (y1 - y0) / sk.height)
        sk = sk.resize((max(1, int(sk.width * k)), max(1, int(sk.height * k))), Image.LANCZOS)
        px, py = x0 + (x1 - x0 - sk.width) // 2, y1 - sk.height
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        lay.alpha_composite(sk, (px, max(0, py)))
        a = lay.split()[3]
        outline = a.filter(ImageFilter.MaxFilter(9))
        clear = Image.new("RGBA", img.size, (0, 0, 0, 0))
        img.alpha_composite(Image.composite(Image.new("RGBA", img.size, (0, 0, 0, 160)), clear,
                                            outline.filter(ImageFilter.GaussianBlur(14 * S))))
        img.alpha_composite(Image.composite(Image.new("RGBA", img.size, (255, 255, 255, 255)), clear, outline))
        img.alpha_composite(lay)
        return
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    cx, w, h = (x0 + x1) / 2, x1 - x0, y1 - y0
    col = (255, 255, 255, 55)
    d.ellipse((cx - w * .16, y0 + h * .06, cx + w * .16, y0 + h * .3), fill=col)
    d.rounded_rectangle((cx - w * .36, y0 + h * .33, cx + w * .36, y1 + 40 * S), int(w * .16), fill=col)
    img.alpha_composite(lay)
    if label:
        ImageDraw.Draw(img).text((cx, y0 + h * .62), "TON SKIN", font=F(max(14, h / S * 0.05)),
                                 fill=(255, 255, 255, 200), anchor="mm")


def arrow(img, tail, tip, width=26, color=(255, 40, 40)):
    """Grosse flèche (style miniature), contour blanc."""
    (x0, y0), (x1, y1) = P(*tail), P(*tip)
    ang = math.atan2(y1 - y0, x1 - x0)
    w = width * S
    head = w * 2.2
    bx, by = x1 - head * math.cos(ang), y1 - head * math.sin(ang)
    nx, ny = -math.sin(ang), math.cos(ang)
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    poly = [(x0 + nx * w / 2, y0 + ny * w / 2), (bx + nx * w / 2, by + ny * w / 2), (bx + nx * w * 1.4, by + ny * w * 1.4),
            (x1, y1), (bx - nx * w * 1.4, by - ny * w * 1.4), (bx - nx * w / 2, by - ny * w / 2), (x0 - nx * w / 2, y0 - ny * w / 2)]
    ImageDraw.Draw(lay).polygon(poly, fill=color)
    sh = lay.split()[3].filter(ImageFilter.MaxFilter(13))
    outline_col = (255, 255, 255, 255) if color != (255, 255, 255) else (14, 16, 40, 255)
    img.alpha_composite(Image.composite(Image.new("RGBA", img.size, outline_col), Image.new("RGBA", img.size, (0, 0, 0, 0)), sh))
    img.alpha_composite(lay)


def leaderboard(img, box, rows, blur_top=0, font=28):
    """Tableau de classement : rows = [(place, nom, points)] ; les blur_top premières lignes sont floutées."""
    x0, y0, x1, y1 = box
    rounded(img, box, 18, (10, 22, 70, 205), outline=(120, 170, 255, 120), width=2)
    rh = (y1 - y0 - 20) / max(1, len(rows))
    d = ImageDraw.Draw(img)
    for i, (place, name, pts) in enumerate(rows):
        y = y0 + 10 + rh * (i + 0.5)
        if name != "":
            lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            dl = ImageDraw.Draw(lay)
            dl.text(P(x0 + 30, y), f"#{place}", font=F(font), fill=(255, 255, 255), anchor="lm")
            dl.text(P(x0 + 30 + font * 2.8, y), str(name), font=F(font), fill=(220, 232, 255), anchor="lm")
            dl.text(P(x1 - 34 - font * 1.6, y), str(pts), font=F(font * 1.05), fill=(255, 255, 255), anchor="rm")
            if i < blur_top:
                lay = lay.filter(ImageFilter.GaussianBlur(5 * S))
            img.alpha_composite(lay)
            globe(img, x1 - 18 - font * 0.7, y, font * 0.45)
        if i < len(rows) - 1:
            d.line(P(x0 + 20, y + rh / 2, x1 - 20, y + rh / 2), fill=(255, 255, 255, 40), width=S)


def highlight_row(img, box, place, name, pts, place_txt=None):
    """Grande ligne blanche avec badge doré : '#1  Camra  351'."""
    x0, y0, x1, y1 = box
    h = y1 - y0
    shadow_box(img, (x0 + 8, y0, x1 + 8, y1), 14, alpha=150)
    paste_rounded(img, vgrad(P(x1 - x0, h)[0:2], (255, 255, 255, 255), (214, 230, 255, 255)), (x0, y0), 14)
    d = ImageDraw.Draw(img)
    bw = h * 1.3
    d.rounded_rectangle(P(x0 + 10, y0 + 8, x0 + 10 + bw, y1 - 8), 12 * S, fill=(255, 204, 0))
    title(img, place_txt or f"#{place}", (x0 + 10 + bw / 2, (y0 + y1) / 2 + 2), h * 0.62, skew=0.12, stroke=5, max_w=bw - 12)
    d.text(P(x0 + bw + 34, (y0 + y1) / 2), str(name), font=F(h * 0.5), fill=(14, 24, 60), anchor="lm")
    d.text(P(x1 - h * 0.75, (y0 + y1) / 2), str(pts), font=F(h * 0.62), fill=(14, 24, 60), anchor="rm")
    globe(img, x1 - h * 0.38, (y0 + y1) / 2, h * 0.2)


# ------------------------------------------------------------------ modèles (miniatures 1280x720)
FAKE = ["Vexo", "Kuzz", "Ralyx", "Mertz", "Okami", "Zenko", "Pyxo", "Lunar"]


def _num(v, default=0):
    try:
        return int(re.sub(r"[^\d-]", "", str(v)) or default)
    except ValueError:
        return default


def _acc(v):
    return THEMES[v["theme"]]["accent"]


def t_cup_leaderboard(v, skins, frame, W=1280, H=720):
    img = background(v["theme"], W, H, frame)
    pts, place = _num(v["points"], 0), _num(v["place"], 1)
    skin(img, skins[0], (20, 120, 430, 720))
    title(img, v["cup"], (820, 74), 82, max_w=720)
    trophy(img, 1200, 72, 88)
    others = [(place + i + 1, FAKE[i], max(0, pts - 30 - 18 * i)) for i in range(5)]
    leaderboard(img, (470, 140, 1240, 660), [(0, "", "")] + others + [(0, "", "")], font=28)
    highlight_row(img, (458, 146, 1252, 236), place, v["pseudo"], pts)
    d = ImageDraw.Draw(img)
    d.text(P(510, 620), "TOI :", font=F(30), fill=(200, 215, 255), anchor="lm")
    d.text(P(590, 620), f"{pts} PTS", font=F(40), fill=(255, 255, 255), anchor="lm")
    if v.get("top"):
        d.text(P(760, 622), f"({v['top']})", font=F(26), fill=(200, 215, 255), anchor="lm")
    return finish(img, W, H)


def t_cup_mystere(v, skins, frame, W=1280, H=720):
    img = background(v["theme"], W, H, frame)
    skin(img, skins[0], (870, 110, 1270, 720), flip=True)
    title(img, v["cup"], (460, 74), 80, max_w=800)
    rows = [(i + 1, FAKE[i], 420 - 9 * i) for i in range(3)]
    leaderboard(img, (60, 150, 860, 470), rows, blur_top=3, font=32)
    highlight_row(img, (40, 500, 880, 600), "?", v["pseudo"], "???", place_txt="#?")
    title(img, v.get("accroche") or "J'AI FINI COMBIEN ?", (460, 668), 46, fill=_acc(v), stroke=5, max_w=820)
    return finish(img, W, H)


def t_cup_duo(v, skins, frame, W=1280, H=720):
    img = background(v["theme"], W, H, frame)
    rows = [(i + 2, f"{FAKE[i]} & {FAKE[i + 3]}", 380 - 21 * i) for i in range(4)]
    leaderboard(img, (250, 260, 1030, 560), rows, font=26)
    skin(img, skins[0], (-30, 170, 400, 720))
    skin(img, skins[1] if len(skins) > 1 else None, (880, 170, 1310, 720), flip=True)
    names = f"{v['pseudo']} & {v.get('mate') or 'TON POTE'}".upper()
    shadow_box(img, (130, 36, 1150, 150), 16, alpha=160)
    paste_rounded(img, vgrad(P(1020, 114)[0:2], (255, 255, 255, 255), (214, 230, 255, 255)), (130, 36), 16)
    ImageDraw.Draw(img).rounded_rectangle(P(142, 46, 296, 140), 12 * S, fill=(255, 204, 0))
    title(img, f"#{_num(v['place'], 1)}", (219, 95), 70, skew=0.12, stroke=5, max_w=144)
    title(img, names, (722, 93), 62, fill=DARK, stroke=0, skew=0.12, max_w=800)
    title(img, f"{_num(v['points'], 0)} PTS", (640, 210), 50, fill=_acc(v), stroke=5)
    trophy(img, 640, 630, 110)
    return finish(img, W, H)


def t_gros_titre(v, skins, frame, W=1280, H=720):
    img = background(v["theme"], W, H, frame)
    skin(img, skins[0], (640, 40, 1220, 720))
    arrow(img, (330, 260), (600, 200), 30)
    if v.get("petit"):
        title(img, v["petit"], (60, 120), 60, anchor="lm", fill=_acc(v), stroke=6, max_w=560)
    m1, m2 = (v.get("mot1") or "CUP").upper(), (v.get("mot2") or "SOLO").upper()
    title(img, m1, (40, 600), 190, anchor="lm", stroke=10, max_w=600)
    title(img, m2, (660, 600), 190, anchor="lm", fill=_acc(v), stroke=10, max_w=580)
    return finish(img, W, H)


def t_ranked_grind(v, skins, frame, W=1280, H=720):
    img = background(v["theme"], W, H, frame)
    start, cur, target = rank_index(v["rang_depart"]), rank_index(v["rang_actuel"]), rank_index(v["objectif"])
    start, target = min(start, cur), max(target, min(7, cur + 1))
    if target == start:
        start = max(0, target - 1)
    prog = max(0, min(100, _num(v.get("progression"), 40))) / 100
    skin(img, skins[0], (870, 110, 1270, 720))
    title(img, f"OBJECTIF {RANKS[target][0]}", (460, 86), 84, max_w=820)
    if v.get("jour"):
        title(img, f"JOUR {v['jour']} DU GRIND", (460, 176), 44, fill=_acc(v), skew=0.15, stroke=5)
    n = target - start + 1
    bx0, bx1, by = 70, 850, 420
    step = (bx1 - bx0) / max(1, n - 1)
    d = ImageDraw.Draw(img)
    rounded(img, (bx0 - 20, by - 18, bx1 + 20, by + 18), 18, (20, 6, 50, 230), outline=(255, 255, 255, 60), width=2)
    fill_to = min(bx1, bx0 + step * ((cur - start) + prog))
    if fill_to > bx0:
        paste_rounded(img, vgrad(P(fill_to - bx0 + 10, 24)[0:2], (140, 255, 170, 255), (40, 190, 90, 255)), (bx0 - 10, by - 12), 12)
    for i in range(n):
        idx = start + i
        x = bx0 + step * i
        big = idx in (cur, target)
        rank_badge(img, x, by - (14 if big else 0), 120 if big else 84, idx)
        d.text(P(x, by + (82 if big else 64)), RANKS[idx][0], font=F(24 if big else 20),
               fill=(255, 255, 255) if idx <= cur else (190, 170, 230), anchor="mm")
    d.polygon([P(fill_to - 12, by - 56), P(fill_to + 12, by - 56), P(fill_to, by - 38)], fill=(255, 255, 255))
    d.text(P(fill_to, by - 74), "TU ES ICI", font=F(22), fill=(255, 255, 255), anchor="mm")
    if v.get("gain"):
        title(img, f"{v['gain']} ELO", (300, 600), 96, fill=_acc(v), max_w=520)
        d.text(P(610, 584), v.get("periode") or "aujourd'hui", font=F(28), fill=(235, 220, 255), anchor="lm")
    d.text(P(610, 622), v["pseudo"].upper(), font=F(28), fill=(255, 255, 255), anchor="lm")
    return finish(img, W, H)


def t_ranked_avant_apres(v, skins, frame, W=1280, H=720):
    img = background(v["theme"], W, H, frame)
    a, b = rank_index(v["rang_depart"]), rank_index(v["objectif"])
    skin(img, skins[0], (860, 120, 1270, 720))
    rank_badge(img, 210, 340, 240, a)
    rank_badge(img, 650, 340, 290, b)
    arrow(img, (350, 340), (490, 340), 34, color=(255, 255, 255))
    ImageDraw.Draw(img).text(P(210, 500), RANKS[a][0], font=F(40), fill=(230, 230, 255), anchor="mm")
    title(img, RANKS[b][0], (650, 530), 70, fill=RANKS[b][1], stroke=7)
    title(img, v.get("accroche") or f"{RANKS[a][0]} → {RANKS[b][0]}", (430, 92), 74, max_w=800)
    if v.get("duree"):
        title(img, v["duree"], (430, 645), 64, fill=_acc(v), stroke=6, max_w=800)
    return finish(img, W, H)


# ------------------------------------------------------------------ autres formats
def t_banniere_chaine(v, skins, frame, W=2560, H=1440):
    """Bannière YouTube 2560x1440 : le texte tient dans la zone visible partout (1546x423 au centre)."""
    img = background(v["theme"], W, H, frame)
    sx0, sy0 = (W - 1546) / 2, (H - 423) / 2
    skin(img, skins[0], (sx0 + 1100, sy0 - 140, sx0 + 1600, sy0 + 470), label=False)
    title(img, v["pseudo"].upper(), (sx0 + 40, sy0 + 150), 170, anchor="lm", stroke=10, max_w=960)
    title(img, v.get("slogan") or "CUPS • RANKED • FORTNITE", (sx0 + 44, sy0 + 300), 58, anchor="lm", fill=_acc(v), stroke=6, max_w=960)
    if v.get("planning"):
        ImageDraw.Draw(img).text(P(sx0 + 48, sy0 + 385), v["planning"], font=F(34), fill=(235, 240, 255), anchor="lm")
    trophy(img, sx0 + 1030, sy0 + 130, 120)
    return finish(img, W, H)


def t_ecran_fin(v, skins, frame, W=1920, H=1080):
    """Écran de fin YouTube : 2 emplacements vidéo + 1 abonnement (positions standard de YouTube)."""
    img = background(v["theme"], W, H, frame)
    title(img, v.get("texte") or "LA SUITE ICI", (W / 2, 150), 110, max_w=1600)
    d = ImageDraw.Draw(img)
    for x in (180, 1000):
        rounded(img, (x, 320, x + 740, 736), 22, (0, 0, 0, 120), outline=(255, 255, 255, 200), width=4)
        d.text(P(x + 370, 528), "vidéo", font=F(40), fill=(255, 255, 255, 120), anchor="mm")
    d.ellipse(P(W / 2 - 120, 790, W / 2 + 120, 1030), outline=(255, 255, 255, 220), width=5 * S)
    d.text(P(W / 2, 910), "abonne-toi", font=F(34), fill=(255, 255, 255, 160), anchor="mm")
    skin(img, skins[0], (1560, 660, 1900, 1080), label=False)
    return finish(img, W, H)


def t_bandeau_stream(v, skins, frame, W=1920, H=140):
    """Bandeau à mettre en bas du stream (PNG transparent) : pseudo, réseaux, info."""
    img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    th = THEMES[v["theme"]]
    paste_rounded(img, vgrad(P(W - 40, H - 30)[0:2], th["bg"][0] + (235,), th["bg"][1] + (235,)), (20, 15), 22)
    d = ImageDraw.Draw(img)
    title(img, v["pseudo"].upper(), (60, H / 2 + 4), 64, anchor="lm", stroke=5, max_w=520)
    x = 640
    for label in (v.get("reseau1"), v.get("reseau2")):
        if label:
            d.text(P(x, H / 2), label, font=F(36), fill=(255, 255, 255), anchor="lm")
            x += 50 + d.textlength(label, font=F(36)) / S
    if v.get("info"):
        title(img, v["info"], (W - 70, H / 2 + 4), 50, anchor="rm", fill=th["accent"], stroke=5, max_w=600)
    return finish(img, W, H)


def t_banniere_x(v, skins, frame, W=1500, H=500):
    img = background(v["theme"], W, H, frame)
    skin(img, skins[0], (1080, 20, 1480, 520), label=False)
    title(img, v["pseudo"].upper(), (560, 200), 130, stroke=9, max_w=900)
    title(img, v.get("slogan") or "CUPS • RANKED • FORTNITE", (560, 340), 48, fill=_acc(v), stroke=5, max_w=900)
    return finish(img, W, H)


# ------------------------------------------------------------------ catalogue
def _f(key, label, kind="text", default="", options=None):
    return {"key": key, "label": label, "type": kind, "default": default, **({"options": options} if options else {})}


COMMON = [_f("pseudo", "Pseudo", default="Camra"),
          _f("theme", "Couleurs", "select", "cup", list(THEMES))]
TEMPLATES = {
    "cup_leaderboard": {"label": "Cup — Classement", "format": "Miniature", "size": (1280, 720), "fn": t_cup_leaderboard, "skins": 1,
                        "fields": [_f("cup", "Titre", default="SOLO CASH CUP"), _f("place", "Ta place", "number", 1),
                                   _f("points", "Tes points", "number", 0), _f("top", "Top %", default="Top 1%")]},
    "cup_mystere": {"label": "Cup — Mystère (#?)", "format": "Miniature", "size": (1280, 720), "fn": t_cup_mystere, "skins": 1,
                    "fields": [_f("cup", "Titre", default="SOLO CASH CUP"), _f("accroche", "Accroche", default="J'AI FINI COMBIEN ?")]},
    "cup_duo": {"label": "Cup — Duo", "format": "Miniature", "size": (1280, 720), "fn": t_cup_duo, "skins": 2,
                "fields": [_f("mate", "Pseudo du duo", default=""), _f("place", "Votre place", "number", 1),
                           _f("points", "Vos points", "number", 0)]},
    "gros_titre": {"label": "Gros titre + flèche", "format": "Miniature", "size": (1280, 720), "fn": t_gros_titre, "skins": 1,
                   "fields": [_f("mot1", "Mot 1 (blanc)", default="CUP"), _f("mot2", "Mot 2 (couleur)", default="SOLO"),
                              _f("petit", "Petit texte", default="")]},
    "ranked_grind": {"label": "Ranked — Grind", "format": "Miniature", "size": (1280, 720), "fn": t_ranked_grind, "skins": 1,
                     "fields": [_f("rang_depart", "Rang de départ", "select", "OR", RANK_NAMES),
                                _f("rang_actuel", "Rang actuel", "select", "DIAMANT", RANK_NAMES),
                                _f("objectif", "Objectif", "select", "UNREAL", RANK_NAMES),
                                _f("progression", "Progression (%)", "number", 40), _f("gain", "ELO gagné", default="+65%"),
                                _f("periode", "Période", default="aujourd'hui"), _f("jour", "Jour du grind", "number", "")]},
    "ranked_avant_apres": {"label": "Ranked — Avant / Après", "format": "Miniature", "size": (1280, 720), "fn": t_ranked_avant_apres,
                           "skins": 1,
                           "fields": [_f("rang_depart", "Rang de départ", "select", "OR", RANK_NAMES),
                                      _f("objectif", "Rang atteint", "select", "UNREAL", RANK_NAMES),
                                      _f("accroche", "Titre", default=""), _f("duree", "En combien de temps", default="EN 24H")]},
    "banniere_chaine": {"label": "Bannière de chaîne YouTube", "format": "Bannière 2560x1440", "size": (2560, 1440),
                        "fn": t_banniere_chaine, "skins": 1,
                        "fields": [_f("slogan", "Slogan", default="CUPS • RANKED • FORTNITE"), _f("planning", "Planning", default="")]},
    "ecran_fin": {"label": "Écran de fin YouTube", "format": "Écran de fin 1920x1080", "size": (1920, 1080), "fn": t_ecran_fin,
                  "skins": 1, "fields": [_f("texte", "Texte", default="LA SUITE ICI")]},
    "bandeau_stream": {"label": "Bandeau de stream (bas d'écran)", "format": "Bandeau 1920x140 (transparent)", "size": (1920, 140),
                       "fn": t_bandeau_stream, "skins": 0,
                       "fields": [_f("reseau1", "Réseau 1", default="TikTok @camra"), _f("reseau2", "Réseau 2", default="YouTube Camra"),
                                  _f("info", "Info à droite", default="CUP EN COURS")]},
    "banniere_x": {"label": "Bannière X / Twitter", "format": "Bannière X 1500x500", "size": (1500, 500), "fn": t_banniere_x,
                   "skins": 1, "fields": [_f("slogan", "Slogan", default="CUPS • RANKED • FORTNITE")]},
}


def catalog(defaults=None):
    defaults = defaults or {}
    out = []
    for tid, t in TEMPLATES.items():
        fields = []
        for f in COMMON + t["fields"]:
            f = dict(f)
            if defaults.get(f["key"]) not in (None, ""):
                f["default"] = defaults[f["key"]]
            fields.append(f)
        out.append({"id": tid, "label": t["label"], "format": t["format"], "size": t["size"], "skins": t["skins"],
                    "fields": fields, "png": tid == "bandeau_stream"})
    return out


def project_defaults(timeline, plan, saved=None):
    """Valeurs préremplies : pseudo/réseaux enregistrés + données du rec analysé (points, rangs, ELO)."""
    d = {k: v for k, v in (saved or {}).items() if v not in (None, "")}
    if not timeline:
        return d
    games = timeline.get("games") or []
    if timeline.get("mode") == "cup" or (plan or {}).get("mode") == "cup":
        d["points"] = timeline.get("final_points") or ((plan or {}).get("final") or {}).get("points") or ""
        d.setdefault("theme", "cup")
    else:
        d["theme"] = "ranked"
        rb = next((g.get("rank_before") for g in games if g.get("rank_before")), None)
        ra = next((g.get("rank_after") for g in reversed(games) if g.get("rank_after")), None)
        if rb and rb.get("name"):
            d["rang_depart"] = RANK_NAMES[rank_index(rb["name"])]
        if ra and ra.get("name"):
            d["rang_actuel"] = RANK_NAMES[rank_index(ra["name"])]
            d["objectif"] = RANK_NAMES[min(7, rank_index(ra["name"]) + 1)]
            if ra.get("pct") is not None:
                d["progression"] = ra["pct"]
        if any(g.get("gain") is not None for g in games):
            gain = sum(g.get("gain") or 0 for g in games)
            d["gain"] = f"{'+' if gain >= 0 else ''}{gain}%"
    return d


def render(tid, values, skins=None, frame=None):
    t = TEMPLATES[tid]
    v = {f["key"]: f["default"] for f in COMMON + t["fields"]}
    v.update({k: val for k, val in (values or {}).items() if val is not None})
    if v.get("theme") not in THEMES:
        v["theme"] = "cup"
    skins = [s for s in (skins or []) if s] + [None, None]
    return t["fn"](v, skins, frame)


def save(img, path):
    path = Path(path)
    if path.suffix.lower() == ".png":
        img.save(path)
        return path
    img = img.convert("RGB")
    q = 92
    while True:                                  # miniatures YouTube : moins de 2 Mo
        img.save(path, "JPEG", quality=q, optimize=True, progressive=True)
        if path.stat().st_size < 1_900_000 or q <= 60:
            return path
        q -= 6


# ------------------------------------------------------------------ skins
ISNET_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx"


def isnet_model():
    """Modèle de détourage (IS-Net, licence Apache 2.0) : livré avec l'app, sinon téléchargé une fois."""
    try:
        from common import BUNDLE_DIR
    except Exception:
        BUNDLE_DIR = ASSET_DIR
    for d in (BUNDLE_DIR / "rembg_models", ASSET_DIR / "rembg_models", DATA_DIR / "rembg_models"):
        if (d / "isnet-general-use.onnx").exists():
            return d / "isnet-general-use.onnx"
    dst = DATA_DIR / "rembg_models" / "isnet-general-use.onnx"
    dst.parent.mkdir(parents=True, exist_ok=True)
    import urllib.request
    tmp = dst.with_suffix(".part")
    with urllib.request.urlopen(urllib.request.Request(ISNET_URL, headers={"User-Agent": "MontageStudio"}), timeout=60) as r, \
            open(tmp, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    tmp.replace(dst)
    return dst


_SESS = {}


def cutout(image, out_path=None):
    """Retire le fond d'une image (skin capturé dans un rec) avec le modèle IS-Net (onnxruntime, sur le CPU)."""
    import numpy as np
    import onnxruntime as ort
    if "s" not in _SESS:
        _SESS["s"] = ort.InferenceSession(str(isnet_model()), providers=["CPUExecutionProvider"])
    sess = _SESS["s"]
    img = image.convert("RGB")
    x = np.asarray(img.resize((1024, 1024), Image.LANCZOS)).astype(np.float32)
    x = x / max(float(x.max()), 1e-6) - 0.5
    out = sess.run(None, {sess.get_inputs()[0].name: x.transpose(2, 0, 1)[None]})[0][0, 0]
    pred = (out - out.min()) / max(float(out.max() - out.min()), 1e-6)
    mask = Image.fromarray((pred * 255).astype("uint8")).resize(img.size, Image.LANCZOS)
    # nettoyage : supprime le bruit, bords nets mais doux
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.2))
    mask = mask.point(lambda v: 0 if v < 40 else 255 if v > 215 else int((v - 40) * 255 / 175))
    res = img.convert("RGBA")
    res.putalpha(mask)
    bb = mask.point(lambda v: 255 if v > 128 else 0).getbbox()
    if bb:
        res = res.crop(bb)
    SKIN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(out_path or SKIN_DIR / f"skin_{time.strftime('%Y%m%d_%H%M%S')}.png")
    res.save(out_path)
    return out_path


def skins_list():
    SKIN_DIR.mkdir(parents=True, exist_ok=True)
    return sorted((p for p in SKIN_DIR.iterdir() if p.suffix.lower() in (".png", ".webp")),
                  key=lambda p: p.stat().st_mtime, reverse=True)


if __name__ == "__main__":
    out = Path("apercu_bannieres")
    out.mkdir(exist_ok=True)
    for tid in TEMPLATES:
        save(render(tid, {"points": 351, "mate": "Kuzz", "jour": 12}), out / f"{tid}.{'png' if tid == 'bandeau_stream' else 'jpg'}")
        print("ok", tid)

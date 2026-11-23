"""Outils partagés du pipeline de montage Fortnite (config, ffmpeg, OCR)."""
import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "Montage Studio"
APP_VERSION = "1.0.0"
FROZEN = getattr(sys, "frozen", False)
# fichiers livrés avec l'installation (lecture seule) : modèles OCR, FFmpeg, moteur PyTorch...
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
# fichiers légers de l'app (interface, polices, musiques) : ceux de la mise à jour active s'il y en a une
ASSET_DIR = Path(os.environ["MONTAGE_ASSETS"]) if os.environ.get("MONTAGE_ASSETS") and \
    Path(os.environ["MONTAGE_ASSETS"]).exists() else BUNDLE_DIR
HERE = ASSET_DIR
# données de l'utilisateur (réglages, scans, cache) : dans %LOCALAPPDATA% pour l'exe installé
DATA_DIR = (Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "MontageStudio") if FROZEN \
    else Path(__file__).resolve().parent
DATA_DIR.mkdir(parents=True, exist_ok=True)
WORK_ROOT = DATA_DIR / "work"
CONFIG_PATH = DATA_DIR / "config.json"

# Zones de l'écran, coordonnées NORMALISÉES (0-1) -> marche quelle que soit la résolution du rec
ROI_NAMES = {
    "hud":      "Colonne a gauche de la minimap : kills / joueurs restants / timer (chiffres seulement, sans les icones)",
    "lobby":    "Panneau du tournoi dans le salon ('Partie X sur Y', 'NN pts')",
    "spectate": "[OPTIONNEL] Bandeau 'MODE SPECTATEUR' en haut au centre (Echap = passer)",
    "top":      "[OPTIONNEL] Encart 'ATTEINDRE LE TOP X / +N POINTS' a gauche (Echap = passer)",
}


def px_roi(x, y, w, h, W=1920, H=1080):
    return [x / W, y / H, w / W, h / H]


DEFAULT_CONFIG = {
    "video": "rec_cup.mp4",
    "work_dir": "work",
    "rois": {
        "hud": px_roi(1585, 25, 67, 165),
        "lobby": px_roi(30, 240, 580, 520),
        "spectate": px_roi(760, 0, 400, 110),
        "top": px_roi(40, 495, 380, 85),
        "score": px_roi(0, 0, 1920, 170),     # bandeau du haut : score des manches (box fight / 1v1)
    },
    "scan": {
        "mode": "keyframes",          # "keyframes" = ne décode que les images clés (ultra rapide) | "fps"
        "fps": 1,
        "max_keyframe_interval_s": 5.0,
        "white_threshold": 190,
        "analysis_width": 1920,
        "analysis_height": 1080,
        "min_conf": 0.30,
        "upscale_numbers": 3.0,
        "upscale_text": 1.5,
        "spectate_keywords": ["spectat"],
        "rank_lobby_every": 2,        # ranked : OCR plein écran 1 image de salon sur N
        "hud_row_threshold": 170,
        "hud_bin_threshold": 190,
        "min_lobby_s": 20,            # ranked : un rang ne compte que s'il est lu dans un vrai salon (>= 20 s sans HUD)
        "merge_gap_s": 45,            # deux morceaux à moins de 45 s sans salon entre eux = même game
        "split_gap_s": 240,           # aucune lecture HUD pendant X s (sans salon lu) => nouvelle game
        "new_game_jump": 30,          # joueurs restants qui remontent de +30 (confirmé) => nouvelle game
        "min_game_s": 45,
        "min_game_reads": 5,
        "kill_confirm": 2,
        "max_kill_jump": 4,
    },
    "library_dirs": [],                   # dossiers de recs (vide = dossier Vidéos de Windows)
    "ui": {
        "mac_window": True,           # fenêtre façon macOS (boutons rouge/orange/vert) ; False = cadre Windows
    },
    "banner": {                       # studio de bannières : valeurs retenues d'une fois sur l'autre
        "pseudo": "", "mate": "", "reseau1": "", "reseau2": "", "slogan": "", "cup": "",
    },
    "edit": {
        "bus_skip_s": 30,             # coupe le bus au début de chaque game (HUD visible dès le bus)
        "end_tail_s": 6,
        "dead_gap_s": 420,            # > 7 min sans kill ni palier de top => on coupe le creux (0 = jamais)
        "dead_keep_after_s": 30,      # ...en gardant 30 s après le dernier événement
        "dead_keep_before_s": 90,     # ...et 90 s avant le suivant (approche du fight)
        "dead_protect_end_s": 240,    # jamais de coupe dans les 4 dernières minutes d'une game
        "dead_min_cut_s": 90,         # une coupe de moins de 90 s ne vaut pas la cassure
        # paliers de top (si l'encart 'ATTEINDRE LE TOP X' n'est pas lu) : joueurs restants franchis
        "top_players_fractions": [0.5, 0.3, 0.2, 0.1, 0.04],
        "final_spectate_keep_s": 5,   # spectate de fin de game (équipe éliminée) : on garde X s puis coupe
        "cup_games": 10,              # nombre de parties de la cup si non lu dans le salon
    },
    "render": {
        "width": 3840,                # 4K (2160p) : YouTube donne bien plus de débit aux uploads 4K
        "height": 2160,
        "fps": 60,
        "preset": "p5",
        "cq": 23,
        "bitrate": "45M",             # ~45 Mb/s : recommandation YouTube pour de la 4K60
        "maxrate": "60M",
        "parallel_encodes": 2,        # encodages simultanés (1 par puce NVENC : 2 sur une 5070 Ti)
        "audio_stream": 0,            # piste audio OBS à garder (0 = la première)
        "card_duration_s": 4.0,
        "font": "C:/Windows/Fonts/arialbd.ttf",
        "intro": "intro.mp3",
        "outro": "outro.mp3",
        "intro_s": 24,
        "outro_s": 15,
        "music_volume": 0.55,         # volume quand il n'y a PAS de son d'origine (cartons, silences)
        "music_tail_s": 14,           # la musique d'un carton déborde de X s sur le début de la game
        "endgame_music": True,        # Cup : musique stressante sur la fin de chaque partie (musiques/fin_de_zone)
        "endgame_music_s": 120,       # durée de cette musique avant la fin de la partie
        "endgame_volume": 0.35,       # son volume (plus bas que les cartons)
        "endgame_duck_db": 9,         # baisse max sous ta voix / les tirs (plus doux : le combat est permanent)
        "live_counter": True,         # compteur en haut de l'écran pendant les games (partie, kills, points)
        "shorts_count": 3,            # nombre de Shorts TikTok créés par rec
        "shorts_layout": "cadre",     # "cadre" (gameplay agrandi + fond flouté) ou "plein" (plein écran, bords coupés)
        "shorts_captions": True,      # sous-titres animés de ta voix sur les Shorts
        "shorts_voice": True,         # Shorts : tes réactions au son (voix qui monte) comptent comme moments forts
        "voice_track": -1,            # piste audio de ton micro (0 = 1re piste...) ; -1 = la piste du montage
        "subtitles_srt": False,       # fichier .srt de sous-titres à côté du montage (à envoyer sur YouTube)
        "whisper_model": "small",     # modèle de transcription : base (rapide) / small (conseillé) / medium (précis)
        "music_fade_s": 6,
        "duck_threshold_db": -45,     # au-dessus de ce niveau de son d'origine, la musique baisse
        "duck_slope": 1.0,            # dB de baisse par dB de son au-dessus du seuil
        "duck_max_db": 20,            # baisse max (20 dB = musique ~10x moins forte sous ta voix/le jeu)
        "duck_release_ms": 700,       # vitesse de remontée quand ça redevient calme
        "intro_fade_s": 4,
        "outro_fade_in_s": 1.5,
        "output": "montage.mp4",
        "final_card": True,
    },
}


MODES = {
    "cup": {
        "label": "Cup",
        "edit": {"bus_skip_s": 30},
    },
    "ranked_reload": {
        "label": "Ranked Reload",
        "rois": {"lobby": None, "top": None},
        "edit": {"bus_skip_s": 20},
    },
    "ranked_br": {
        "label": "Ranked Battle Royale",
        "rois": {"lobby": None, "top": None},
        "edit": {"bus_skip_s": 30},
    },
    "box_arena": {
        "label": "Arène Box Fight",
        "kind": "box", "rank": True,
        "rois": {"lobby": None, "top": None, "spectate": None},
        "edit": {"bus_skip_s": 0, "dead_gap_s": 120, "dead_keep_after_s": 8, "dead_keep_before_s": 15,
                 "end_tail_s": 3},
    },
    "creative_1v1": {
        "label": "Créatif 1v1",
        "kind": "box", "rank": False,
        "rois": {"lobby": None, "top": None, "spectate": None},
        "edit": {"bus_skip_s": 0, "dead_gap_s": 120, "dead_keep_after_s": 8, "dead_keep_before_s": 15,
                 "end_tail_s": 3},
    },
}
MODE_META_KEYS = ("label", "kind", "rank")
VIDEO_EXT = (".mp4", ".mkv", ".mov")
RAW_DIR_NAME = "Vidéos brutes"        # les recs d'origine y sont rangés une fois montés


def make_cfg(mode, video):
    """Config complète pour UNE vidéo dans UN mode (dossier de travail séparé par vidéo)."""
    import re
    cfg = load_config()
    _merge(cfg, copy.deepcopy({k: v for k, v in MODES[mode].items() if k not in MODE_META_KEYS}))
    cfg["rois"] = {k: v for k, v in cfg["rois"].items() if v}
    video = Path(video).resolve()
    stem = re.sub(r"[^\w\- ]", "_", video.stem)
    cfg["mode"], cfg["mode_label"] = mode, MODES[mode]["label"]
    cfg["mode_kind"] = MODES[mode].get("kind", "br")
    cfg["mode_rank"] = MODES[mode].get("rank", mode.startswith("ranked"))
    cfg["video"] = str(video)
    cfg["work_dir"] = str(WORK_ROOT / f"{stem} [{mode}]")
    res = "4K" if cfg["render"]["height"] >= 2160 else f"{cfg['render']['height']}p"
    out_dir = video.parent.parent if video.parent.name == RAW_DIR_NAME else video.parent
    cfg["render"]["output"] = str(out_dir / f"[PRÉ-UPLOAD] {video.stem} - {MODES[mode]['label']} {res}.mp4")
    for k in ("intro", "outro"):
        cfg["render"][k] = str(resolve(cfg, cfg["render"][k]))
    return cfg


def _merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["_cfg_v"] = 2
    if CONFIG_PATH.exists():
        user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        user.pop("video", None)
        user.get("render", {}).pop("output", None)
        if user.get("_cfg_v", 0) < 2:   # anciens réglages de coupe trop agressifs -> nouveaux
            ed = user.get("edit", {})
            for k, old in (("dead_gap_s", 300), ("dead_keep_after_s", 20), ("dead_keep_before_s", 60)):
                if ed.get(k) == old:
                    ed.pop(k)
            user["_cfg_v"] = 2
        _merge(cfg, user)
    else:
        save_config(cfg)
    return cfg


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def resolve(cfg, key_path):
    p = Path(key_path)
    return p if p.is_absolute() else ASSET_DIR / p


def work_dir(cfg):
    d = resolve(cfg, cfg["work_dir"])
    d.mkdir(parents=True, exist_ok=True)
    return d


def video_path(cfg):
    v = resolve(cfg, cfg["video"])
    if not v.exists():
        sys.exit(f"[ERREUR] Vidéo introuvable : {v}")
    return v


_NEED = {}


def need(binary):
    """FFmpeg livré avec l'app (dossier ffmpeg/ à côté de l'exe), sinon celui du PATH."""
    if binary in _NEED:
        return _NEED[binary]
    exe = binary + (".exe" if os.name == "nt" else "")
    for d in (BUNDLE_DIR / "ffmpeg", Path(sys.executable).parent / "ffmpeg", Path(sys.executable).parent):
        if (d / exe).exists():
            _NEED[binary] = str(d / exe)
            return _NEED[binary]
    path = shutil.which(binary)
    if not path:
        sys.exit(f"[ERREUR] {binary} introuvable (ni livré avec l'app, ni dans le PATH)")
    _NEED[binary] = path
    return path


_ENCODER = None


def detect_encoder():
    """Encodeur matériel dispo : NVIDIA (nvenc) > AMD (amf) > Intel (qsv) > processeur (x264)."""
    global _ENCODER
    if os.environ.get("MONTAGE_CPU") == "1":
        return "x264"
    if _ENCODER:
        return _ENCODER
    cache = DATA_DIR / "encoder.json"
    ff = need("ffmpeg")
    try:
        c = json.loads(cache.read_text(encoding="utf-8"))
        if c.get("ffmpeg") == ff:
            _ENCODER = c["encoder"]
            return _ENCODER
    except (OSError, ValueError, KeyError):
        pass
    _ENCODER = "x264"
    for kind, codec, extra in (("nvenc", "h264_nvenc", []), ("amf", "h264_amf", []),
                               ("qsv", "h264_qsv", ["-pix_fmt", "nv12"])):
        r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            "color=c=black:s=640x360:d=0.2", *extra, "-c:v", codec, "-f", "null", "-"],
                           capture_output=True)
        if r.returncode == 0:
            _ENCODER = kind
            break
    try:
        cache.write_text(json.dumps({"ffmpeg": ff, "encoder": _ENCODER}), encoding="utf-8")
    except OSError:
        pass
    return _ENCODER


def library_dirs(cfg=None):
    cfg = cfg or load_config()
    dirs = [Path(d) for d in cfg.get("library_dirs") or [] if Path(d).exists()]
    return dirs or [Path.home() / "Videos"]


def ffprobe_info(path):
    out = subprocess.run(
        [need("ffprobe"), "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height,r_frame_rate",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    info = {"duration": float(data["format"]["duration"]), "width": None, "height": None,
            "fps": None, "has_audio": False}
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and info["width"] is None:
            info["width"], info["height"] = s["width"], s["height"]
            num, den = s.get("r_frame_rate", "0/1").split("/")
            info["fps"] = float(num) / float(den) if float(den) else None
        if s.get("codec_type") == "audio":
            info["has_audio"] = True
    return info


def fmt_tc(t):
    t = max(0.0, float(t))
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def parse_tc(s):
    parts = [float(p) for p in str(s).split(":")]
    t = 0.0
    for p in parts:
        t = t * 60 + p
    return t


def crop(frame, roi):
    h, w = frame.shape[:2]
    x, y, rw, rh = roi
    x0, y0 = max(0, int(round(x * w))), max(0, int(round(y * h)))
    x1, y1 = min(w, int(round((x + rw) * w))), min(h, int(round((y + rh) * h)))
    return frame[y0:y1, x0:x1]


def cuda_usable(torch):
    """Vrai si PyTorch peut VRAIMENT calculer sur la carte. Les GTX 10xx (Pascal) et plus anciennes ne sont
    plus supportées par les builds CUDA 12.8 : on bascule alors l'OCR sur le processeur au lieu de planter."""
    try:
        if not torch.cuda.is_available():
            return False
        major, minor = torch.cuda.get_device_capability(0)
        archs = torch.cuda.get_arch_list()
        if archs and f"sm_{major}{minor}" not in archs and not any(
                a.startswith("compute_") and int(a[8:]) <= major * 10 + minor for a in archs):
            return False
        x = torch.ones(8, device="cuda")
        return float((x * 2).sum().item()) == 16.0
    except Exception:
        return False


class HudOCR:
    """EasyOCR sur GPU, avec pré-traitement adapté au HUD Fortnite (texte blanc détouré)."""

    def __init__(self, scan_cfg, gpu=True):
        import cv2  # noqa
        try:
            import torch
            import easyocr
        except ImportError:
            sys.exit("[ERREUR] easyocr / torch non installés (voir README.md)")
        if gpu:
            gpu = cuda_usable(torch)
        print(f"[OCR] GPU : {torch.cuda.get_device_name(0)}" if gpu else
              "[OCR] processeur (carte graphique non compatible avec PyTorch : scan plus lent, rendu inchangé)")
        models = BUNDLE_DIR / "ocr_models"
        if not (models / "craft_mlt_25k.pth").exists():
            models = DATA_DIR / "ocr_models"       # téléchargés au 1er lancement
            models.mkdir(parents=True, exist_ok=True)
        self.reader = easyocr.Reader(["en", "fr"], gpu=gpu, verbose=False,
                                     model_storage_directory=str(models), user_network_directory=str(models))
        self.sc = scan_cfg
        self.cache = {}
        self.calls = 0
        self.hits = 0

    def _mask_key(self, img, tag):
        """Signature du texte blanc de la zone : même forme de chiffres => même résultat, sans OCR."""
        import cv2
        import numpy as np
        m = (img.min(axis=2) >= self.sc["white_threshold"]).astype(np.uint8)
        if m.mean() < 0.004:
            return tag, None                  # quasi aucun pixel blanc => rien d'affiché
        m = cv2.resize(m, (48, 16), interpolation=cv2.INTER_AREA) > 0
        return tag, np.packbits(m).tobytes()

    def cached(self, img, tag, fn):
        key = self._mask_key(img, tag)
        if key[1] is None:
            return None if tag != "text" else ""
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
        self.calls += 1
        val = fn(img)
        if len(self.cache) > 20000:
            self.cache.clear()
        self.cache[key] = val
        return val

    def number(self, img):
        return self.cached(img, "num", self.read_number)

    def text(self, img):
        return self.cached(img, "text", self.read_text)

    def _prep(self, img, scale):
        import cv2
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if scale != 1:
            g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        return g

    def read_number(self, img):
        if img.size == 0:
            return None
        res = self.reader.readtext(self._prep(img, self.sc["upscale_numbers"]),
                                   allowlist="0123456789", detail=1, paragraph=False)
        res = [r for r in res if r[2] >= self.sc["min_conf"]]
        if not res:
            return None
        res.sort(key=lambda r: r[0][0][0])  # gauche -> droite
        digits = "".join(c for r in res for c in r[1] if c.isdigit())
        if not digits or len(digits) > 4:
            return None
        return int(digits)

    def _hud_rows(self, c):
        """Découpe la colonne en lignes de texte blanc (projection horizontale)."""
        import numpy as np
        mn = c.min(axis=2)
        sat = c.max(axis=2).astype(int) - mn
        m = (mn >= self.sc["hud_row_threshold"]) & (sat < 60)
        proj = m.sum(axis=1) >= 2
        runs, y, H = [], 0, c.shape[0]
        while y < H:
            if proj[y]:
                y0 = y
                while y < H and proj[y]:
                    y += 1
                if runs and y0 - runs[-1][1] <= 2:
                    runs[-1][1] = y
                else:
                    runs.append([y0, y])
            y += 1
        rows, W = [], c.shape[1]
        for y0, y1 in runs:
            if not 8 <= y1 - y0 <= 24:
                continue
            cols = np.where(m[y0:y1].sum(axis=0) > 0)[0]
            # chiffres alignés à droite contre les icônes
            if len(cols) and cols[-1] + 1 >= 0.78 * W and m[y0:y1].sum() >= 20:
                rows.append((y0, y1, int(cols[0]), int(cols[-1]) + 1))
        return rows

    def _read_row(self, c, row):
        import cv2
        import numpy as np
        y0, y1, x0, x1 = row
        p, up = 3, 2
        sub = c[max(0, y0 - p):y1 + p, max(0, x0 - p):x1 + p]
        b = np.where(sub.min(axis=2) >= self.sc["hud_bin_threshold"], 0, 255).astype(np.uint8)
        b = cv2.resize(b, None, fx=up, fy=up, interpolation=cv2.INTER_NEAREST)
        b = cv2.copyMakeBorder(b, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=255)
        r = self.reader.recognize(b, allowlist="0123456789:", detail=1)
        if not r or r[0][2] < self.sc["min_conf"]:
            return None
        return r[0][1].strip()

    def read_hud_column(self, img):
        """Colonne kills / (ligne équipe) / joueurs restants / timer.
        Lignes repérées par position : timer = dernière, joueurs = avant-dernière, kills = première."""
        if img.size == 0:
            return None, None
        rows = self._hud_rows(img)
        if len(rows) < 2:
            return None, None
        texts = [self._read_row(img, r) for r in rows]
        timer = texts[-1] or ""
        digits = timer.replace(":", "")
        if not (digits.isdigit() and 3 <= len(digits) <= 4):
            return None, None
        def num(t, hi):
            if not t or not t.isdigit() or len(t) > 3:
                return None
            v = int(t)
            return v if v <= hi else None
        players = num(texts[-2], 100)
        if players == 0:
            players = None
        kills = num(texts[0], 60) if len(rows) >= 3 else None
        return players, kills

    def read_text(self, img):
        if img.size == 0:
            return ""
        res = self.reader.readtext(self._prep(img, self.sc["upscale_text"]), detail=1, paragraph=False)
        return " ".join(r[1] for r in res if r[2] >= self.sc["min_conf"]).lower()

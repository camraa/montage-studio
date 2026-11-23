"""Mode direct : ton rang lu à l'écran pendant que tu joues (comme pour les recs, sans compte Epic).

- toutes les 4 s : capture de l'écran (sans rien installer : PIL.ImageGrab) ;
  en game (HUD visible) -> rien de lourd ; au salon -> lecture du rang + % (OCR sur la carte graphique)
- un rang n'est retenu que s'il est lu 2 fois de suite et qu'il est cohérent avec le précédent
- met à jour la Progression (session « Mode direct » du jour) et le widget du live :
  http://127.0.0.1:8765/live/widget (source navigateur / lien) et <données>/live/rang.png
"""
import json
import subprocess
import sys
import threading
import time
from datetime import date

from common import DATA_DIR, MODES, crop, load_config

LIVE_DIR = DATA_DIR / "live"
INTERVAL = 4.0
GAME_EXE = "FortniteClient-Win64-Shipping.exe"
_NOWIN = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

STATE = {"running": False, "mode": None, "status": "arrêté", "rank_start": None, "rank": None, "gain": None,
         "games": 0, "since": None, "updated": None, "error": None, "last_read": None}
_lock = threading.Lock()
_thread = {"t": None, "stop": None}


def _score(r):
    if not r or r.get("level") is None or r.get("pct") is None or r["level"] >= 17:
        return None
    return r["level"] * 100 + r["pct"]


def _rank(level, pct):
    from scan import rank_name
    return {"level": level, "pct": pct, "name": rank_name(level)}


def fortnite_running():
    if sys.platform != "win32":
        return True
    try:
        r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {GAME_EXE}", "/NH"], capture_output=True,
                           text=True, timeout=5, **_NOWIN)
        return GAME_EXE.lower() in r.stdout.lower()
    except Exception:
        return True


def grab(w=1920, h=1080):
    """Écran principal en BGR (comme les images du scan)."""
    import cv2
    import numpy as np
    from PIL import ImageGrab
    img = np.asarray(ImageGrab.grab().convert("RGB"))[:, :, ::-1]
    if img.shape[1] != w or img.shape[0] != h:
        img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(img)


def _set(**kw):
    with _lock:
        STATE.update(kw)
        STATE["updated"] = time.time()


def state():
    with _lock:
        return dict(STATE)


class Tracker:
    """Logique pure (testable sans écran) : lectures -> rang retenu, games, gain."""

    def __init__(self):
        self.pending, self.confirm = None, []
        self.game_since, self.lobby_n = None, 0

    def feed(self, in_game, rk, now=None):
        """in_game : HUD visible ; rk : [niveau, %] lu au salon (ou None). Retourne le rang retenu s'il change."""
        now = time.time() if now is None else now
        if in_game:
            if self.game_since is None:
                self.game_since = now
            self.lobby_n = 0
            self.pending = None
            _set(status="en game")
            return None
        self.lobby_n += 1
        if self.game_since is not None and self.lobby_n >= 2:     # vraie fin de game (pas la carte ouverte)
            if now - self.game_since >= 30:
                _set(games=STATE["games"] + 1)
            self.game_since = None
        if self.lobby_n < 2:
            return None
        _set(status="au salon")
        if not rk:
            return None
        rk = tuple(rk)
        if rk != self.pending:                     # 2 lectures identiques d'affilée
            self.pending = rk
            return None
        new = _rank(*rk)
        cur = STATE["rank"]
        if cur and _score(cur) is not None and _score(new) is not None and abs(_score(new) - _score(cur)) > 250:
            self.confirm.append(rk)                # gros saut : il faut 3 confirmations
            if len(self.confirm) < 3 or len(set(self.confirm[-3:])) != 1:
                return None
        self.confirm = []
        if cur and cur.get("level") == new["level"] and cur.get("pct") == new["pct"]:
            return None
        start = STATE["rank_start"] or new
        gain = (_score(new) - _score(start)) if _score(new) is not None and _score(start) is not None else None
        _set(rank=new, rank_start=start, gain=gain)
        return new


def record_progress(mode):
    """Session « Mode direct » du jour dans la Progression."""
    import progress
    st = state()
    if not st["rank"]:
        return
    s = {"id": f"direct {date.today().isoformat()} [{mode}]", "rec": "Mode direct", "date": date.today().isoformat(),
         "mode": mode, "label": MODES[mode]["label"], "kind": "ranked", "games": st["games"], "kills": 0,
         "rank_start": st["rank_start"], "rank_end": st["rank"], "gain": st["gain"], "live": True,
         "updated": int(time.time())}
    progress.upsert(s)


def widget_png():
    """Image du widget (pour une source « Image » qui se recharge)."""
    from PIL import Image, ImageDraw, ImageFont
    from common import ASSET_DIR
    st = state()
    W, H = 520, 120
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, W - 1, H - 1), 22, fill=(16, 16, 20, 215), outline=(255, 255, 255, 40), width=2)
    fonts = sorted((ASSET_DIR / "polices").glob("*.ttf")) if (ASSET_DIR / "polices").exists() else []
    big = next((f for f in fonts if "luckiest" in f.name.lower()), fonts[0] if fonts else None)

    def font(sz):
        try:
            return ImageFont.truetype(str(big), sz) if big else ImageFont.load_default()
        except OSError:
            return ImageFont.load_default()
    r = st["rank"]
    name = r["name"] if r else "EN ATTENTE"
    d.text((26, 18), name, font=font(40), fill=(255, 255, 255, 255))
    pct = r.get("pct") if r else None
    if pct is not None:
        d.rounded_rectangle((26, 78, 26 + 330, 96), 9, fill=(255, 255, 255, 45))
        d.rounded_rectangle((26, 78, 26 + max(18, int(330 * pct / 100)), 96), 9, fill=(255, 196, 0, 255))
        d.text((370, 70), f"{pct}%", font=font(28), fill=(255, 255, 255, 255))
    g = st["gain"]
    if g is not None:
        col = (60, 220, 120, 255) if g >= 0 else (255, 80, 80, 255)
        txt = f"{'+' if g >= 0 else '-'}{abs(g)}%"
        tw = d.textlength(txt, font=font(34))
        d.text((W - 26 - tw, 20), txt, font=font(34), fill=col)
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = LIVE_DIR / "rang.tmp.png"
    im.save(tmp)
    tmp.replace(LIVE_DIR / "rang.png")


def _loop(mode, stop):
    try:
        from common import HudOCR
        from scan import parse_rank
        cfg = load_config()
        rois = cfg["rois"]
        _set(status="chargement de la lecture d'écran…")
        ocr = HudOCR(cfg["scan"])
        tr = Tracker()
        widget_png()
        last_check, running = 0.0, True
        while not stop.is_set():
            t0 = time.time()
            if t0 - last_check > 15:
                running, last_check = fortnite_running(), t0
            if not running:
                _set(status="en attente de Fortnite")
                stop.wait(5)
                continue
            frame = grab()
            players, _ = ocr.read_hud_column(crop(frame, rois["hud"]))
            rk = None
            if players is None:
                rk = parse_rank(ocr.reader.readtext(frame, detail=1, paragraph=False), frame.shape[1])
                _set(last_read=rk)
            if tr.feed(players is not None, rk):
                print(f"[DIRECT] rang : {STATE['rank']['name']} {STATE['rank'].get('pct')}%", flush=True)
                record_progress(mode)
                widget_png()
            stop.wait(max(0.5, INTERVAL - (time.time() - t0)))
    except Exception as e:
        _set(error=f"{type(e).__name__}: {e}")
    finally:
        _set(running=False, status="arrêté")


def start(mode):
    if mode not in MODES or not MODES[mode].get("rank", mode.startswith("ranked")):
        raise ValueError("choisis un mode classé (Ranked BR, Ranked Reload, Arène Box Fight)")
    stop_()
    ev = threading.Event()
    with _lock:
        STATE.update(running=True, mode=mode, status="démarrage…", rank_start=None, rank=None, gain=None,
                     games=0, since=time.time(), error=None, last_read=None)
    t = threading.Thread(target=_loop, args=(mode, ev), daemon=True, name="mode-direct")
    _thread.update(t=t, stop=ev)
    t.start()
    return state()


def stop_():
    ev, t = _thread.get("stop"), _thread.get("t")
    if ev:
        ev.set()
    if t and t.is_alive():
        t.join(timeout=8)
    _thread.update(t=None, stop=None)
    return state()


WIDGET_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Rang</title>
<style>
html,body{margin:0;background:transparent;font-family:'Luckiest Guy',Inter,system-ui,sans-serif;color:#fff}
@font-face{font-family:'Luckiest Guy';src:url('/live/font.ttf')}
.w{display:inline-flex;flex-direction:column;gap:8px;padding:14px 20px;border-radius:20px;background:rgba(16,16,20,.84);
 border:2px solid rgba(255,255,255,.15);min-width:340px}
.top{display:flex;justify-content:space-between;align-items:baseline;gap:18px}
.n{font-size:34px;letter-spacing:.5px}.g{font-size:28px}.up{color:#3cdc78}.down{color:#ff5050}
.bar{position:relative;height:16px;border-radius:8px;background:rgba(255,255,255,.18);overflow:hidden}
.bar i{position:absolute;inset:0 auto 0 0;background:#ffc400;border-radius:8px;transition:width .8s}
.p{font-size:20px;opacity:.9}
</style></head><body><div class="w" id="w"><div class="top"><span class="n" id="n">…</span><span class="g" id="g"></span></div>
<div class="bar"><i id="b" style="width:0"></i></div><span class="p" id="p"></span></div>
<script>
async function tick(){try{const s=await (await fetch('/api/live')).json();const r=s.rank;
document.getElementById('n').textContent=r?r.name:'EN ATTENTE';
document.getElementById('b').style.width=(r&&r.pct!=null?r.pct:0)+'%';
document.getElementById('p').textContent=r&&r.pct!=null?r.pct+'% • '+(s.games||0)+' game'+(s.games>1?'s':''):'';
const g=document.getElementById('g');g.textContent=s.gain==null?'':(s.gain>=0?'+':'−')+Math.abs(s.gain)+'%';
g.className='g '+(s.gain>=0?'up':'down');}catch(e){}}
tick();setInterval(tick,2000);
</script></body></html>"""

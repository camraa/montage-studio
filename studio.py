"""FN Montage Studio - interface de montage locale (s'ouvre dans le navigateur).

  python studio.py            -> http://127.0.0.1:8765
"""
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from common import (APP_VERSION, ASSET_DIR, CONFIG_PATH, DATA_DIR, DEFAULT_CONFIG, FROZEN, MODES, RAW_DIR_NAME,
                    VIDEO_EXT, WORK_ROOT, detect_encoder, ffprobe_info, library_dirs, load_config, make_cfg,
                    need, work_dir)

PORT = 8765
UI = ASSET_DIR / "studio"
CACHE = WORK_ROOT / "_studio"
CACHE.mkdir(parents=True, exist_ok=True)
STATE_P = CACHE / "state.json"
MUSIC_EXT = (".mp3", ".wav", ".ogg", ".m4a", ".flac")
LOCK = threading.Lock()


# ------------------------------------------------------------------ état / utilitaires
def state():
    try:
        return json.loads(STATE_P.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"modes": {}, "durations": {}}


def save_state(st):
    STATE_P.write_text(json.dumps(st, indent=1, ensure_ascii=False), encoding="utf-8")


def allowed(p):
    p = Path(p).resolve()
    roots = library_dirs() + [ASSET_DIR, DATA_DIR]
    return any(str(p).lower().startswith(str(r.resolve()).lower()) for r in roots)


def find_video(path):
    """Le rec a pu être rangé dans 'Vidéos brutes' après un rendu : on le retrouve par son nom."""
    p = Path(path)
    if p.exists():
        return p
    for d in [p.parent, p.parent.parent] + library_dirs():
        for cand in (d / p.name, d / RAW_DIR_NAME / p.name):
            if cand.exists():
                return cand
    return p


def safe_stem(stem):
    return re.sub(r"[^\w\- ]", "_", stem)


def existing_modes(stem):
    out = []
    for m in MODES:
        if (WORK_ROOT / f"{safe_stem(stem)} [{m}]" / "timeline.json").exists():
            out.append(m)
    return out


def duration(p, st):
    key = f"{p}|{p.stat().st_size}"
    if key not in st["durations"]:
        try:
            st["durations"][key] = ffprobe_info(p)["duration"]
        except Exception:
            st["durations"][key] = 0
    return st["durations"][key]


def library():
    st = state()
    vids = []
    seen = set()
    folders = [(d, False) for d in library_dirs()] + [(d / RAW_DIR_NAME, True) for d in library_dirs()]
    for folder, raw in folders:
        if not folder.exists():
            continue
        for p in sorted(folder.iterdir(), key=lambda x: -x.stat().st_mtime):
            if p.suffix.lower() not in VIDEO_EXT or p.name.startswith("[PRÉ-UPLOAD]") or p in seen:
                continue
            seen.add(p)
            mode = st["modes"].get(p.stem) or (existing_modes(p.stem) or ["ranked_reload"])[0]
            out_dir = p.parent.parent if raw else p.parent
            outs = [o.name for o in out_dir.glob(f"[[]PRÉ-UPLOAD[]] {p.stem} - *.mp4")]
            wd = WORK_ROOT / f"{safe_stem(p.stem)} [{mode}]"
            vids.append({
                "path": str(p), "name": p.name, "stem": p.stem, "size": p.stat().st_size,
                "duration": duration(p, st), "archived": raw, "mode": mode,
                "scanned": (wd / "timeline.json").exists(), "planned": (wd / "edit_plan.json").exists(),
                "outputs": outs, "proxy": (wd / "proxy.mp4").exists(),
            })
    save_state(st)
    return vids


def thumb_of(path):
    p = find_video(path)
    h = hashlib.md5(f"{p.name}{p.stat().st_size}".encode()).hexdigest()[:16]
    out = CACHE / f"{h}.jpg"
    if not out.exists():
        try:
            d = ffprobe_info(p)["duration"]
        except Exception:
            d = 60
        subprocess.run([need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{d * 0.3:.1f}",
                        "-i", str(p), "-frames:v", "1", "-vf", "scale=320:-2", "-q:v", "4", str(out)])
    return out


def project(path, mode):
    p = find_video(path)
    cfg = make_cfg(mode, p)
    wd = work_dir(cfg)
    res = {"path": str(p), "mode": mode, "label": cfg["mode_label"], "duration": duration(p, state()),
           "proxy": (wd / "proxy.mp4").exists(), "scanned": (wd / "timeline.json").exists()}
    try:
        inf = ffprobe_info(p)
        res["source"] = {"width": inf["width"], "height": inf["height"], "fps": round(inf["fps"])}
    except Exception:
        pass
    if not res["scanned"]:
        return res
    res["timeline"] = json.loads((wd / "timeline.json").read_text(encoding="utf-8"))
    if not (wd / "edit_plan.json").exists():
        import edit
        edit.build(cfg)
    res["plan"] = json.loads((wd / "edit_plan.json").read_text(encoding="utf-8"))
    return res


def frame_at(video, t, width=None):
    """Image du rec à l'instant t (pleine définition par défaut)."""
    from io import BytesIO
    from PIL import Image
    vf = ["-vf", f"scale={width}:-2"] if width else []
    raw = subprocess.run([need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, float(t)):.2f}",
                          "-i", str(video), "-frames:v", "1", *vf, "-f", "image2pipe", "-vcodec", "png", "-"],
                         capture_output=True).stdout
    return Image.open(BytesIO(raw)).convert("RGB") if raw else None


def banners_info(path=None, mode=None):
    import banners
    saved = load_config().get("banner", {})
    tl = plan = None
    if path and mode:
        try:
            pr = project(path, mode)
            tl, plan = pr.get("timeline"), pr.get("plan")
        except Exception:
            pass
    for d_ in (banners.SKIN_DIR, banners.RANK_DIR, banners.CUP_DIR):
        d_.mkdir(parents=True, exist_ok=True)
    import progress
    defaults = banners.project_defaults(tl, plan, saved, progress.summary(mode) if mode else None)
    return {"templates": banners.catalog(defaults), "themes": {k: v["label"] for k, v in banners.THEMES.items()},
            "skins": [{"name": p.name, "path": str(p), "url": furl(p, f"&v={p.stat().st_mtime:.0f}")} for p in banners.skins_list()],
            "skin_dir": str(banners.SKIN_DIR), "assets_dir": str(banners.USER_ASSETS)}


def progress_info():
    import progress
    ss = progress.sessions()
    return {"sessions": ss, "modes": {m: progress.summary(m) for m in dict.fromkeys(s["mode"] for s in ss)},
            "labels": {m: v["label"] for m, v in MODES.items()}}


def banner_image(d):
    import banners
    frame = None
    if d.get("bg") == "frame" and d.get("path"):
        frame = frame_at(find_video(d["path"]), d.get("t") or 0, 1920)
    return banners.render(d["id"], d.get("values") or {}, d.get("skins") or [], frame)


def furl(p, extra=""):
    return f"/file?path={quote(str(p))}{extra}"


def music_list():
    out = []
    for f in (ASSET_DIR / "intro.mp3", ASSET_DIR / "outro.mp3"):
        if f.exists():
            out.append({"name": f.name, "url": furl(f)})
    (DATA_DIR / "musiques").mkdir(exist_ok=True)
    for d in (ASSET_DIR / "musiques", DATA_DIR / "musiques"):
        if d.exists():
            for f in sorted(d.iterdir()):
                if f.suffix.lower() in MUSIC_EXT:
                    out.append({"name": f.name, "url": furl(f)})
    return out


def settings_get():
    cfg = load_config()
    return {"render": cfg["render"], "edit": cfg["edit"], "ui": cfg.get("ui", {}), "banner": cfg.get("banner", {}), "library_dirs": [str(d) for d in library_dirs(cfg)],
            "encoder": detect_encoder(), "version": APP_VERSION,
            "music_dir": str(DATA_DIR / "musiques"), "data_dir": str(DATA_DIR),
            "modes": {k: v["label"] for k, v in MODES.items()}}


def settings_set(data):
    user = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
    for sec in ("render", "edit", "ui", "banner"):
        for k, v in (data.get(sec) or {}).items():
            if k in DEFAULT_CONFIG[sec]:
                user.setdefault(sec, {})[k] = v
    if "library_dirs" in data:
        user["library_dirs"] = [str(Path(d)) for d in data["library_dirs"] if d and Path(d).exists()]
    CONFIG_PATH.write_text(json.dumps(user, indent=2, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ file d'attente des tâches
JOBS, QUEUE = [], []
PCT_RE = re.compile(r"(\d{1,3}(?:\.\d)?)%")
SCAN_RE = re.compile(r"(\d+)/(\d+)\s+[\d.]+ img/s")
SPEED_RE = re.compile(r"\bx\s*(\d+(?:\.\d+)?)")
ETA_RE = re.compile(r"reste\s+(~?\s*[\d.]+\s*min|\d+:\d{2}(?::\d{2})?)")
PARTS_RE = re.compile(r"\((\d+) morceaux, (\d+) en parall")
STAGES = {"[SCAN]": "Scan", "[RENDU]": "Rendu des games", "[CONCAT]": "Assemblage", "[FINAL]": "Assemblage + musique",
          "[SHORTS]": "Shorts", "[SRT]": "Sous-titres", "[BIP]": "Bip des gros mots", ">> Scan": "Scan", ">> Chargement": "Chargement OCR"}


def _progress_detail(j, line):
    """Vitesse / temps restant / étape, affichés sous la barre du travail."""
    for k, v in STAGES.items():
        if line.startswith(k) and j.get("stage") != v:
            j["stage"] = v
            for x in ("eta", "speed", "parts"):      # chiffres de l'étape précédente
                j.pop(x, None)
    m = ETA_RE.search(line)
    if m:
        eta = m.group(1).replace("~", "").strip()
        if eta.count(":") == 2 and eta.startswith("0:"):
            eta = eta[2:]
        j["eta"] = eta
    m = SPEED_RE.search(line)
    if m and "%" in line:
        j["speed"] = float(m.group(1))
    m = PARTS_RE.search(line)
    if m:
        j["parts"] = f"{m.group(1)} morceaux, {m.group(2)} en parallèle"


def add_job(action, mode, path):
    j = {"id": uuid.uuid4().hex[:8], "action": action, "mode": mode, "path": str(find_video(path)),
         "name": Path(path).name, "status": "en attente", "pct": 0.0, "msg": "", "log": [], "output": None,
         "created": time.time()}
    with LOCK:
        JOBS.append(j)
        QUEUE.append(j)
    return j


def worker():
    while True:
        j = None
        with LOCK:
            if QUEUE:
                j = QUEUE.pop(0)
        if not j:
            time.sleep(0.5)
            continue
        j["status"] = "en cours"
        j["msg"] = "Démarrage…"
        j["t0"] = time.time()
        j["path"] = str(find_video(j["path"]))
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        worker_exe = Path(sys.executable).parent / ("MontageStudioWorker.exe" if os.name == "nt" else "MontageStudioWorker")
        cmd = ([str(worker_exe), "--job", j["action"], j["mode"], j["path"]] if FROZEN else
               [sys.executable, "-u", str(ASSET_DIR / "job.py"), j["action"], j["mode"], j["path"]])
        flags = 0x08000000 if os.name == "nt" else 0          # CREATE_NO_WINDOW : pas de console qui s'ouvre
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(DATA_DIR), env=env,
                             creationflags=flags)
        j["pid"] = p.pid
        buf = b""
        while True:
            ch = p.stdout.read(256)
            if not ch:
                break
            buf += ch
            parts = re.split(rb"[\r\n]", buf)
            buf = parts.pop()
            for raw in parts:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                _progress_detail(j, line)
                m = SCAN_RE.search(line)
                if m:
                    j["pct"] = int(m.group(1)) / max(1, int(m.group(2))) * 100
                    j["msg"] = "Scan OCR " + line[:40]
                else:
                    m = PCT_RE.search(line)
                    if m and ("[" in line or "PROXY" in line or "final" in line):
                        j["pct"] = float(m.group(1))
                if line.startswith(">>") or line.startswith("[") and "%" not in line:
                    j["msg"] = line[:120]
                if line.startswith("[OUTPUT]"):
                    j["output"] = line[9:].strip()
                if "%" not in line:
                    j["log"] = (j["log"] + [line])[-60:]
        p.wait()
        j["eta"] = None
        j["elapsed_s"] = int(time.time() - j["t0"])
        j["status"] = "terminé" if p.returncode == 0 else ("annulé" if j.get("cancel") else "erreur")
        if p.returncode == 0:
            j["pct"] = 100.0


def cancel_job(jid):
    with LOCK:
        for j in JOBS:
            if j["id"] == jid:
                if j["status"] == "en attente":
                    QUEUE.remove(j)
                    j["status"] = "annulé"
                elif j["status"] == "en cours" and j.get("pid"):
                    j["cancel"] = True
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(j["pid"])] if os.name == "nt"
                                   else ["kill", str(j["pid"])], capture_output=True)


# ------------------------------------------------------------------ HTTP
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _bytes(self, b, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _file(self, p):
        p = Path(p)
        if not p.exists() or not allowed(p):
            return self._json({"error": "introuvable"}, 404)
        size = p.stat().st_size
        ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else max(0, size - int(b))
            end = int(b) if a and b else size - 1
            end = min(end, size - 1, start + 16 * 1024 * 1024 - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        try:
            with open(p, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if u.path in ("/", "/index.html"):
                return self._file(UI / "index.html")
            if u.path.startswith("/ui/"):
                return self._file(UI / unquote(u.path[4:]))
            if u.path == "/file":
                return self._file(find_video(q["path"]) if Path(q["path"]).suffix.lower() in VIDEO_EXT
                                  else q["path"])
            if u.path == "/api/library":
                return self._json(library())
            if u.path == "/api/thumb":
                return self._file(thumb_of(q["path"]))
            if u.path == "/api/project":
                return self._json(project(q["path"], q["mode"]))
            if u.path == "/api/proxy_url":
                cfg = make_cfg(q["mode"], find_video(q["path"]))
                pp = work_dir(cfg) / "proxy.mp4"
                return self._json({"url": furl(pp) if pp.exists() else None})
            if u.path == "/api/jobs":
                with LOCK:
                    now = time.time()
                    for j in JOBS:
                        if j["status"] == "en cours" and j.get("t0"):
                            j["elapsed_s"] = int(now - j["t0"])
                    return self._json([{k: v for k, v in j.items() if k != "pid"} for j in JOBS[-30:]])
            if u.path == "/api/music":
                return self._json(music_list())
            if u.path == "/api/settings":
                try:
                    import updater
                    updater.mark_ok()           # l'interface s'affiche : la version active est saine
                except ImportError:
                    pass
                return self._json(settings_get())
            if u.path == "/api/update":
                import updater
                return self._json(dict(updater.STATE, version=APP_VERSION, base=updater.BASE_VERSION,
                                       configured=bool(updater.latest_url())))
            if u.path == "/api/banners":
                return self._json(banners_info(q.get("path"), q.get("mode")))
            if u.path == "/api/progress":
                return self._json(progress_info())
            if u.path == "/api/live":
                import live
                return self._json(live.state())
            if u.path == "/live/widget":
                import live
                return self._bytes(live.WIDGET_HTML.encode("utf-8"), "text/html; charset=utf-8")
            if u.path == "/live/font.ttf":
                f = ASSET_DIR / "polices" / "LuckiestGuy-Regular.ttf"
                return self._bytes(f.read_bytes(), "font/ttf") if f.exists() else self._json({}, 404)
            if u.path == "/live/rang.png":
                import live
                f = live.LIVE_DIR / "rang.png"
                return self._bytes(f.read_bytes(), "image/png") if f.exists() else self._json({}, 404)
            if u.path == "/api/youtube":
                import youtube
                try:
                    return self._json(youtube.for_project(make_cfg(q.get("mode"), find_video(q.get("path")))) or
                                      {"error": "Analyse d'abord ce rec."})
                except Exception as e:
                    return self._json({"error": f"{type(e).__name__}: {e}"})
            if u.path == "/api/fonts":
                return self._json(["LuckiestGuy-Regular.ttf", "Anton-Regular.ttf"])
            return self._json({"error": "route inconnue"}, 404)
        except Exception as e:
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        try:
            d = self._body()
            if u.path == "/api/mode":
                st = state()
                st["modes"][Path(d["path"]).stem] = d["mode"]
                save_state(st)
                return self._json({"ok": True})
            if u.path == "/api/job":
                return self._json(add_job(d["action"], d["mode"], d["path"]))
            if u.path == "/api/job/cancel":
                cancel_job(d["id"])
                return self._json({"ok": True})
            if u.path == "/api/plan/save":
                cfg = make_cfg(d["mode"], find_video(d["path"]))
                plan = d["plan"]
                plan["user_edited"] = True
                (work_dir(cfg) / "edit_plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False),
                                                             encoding="utf-8")
                import progress
                tl_p = work_dir(cfg) / "timeline.json"
                progress.record(cfg, plan, json.loads(tl_p.read_text(encoding="utf-8")) if tl_p.exists() else None)
                return self._json({"ok": True})
            if u.path == "/api/live/start":
                import live
                try:
                    return self._json(live.start(d.get("mode")))
                except ValueError as e:
                    return self._json({"error": str(e)})
            if u.path == "/api/live/stop":
                import live
                return self._json(live.stop_())
            if u.path == "/api/progress/hide":
                import progress
                progress.hide(d["id"], d.get("hidden", True))
                return self._json(progress_info())
            if u.path == "/api/plan/reset":
                import edit
                cfg = make_cfg(d["mode"], find_video(d["path"]))
                edit.build(cfg)
                return self._json(project(d["path"], d["mode"]))
            if u.path == "/api/card":
                import render
                cfg = load_config()
                rc = dict(cfg["render"], width=1280, height=720)
                out = CACHE / f"card_{uuid.uuid4().hex[:6]}.png"
                render.make_card(rc, d["card"], out, final=d.get("final", False))
                b = out.read_bytes()
                out.unlink()
                return self._bytes(b, "image/png")
            if u.path == "/api/thumbnails":
                import thumbs
                cfg = make_cfg(d["mode"], find_video(d["path"]))
                times = [float(t) for t in d.get("times") or []] or None
                files, info = thumbs.generate(cfg, d.get("main") or None, d.get("sub") or None, times)
                info["files"] = [{"name": f.name, "url": furl(f, f"&v={time.time():.0f}")} for f in files]
                info["dir"] = str(files[0].parent) if files else None
                return self._json(info)
            if u.path == "/api/banner/render":
                import banners
                img = banner_image(d)
                png = banners.TEMPLATES[d["id"]].get("fn") is banners.t_bandeau_stream
                out = banners.save(img, CACHE / f"banner_preview.{'png' if png else 'jpg'}")
                return self._json({"url": furl(out, f"&v={time.time():.3f}"), "size": img.size})
            if u.path == "/api/banner/export":
                import banners
                img = banner_image(d)
                png = d["id"] == "bandeau_stream"
                base = library_dirs()[0]
                dst_dir = base / ("Miniatures" if banners.TEMPLATES[d["id"]]["format"] == "Miniature" else "Bannières")
                dst_dir.mkdir(parents=True, exist_ok=True)
                stem = Path(d["path"]).stem + " - " if d.get("path") else ""
                dst = dst_dir / f"{stem}{banners.TEMPLATES[d['id']]['label'].replace('/', '-')} {time.strftime('%H%M%S')}.{'png' if png else 'jpg'}"
                banners.save(img, dst)
                keep = {k: v for k, v in (d.get("values") or {}).items()
                        if k in DEFAULT_CONFIG["banner"] and v not in (None, "")}
                if keep:
                    settings_set({"banner": keep})
                return self._json({"ok": True, "saved": str(dst)})
            if u.path == "/api/banner/cutout":
                import banners
                if not d.get("path"):
                    return self._json({"ok": False, "message": "Ouvre d'abord un rec et place le curseur sur ton skin."})
                fr = frame_at(find_video(d["path"]), d.get("t") or 0)
                if fr is None:
                    return self._json({"ok": False, "message": "Impossible de lire l'image du rec à cet endroit."})
                try:
                    p = banners.cutout(fr)
                except ImportError:
                    return self._json({"ok": False, "message": "Détourage indisponible (module rembg absent). "
                                       "Mets un PNG sans fond dans le dossier des skins."})
                return self._json({"ok": True, "skin": {"name": p.name, "path": str(p), "url": furl(p, f"&v={time.time():.0f}")}})
            if u.path == "/api/banner/skin_delete":
                import banners
                p = Path(d["path"])
                if p.parent.resolve() == banners.SKIN_DIR.resolve() and p.exists():
                    p.unlink()
                return self._json({"ok": True})
            if u.path == "/api/update/check":
                import updater
                if not updater.STATE["checking"]:
                    threading.Thread(target=updater.check, daemon=True).start()
                return self._json({"ok": True})
            if u.path == "/api/update/restart":
                import updater
                if any(j["status"] == "en cours" for j in JOBS):
                    return self._json({"ok": False, "message": "Une tâche est en cours : attends la fin."})
                kill_jobs()
                threading.Timer(0.5, updater.restart).start()
                return self._json({"ok": True})
            if u.path == "/api/thumbnails/export":
                src = Path(d["file"])
                vp = find_video(d["path"])
                dst_dir = (vp.parent.parent if vp.parent.name == RAW_DIR_NAME else vp.parent) / "Miniatures"
                dst_dir.mkdir(exist_ok=True)
                dst = dst_dir / f"{Path(d['path']).stem} - miniature.jpg"
                dst.write_bytes(src.read_bytes())
                return self._json({"ok": True, "saved": str(dst)})
            if u.path == "/api/settings":
                settings_set(d)
                return self._json(settings_get())
            if u.path == "/api/open":
                if d.get("folder") == "diag":
                    t_ = work_dir(make_cfg(d["mode"], find_video(d["video"]))) / "diagnostic"
                    t_.mkdir(parents=True, exist_ok=True)
                    if os.name == "nt":
                        subprocess.Popen(["explorer", str(t_)])
                    return self._json({"ok": True, "path": str(t_)})
                base = library_dirs()[0]
                target = Path(d.get("path") or (base / "Miniatures" if d.get("folder") == "thumbs" else
                                                DATA_DIR / "musiques" if d.get("folder") == "music" else base))
                target.mkdir(exist_ok=True) if not target.suffix and not target.exists() else None
                if os.name == "nt":
                    subprocess.Popen(["explorer", "/select,", str(target)] if target.is_file()
                                     else ["explorer", str(target)])
                return self._json({"ok": True})
            return self._json({"error": "route inconnue"}, 404)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)


def start_server(port=PORT):
    """Démarre le serveur (et la file des tâches) ; renvoie (serveur, url). Port libre auto si occupé."""
    threading.Thread(target=worker, daemon=True).start()
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    except OSError:
        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, url


def kill_jobs():
    with LOCK:
        for j in JOBS:
            if j["status"] in ("en cours", "en attente"):
                j["cancel"] = True
                if j.get("pid"):
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(j["pid"])] if os.name == "nt"
                                   else ["kill", str(j["pid"])], capture_output=True)


def main():
    srv, url = start_server()
    print(f"FN Montage Studio -> {url}   (ferme cette fenêtre pour quitter)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        kill_jobs()


if __name__ == "__main__":
    main()

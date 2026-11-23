"""Mises à jour automatiques de Montage Studio (fait partie du LANCEUR : n'est jamais mis à jour lui-même).

- Au démarrage, `activate()` charge le code de la mise à jour installée (si elle est saine) AVANT le code
  livré dans l'exe : un « finder » placé en tête de sys.meta_path sert nos modules depuis code.zip.
- En arrière-plan, `check_async()` lit latest.json sur GitHub Releases, télécharge le paquet (quelques Mo),
  vérifie qu'il vient de ton dépôt + son empreinte SHA-256, puis le décompresse.
  Il sera actif au prochain lancement (bouton « Redémarrer » dans l'app).
- Si une nouvelle version plante 2 fois de suite avant d'afficher l'interface -> retour à la précédente.
"""
import hashlib
import importlib.abc
import importlib.machinery
import json
import os
import shutil
import sys
import threading
import time
import urllib.request
import zipfile
import zipimport
from pathlib import Path

BASE_VERSION = "1.1.0"          # version du lanceur (l'exe installé). 1.1.0 : charge les nouveaux modules des MAJ
APP_MODULES = {"common", "scan", "edit", "render", "run", "job", "thumbs", "studio", "banners", "shorts", "transcribe", "youtube", "voice", "progress", "bleep", "_version"}
PREFIX = "MSTUDIO-UPDATE"


def _data_dir():
    return (Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "MontageStudio") \
        if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


UPD = _data_dir() / "updates"
STATE_P = UPD / "state.json"
STATE = {"available": None, "ready": None, "error": None, "checking": False, "active": None,
         "rolled_back": None, "notes": "", "progress": 0}


def vtuple(v):
    try:
        return tuple(int(x) for x in str(v).lstrip("v").split("."))
    except ValueError:
        return (0,)


def _read_state():
    try:
        return json.loads(STATE_P.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_state(st):
    UPD.mkdir(parents=True, exist_ok=True)
    tmp = STATE_P.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1), encoding="utf-8")
    tmp.replace(STATE_P)


def normalize_repo(r):
    """'pseudo' -> 'pseudo/montage-studio' ; accepte aussi une URL github.com/... ou un .git."""
    r = (r or "").strip().strip('"').strip()
    for p in ("https://", "http://", "github.com/", "www.github.com/"):
        if r.lower().startswith(p):
            r = r[len(p):]
    r = r.rstrip("/")
    if r.endswith(".git"):
        r = r[:-4]
    parts = [x for x in r.split("/") if x]
    if not parts:
        return None
    if len(parts) == 1:
        parts.append("montage-studio")
    return f"{parts[0]}/{parts[1]}"


def _repo():
    if os.environ.get("MONTAGE_UPDATE_URL"):
        return None
    try:
        from update_cfg import REPO
        return normalize_repo(REPO)
    except ImportError:
        return None


def latest_url():
    if os.environ.get("MONTAGE_UPDATE_URL"):          # pour les tests
        return os.environ["MONTAGE_UPDATE_URL"]
    repo = _repo()
    return f"https://github.com/{repo}/releases/latest/download/latest.json" if repo else None


# ------------------------------------------------------------------ chargement du code mis à jour
class _UpdateFinder(importlib.abc.MetaPathFinder):
    """Sert depuis code.zip tous les modules qu'il contient (un module ajouté dans une mise à jour
    marche donc sans réinstaller l'app), jamais les bibliothèques (torch, PIL...)."""
    def __init__(self, zpath):
        self.zi = zipimport.zipimporter(str(zpath))
        with zipfile.ZipFile(zpath) as z:
            self.names = {n[:-4] for n in z.namelist() if n.endswith(".pyc") and "/" not in n}

    def find_spec(self, name, path=None, target=None):
        if name in self.names or name in APP_MODULES:
            try:
                return self.zi.find_spec(name)
            except Exception:
                return None
        return None


def activate(worker=False):
    """À appeler AVANT d'importer le moindre module de l'app. Renvoie la version active (ou None)."""
    st = _read_state()
    cur = st.get("current")
    if worker and "MONTAGE_ACTIVE_VERSION" in os.environ:
        cur = os.environ["MONTAGE_ACTIVE_VERSION"] or None     # même version que la fenêtre qui l'a lancé
    if not cur:
        os.environ["MONTAGE_ACTIVE_VERSION"] = ""
        return None
    d = UPD / cur
    if not (d / "code.zip").exists() or vtuple(st.get("min_base", "0")) > vtuple(BASE_VERSION):
        return None
    if not worker:
        # garde-fou : 2 démarrages ratés d'affilée -> retour à la version précédente
        if st.get("boots_without_ok", 0) >= 2:
            STATE["rolled_back"] = cur
            st["bad"] = sorted(set(st.get("bad", []) + [cur]))
            st["current"] = st.get("previous")
            st["boots_without_ok"] = 0
            _write_state(st)
            return activate(worker)
        st["boots_without_ok"] = st.get("boots_without_ok", 0) + 1
        _write_state(st)
    sys.meta_path.insert(0, _UpdateFinder(d / "code.zip"))
    os.environ["MONTAGE_ACTIVE_VERSION"] = cur
    if (d / "assets").exists():
        os.environ["MONTAGE_ASSETS"] = str(d / "assets")
    STATE["active"] = cur
    return cur


def mark_ok():
    """L'interface s'est affichée : la version active est saine."""
    st = _read_state()
    if st.get("boots_without_ok"):
        st["boots_without_ok"] = 0
        _write_state(st)


# ------------------------------------------------------------------ vérification / téléchargement
def verify_manifest(m, blob):
    """Le paquet doit venir de ton dépôt GitHub et avoir exactement l'empreinte annoncée."""
    url = m.get("url", "")
    if not url.startswith(f"https://github.com/{_repo()}/releases/download/"):
        raise ValueError("mise à jour refusée : elle ne vient pas du dépôt officiel")
    if hashlib.sha256(blob).hexdigest() != m.get("sha256"):
        raise ValueError("fichier corrompu (empreinte différente)")


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "MontageStudio-Updater"})
    return urllib.request.urlopen(req, timeout=timeout)


def current_version():
    try:
        import common
        return common.APP_VERSION
    except Exception:
        return BASE_VERSION


def check(download=True):
    url = latest_url()
    if not url:
        STATE["error"] = "mises à jour non configurées dans ce build"
        return STATE
    STATE.update(checking=True, error=None)
    try:
        with _get(url, 10) as r:
            m = json.loads(r.read().decode("utf-8"))
        st = _read_state()
        ver = m["version"]
        if vtuple(ver) <= vtuple(current_version()) or ver in st.get("bad", []):
            STATE["available"] = None
            return STATE
        if vtuple(m.get("min_base", "0")) > vtuple(BASE_VERSION):
            STATE.update(available=ver, notes=m.get("notes", ""),
                         error="Cette version demande de réinstaller l'app (nouveau moteur) : "
                               f"https://github.com/{_repo()}/releases/latest")
            return STATE
        STATE.update(available=ver, notes=m.get("notes", ""))
        if st.get("current") == ver and (UPD / ver / "code.zip").exists():
            STATE["ready"] = ver
            return STATE
        if not download:
            return STATE
        with _get(m["url"], 60) as r:
            total = int(r.headers.get("Content-Length") or 0)
            buf = bytearray()
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                buf += chunk
                STATE["progress"] = round(len(buf) / total * 100, 1) if total else 0
        blob = bytes(buf)
        verify_manifest(m, blob)
        dest, tmp = UPD / ver, UPD / (ver + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        zp = tmp / "package.zip"
        zp.write_bytes(blob)
        with zipfile.ZipFile(zp) as z:
            for n in z.namelist():
                if n.startswith("/") or ".." in Path(n).parts:
                    raise ValueError("paquet invalide")
            z.extractall(tmp)
        zp.unlink()
        if not (tmp / "code.zip").exists():
            raise ValueError("paquet sans code")
        shutil.rmtree(dest, ignore_errors=True)
        tmp.replace(dest)
        st = _read_state()
        st.update(previous=st.get("current"), current=ver, min_base=m.get("min_base", "0"),
                  boots_without_ok=0, installed_at=time.time())
        _write_state(st)
        # ménage : on garde la version active et la précédente
        for d in UPD.iterdir():
            if d.is_dir() and d.name not in (st["current"], st.get("previous")):
                shutil.rmtree(d, ignore_errors=True)
        STATE["ready"] = ver
    except Exception as e:
        STATE["error"] = f"{type(e).__name__}: {e}"
    finally:
        STATE["checking"] = False
    return STATE


def check_async(delay=3, every=20 * 60):
    """Vérifie au démarrage, puis toutes les 20 min tant que l'app est ouverte."""
    def run():
        time.sleep(delay)
        while True:
            try:
                check()
            except Exception:
                pass
            if not every:
                return
            time.sleep(every)
    threading.Thread(target=run, daemon=True).start()


def restart():
    """Relance l'application (pour activer la mise à jour téléchargée)."""
    import subprocess
    if getattr(sys, "frozen", False):
        subprocess.Popen([sys.executable], close_fds=True)
    else:
        subprocess.Popen([sys.executable] + sys.argv, close_fds=True)
    os._exit(0)

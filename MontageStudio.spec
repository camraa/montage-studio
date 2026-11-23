# -*- mode: python ; coding: utf-8 -*-
# Build de Montage Studio (PyInstaller) - lancé par BUILD_EXE.bat
#   -> dist/MontageStudio/MontageStudio.exe        (l'application, fenêtre)
#   -> dist/MontageStudio/MontageStudioWorker.exe  (tâches de fond : scan, rendu)
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = SPECPATH
B = os.path.join(ROOT, "build_assets")

datas = [
    (os.path.join(ROOT, "studio"), "studio"),
    (os.path.join(ROOT, "polices"), "polices"),
    (os.path.join(ROOT, "musiques"), "musiques"),
    (os.path.join(ROOT, "intro.mp3"), "."),
    (os.path.join(ROOT, "outro.mp3"), "."),
    (os.path.join(ROOT, "icone.ico"), "."),
    (os.path.join(ROOT, "icone.png"), "."),
    (os.path.join(ROOT, "THIRD_PARTY_LICENSES.txt"), "."),
]
for sub in ("ocr_models", "ffmpeg", "whisper_models", "rembg_models"):
    if os.path.isdir(os.path.join(B, sub)):
        datas.append((os.path.join(B, sub), sub))

binaries, hidden = [], []
for pkg in ("easyocr", "webview", "pythonnet", "clr_loader", "faster_whisper", "ctranslate2", "onnxruntime", "av"):
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue
    datas += d
    binaries += b
    hidden += h
hidden += ["scan", "edit", "render", "thumbs", "job", "run", "banners", "shorts", "transcribe", "youtube", "voice", "progress", "bleep", "live", "_version", "studio", "common",
           "updater", "update_cfg", "zipimport", "py_compile", "urllib.request", "ssl",
           "clr_loader", "pythonnet"]
hidden += collect_submodules("webview.platforms")

a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=["matplotlib", "tensorboard", "torch.utils.tensorboard", "IPython", "jupyter", "pandas",
              "keygen", "publish", "pytest", "sphinx"],
    noarchive=False,
)
pyz = PYZ(a.pure)

app_exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="MontageStudio",
              icon=os.path.join(ROOT, "icone.ico"), console=False, upx=False,
              version=os.path.join(B, "version_info.txt") if os.path.exists(os.path.join(B, "version_info.txt")) else None)
worker_exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="MontageStudioWorker",
                 icon=os.path.join(ROOT, "icone.ico"), console=True, upx=False)

coll = COLLECT(app_exe, worker_exe, a.binaries, a.datas, strip=False, upx=False, name="MontageStudio")

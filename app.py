"""Montage Studio - point d'entrée de l'application.

  MontageStudio.exe                         -> fenêtre de l'application
  MontageStudioWorker.exe --job <action> <mode> <vidéo>   -> tâche de fond (scan / rendu / proxy)
  MontageStudioWorker.exe --cli <mode> [vidéos...]         -> montage auto sans interface
"""
import json
import os
import sys


def run_job(argv):
    import job
    sys.argv = ["job.py"] + argv
    job.main()


def run_cli(argv):
    import run
    sys.argv = ["run.py"] + argv
    run.main()


def migrate_old_install():
    """1er lancement de l'exe : récupère les scans faits avec la version 'scripts' (évite de tout re-scanner)."""
    import shutil
    from pathlib import Path
    from common import FROZEN, WORK_ROOT
    if not FROZEN or (WORK_ROOT / ".migrated").exists():
        return
    old = Path.home() / "Videos" / "montage_fortnite" / "work"
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    if old.exists():
        for d in old.iterdir():
            if d.is_dir() and not d.name.startswith("_") and not (WORK_ROOT / d.name).exists():
                (WORK_ROOT / d.name).mkdir()
                for f in d.glob("*.json*"):
                    shutil.copy2(f, WORK_ROOT / d.name / f.name)
    (WORK_ROOT / ".migrated").write_text("ok")


def run_gui():
    try:
        import shell                      # fenêtre (module mis à jour automatiquement)
    except Exception:
        return run_gui_legacy()
    return shell.run_gui()


def run_gui_legacy():
    import studio
    from common import APP_NAME, APP_VERSION, DATA_DIR
    migrate_old_install()
    import updater
    srv, url = studio.start_server()
    updater.check_async()
    try:
        import webview
    except ImportError:          # pas de pywebview : on ouvre dans le navigateur
        import time
        import webbrowser
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    try:
        from common import load_config
        frameless = bool(load_config().get("ui", {}).get("mac_window", True))
    except Exception:
        frameless = True
    try:                         # seules les zones vides de la barre de titre déplacent la fenêtre
        webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True
    except Exception:
        pass
    closing_ok = {"v": False}
    win_state = {"max": False}

    def confirm_close():
        running = [j for j in studio.JOBS if j["status"] in ("en cours", "en attente")]
        if running:
            ok = window.create_confirmation_dialog(
                "Une tâche est en cours",
                f"{len(running)} tâche(s) en cours ({running[0]['name']}).\n"
                "Si tu quittes maintenant, elle sera arrêtée et devra être relancée.\nQuitter quand même ?")
            if not ok:
                return False
        studio.kill_jobs()
        return True

    class Api:
        # ----- boutons de fenêtre façon macOS (fenêtre sans cadre)
        def win_info(self):
            return {"frameless": frameless}

        def win_close(self):
            if confirm_close():
                closing_ok["v"] = True
                window.destroy()

        def win_min(self):
            window.minimize()

        def win_max(self):           # bouton vert / double-clic sur la barre : agrandir <-> restaurer
            if win_state["max"]:
                window.restore()
            else:
                window.maximize()
            win_state["max"] = not win_state["max"]

        def pick_folder(self):
            r = window.create_file_dialog(webview.FOLDER_DIALOG)
            return r[0] if r else None

        def pick_videos(self):
            r = window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True,
                                          file_types=("Vidéos (*.mp4;*.mkv;*.mov)", "Tous (*.*)"))
            return list(r) if r else []

    win_kw = dict(js_api=Api(), width=1600, height=960, min_size=(1200, 720),
                  background_color="#1e1e20", text_select=False)
    if frameless:
        win_kw.update(frameless=True, easy_drag=False, shadow=True)
    try:
        window = webview.create_window(f"{APP_NAME} {APP_VERSION}", url, **win_kw)
    except TypeError:            # anciennes versions de pywebview : pas d'option shadow/easy_drag
        for k in ("shadow", "easy_drag"):
            win_kw.pop(k, None)
        window = webview.create_window(f"{APP_NAME} {APP_VERSION}", url, **win_kw)

    def on_closing():
        if closing_ok["v"]:      # déjà confirmé par le bouton rouge
            return
        if not confirm_close():
            return False

    window.events.closing += on_closing
    try:                         # garde l'état agrandi/restauré à jour (Win+flèches, etc.)
        window.events.maximized += lambda *a: win_state.update(max=True)
        window.events.restored += lambda *a: win_state.update(max=False)
    except Exception:
        pass
    kw = {"storage_path": str(DATA_DIR / "webview"), "private_mode": False}
    if os.name == "nt":
        kw["gui"] = "edgechromium"
    icon = studio.ASSET_DIR / "icone.ico"
    if icon.exists():
        kw["icon"] = str(icon)
    try:
        webview.start(**kw)
    except TypeError:            # anciennes versions de pywebview
        kw.pop("icon", None)
        webview.start(**kw)
    studio.kill_jobs()


def unbuffer():
    """Dans l'exe, la sortie vers le studio est mise en tampon -> plus de progression en direct.
    On force l'écriture immédiate de chaque ligne (et l'UTF-8 pour les accents)."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True, write_through=True)
        except (AttributeError, ValueError):
            pass


def main():
    argv = sys.argv[1:]
    import updater
    worker = argv[:1] in (["--job"], ["--cli"], ["--check-update"], ["--version"])
    updater.activate(worker=worker)          # code de la mise à jour installée, AVANT tout import de l'app
    if argv[:1] == ["--version"]:
        import common
        print(f"app {common.APP_VERSION} | lanceur {updater.BASE_VERSION} | maj active {updater.STATE['active']}")
        return
    if argv[:1] == ["--check-update"]:
        unbuffer()
        print(json.dumps(updater.check(), ensure_ascii=False))
        return
    if argv[:1] in (["--job"], ["--cli"]):
        unbuffer()
    if argv[:1] == ["--job"]:
        return run_job(argv[1:])
    if argv[:1] == ["--cli"]:
        return run_cli(argv[1:])
    return run_gui()


if __name__ == "__main__":
    main()

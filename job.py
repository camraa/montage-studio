"""Tâche lancée par le studio en arrière-plan.

  python job.py scan   <mode> <vidéo>   scan OCR + plan de montage
  python job.py render <mode> <vidéo>   rendu du plan (modifié ou non dans le studio)
  python job.py all    <mode> <vidéo>   scan + rendu
  python job.py proxy  <mode> <vidéo>   copie légère 720p pour l'aperçu dans le studio
  python job.py shorts <mode> <vidéo>   Shorts TikTok verticaux (meilleurs fights + sous-titres)
"""
import json
import subprocess
import sys
from pathlib import Path

from common import ffprobe_info, make_cfg, need, work_dir


FORCE_RESCAN = False


def ensure_plan(cfg, force=False):
    import edit
    p = work_dir(cfg) / "edit_plan.json"
    if p.exists() and not force:
        try:
            if json.loads(p.read_text(encoding="utf-8")).get("user_edited"):
                print("[PLAN] plan modifié dans le studio -> conservé")
                return p
        except ValueError:
            pass
    return edit.build(cfg)


def do_scan(cfg):
    import scan
    from run import migrate_old_scan
    migrate_old_scan(cfg)
    tl = scan.run(cfg, rescan=FORCE_RESCAN or "--rescan" in sys.argv)
    games = json.loads(Path(tl).read_text(encoding="utf-8")).get("games", [])
    ensure_plan(cfg)
    if not games:
        sys.exit("[ERREUR] Analyse terminée mais AUCUNE game trouvée. Mauvaise catégorie ? "
                 "Ouvre le dossier diagnostic (bouton dans la file) pour voir ce que le scan a lu.")


def do_render(cfg):
    import render
    from run import archive_raw
    if not (work_dir(cfg) / "edit_plan.json").exists():
        ensure_plan(cfg)
    out = render.render(cfg)
    if out and Path(out).exists():
        if cfg["render"].get("subtitles_srt"):
            try:
                import transcribe
                transcribe.srt_for_video(out, Path(out).with_suffix(".srt"))
            except Exception as e:
                print(f"[VOIX] sous-titres .srt impossibles : {type(e).__name__}: {e}")
        archive_raw(cfg["video"])


def do_proxy(cfg):
    src = cfg["video"]
    dst = work_dir(cfg) / "proxy.mp4"
    dur = ffprobe_info(src)["duration"]
    cmd = [need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-progress", "pipe:1", "-nostats",
           "-hwaccel", "cuda", "-i", str(src), "-vf", "scale=-2:720,fps=30", "-c:v", "h264_nvenc",
           "-preset", "p1", "-b:v", "3M", "-g", "30", "-c:a", "aac", "-b:a", "96k", "-ac", "2",
           "-movflags", "+faststart", str(dst.with_suffix(".tmp.mp4"))]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    for line in p.stdout:
        if line.startswith("out_time_us="):
            try:
                print(f"\r[PROXY] {min(100, int(line.split('=')[1]) / 1e6 / dur * 100):5.1f}%", end="", flush=True)
            except ValueError:
                pass
    p.wait()
    if p.returncode:
        sys.exit("[ERREUR] création du proxy impossible")
    dst.with_suffix(".tmp.mp4").replace(dst)
    print(f"\n[OK] proxy prêt")


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(line_buffering=True, write_through=True)
        except (AttributeError, ValueError):
            pass
    action, mode, video = sys.argv[1], sys.argv[2], sys.argv[3]
    print(f">> Démarrage : {action} ({mode})", flush=True)
    global FORCE_RESCAN
    cfg = make_cfg(mode, video)
    if action == "rescan":
        FORCE_RESCAN, action = True, "scan"
    if action in ("scan", "all"):
        do_scan(cfg)
    if action in ("render", "all"):
        do_render(cfg)
    if action == "proxy":
        do_proxy(cfg)
    if action == "shorts":
        import shorts
        shorts.run(cfg)
    print("[FIN]")


if __name__ == "__main__":
    main()

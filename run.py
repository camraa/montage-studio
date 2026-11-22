"""Montage automatique Fortnite - lance tout pour une ou plusieurs vidéos.

  python run.py cup            [vidéos...]
  python run.py ranked_reload  [vidéos...]
  python run.py ranked_br      [vidéos...]

Sans vidéo en argument : une fenêtre s'ouvre pour les choisir (sélection multiple possible).
Options : --rescan (refaire le scan OCR), --cpu (encodage sans NVENC),
          --no-archive (ne pas ranger le rec d'origine dans 'Vidéos brutes')

Le montage s'appelle "[PRÉ-UPLOAD] <nom du rec> - <mode> 4K.mp4" et le rec d'origine est rangé
dans le dossier "Vidéos brutes" une fois le montage réussi.
"""
import shutil
import sys
import time
import traceback
from pathlib import Path

from common import MODES, RAW_DIR_NAME, VIDEO_EXT, WORK_ROOT, library_dirs, make_cfg, work_dir


def pick_videos(mode):
    start = library_dirs()[0]
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        files = filedialog.askopenfilenames(
            title=f"Choisis tes recs ({MODES[mode]['label']}) - Ctrl+clic pour en prendre plusieurs",
            initialdir=str(start),
            filetypes=[("Vidéos", " ".join(f"*{e}" for e in VIDEO_EXT)), ("Tous", "*.*")])
        root.destroy()
        return [Path(f) for f in files]
    except Exception:
        vids = sorted(p for p in start.iterdir()
                      if p.suffix.lower() in VIDEO_EXT and not p.name.startswith("[PRÉ-UPLOAD]"))
        for i, p in enumerate(vids, 1):
            print(f"  {i:2d}. {p.name}  ({p.stat().st_size / 1e9:.1f} Go)")
        sel = input("Numéros des vidéos à monter (ex: 1 3 4) : ").split()
        return [vids[int(x) - 1] for x in sel if x.isdigit() and 0 < int(x) <= len(vids)]


def migrate_old_scan(cfg):
    """Réutilise le scan de la Cup fait avec l'ancienne version (évite de re-scanner)."""
    old = WORK_ROOT / "scan_raw_v3.jsonl"
    new = work_dir(cfg) / "scan_raw_v3.jsonl"
    if cfg["mode"] == "cup" and old.exists() and not new.exists() \
            and Path(cfg["video"]).stem == "2026-10-25 18-59-58":
        shutil.copy(old, new)


def archive_raw(video):
    """Range le rec d'origine dans 'Vidéos brutes' (même disque -> déplacement instantané)."""
    video = Path(video)
    if video.parent.name == RAW_DIR_NAME:
        return video
    dest_dir = video.parent / RAW_DIR_NAME
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / video.name
    if dest.exists():
        print(f"[RANGEMENT] {dest.name} existe déjà dans '{RAW_DIR_NAME}', rec laissé en place")
        return video
    try:
        video.rename(dest)
        print(f"[RANGEMENT] rec d'origine déplacé dans '{RAW_DIR_NAME}'")
        return dest
    except OSError as e:
        print(f"[RANGEMENT] impossible de déplacer le rec ({e}) - il est peut-être ouvert ailleurs")
        return video


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args or args[0] not in MODES:
        sys.exit(f"Usage : python run.py {{{'|'.join(MODES)}}} [vidéos...]")
    mode, videos = args[0], [Path(a) for a in args[1:]]
    if not videos:
        videos = pick_videos(mode)
    videos = [v for v in videos if v.exists()]
    if not videos:
        sys.exit("Aucune vidéo choisie.")

    import scan
    import edit
    import render

    print(f"\n=== MONTAGE {MODES[mode]['label'].upper()} : {len(videos)} vidéo(s) ===")
    results = []
    for i, v in enumerate(videos, 1):
        print(f"\n------------------------------------------------------------\n"
              f"[{i}/{len(videos)}] {v.name}\n"
              f"------------------------------------------------------------")
        t0 = time.time()
        try:
            cfg = make_cfg(mode, v)
            migrate_old_scan(cfg)
            print("\n>> SCAN")
            scan.run(cfg, rescan="--rescan" in flags)
            print("\n>> MONTAGE")
            edit.build(cfg)
            print("\n>> RENDU")
            out = render.render(cfg, cpu="--cpu" in flags)
            if out and Path(out).exists() and "--no-archive" not in flags:
                archive_raw(v)
            results.append((v.name, out and Path(out).name, None, time.time() - t0))
        except KeyboardInterrupt:
            raise
        except BaseException as e:      # une vidéo qui plante n'arrête pas les autres
            traceback.print_exc()
            results.append((v.name, None, str(e) or type(e).__name__, time.time() - t0))

    print("\n=================== RÉSUMÉ ===================")
    for name, out, err, dt in results:
        status = f"OK -> {out}" if out else f"ÉCHEC : {err}" if err else "rien à monter"
        print(f"  {name}  [{dt / 60:.0f} min]  {status}")


if __name__ == "__main__":
    main()

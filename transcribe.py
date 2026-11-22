"""Transcription de ta voix (faster-whisper) : sous-titres des Shorts et fichier .srt de la vidéo longue.

Sur la carte NVIDIA si possible (les DLL CUDA de PyTorch sont réutilisées), sinon sur le processeur.
Le modèle est livré avec l'app (whisper_models/<taille>), sinon téléchargé une fois dans les données.
"""
import os
import subprocess
from pathlib import Path

from common import ASSET_DIR, BUNDLE_DIR, DATA_DIR, load_config, need

SR = 16000
_MODEL = {}


def _model_dir(size):
    for d in (BUNDLE_DIR / "whisper_models" / size, ASSET_DIR / "whisper_models" / size,
              DATA_DIR / "whisper_models" / size):
        if (d / "model.bin").exists():
            return d
    from faster_whisper import download_model
    dst = DATA_DIR / "whisper_models" / size
    dst.mkdir(parents=True, exist_ok=True)
    print(f"[VOIX] téléchargement du modèle de transcription « {size} » (une seule fois)...", flush=True)
    return Path(download_model(size, output_dir=str(dst)))


def _cuda_dlls():
    """ctranslate2 a besoin de cuBLAS / cuDNN : on pointe vers ceux livrés avec PyTorch."""
    try:
        import torch
        lib = Path(torch.__file__).parent / "lib"
        if lib.exists():
            os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(lib))
        return torch.cuda.is_available()
    except Exception:
        return False


def model():
    if "m" in _MODEL:
        return _MODEL["m"]
    from faster_whisper import WhisperModel
    size = load_config()["render"].get("whisper_model", "small")
    path = str(_model_dir(size))
    m = None
    if os.environ.get("MONTAGE_NO_CUDA") != "1" and _cuda_dlls():
        try:
            m = WhisperModel(path, device="cuda", compute_type="float16")
            m.transcribe(_silence(1.0), language="fr")          # vérifie que CUDA marche vraiment
            print("[VOIX] transcription sur la carte graphique", flush=True)
        except Exception as e:
            print(f"[VOIX] CUDA indisponible pour la transcription ({type(e).__name__}) -> processeur", flush=True)
            m = None
    if m is None:
        m = WhisperModel(path, device="cpu", compute_type="int8", cpu_threads=max(2, (os.cpu_count() or 4) - 2))
        print("[VOIX] transcription sur le processeur", flush=True)
    _MODEL["m"] = m
    return m


def _silence(sec):
    import numpy as np
    return np.zeros(int(SR * sec), dtype=np.float32)


def load_audio(src, start=0.0, dur=None, concat=False):
    """Audio mono 16 kHz (float32) d'un fichier, ou d'une liste concat ffmpeg."""
    import numpy as np
    cmd = [need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin"]
    if concat:
        cmd += ["-f", "concat", "-safe", "0"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(src)]
    if dur:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def words(audio, progress=None):
    """Liste de mots [(début, fin, mot)] en secondes, avec les horodatages de chaque mot."""
    if len(audio) < SR // 2:
        return []
    segs, info = model().transcribe(audio, language="fr", word_timestamps=True, vad_filter=True,
                                    vad_parameters={"min_silence_duration_ms": 400}, beam_size=5,
                                    condition_on_previous_text=False)
    out, total = [], max(1e-6, len(audio) / SR)
    for s in segs:
        for w in s.words or []:
            t = w.word.strip()
            if not t:
                continue
            if out and (t[0] in "'’-" or w.word[:1] not in (" ", "") and out[-1][2][-1:] in "'’"):
                out[-1] = (out[-1][0], float(w.end), out[-1][2] + t)      # qu + 'il -> qu'il
            else:
                out.append((float(w.start), float(w.end), t))
        if progress:
            progress(min(1.0, s.end / total))
    return out


def chunks(ws, max_words=3, max_gap=0.6, max_len=1.6):
    """Regroupe les mots en petites phrases de sous-titres (style Shorts)."""
    out, cur = [], []
    for w in ws:
        if cur and (len(cur) >= max_words or w[0] - cur[-1][1] > max_gap or w[1] - cur[0][0] > max_len
                    or cur[-1][2][-1:] in ".?!"):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def _ts(t):
    h, r = divmod(max(0.0, t), 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"


def write_srt(ws, path, max_words=8):
    lines = []
    for i, c in enumerate(chunks(ws, max_words=max_words, max_gap=0.8, max_len=4.0), 1):
        text = " ".join(w[2] for w in c)
        lines.append(f"{i}\n{_ts(c[0][0])} --> {_ts(c[-1][1] + 0.15)}\n{text}\n")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return path


def srt_for_video(video, out_srt):
    """Sous-titres complets d'une vidéo (le montage final) -> fichier .srt à envoyer sur YouTube."""
    from common import ffprobe_info
    dur = ffprobe_info(video)["duration"]
    print(f"[VOIX] sous-titres de la vidéo ({dur / 60:.0f} min de son)...", flush=True)
    ws, step, t0 = [], 600.0, 0.0                    # par morceaux de 10 min (mémoire maîtrisée)
    while t0 < dur:
        a = load_audio(video, t0, min(step, dur - t0))
        for s, e, w in words(a, lambda f, t0=t0: print(f"\r[VOIX] {min(100, (t0 + f * step) / dur * 100):5.1f}%",
                                                     end="", flush=True)):
            ws.append((s + t0, e + t0, w))
        t0 += step
    print()
    write_srt(ws, out_srt)
    print(f"[OK] sous-titres : {out_srt}")
    return out_srt

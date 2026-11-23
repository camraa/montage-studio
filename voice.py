"""Moments forts au son : tes réactions (voix qui monte d'un coup, cris, fous rires).

Analyse légère : l'audio du rec est lu en continu par ffmpeg (4 kHz, mono, bande de la voix),
découpé en fenêtres de 0,5 s, jamais chargé en entier en mémoire (quelques Mo pour 3 h de rec).
Un pic = la voix au-dessus de son niveau habituel (+9 dB) pendant au moins 1 s.
Si faster-whisper est installé, son détecteur de parole (VAD) confirme que c'est bien de la voix.
Résultat mis en cache dans le dossier de travail : voice_peaks.json
"""
import json
import subprocess
import sys

from common import ffprobe_info, need, work_dir

RATE, WIN = 4000, 0.5
_NOWIN = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def _envelope(video, track):
    """Niveau (dBFS) de la bande de la voix, une valeur toutes les 0,5 s."""
    import numpy as np
    cmd = [need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(video), "-vn",
           "-map", f"0:a:{track}", "-af", "highpass=f=250,lowpass=f=3400", "-ac", "1", "-ar", str(RATE),
           "-f", "s16le", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **_NOWIN)
    n = int(RATE * WIN) * 2
    out, buf = [], b""
    while True:
        ch = p.stdout.read(n * 64)
        if not ch:
            break
        buf += ch
        k = len(buf) // n * n
        if k:
            a = np.frombuffer(buf[:k], dtype=np.int16).astype(np.float32).reshape(-1, n // 2) / 32768.0
            rms = np.sqrt((a ** 2).mean(axis=1)) + 1e-6
            out.extend((20 * np.log10(rms)).tolist())
            buf = buf[k:]
    p.wait()
    return np.array(out, dtype=np.float32)


def _baseline(db):
    """Niveau habituel autour de chaque instant (60e centile sur ±60 s), calculé par blocs de 15 s."""
    import numpy as np
    blk, half = int(15 / WIN), int(60 / WIN)
    base = np.empty_like(db)
    for i in range(0, len(db), blk):
        seg = db[max(0, i - half): i + blk + half]
        base[i:i + blk] = np.percentile(seg, 60)
    return base


def _speech_ratio(video, track, s, e):
    """Part de parole (0-1) entre s et e selon le VAD de faster-whisper ; None si indisponible."""
    try:
        import numpy as np
        from faster_whisper.vad import VadOptions, get_speech_timestamps
        cmd = [need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-ss", f"{s:.2f}", "-i", str(video),
               "-t", f"{e - s:.2f}", "-map", f"0:a:{track}", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"]
        a = np.frombuffer(subprocess.run(cmd, capture_output=True, **_NOWIN).stdout, dtype=np.float32)
        if len(a) < 8000:
            return None
        ts = get_speech_timestamps(a, VadOptions(min_silence_duration_ms=300))
        return sum(t["end"] - t["start"] for t in ts) / len(a)
    except Exception:
        return None


def peaks(video, track=0, jump_db=9.0, floor_db=-38.0, max_peaks=40):
    """[{t, start, end, strength}] triés par force décroissante."""
    import numpy as np
    db = _envelope(video, track)
    if len(db) < 20:
        return []
    ex = db - _baseline(db)
    hot = (ex >= jump_db) & (db >= floor_db)
    found, i = [], 0
    while i < len(hot):
        if not hot[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(hot) and (hot[j + 1] or (j + 2 < len(hot) and hot[j + 2])):   # tolère 0,5 s de creux
            j += 1
        if j - i + 1 >= 2:                                                                # au moins 1 s
            seg = ex[i:j + 1]
            found.append({"start": round(i * WIN, 2), "end": round((j + 1) * WIN, 2),
                          "t": round((i + int(np.argmax(seg))) * WIN, 2),
                          "strength": round(float(np.sort(seg)[-3:].mean() + min(4.0, (j - i + 1) * WIN)), 2)})
        i = j + 1
    found.sort(key=lambda p: -p["strength"])
    found = found[:max_peaks * 2]
    out = []
    for p in found:                    # confirmation « c'est bien ta voix » sur les meilleurs pics
        r = _speech_ratio(video, track, max(0, p["start"] - 0.5), p["end"] + 0.5)
        if r is not None:
            p["speech"] = round(r, 2)
            if r < 0.25:
                continue
        out.append(p)
        if len(out) >= max_peaks:
            break
    return out


def load_or_compute(cfg):
    rc = cfg["render"]
    track = int(rc.get("voice_track", -1))
    if track < 0:
        track = int(rc.get("audio_stream", 0))
    cache = work_dir(cfg) / "voice_peaks.json"
    if cache.exists():
        try:
            d = json.loads(cache.read_text(encoding="utf-8"))
            if d.get("track") == track:
                return d["peaks"]
        except ValueError:
            pass
    info = ffprobe_info(cfg["video"])
    if not info.get("has_audio"):
        return []
    print(f"[VOIX] recherche de tes réactions dans le son (piste {track + 1})…", flush=True)
    try:
        ps = peaks(cfg["video"], track)
    except Exception as e:
        print(f"[VOIX] analyse du son impossible ({type(e).__name__}: {e}) -> Shorts choisis sur les kills seuls")
        return []
    cache.write_text(json.dumps({"track": track, "peaks": ps}, ensure_ascii=False), encoding="utf-8")
    print(f"[VOIX] {len(ps)} réaction(s) repérée(s)", flush=True)
    return ps

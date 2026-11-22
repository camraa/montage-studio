"""Compose des musiques ORIGINALES (100 % générées par code -> aucun droit d'auteur).

  python make_music.py <dossier>

Crée dans <dossier> : intro.mp3, outro.mp3 et plusieurs ambiances (lofi, synthwave, trap, house, epic).
Tu peux aussi ajouter tes propres musiques libres de droit dans le dossier musiques/ :
elles seront utilisées aléatoirement sur les cartons entre les games.
"""
import subprocess
import sys

import numpy as np
from scipy.signal import butter, fftconvolve, lfilter

SR = 48000


# ------------------------------------------------------------------ briques de base
def t_(n):
    return np.arange(n) / SR


def env(n, a=0.005, d=0.2, s=0.0, r=0.05):
    """Enveloppe ADSR simplifiée (attaque, déclin exponentiel vers sustain, relâche)."""
    t = t_(n)
    e = np.minimum(1, t / max(a, 1e-4))
    e = e * (s + (1 - s) * np.exp(-np.maximum(0, t - a) / max(d, 1e-4)))
    rn = min(n, int(r * SR))
    if rn > 0:
        e[-rn:] *= np.linspace(1, 0, rn)
    return e


def hz(m):
    return 440 * 2 ** ((m - 69) / 12)


def saw(f, n, det=0.0, voices=3):
    t = t_(n)
    out = 0
    for k in range(voices):
        d = det * (k - (voices - 1) / 2)
        out = out + 2 * ((t * f * (1 + d)) % 1.0) - 1
    return out / voices


def sine(f, n, phase=0):
    return np.sin(2 * np.pi * f * t_(n) + phase)


def tri(f, n):
    return 2 * np.abs(2 * ((t_(n) * f) % 1) - 1) - 1


def lp(x, cut, order=2):
    b, a = butter(order, min(cut, SR / 2 - 100) / (SR / 2), "low")
    return lfilter(b, a, x, axis=0)


def hp(x, cut, order=2):
    b, a = butter(order, cut / (SR / 2), "high")
    return lfilter(b, a, x, axis=0)


def reverb(x, size=1.8, mix=0.25, seed=0):
    rng = np.random.default_rng(seed)
    n = int(size * SR)
    ir = rng.standard_normal(n) * np.exp(-t_(n) * 6 / size)
    ir = lp(ir, 6000)
    ir /= np.abs(ir).sum() ** 0.5 * 8
    wet = np.stack([fftconvolve(x[:, c], ir * (1 if c == 0 else -1))[:len(x)] for c in range(2)], 1)
    return x * (1 - mix) + wet * mix


def kick(n, f0=150, f1=48, decay=7, click=0.3):
    t = t_(n)
    f = f1 + (f0 - f1) * np.exp(-t * 30)
    k = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * decay)
    return k + click * np.random.default_rng(1).uniform(-1, 1, n) * np.exp(-t * 300)


def snare(n, rng, tone=190, decay=12):
    t = t_(n)
    return (hp(rng.uniform(-1, 1, n), 1500) * 0.8 + np.sin(2 * np.pi * tone * t) * 0.4) * np.exp(-t * decay)


def hat(n, rng, decay=60):
    return hp(rng.uniform(-1, 1, n), 7000) * np.exp(-t_(n) * decay)


def clap(n, rng):
    t = t_(n)
    e = sum(np.exp(-np.maximum(0, t - o) * 80) * (t >= o) for o in (0, 0.008, 0.016)) / 3
    return hp(rng.uniform(-1, 1, n), 1200) * (e + 0.5 * np.exp(-t * 18))


def epiano(f, n):
    """Piano électrique (FM simple) avec léger trémolo."""
    t = t_(n)
    mod = np.sin(2 * np.pi * f * 14 * t) * np.exp(-t * 8) * 1.2
    car = np.sin(2 * np.pi * f * t + mod)
    return car * (1 + 0.15 * np.sin(2 * np.pi * 5 * t)) * env(n, 0.003, 1.2, 0.0, 0.08)


def pluck(f, n, rng, damp=0.996):
    """Corde pincée (Karplus-Strong)."""
    p = max(2, int(SR / f))
    buf = rng.uniform(-1, 1, p)
    out = np.empty(n)
    for i in range(n):
        out[i] = buf[i % p]
        buf[i % p] = damp * 0.5 * (buf[i % p] + buf[(i + 1) % p])
    return out * env(n, 0.001, 2.0, 0, 0.05)


def bell(f, n):
    t = t_(n)
    return (np.sin(2 * np.pi * f * t + 2 * np.sin(2 * np.pi * f * 3.5 * t) * np.exp(-t * 3))
            * np.exp(-t * 2.5))


class Track:
    def __init__(self, seconds, bpm, seed):
        self.N = int(seconds * SR)
        self.mix = np.zeros((self.N, 2))
        self.beat = 60 / bpm
        self.rng = np.random.default_rng(seed)

    def put(self, x, at, gain=1.0, pan=0.0):
        s = int(at * SR)
        if s >= self.N:
            return
        x = x[: self.N - s] * gain
        if x.ndim == 1:
            self.mix[s:s + len(x), 0] += x * (1 - max(0, pan))
            self.mix[s:s + len(x), 1] += x * (1 + min(0, pan))
        else:
            self.mix[s:s + len(x)] += x

    def n(self, beats):
        return int(beats * self.beat * SR)

    def master(self, rev=0.2, fade_in=0.05, fade_out=1.5):
        m = reverb(self.mix, mix=rev) if rev else self.mix
        m = hp(m, 30)
        m = np.tanh(m * 1.2)
        m /= np.abs(m).max() / 0.9
        fi, fo = int(fade_in * SR), int(fade_out * SR)
        m[:fi] *= np.linspace(0, 1, fi)[:, None]
        m[-fo:] *= np.linspace(1, 0, fo)[:, None]
        return m


# ------------------------------------------------------------------ styles
def techno(seconds, seed, build=True, ending=False):
    T = Track(seconds, 128, seed)
    prog = [(57, [57, 60, 64]), (53, [53, 57, 60]), (48, [55, 60, 64]), (55, [55, 59, 62])]
    bars = int(np.ceil(seconds / (4 * T.beat)))
    for b in range(bars):
        root, ch = prog[b % 4]
        t0 = b * 4 * T.beat
        k = 0.5 if build and b < 2 else max(0.2, 1 - b / bars) if ending else 1.0
        pad = sum(saw(hz(c + 12), T.n(4), 0.006) for c in ch) / 3
        T.put(lp(pad, 2500) * env(T.n(4), 0.3, 9, 1, 0.1), t0, 0.12)
        for e in range(8):
            T.put(lp(saw(hz(root - 12), T.n(0.5)), 900) * env(T.n(0.5), 0.003, 0.1), t0 + e * T.beat / 2, 0.3 * k)
        for e in range(16):
            T.put(saw(hz(ch[[0, 1, 2, 1][e % 4]] + 24), T.n(0.25), 0.003) * env(T.n(0.25), 0.002, 0.07),
                  t0 + e * T.beat / 4, 0.08 * k, pan=0.4 * np.sin(e))
        for q in range(4):
            if not build or b >= 1:
                T.put(kick(T.n(1)), t0 + q * T.beat, 0.7 * k)
            if q % 2 and (not build or b >= 2):
                T.put(clap(T.n(0.5), T.rng), t0 + q * T.beat, 0.3 * k)
            T.put(hat(T.n(0.25), T.rng), t0 + (q + 0.5) * T.beat, 0.15 * k)
    return T.master(0.15, fade_out=3 if ending else 1)


def lofi(seconds, seed):
    T = Track(seconds, 80, seed)
    prog = [[62, 65, 69, 72], [55, 59, 62, 65], [60, 64, 67, 71], [57, 60, 64, 67]]   # Dm9 G7 Cmaj7 Am7
    bars = int(np.ceil(seconds / (4 * T.beat)))
    sw = 0.08
    for b in range(bars):
        ch = prog[b % 4]
        t0 = b * 4 * T.beat
        for i, c in enumerate(ch):
            T.put(epiano(hz(c), T.n(4)), t0 + i * 0.012, 0.11, pan=(i - 1.5) * 0.2)
        T.put(lp(tri(hz(ch[0] - 24), T.n(2)), 400) * env(T.n(2), 0.01, 1.5, 0.3, 0.1), t0, 0.35)
        T.put(lp(tri(hz(ch[0] - 24 + 7), T.n(2)), 400) * env(T.n(2), 0.01, 1.5, 0.3, 0.1), t0 + 2 * T.beat, 0.3)
        for q in range(4):
            if q in (0, 2) or (q == 3 and b % 2):
                T.put(lp(kick(T.n(1), 110, 45, 9, 0.05), 2000), t0 + q * T.beat + (0.25 * T.beat if q == 3 else 0), 0.55)
            if q in (1, 3):
                T.put(lp(snare(T.n(0.6), T.rng, 180, 10), 4000), t0 + q * T.beat, 0.25)
            for h in (0, 0.5):
                T.put(lp(hat(T.n(0.25), T.rng, 80), 9000), t0 + (q + h) * T.beat + (sw if h else 0), 0.07)
        if b % 2 == 1:   # petite mélodie
            for j, m in enumerate([ch[3] + 12, ch[2] + 12, ch[1] + 12]):
                T.put(bell(hz(m), T.n(1.5)), t0 + (j + 1) * T.beat, 0.05, pan=0.3)
    crackle = (T.rng.random(T.N) < 0.0008) * T.rng.uniform(-1, 1, T.N) * 0.3
    T.put(np.stack([crackle, crackle], 1) + T.rng.standard_normal((T.N, 2)) * 0.004, 0)
    m = T.master(0.3)
    return lp(m, 6500)


def synthwave(seconds, seed):
    T = Track(seconds, 100, seed)
    prog = [(52, [64, 67, 71]), (48, [60, 64, 67]), (55, [62, 67, 71]), (50, [62, 66, 69])]  # Em C G D
    bars = int(np.ceil(seconds / (4 * T.beat)))
    for b in range(bars):
        root, ch = prog[b % 4]
        t0 = b * 4 * T.beat
        pad = sum(saw(hz(c), T.n(4), 0.008, 5) for c in ch) / 3
        T.put(lp(pad, 1800) * env(T.n(4), 0.5, 9, 1, 0.3), t0, 0.16)
        for e in range(8):
            T.put(lp(saw(hz(root - 12), T.n(0.5), 0.004), 700) * env(T.n(0.5), 0.003, 0.15, 0.4, 0.02),
                  t0 + e * T.beat / 2, 0.3)
        for e in range(8):
            n = [ch[0], ch[1], ch[2], ch[1] + 12, ch[2], ch[1], ch[0] + 12, ch[2]][e]
            T.put(lp(saw(hz(n + 12), T.n(0.5), 0.002), 3500) * env(T.n(0.5), 0.002, 0.18), t0 + e * T.beat / 2,
                  0.07, pan=0.5 if e % 2 else -0.5)
        for q in range(4):
            T.put(kick(T.n(1), 120, 45, 6), t0 + q * T.beat, 0.6 if q % 2 == 0 else 0.0)
            if q % 2:
                T.put(reverb(np.stack([snare(T.n(1), T.rng, 200, 6)] * 2, 1), 2.5, 0.6), t0 + q * T.beat, 0.35)
            T.put(hat(T.n(0.25), T.rng), t0 + (q + 0.5) * T.beat, 0.1)
    return T.master(0.2)


def trap(seconds, seed):
    T = Track(seconds, 140, seed)
    prog = [57, 53, 55, 52]                       # A F G E (mineur)
    mel = [[69, 72, 76, 72], [65, 69, 72, 69], [67, 71, 74, 71], [64, 68, 71, 68]]
    bars = int(np.ceil(seconds / (4 * T.beat)))
    for b in range(bars):
        root = prog[b % 4]
        t0 = b * 4 * T.beat
        # 808 avec glissé
        n = T.n(3)
        t = t_(n)
        f = hz(root - 24) * (1 + 0.5 * np.exp(-t * 25))
        b808 = np.tanh(np.sin(2 * np.pi * np.cumsum(f) / SR) * 2) * env(n, 0.002, 1.2, 0.3, 0.1)
        T.put(b808, t0, 0.45)
        T.put(kick(T.n(1), 160, 50, 10), t0, 0.5)
        T.put(kick(T.n(1), 160, 50, 10), t0 + 2.5 * T.beat, 0.4)
        T.put(clap(T.n(0.7), T.rng), t0 + 2 * T.beat, 0.35)
        # charleston + roulements
        for s in range(8):
            T.put(hat(T.n(0.2), T.rng, 90), t0 + s * T.beat / 2, 0.12, pan=0.2)
        if b % 2:
            for r in range(6):
                T.put(hat(T.n(0.1), T.rng, 120), t0 + 3 * T.beat + r * T.beat / 6, 0.09, pan=0.2)
        for j, m in enumerate(mel[b % 4]):
            T.put(bell(hz(m + 12), T.n(1)), t0 + j * T.beat, 0.07, pan=-0.3)
        T.put(lp(sum(saw(hz(c), T.n(4), 0.01, 4) for c in mel[b % 4][:3]) / 3, 1200) * env(T.n(4), 0.4, 9, 1, 0.3),
              t0, 0.08)
    return T.master(0.2)


def house(seconds, seed):
    T = Track(seconds, 124, seed)
    prog = [[60, 63, 67, 70], [58, 62, 65, 69], [56, 60, 63, 67], [55, 58, 62, 65]]   # Cm7 Bb Ab G
    bars = int(np.ceil(seconds / (4 * T.beat)))
    for b in range(bars):
        ch = prog[b % 4]
        t0 = b * 4 * T.beat
        for q in range(4):
            T.put(kick(T.n(1), 140, 48, 8), t0 + q * T.beat, 0.65)
            T.put(hat(T.n(0.3), T.rng, 35), t0 + (q + 0.5) * T.beat, 0.16)
            if q % 2:
                T.put(clap(T.n(0.5), T.rng), t0 + q * T.beat, 0.28)
            T.put(lp(saw(hz(ch[0] - 24), T.n(0.5), 0.003), 600) * env(T.n(0.5), 0.003, 0.12, 0.3, 0.03),
                  t0 + (q + 0.5) * T.beat, 0.35)
        for st in (0, 1.5, 3):     # stabs d'accords type piano
            for c in ch:
                T.put(epiano(hz(c + 12), T.n(0.8)), t0 + st * T.beat, 0.05, pan=(c % 3 - 1) * 0.3)
    return T.master(0.18)


def epic(seconds, seed):
    T = Track(seconds, 90, seed)
    prog = [(45, [57, 60, 64]), (41, [57, 60, 65]), (48, [55, 60, 64]), (43, [55, 59, 62])]  # Am F C G
    bars = int(np.ceil(seconds / (4 * T.beat)))
    for b in range(bars):
        root, ch = prog[b % 4]
        t0 = b * 4 * T.beat
        k = min(1.0, 0.4 + b * 0.15)
        strings = sum(lp(saw(hz(c), T.n(4), 0.012, 6), 2200) for c in ch + [ch[0] + 12]) / 4
        T.put(strings * env(T.n(4), 0.6, 9, 1, 0.4), t0, 0.2)
        T.put(lp(saw(hz(root - 12), T.n(4), 0.005), 300) * env(T.n(4), 0.2, 9, 1, 0.3), t0, 0.3)
        for q, acc in ((0, 1), (1.5, 0.6), (2, 0.8), (3, 0.6), (3.5, 0.7)):
            tom = kick(T.n(1.5), 110, 60, 4, 0.1) + 0.3 * hp(T.rng.uniform(-1, 1, T.n(1.5)), 300) * np.exp(-t_(T.n(1.5)) * 20)
            T.put(tom, t0 + q * T.beat, 0.55 * acc * k)
        if b >= 2:
            for j, m in enumerate([ch[2] + 12, ch[1] + 12, ch[2] + 12, ch[0] + 24]):
                T.put(lp(saw(hz(m), T.n(1), 0.004), 3000) * env(T.n(1), 0.05, 0.6, 0.5, 0.1),
                      t0 + j * T.beat, 0.08 * k)
    return T.master(0.4, fade_out=2)


def save(mix, path):
    pcm = (np.clip(mix, -1, 1) * 32767).astype("<i2").tobytes()
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "s16le", "-ar", str(SR),
                    "-ac", "2", "-i", "-", "-b:a", "256k", str(path)], input=pcm, check=True)


if __name__ == "__main__":
    from pathlib import Path
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    (out / "musiques").mkdir(parents=True, exist_ok=True)
    save(techno(34, 1, build=False), out / "intro.mp3")
    save(techno(18, 2, build=False, ending=True), out / "outro.mp3")
    for name, fn in [("lofi", lofi), ("synthwave", synthwave), ("trap", trap), ("house", house), ("epic", epic)]:
        save(fn(26, 7), out / "musiques" / f"{name}.mp3")
        print(f"  {name}.mp3")
    print("musiques OK")

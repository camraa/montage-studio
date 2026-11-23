"""Bip sur les gros mots : ta voix est transcrite (faster-whisper, horodatage par mot), chaque gros mot
est coupé (son à 0) et remplacé par un bip à 1 kHz, dans le montage et dans les Shorts.

- liste française + anglaise + insultes racistes / homophobes, et « mots en plus » réglables
- transcription mise en cache par morceau (work/<rec>/voice_words.json) : un 2e rendu est instantané,
  et changer la liste de mots ne demande pas de retranscrire
"""
import json
import re
import unicodedata

from common import work_dir

# mot entier (après nettoyage : minuscules, sans accents ni ponctuation)
EXACT = {
    "con", "cons", "conne", "connes", "pd", "pds", "fdp", "ntm", "tg", "nik", "niq", "bite", "bites",
    "pute", "putes", "cul", "chier", "foutre", "batard", "batards", "batarde",
    "dick", "cunt", "cunts", "pussy", "whore", "slut", "bastard", "asshole", "twat", "wanker",
}
# début de mot
PREFIX = (
    "putain", "putin", "merde", "merdi", "connard", "connass", "conasse", "encul", "nique", "niqu",
    "salop", "salaud", "pede", "tapette", "tarlouz", "gouine", "couill", "enfoir", "batard",
    "negre", "negro", "nigg", "nigga", "bougnoul", "youpin", "bicot",
    "fuck", "motherfuck", "shit", "bitch", "fag",
)
PAD_BEFORE, PAD_AFTER, MIN_LEN = 0.05, 0.08, 0.25


def norm(w):
    w = unicodedata.normalize("NFKD", w.lower())
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9']", "", w).split("'")[-1]          # « l'enculé » -> « encule »


def extra_words(rc):
    return {norm(x) for x in re.split(r"[,;\n]+", rc.get("bleep_extra", "") or "") if norm(x)}


def is_swear(word, extra=()):
    w = norm(word)
    if not w:
        return False
    return w in EXACT or w in extra or w.startswith(PREFIX)


def mask(word):
    """Texte des sous-titres : « putain » -> « p***** », « l'enculé » -> « l'e***** »."""
    cut = max(word.rfind("'"), word.rfind("’")) + 1
    head, core = word[:cut], word[cut:]
    out, first = [], True
    for c in core:
        if c.isalpha():
            out.append(c if first else "*")
            first = False
        else:
            out.append(c)
    return head + "".join(out)


def windows(words, extra=(), offset=0.0):
    """[(début, fin)] à biper (fusionnées si proches), décalées de offset."""
    out = []
    for s, e, w in words:
        if not is_swear(w, extra):
            continue
        a, b = s - PAD_BEFORE + offset, max(e + PAD_AFTER, s + MIN_LEN) + offset
        if out and a - out[-1][1] < 0.15:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((max(0.0, a), b))
    return out


def voice_track(rc):
    t = int(rc.get("voice_track", -1))
    return t if t >= 0 else int(rc.get("audio_stream", 0))


def words_for(cfg, video, ranges, label="BIP"):
    """Mots de ta voix pour chaque morceau (début, fin) du rec -> {clé: [(s, e, mot)] relatifs au morceau}."""
    import transcribe
    track = voice_track(cfg["render"])
    cache_p = work_dir(cfg) / "voice_words.json"
    try:
        cache = json.loads(cache_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    key = lambda s, e: f"{track}:{s:.2f}-{e:.2f}"
    todo = [(s, e) for s, e in ranges if key(s, e) not in cache]
    total = sum(e - s for s, e in todo) or 1
    done = 0.0
    if todo:
        print(f"[{label}] transcription de ta voix ({total / 60:.0f} min)...", flush=True)
    for s, e in todo:
        ws = []
        for t0 in range(0, int(e - s) + 1, 600):                    # tranches de 10 min (mémoire maîtrisée)
            d = min(600, e - s - t0)
            if d <= 0.3:
                break
            a = transcribe.load_audio(video, s + t0, d, track=track)
            ws += [(round(a_ + t0, 2), round(b_ + t0, 2), w) for a_, b_, w in transcribe.words(
                a, lambda f, base=done + t0, d=d: print(f"\r[{label}] {min(100, (base + f * d) / total * 100):5.1f}%",
                                                      end="", flush=True))]
        done += e - s
        cache[key(s, e)] = ws
        cache_p.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    if todo:
        print(f"\r[{label}] 100.0%")
        transcribe.release()                                          # libère la carte graphique pour l'encodage
    return {(s, e): [tuple(x) for x in cache[key(s, e)]] for s, e in ranges}


def enable_expr(wins):
    return "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in wins)


def audio_filter(wins, src="[0:a]", out="[vx]", level=0.22):
    """Filtre ffmpeg : son coupé + bip sur les fenêtres. Une seule entrée, une sortie."""
    if not wins:
        return f"{src}anull{out}"
    e = enable_expr(wins)
    return (f"{src}aformat=sample_rates=48000:channel_layouts=stereo,volume=0:enable='{e}'[bx_dry];"
            f"sine=frequency=1000:sample_rate=48000,aformat=channel_layouts=stereo,volume={level},"
            f"volume=0:enable='eq({e},0)'[bx_beep];"
            f"[bx_dry][bx_beep]amix=inputs=2:duration=first:dropout_transition=0:normalize=0{out}")

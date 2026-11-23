"""Suivi de progression : une ligne par rec analysé (rangs Ranked, points de Cup, victoires Box).

Fichier : <données>/progression.json — mis à jour à chaque analyse et à chaque correction du plan
dans le studio (les rangs corrigés à la main remplacent ceux lus par le scan).
Sert à la vue « Progression » du studio et à préremplir les bannières (jour du grind, rang de départ...).
"""
import json
import re
import time
from datetime import date, datetime
from pathlib import Path

from common import DATA_DIR

PATH = DATA_DIR / "progression.json"
DATE_RE = re.compile(r"(20\d\d)[-_. ](\d\d)[-_. ](\d\d)")


def _load():
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"sessions": []}


def _save(d):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PATH)


def rec_date(video):
    """Date du rec : dans le nom OBS (2026-11-22 20-14-03.mkv), sinon date du fichier."""
    m = DATE_RE.search(Path(video).name)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
    try:
        return datetime.fromtimestamp(Path(video).stat().st_mtime).date().isoformat()
    except OSError:
        return date.today().isoformat()


def score(r):
    if not r or r.get("level") is None or r.get("pct") is None or r["level"] >= 17:
        return None
    return r["level"] * 100 + r["pct"]


def session_of(cfg, plan, timeline):
    fin = plan.get("final") or {}
    tl = {g["game"]: g for g in (timeline or {}).get("games", [])}
    kept = [g for g in plan.get("games", []) if not g.get("disabled")]
    kills = sum(len(tl.get(g["game"], {}).get("kills", [])) for g in kept)
    kind = "cup" if cfg["mode"] == "cup" else ("box" if cfg.get("mode_kind") == "box" else "ranked")
    s = {"id": f"{Path(cfg['video']).stem} [{cfg['mode']}]", "rec": Path(cfg["video"]).name,
         "date": rec_date(cfg["video"]), "mode": cfg["mode"], "label": cfg.get("mode_label") or cfg["mode"],
         "kind": kind, "games": len(kept), "kills": kills, "updated": int(time.time())}
    if kind == "cup":
        s.update(points=fin.get("points"), cup_games=fin.get("cup_games"))
    elif kind == "box":
        s.update(wins=fin.get("wins"), losses=fin.get("losses"))
    if kind == "ranked" or cfg.get("mode_rank"):
        rs, re_ = fin.get("rank_start"), fin.get("rank_end")
        s.update(rank_start=rs, rank_end=re_, gain=fin.get("session_gain"))
    return s


def record(cfg, plan, timeline=None):
    """Ajoute ou met à jour la session de ce rec (jamais bloquant pour le montage)."""
    try:
        d = _load()
        s = session_of(cfg, plan, timeline)
        old = next((x for x in d["sessions"] if x["id"] == s["id"]), None)
        if old:
            if old.get("hidden"):
                s["hidden"] = True
            if old.get("note"):
                s["note"] = old["note"]
            d["sessions"].remove(old)
        d["sessions"].append(s)
        d["sessions"].sort(key=lambda x: (x["date"], x["rec"]))
        _save(d)
    except Exception as e:
        print(f"[PROGRESSION] non enregistrée : {type(e).__name__}: {e}")


def sessions(include_hidden=False):
    return [s for s in _load()["sessions"] if include_hidden or not s.get("hidden")]


def hide(sid, hidden=True):
    d = _load()
    for s in d["sessions"]:
        if s["id"] == sid:
            s["hidden"] = hidden
    _save(d)


def summary(mode):
    """Résumé d'un mode (ex. ranked_br) pour les bannières : début du grind, rang actuel, jours..."""
    ss = [s for s in sessions() if s["mode"] == mode]
    if not ss:
        return {}
    first, last = ss[0], ss[-1]
    d0, d1 = date.fromisoformat(first["date"]), date.fromisoformat(last["date"])
    out = {"kind": first.get("kind"), "sessions": len(ss), "days": (d1 - d0).days + 1, "first_date": first["date"], "last_date": last["date"],
           "kills": sum(s.get("kills") or 0 for s in ss), "games": sum(s.get("games") or 0 for s in ss)}
    if first.get("kind") == "cup":
        pts = [s["points"] for s in ss if s.get("points") is not None]
        if pts:
            out.update(best_points=max(pts), avg_points=round(sum(pts) / len(pts)), last_points=pts[-1])
        return out
    start = next((s["rank_start"] for s in ss if (s.get("rank_start") or {}).get("name")), None)
    end = next((s["rank_end"] for s in reversed(ss) if (s.get("rank_end") or {}).get("name")), None)
    out.update(rank_start=start, rank_end=end, last_gain=last.get("gain"))
    if score(start) is not None and score(end) is not None:
        out["gain_total"] = score(end) - score(start)
    if start and end and start.get("level") is not None and end.get("level") is not None:
        out["divisions"] = end["level"] - start["level"]
    return out

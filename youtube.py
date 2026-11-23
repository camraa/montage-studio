"""Titre, description et tags YouTube générés à partir de l'analyse du rec.

- 3 titres proposés (le 1er est le conseillé), en majuscules, < 100 caractères
- description : résumé de la session, chapitres détaillés (kills, points / ELO par game), réseaux, hashtags
- tags (< 500 caractères au total, limite YouTube)
Sortie : <montage>.txt (à côté de la vidéo) + youtube.json dans le dossier de travail (lu par le studio).
"""
import json
from pathlib import Path

from common import load_config, work_dir


def _stamp(t):
    m, s = divmod(int(t), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _rank_txt(r):
    if not r or not r.get("name"):
        return None
    return r["name"] + (f" {r['pct']}%" if r.get("pct") is not None and r.get("level", 0) < 17 else "")


def _signed(v, unit):
    return f"{'+' if v >= 0 else '-'}{abs(v)}{unit}"


def game_infos(plan, timeline):
    """Par game du montage : kills, points gagnés (cup), ELO (ranked), score (box), dernier palier de top."""
    tl = {g["game"]: g for g in (timeline or {}).get("games", [])}
    out = []
    for g in plan.get("games", []):
        t = tl.get(g["game"], {})
        out.append({"game": g["game"], "kills": len(t.get("kills", [])),
                    "points": t.get("points_gained"), "gain": t.get("gain"), "score": t.get("score"),
                    "type": g["card"].get("type")})
    return out


def chapters_from_plan(plan, card_s):
    """Chapitres estimés depuis le plan (avant le rendu) : carton + morceaux de chaque game."""
    t, out = 0.0, []
    for g in plan.get("games", []):
        out.append((t, g["game"]))
        t += card_s + sum(s["end"] - s["start"] for s in g["segments"])
    return out, (t if plan.get("final") else None)


def build(cfg, plan, timeline, chapters=None, final_t=None):
    """chapters = [(secondes, numéro de game)] ; final_t = début du carton de fin (ou None)."""
    bn = load_config().get("banner", {})
    pseudo = (bn.get("pseudo") or "").strip()
    kind = plan.get("mode") == "cup" and "cup" or ((plan.get("final") or {}).get("type") or
                                                   (plan["games"][0]["card"].get("type") if plan.get("games") else "ranked"))
    label = plan.get("label") or cfg.get("mode_label") or "Fortnite"
    LABEL = label.upper()
    fin = plan.get("final") or {}
    infos = game_infos(plan, timeline)
    by_game = {i["game"]: i for i in infos}
    n = len(infos)
    kills = sum(i["kills"] for i in infos)
    best = max(infos, key=lambda i: i["kills"], default=None)
    if chapters is None:
        chapters, final_t = chapters_from_plan(plan, cfg["render"]["card_duration_s"])

    # ---------- titres
    titles = []
    if kind == "cup":
        cup = (bn.get("cup") or "").strip().upper() or "CUP"
        pts = fin.get("points")
        if pts is not None:
            titles.append(f"{pts} POINTS EN {cup} FORTNITE ({kills} KILLS)")
            titles.append(f"MA {cup} : {pts} POINTS EN {n} PARTIES")
        if best and best["kills"] >= 3:
            titles.append(f"{best['kills']} KILLS EN UNE PARTIE DE {cup}")
        titles.append(f"{cup} FORTNITE : TOUTES MES PARTIES ({kills} KILLS)")
    elif kind == "box":
        w, l = fin.get("wins", 0), fin.get("losses", 0)
        titles.append(f"{w} VICTOIRES EN {LABEL}" + (f" ({w}-{l})" if l else ""))
        g = fin.get("session_gain")
        if g:
            titles.append(f"{_signed(g, '%')} EN {LABEL} EN UNE SESSION")
        titles.append(f"SESSION {LABEL} : {n} MATCHS")
    else:
        g = fin.get("session_gain")
        rs, re_ = fin.get("rank_start") or {}, fin.get("rank_end") or {}
        if g is not None and g > 0:
            titles.append(f"+{g}% EN UNE SESSION {LABEL}" + (f" ({re_['name']})" if re_.get("name") else ""))
        if rs.get("name") and re_.get("name") and rs["name"] != re_["name"]:
            titles.append(f"DE {rs['name']} À {re_['name']} EN {n} GAMES ({LABEL})")
        if re_.get("name"):
            titles.append(f"SESSION {LABEL} EN {re_['name']} : {kills} KILLS")
        if best and best["kills"] >= 5:
            titles.append(f"{best['kills']} KILLS EN UNE GAME {LABEL}")
        titles.append(f"SESSION {LABEL} FORTNITE ({n} GAMES, {kills} KILLS)")
    seen, uniq = set(), []
    for t in titles:
        t = (t + (f" | {pseudo}" if pseudo and len(t) + len(pseudo) + 3 <= 100 else ""))[:100]
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    titles = uniq[:3]

    # ---------- chapitres
    word = "Partie" if kind == "cup" else "Match" if kind == "box" else "Game"
    lines = []
    for i, (t, num) in enumerate(chapters):
        inf = by_game.get(num, {})
        bits = [f"{inf.get('kills', 0)} kill{'s' if inf.get('kills', 0) > 1 else ''}"]
        if inf.get("points") is not None:
            bits.append(f"+{inf['points']} pts")
        if inf.get("gain") is not None:
            bits.append(_signed(inf["gain"], "%"))
        if inf.get("score"):
            bits.append(f"{inf['score'][0]}-{inf['score'][1]}")
        lines.append(f"{'00:00' if i == 0 else _stamp(t)} {word} {num} • " + " • ".join(bits))
    if final_t is not None and lines:
        lines.append(f"{_stamp(final_t)} Résultat final")

    # ---------- description
    res = []
    if kind == "cup":
        if fin.get("points") is not None:
            res.append(f"🏆 {fin['points']} points en {n} partie{'s' if n > 1 else ''}")
    elif kind == "box":
        res.append(f"🏆 {fin.get('wins', 0)} victoire(s), {fin.get('losses', 0)} défaite(s)")
    else:
        a, b = _rank_txt(fin.get("rank_start")), _rank_txt(fin.get("rank_end"))
        if a and b:
            res.append(f"📈 {a} → {b}" + (f" ({_signed(fin['session_gain'], '%')})"
                                          if fin.get("session_gain") is not None else ""))
    res.append(f"⚔️ {kills} kill{'s' if kills > 1 else ''} au total" +
               (f", record : {best['kills']} en {word.lower()} {best['game']}" if best and best["kills"] else ""))
    intro = {"cup": f"Toutes mes parties de {(bn.get('cup') or 'cup').strip()} en long format, sans coupure inutile.",
             "box": f"Session {label} en long format.",
             }.get(kind, f"Session {label} en long format : toutes les games, du début à la fin.")
    tags_mode = {"cup": ["cup fortnite", "fortnite cup", "cash cup fortnite", "fortnite tournoi", "fncs"],
                 "box": ["box fight fortnite", "fortnite 1v1", "fortnite box fight", "zone wars"],
                 }.get(kind, ["fortnite ranked", "ranked fortnite", "fortnite classé", "fortnite ranked fr"])
    socials = [s for s in (bn.get("reseau1"), bn.get("reseau2")) if s]
    hashtags = ["#fortnite", "#fortnitefr", {"cup": "#cupfortnite", "box": "#boxfight"}.get(kind, "#fortniteranked")]
    desc = "\n".join([intro, "", *res, "", "CHAPITRES", *lines] +
                     (["", "Mes réseaux :", *socials] if socials else []) + ["", " ".join(hashtags)])

    # ---------- tags (500 caractères max)
    tags = ["fortnite", "fortnite fr", label.lower(), f"fortnite {label.lower()}", *tags_mode]
    rk = (fin.get("rank_end") or {}).get("name")
    if rk:
        tags += [f"{rk.lower()} fortnite", f"fortnite {rk.lower()}"]
    if kind == "cup" and bn.get("cup"):
        tags.append(bn["cup"].lower())
    if pseudo:
        tags += [pseudo.lower(), f"{pseudo.lower()} fortnite"]
    tags += ["fortnite gameplay", "fortnite français", "fortnite long format"]
    out_tags, size = [], 0
    for t in dict.fromkeys(t.strip() for t in tags if t and t.strip()):
        if size + len(t) + 1 > 480:
            break
        out_tags.append(t)
        size += len(t) + 1
    return {"titles": titles, "title": titles[0] if titles else "", "description": desc, "tags": out_tags,
            "estimated": False}


def write(cfg, data, video_out=None):
    (work_dir(cfg) / "youtube.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    if video_out:
        txt = ("TITRES PROPOSÉS :\n" + "\n".join(f"  {i}. {t}" for i, t in enumerate(data["titles"], 1)) +
               "\n\nDESCRIPTION :\n" + data["description"] + "\n\nTAGS :\n" + ", ".join(data["tags"]) + "\n")
        p = Path(str(video_out)).with_suffix(".txt")
        p.write_text(txt, encoding="utf-8")
        print(f"[YOUTUBE] titre, description, tags -> {p.name}")


def for_project(cfg):
    """Texte YouTube d'un rec : celui du dernier rendu (chapitres exacts), sinon estimé depuis le plan."""
    wd = work_dir(cfg)
    p = wd / "youtube.json"
    plan_p, tl_p = wd / "edit_plan.json", wd / "timeline.json"
    if p.exists() and (not plan_p.exists() or p.stat().st_mtime >= plan_p.stat().st_mtime):
        return json.loads(p.read_text(encoding="utf-8"))
    if not plan_p.exists():
        return None
    plan = json.loads(plan_p.read_text(encoding="utf-8"))
    tl = json.loads(tl_p.read_text(encoding="utf-8")) if tl_p.exists() else None
    d = build(cfg, plan, tl)
    d["estimated"] = True
    return d

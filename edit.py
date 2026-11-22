"""Montage LONG FORMAT : timeline.json -> edit_plan.json

Toutes les parties sont gardées, dans l'ordre. Dans chaque partie on coupe seulement :
  - matchmaking / salon / chargement (tout ce qui est entre deux parties)
  - les X premières secondes de bus (edit.bus_skip_s)
  - les creux de plus de 5 min sans kill ni palier de top (on garde 20 s après / 60 s avant)
  - le spectate final quand ton équipe est éliminée (on en garde quelques secondes)
Avant chaque partie : carton récap (cup : partie X/Y + points ; ranked : rang + elo gagné).
"""
import json

from common import fmt_tc, work_dir


def cut_dead_time(start, end, g, ed):
    """Retire les creux > dead_gap_s entre deux événements (kill ou palier de top)."""
    events = sorted([k["t"] for k in g["kills"]] + [x["t"] for x in g.get("tops", [])])
    anchors = [start] + [e for e in events if start < e < end] + [end]
    segs = [[start, end]]
    for a, b in zip(anchors, anchors[1:]):
        if b - a <= ed["dead_gap_s"]:
            continue
        cut_a, cut_b = a + ed["dead_keep_after_s"], b - ed["dead_keep_before_s"]
        if b == end:                      # fin de partie : on garde quand même la mort / le top 1
            cut_b = end - ed["dead_keep_before_s"]
        if cut_b - cut_a < 30:
            continue
        last = segs[-1]
        segs[-1] = [last[0], cut_a]
        segs.append([cut_b, last[1]])
    return [(a, b) for a, b in segs if b - a > 2]


def build(cfg):
    ed = cfg["edit"]
    wd = work_dir(cfg)
    tl = json.loads((wd / "timeline.json").read_text(encoding="utf-8"))
    games = tl["games"]
    cup = cfg["mode"] == "cup"
    box = cfg.get("mode_kind") == "box"
    cup_games = (next((g["cup_games"] for g in games if g.get("cup_games")), None) or ed["cup_games"]) \
        if cup else None

    plan = {"video": tl["video"], "mode": cfg["mode"], "label": cfg["mode_label"],
            "cup_games": cup_games, "games": [], "final": None}
    total = 0.0
    prev = None
    first_rank = next((g["rank_before"] for g in games if g.get("rank_before")), None) if not cup else None
    session_gain = 0
    for g in games:
        start = g["start"] + ed["bus_skip_s"]
        end = g["end"] + ed["end_tail_s"]
        if g.get("final_spectate") is not None:
            end = min(end, g["final_spectate"] + ed["final_spectate_keep_s"])
        if end - start < 20:
            print(f"  GAME {g['game']:2d} trop courte, ignorée")
            continue
        prev_info = None if prev is None else {"game": prev["game"], "kills": len(prev["kills"]),
                                               "gained": prev.get("points_gained"), "gain": prev.get("gain"),
                                               "score": prev.get("score")}
        if cup:
            card = {"type": "cup", "partie": g["game"], "cup_games": cup_games,
                    "points": g["points_before"], "prev": prev_info and {
                        "partie": prev_info["game"], "gained": prev_info["gained"], "kills": prev_info["kills"]}}
        elif box:
            card = {"type": "box", "label": cfg["mode_label"], "game": g["game"],
                    "rank": g.get("rank_before") if cfg.get("mode_rank") else None, "prev": prev_info}
        else:
            card = {"type": "ranked", "label": cfg["mode_label"], "game": g["game"],
                    "rank": g.get("rank_before"), "prev": prev_info}
        segs = [(start, end)] if g.get("no_score") else cut_dead_time(start, end, g, ed)
        kept = sum(b - a for a, b in segs)
        plan["games"].append({"game": g["game"], "card": card, "segments": [
            {"start": round(a, 3), "end": round(b, 3), "start_tc": fmt_tc(a), "end_tc": fmt_tc(b)}
            for a, b in segs]})
        total += kept + cfg["render"]["card_duration_s"]
        if g.get("gain") is not None:
            session_gain += g["gain"]
        print(f"  GAME {g['game']:2d}  gardé {kept / 60:4.1f} / {(end - start) / 60:4.1f} min "
              f"({len(segs)} morceau(x))  kills={len(g['kills'])}")
        prev = g

    if prev is not None and cfg["render"].get("final_card", True):
        last = {"game": prev["game"], "kills": len(prev["kills"]),
                "gained": prev.get("points_gained"), "gain": prev.get("gain"), "score": prev.get("score")}
        if cup:
            plan["final"] = {"type": "cup", "points": tl.get("final_points"), "parties": len(plan["games"]),
                             "cup_games": cup_games,
                             "last": {"partie": last["game"], "gained": last["gained"], "kills": last["kills"]},
                             "history": [{"partie": g["game"], "gained": g.get("points_gained"),
                                          "total": (g["points_before"] or 0) + (g.get("points_gained") or 0)
                                          if g.get("points_before") is not None else None,
                                          "kills": len(g["kills"])} for g in games]}
        elif box:
            sc_ = [g["score"] for g in games if g.get("score")]
            last_rank = next((g["rank_after"] for g in reversed(games) if g.get("rank_after")), None)
            plan["final"] = {"type": "box", "label": cfg["mode_label"], "games": len(plan["games"]),
                             "wins": sum(1 for s in sc_ if s[0] > s[1]), "losses": sum(1 for s in sc_ if s[0] < s[1]),
                             "rounds": [sum(s[0] for s in sc_), sum(s[1] for s in sc_)],
                             "rank_start": first_rank, "rank_end": last_rank if cfg.get("mode_rank") else None,
                             "session_gain": session_gain if any(g.get("gain") is not None for g in games) else None,
                             "last": last}
        else:
            last_rank = next((g["rank_after"] for g in reversed(games) if g.get("rank_after")), None)
            plan["final"] = {"type": "ranked", "label": cfg["mode_label"], "games": len(plan["games"]),
                             "rank_start": first_rank, "rank_end": last_rank,
                             "session_gain": session_gain if any(g.get("gain") is not None for g in games) else None,
                             "last": last}
        total += cfg["render"]["card_duration_s"]

    out = wd / "edit_plan.json"
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    h, rem = divmod(int(total), 3600)
    print(f"[OK] {out.name} -> durée du montage : {h} h {rem // 60:02d} min")
    return out

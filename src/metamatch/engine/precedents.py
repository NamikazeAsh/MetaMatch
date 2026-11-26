"""
Real game precedents: for a threat to your team, a public ladder replay where a team sharing several of your
members faced it and one of those shared members knocked it out (engine/team_neighbors' corpus, the knockouts the
Replay Auditor's parser read from each game). It's an example to watch, with the turn it happened: never a win
rate, and never a claim about who won the game.
"""
from metamatch.engine.team_neighbors import MIN_SHARED, base, corpus


def precedent(team_names, threat, format_id, min_shared=MIN_SHARED, prefer=()):
    """The best example game, or None: {id, rating, time, turn, by (your member), threat, shared}. Best means a
    knockout by a member in `prefer` (the ones the Threat Board says beat it, so the example agrees with the board
    beside it), then the team sharing the most of yours, then the higher rated game, then the newer one."""
    preferred = {base(n) for n in prefer}
    mine = {base(n) for n in team_names if n}
    target = base(threat)
    best = None
    for key, t in corpus(format_id).items():
        shared = mine & key
        if len(shared) < min_shared:
            continue
        for r in t["records"]:
            for turn, by, fainted in r.get("kos") or []:
                if base(fainted) != target or base(by) not in shared:
                    continue
                cand = {"id": r["id"], "rating": r.get("rating") or 0, "time": r.get("time") or 0, "turn": turn,
                        "by": base(by), "threat": target, "shared": len(shared)}
                rank = (cand["by"] in preferred, cand["shared"], cand["rating"], cand["time"])
                if best is None or rank > best[0]:
                    best = (rank, cand)
    return best[1] if best else None


def line(p):
    """'In a 1,720 rated ladder game, Great Tusk knocked out Kingambit on turn 23 (a team sharing 4 of your
    members).' for a precedent."""
    rating = f"{p['rating']:,} rated " if p["rating"] else ""
    return (f"In a {rating}ladder game, {p['by']} knocked out {p['threat']} on turn {p['turn']} "
            f"(a team sharing {p['shared']} of your members).")

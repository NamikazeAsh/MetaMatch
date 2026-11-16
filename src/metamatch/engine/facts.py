"""
Typed fact constructors: engine results turned into packet facts (engine/packet.py), one plain claim each, with the
owner word on every Pokemon and units on every number. The exact engine wording goes in `detail` for the dropdown.
"""
from metamatch.engine.packet import Fact, cap, hits, mon, pct


def _side(name, mine):
    return mon(name, mine)


def exchange_facts(x, member, opponent, verdict=None, mirror=False):
    """Facts for one team member against one opposing set (briefing.exchange output `x`): who wins, Speed, the
    member's best hit, the opponent's best hit, and who finishes first with priority. `mirror`: the opponent is the
    same species as the member (owner words matter most there)."""
    me, them = _side(member, True), _side(opponent, False)
    out = []
    if verdict in ("win", "lose", "even"):
        word = {"win": "beats", "lose": "loses to", "even": "trades evenly with"}[verdict]
        out.append(Fact("matchup", f"{cap(me)} {word} {them} one on one.",
                        {"member": member, "opponent": opponent, "verdict": verdict}))
    out.append(speed_share_fact(x, me, them))
    for direction in ("dealt", "taken"):
        f = _hit_fact(x, direction, me, them)
        if f:
            out.append(f)
    pri, move = x.get("priority", (0, None))
    if move and x.get("to_ko") == x.get("to_be_koed"):
        out.append(Fact("speed", f"{cap(me)} lands the last hit first with {move}, a priority move.",
                        {"member": member, "move": move}))
    opp_pri, opp_move = x.get("opp_priority", (0, None))
    if opp_move and x.get("to_ko") == x.get("to_be_koed"):
        out.append(Fact("speed", f"{cap(them)} lands the last hit first with {opp_move}, a priority move.",
                        {"opponent": opponent, "move": opp_move}))
    return out


def speed_share_fact(x, me, them):
    share, ties = x.get("outspeeds", 0.0), x.get("ties", 0.0)
    if ties >= 0.95:
        text, first = f"{cap(me)} and {them} have the same Speed, so either can move first.", "tie"
    elif share >= 0.95:
        text, first = f"{cap(me)} moves before {them}.", "member"
    elif share + ties <= 0.05:
        text, first = f"{cap(them)} moves before {me}.", "opponent"
    else:
        text, first = f"{cap(me)} outspeeds {round(share * 100)}% of {them}'s ladder sets.", "mixed"
    return Fact("speed", text, {"first": first, "outspeeds_share": round(share, 3), "speed": x.get("speed")})


def _hit_fact(x, direction, me, them):
    """'Your Dragapult's Draco Meteor does 74 to 88% of the opposing Landorus's HP, knocking it out in 2 hits.'"""
    pair = x.get(direction)
    if not pair:
        if direction == "taken":
            return Fact("damage", f"{cap(them)}'s usual attacks do no damage to {me}.", {"direction": direction,
                                                                                            "immune": True})
        return Fact("damage", f"{cap(me)} has no attack that damages {them}.", {"direction": direction, "immune": True})
    move, r = pair
    attacker, defender = (me, them) if direction == "dealt" else (them, me)
    worst = x.get("to_ko" if direction == "dealt" else "to_be_koed")
    best = x.get("to_ko_best" if direction == "dealt" else "to_be_koed_best")
    lo, hi = r["percent"]
    if r.get("half_hp"):
        text = f"{cap(attacker)}'s {move} takes half of {defender}'s current HP"
        ko_pair = x.get("dealt_ko_move" if direction == "dealt" else "taken_ko_move")
        turns = (f"{best} or {worst}" if best and best != worst else f"{worst}") if worst else ""
        text += (f", then {ko_pair[0]} finishes, {turns} turns in all." if ko_pair and worst
                 else "; that alone never knocks out.")
    else:
        text = f"{cap(attacker)}'s {move} does {pct(lo, hi)} of {defender}'s HP"
        count = hits(worst, best)
        text += f", knocking it out {count}." if count else "."
    return Fact("damage", text, {"direction": direction, "move": move, "pct": [lo, hi], "hits": worst, "hits_best": best,
                                 "half_hp": bool(r.get("half_hp"))}, detail=r.get("desc", ""))


def stated_fact(who, summary):
    return Fact("stated", f"The question states for {who}: {summary}.", {"who": who})


def basis_fact(opponent, basis):
    return Fact("stated", f"{cap(mon(opponent, False))} is assumed on {basis}; switching, hazards and setup are not "
                          "counted.", {"opponent": opponent, "basis": basis})

"""
Engine facts for strategy answers. A 3B model can't reliably reason over a damage table, so the
engine also draws the conclusions: which team members win a one on one against a named opponent
or a top meta threat, which lose, and which members are the team's likely win conditions.
Oak gets this so his advice is built on computed verdicts instead of the model's memory.
"""
import math
from dataclasses import dataclass, field

from metamatch import config
from metamatch.engine.dex import dex_for_format
from metamatch.engine import mechanics
from metamatch.engine.sets import calc_spec, likely_set
from metamatch.engine.solvers import user_spec
from metamatch.logic_engine import best_hits
from metamatch.suggestions import compute_threats
from metamatch.type_chart import TYPE_CHART


def _mult(x):
    return f"{x:g}x"


def team_weaknesses(team):
    """Attack types that hit at least two members super effectively and more members than resist them."""
    lines = []
    for atk_type in TYPE_CHART:
        weak, resist = [], []
        for p in team.values():
            mult = p.get("Damage From", {}).get(atk_type.lower(), 1.0)
            if mult >= 2.0:
                weak.append(f"{p['Pokemon']} ({_mult(mult)})")
            elif mult <= 0.5:
                resist.append(f"{p['Pokemon']} ({'immune' if mult == 0 else _mult(mult)})")
        if len(weak) >= 2 and len(weak) > len(resist):
            lines.append(f"{atk_type}: weak {', '.join(weak)}; resisted by {', '.join(resist) or 'nobody'}.")
    return lines


def _hits_to_ko(result):
    """Hits needed at the lowest roll, or None when the move does no damage."""
    lo = result["percent"][0] if result else 0
    return math.ceil(100 / lo) if lo > 0 else None


def _kill_priority(pairs, k, attacker, defender, dex):
    """(priority, move) of the strongest priority bracket that can land the k-th, killing hit."""
    if not pairs or k is None:
        return 0, None
    best = pairs[0][1]
    hp = best["defender_stats"]["hp"]
    effect = mechanics.survival_effect(best, attacker, defender, pairs[0][0])
    before = mechanics._total(best, k - 1, effect)[0] if k > 1 else 0
    top = (0, None)
    for move, r in pairs:
        pri = mechanics.move_priority(move, dex, attacker, turn=k)
        first_hit = mechanics._total(r, 1, effect if k == 1 else None)[0]
        if pri > top[0] and before + first_hit >= hp:
            top = (pri, move)
    return top


def exchange(p, opp_set, game, dex):
    """
    One on one numbers for a team member vs an opponent set: speed share (Choice Scarf mixed in at its
    usage share), best hit each way, hits to KO each way (Sturdy, Sash and Disguise aware) and the
    priority each side can finish with. None when the calc is unavailable.
    """
    hits = best_hits(p, opp_set, game, dex, n=4)
    if hits is None:
        return None
    dealt, taken = hits
    mine, theirs = user_spec(p, game), calc_spec(opp_set)
    speeds = opp_set.get("speeds") or []
    # Final Speed from the same calc call the damage came from, so it matches the chat speed solver
    user_speed = next((r.get("attacker_speed") for _, r in dealt), None) or p.get("Speed", 0)
    to_ko = mechanics.hits_to_ko(dealt[0][1], mine, theirs, dealt[0][0]) if dealt else None
    to_be_koed = mechanics.hits_to_ko(taken[0][1], theirs, mine, taken[0][0]) if taken else None
    return {
        "name": p["Pokemon"],
        "speed": user_speed,
        "outspeeds": mechanics.scarf_adjusted_share(user_speed, speeds, opp_set.get("scarf_share", 0.0)),
        "dealt": dealt[0] if dealt else None,
        "taken": taken[0] if taken else None,
        "to_ko": to_ko,
        "to_be_koed": to_be_koed,
        "priority": _kill_priority(dealt, to_ko, mine, theirs, dex),
        "opp_priority": _kill_priority(taken, to_be_koed, theirs, mine, dex),
    }


def _verdict(x):
    """'win', 'lose' or 'even' for a one on one exchange, ignoring switching and setup."""
    mine, theirs = x["to_ko"], x["to_be_koed"]
    if mine is None:
        return "lose" if theirs else "even"
    if theirs is None:
        return "win"
    # On the turn both would land the KO, the higher priority finisher moves first, then Speed
    pri, opp_pri = x.get("priority", (0, None))[0], x.get("opp_priority", (0, None))[0]
    faster = pri > opp_pri or (pri == opp_pri and x["outspeeds"] >= 0.5)
    if mine < theirs or (mine == theirs and faster):
        return "win"
    if theirs == 1 or mine > theirs or (mine == theirs and not faster):
        return "lose"
    return "even"


def _hko(n):
    return "OHKO" if n == 1 else f"{n}HKO"


def _hit(pair):
    move, r = pair
    lo, hi = r["percent"]
    return f"{move} {lo:g}-{hi:g}%"


def _reason(x):
    """'faster; Earthquake 69-82% (2HKO); takes Iron Head 43-51% (3HKO)'"""
    share = x["outspeeds"]
    speed = "faster" if share >= 0.95 else "slower" if share <= 0.05 else f"faster than {share * 100:.0f}% of sets"
    if x.get("priority", (0, None))[1] and x["to_ko"] == x["to_be_koed"]:
        speed += f", finishes first with {x['priority'][1]}"
    if x.get("opp_priority", (0, None))[1] and x["to_ko"] == x["to_be_koed"]:
        speed += f", but it finishes with {x['opp_priority'][1]}"
    dealt = f"{_hit(x['dealt'])} ({_hko(x['to_ko'])})" if x["dealt"] else "no damaging move"
    taken = f"takes {_hit(x['taken'])} ({_hko(x['to_be_koed'])})" if x["taken"] else "takes no damage"
    return f"{speed}; {dealt}; {taken}"


@dataclass
class Matchup:
    """One on one verdicts for the whole team vs one opponent's likely set."""
    opponent: str
    wins: list = field(default_factory=list)     # exchange dicts, strongest answer first
    losses: list = field(default_factory=list)   # exchange dicts, worst loss first

    def fact_lines(self, max_losses=6):
        lines = [f"Best answers to {self.opponent}: "
                 + ("; ".join(f"{x['name']} ({_reason(x)})" for x in self.wins) or "none one on one")]
        if self.losses:
            lines.append(f"Loses to {self.opponent}: "
                         + "; ".join(f"{x['name']} ({_reason(x)})" for x in self.losses[:max_losses]))
        return lines

    def summary(self, max_losses=3):
        """'answer Corviknight, Garchomp; loses: Dragapult (OHKO'd by Sucker Punch), Venusaur'"""
        answers = ", ".join(x["name"] for x in self.wins) or "no one on one answer"
        losers = [x["name"] + (f" (OHKO'd by {x['taken'][0]})" if x["to_be_koed"] == 1 else "")
                  for x in self.losses[:max_losses]]
        return f"answers: {answers}" + (f"; loses: {', '.join(losers)}" if losers else "")


def matchup_verdicts(team, opponent, format_id):
    """Matchup for `opponent`'s likely set, or None without usage data or the calc."""
    opp_set = likely_set(opponent, format_id)
    dex = dex_for_format(format_id)
    if not opp_set or not dex:
        return None
    game = config.format_game(format_id)
    rows = [x for x in (exchange(p, opp_set, game, dex) for p in team.values()) if x]
    if not rows:
        return None
    wins = [x for x in rows if _verdict(x) == "win"]
    losses = [x for x in rows if _verdict(x) == "lose"]
    # Strongest answers first: fewest hits to KO it, then most hits it needs; worst losses first
    wins.sort(key=lambda x: (x["to_ko"] or 99, -(x["to_be_koed"] or 99)))
    losses.sort(key=lambda x: (x["to_be_koed"] or 99, -(x["to_ko"] or 99)))
    return Matchup(opp_set["name"], wins, losses)


def win_conditions(team):
    """Setup sweepers and weather abusers backed by a setter on the same team."""
    roles = {p["Pokemon"]: set(p.get("Roles", [])) for p in team.values()}
    has_setter = any("Weather Setter" in r for r in roles.values())
    return [name for name, r in roles.items()
            if "Setup Sweeper" in r or ("Weather Abuser" in r and has_setter)]


def _engine_facts(team, format_id, per_engine=3):
    """Plain lines about each team engine for the coach's facts block; [] without the calc or a core."""
    from metamatch.engine import synergy
    try:
        engines = synergy.team_engines(team, format_id)
    except Exception:
        return []
    lines = []
    for e in engines[:3]:
        lines.append(synergy.describe(e))
        detail = [f"{u.name}: {pt}" for u in e.users if u.major for pt in u.points[:2]][:per_engine]
        detail += e.drawbacks[:2]
        if e.partners:
            detail.append(f"Ladder players pair it with {', '.join(e.partners)}")
        lines += [f"  {d}" for d in detail]
    return lines


@dataclass
class Briefing:
    facts: str = ""                                  # ENGINE FACTS block for the LLM prompt
    summary: str = ""                                # markdown verdicts shown to the user
    matchups: list = field(default_factory=list)     # Matchup per named opponent or top threat


def strategy_briefing(team, opponents=(), n_threats=3):
    """Engine facts and a short user facing summary for a strategy question about `team`."""
    if not team:
        return Briefing()
    format_id = config.team_format(team)
    sections, bullets, matchups = [], [], []

    for opponent in list(opponents)[:2]:
        m = matchup_verdicts(team, opponent, format_id)
        if m:
            matchups.append(m)
            sections.append(f"Vs {m.opponent} (its most common set, one on one):\n"
                            + "\n".join(f"- {l}" for l in m.fact_lines()))
            bullets.append(f"**Vs {m.opponent}** {m.summary()}")

    wincons = win_conditions(team)
    if wincons:
        sections.append("Likely win conditions (setup sweepers and weather abusers): " + ", ".join(wincons) + ".")
        bullets.append(f"**Likely win conditions:** {', '.join(wincons)}")

    # The cores the team is built around (sun, rain, Trick Room...), measured with the calc
    engine_lines = _engine_facts(team, format_id)
    if engine_lines:
        sections.append("Team engines:\n" + "\n".join(f"  - {l.strip()}" if l.startswith("  ") else f"- {l}" for l in engine_lines))
        bullets.append("**Team engines:** " + "; ".join(l for l in engine_lines if not l.startswith("  ")))

    # Threat verdicts only when no opponent was named, to keep the prompt short
    if not opponents:
        for t in compute_threats(team, format_id, top_n=n_threats):
            m = matchup_verdicts(team, t["pokemon"], format_id)
            head = f"Top meta threat {t['pokemon']}: {t['explanation']}"
            if m:
                matchups.append(m)
                head += "\n" + "\n".join(f"- {l}" for l in m.fact_lines(max_losses=3))
                bullets.append(f"**Threat {m.opponent}** {m.summary()}")
            sections.append(head)

    weak = team_weaknesses(team)
    if weak:
        sections.append("Shared weaknesses:\n" + "\n".join(f"- {w}" for w in weak))
        bullets.append("**Shared weaknesses:** " + ", ".join(w.split(":")[0] for w in weak))

    if not sections:
        return Briefing()
    facts = ("### ENGINE FACTS (computed by MetaMatch; trust these over your own memory)\n"
             + "\n\n".join(sections) + "\n")
    summary = "**Engine check** (most common sets, one on one)\n" + "\n".join(f"* {b}" for b in bullets)
    return Briefing(facts, summary, matchups)

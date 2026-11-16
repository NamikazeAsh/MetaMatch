"""
Builds the answer packet (engine/packet.py) for a planned question: the engine's answer sentence, typed facts, the
facts the model may explain, what was not counted, and which dashboard category and tab the answer belongs to.
"""
from metamatch.engine.packet import Fact, Packet, plainify

# Intent -> (category, persona, dashboard tab the answer comes from)
CATEGORIES = {
    "checks": ("matchups", "strategy", "Threat Board"),
    "matchup": ("matchups", "strategy", "Threat Board"),
    "switchins": ("matchups", "strategy", "Threat Board"),
    "threats": ("matchups", "strategy", "Threat Board"),
    "speed": ("speed", "mechanics", "Speed Tiers"),
    "speed_spread": ("speed", "mechanics", "Speed Tiers"),
    "usage": ("building", "builder", "Team Completer"),
    "compare": ("building", "builder", "Audit"),
    "teammate": ("building", "builder", "Team Completer"),
    "roles": ("building", "builder", "Team Overview"),
    "score": ("score", "strategy", "Team Overview"),
    "win": ("gameplan", "strategy", "Coach Guide"),
    "lead": ("gameplan", "strategy", "Coach Guide"),
    "tera": ("gameplan", "strategy", "Coach Guide"),
    "member": ("gameplan", "strategy", "Coach Guide"),
    "gameplan": ("gameplan", "strategy", "Coach Guide"),
    "rules": ("rules", "mechanics", ""),
    "type": ("rules", "mechanics", "Matchup Matrices"),
    "team_type": ("rules", "mechanics", "Matchup Matrices"),
    "damage": ("rules", "mechanics", ""),
    "ko": ("rules", "mechanics", ""),
    "stat": ("rules", "mechanics", ""),
}


def category_of(intent):
    return CATEGORIES.get(intent, ("open", "strategy", ""))


def packet_for(question, plan, verdict):
    """The packet for an engine answered question. Verdicts without typed facts yet fall back to their exact engine
    lines (kind 'engine'), so every answer has the same shape while solvers are converted."""
    category, persona, link = category_of(verdict.intent)
    p = Packet(question=question, intent=verdict.intent, category=category, persona=verdict.persona or persona,
               answer=verdict.plain or plainify(verdict.statement), link=link)
    if verdict.typed:
        for f in verdict.typed:
            p.add(Fact(f.kind, f.text, dict(f.data), f.role, f.detail), why=f.role == "why")
    else:
        for line in verdict.facts:
            p.add(Fact("engine", plainify(line), {}, "context", line))
    if not p.why and p.facts:
        p.why.append(p.facts[0].id)
    for c in getattr(plan, "unhandled", None) or []:
        p.caveats.append(f"{c} is not counted.")
    return p

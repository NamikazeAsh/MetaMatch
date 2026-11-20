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
    "archetype": ("matchups", "strategy", "Threat Board"),
    "weather": ("gameplan", "strategy", "Coach Guide"),
    "speed_tiers": ("speed", "mechanics", "Speed Tiers"),
    "audit": ("building", "builder", "Audit"),
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
    # Tera usage sits next to the Coach Guide's Tera plan, which shows Smogon's pick and the ladder's side by side
    if verdict.intent == "usage" and getattr(plan, "usage_field", None) == "tera":
        link = "Coach Guide"
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
    p.cards = pair_cards(verdict, plan) + smogon_cards(plan)
    return p


def pair_cards(verdict, plan):
    """For a matchup answer ("what checks Kingambit", "who switches into it", "how does my Corviknight do"), Smogon's
    sentence about each member and the opponent, quoted under the engine's verdicts: the members that win first.
    The sentence is never read as a verdict (rag/pair_quotes.py)."""
    if verdict.intent not in ("checks", "switchins", "matchup") or not verdict.other or plan is None:
        return []
    if verdict.intent == "matchup":
        members = [verdict.subject]
    else:
        winners = [m for m in (verdict.answer or "").split(", ") if m and m != "none"]
        members = winners + [m for m in verdict.losers if m not in winners]
    try:
        from metamatch.rag.pair_quotes import quotes_for
        # Two at most: on held out pairs about one quote in ten was still off (docs/research/rag_2_0_checks_test.md)
        return quotes_for([m for m in members if m], verdict.other, plan.format_id, limit=2)
    except Exception as e:   # the analyses are a bonus, never a reason an answer fails
        print(f"Smogon matchup quotes failed: {e}")
        return []


def smogon_cards(plan):
    """Smogon analysis cards for the Pokemon the question is about: the opponent first, else the named member."""
    if plan is None:
        return []
    names = list(getattr(plan, "opponents", None) or [])
    user = getattr(plan, "user", None)
    if user is not None and getattr(plan, "user_named", False):
        names.append(user.get("Forme") or user.get("Pokemon"))
    try:
        from metamatch.rag.cards import cards_for
        return cards_for(names, plan.format_id, limit=1)
    except Exception as e:   # the cache is optional
        print(f"Smogon card failed: {e}")
        return []

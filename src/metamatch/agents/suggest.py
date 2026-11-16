"""
Close questions the engine can answer, offered as clickable chips when a question falls outside what it works out.
Each suggestion is built from what the question names (an opposing Pokemon, a team member, a weather or archetype, a
topic word) and kept only if the planner routes it to an engine answer, so every chip answers exactly.
The chat tab reads them from a marker at the end of the spoken part of a reply.
"""
import re

SUGGEST_MARK = "<!--suggest:"
SUGGEST_RE = re.compile(r"\n*<!--suggest:(.*?)-->", re.S)

# Topic words in the question -> team level questions the engine answers
TOPICS = [
    (re.compile(r"\b(?:lead|leads|start|open\w*)\b", re.I), "What should I lead?"),
    (re.compile(r"\b(?:win\w*|sweep\w*|clean\w*|clos\w+ out|endgame|late game)\b", re.I), "What's my win condition?"),
    (re.compile(r"\b(?:threat\w*|scar\w*|problem\w*|struggl\w*|trouble|counter\w*|lose|losing)\b", re.I),
     "What are my biggest threats?"),
    (re.compile(r"\btera\w*\b", re.I), "Who should I Tera?"),
    (re.compile(r"\b(?:speed|fast\w*|slow\w*|outspeed\w*|priority)\b", re.I), "Walk me through my speed tiers"),
    (re.compile(r"\b(?:replac\w*|swap\w*|chang\w*|improv\w*|fix\w*|better|build\w*|audit)\b", re.I),
     "What did the audit flag?"),
    (re.compile(r"\b(?:weak\w*|resist\w*|typ\w+)\b", re.I), "What am I weak to?"),
    (re.compile(r"\b(?:good|rate|score|strong|viable)\b", re.I), "Is my team good?"),
    (re.compile(r"\b(?:weather|rain|sun|sand|snow)\b", re.I), "How do I use weather on my team?"),
]
DEFAULTS = ["Walk me through my game plan", "What are my biggest threats?", "What's my win condition?"]
ARCHETYPES = re.compile(r"\b(rain|sun|sand|stall|hazard stack\w*)\b", re.I)


def _candidates(query, plan, team):
    """Two about what the question names, then its archetype and topic words, then the rest, then team defaults."""
    named = []
    for name in (getattr(plan, "opponents", None) or [])[:2]:
        named += [f"How do I beat {name}?", f"Who can switch into {name}?", f"What does {name} usually run?"]
    user = getattr(plan, "user", None)
    if user is not None and getattr(plan, "user_named", False):
        name = user["Pokemon"]
        named += [f"Why is {name} on my team?", f"What is my {name} weak to?", f"What does {name} usually run?"]
    topical = []
    arche = ARCHETYPES.search(query)
    if arche:
        topical.append(f"How do I play against {arche.group(1).lower()}?")
    topical += [q for pattern, q in TOPICS if pattern.search(query)]
    return named[:2] + topical + named[2:] + DEFAULTS


def suggestions(query, plan, team, limit=3):
    """Up to `limit` questions close to `query` that the engine answers, most specific first."""
    from metamatch.engine.planner import plan_query
    seen, out = set(), []
    for q in _candidates(query, plan, team):
        if q in seen or q.lower().rstrip("?") == query.lower().strip().rstrip("?"):
            continue
        seen.add(q)
        try:
            intent = plan_query(q, team).intent
        except Exception:
            continue
        if intent not in ("open", "clarify"):
            out.append(q)
        if len(out) == limit:
            break
    return out


def marker(questions):
    return f"\n\n{SUGGEST_MARK}{'|'.join(questions)}-->" if questions else ""


def split(text):
    """(text without the marker, [suggested questions])."""
    m = SUGGEST_RE.search(text or "")
    if not m:
        return text, []
    return SUGGEST_RE.sub("", text), [q for q in m.group(1).split("|") if q.strip()]

"""
Professor Oak, the strategy agent. Strategy questions get the engine's briefing (one on one
verdicts vs named opponents and top threats, win conditions, shared weaknesses). For questions
about threats, opponents or win conditions the verdicts are shown first as an "Engine check";
the LLM's advice is shown only if it passes a verifier, with one retry.
"""
import re

from .client import get_agent_client
from .grounded import FREE_NUMBERS, _numbers
from metamatch import config
from metamatch.engine.briefing import Briefing
from metamatch.engine.names import find_pokemon
from metamatch.rag import store

# Retrieved analyses can run past 3,000 characters; a 3B model loses the engine facts behind them
RAG_CHARS = 700
# Questions where the engine's verdicts are the core of the answer
SUMMARY_RE = re.compile(r"\b(threats?|counters?|struggle\w*|win ?con\w*|weakness\w*|weak to)", re.I)
RECOMMEND = re.compile(r"\b(answer|counter|handle|best|deal with|check|beat|use|great|ideal|recommend|switch|option|"
                       r"take (?:out|down)|viable|good|strong|effective|key|reliable)", re.I)
CAUTION = re.compile(r"\b(lose|loses|avoid|struggle|weak|ohko|threat|vulnerable|careful|risk|not|can't|cannot|don't|no )", re.I)


def _trim(text, limit=RAG_CHARS):
    """Cuts text to `limit` characters at the last sentence end."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = cut.rfind(". ")
    return cut[:end + 1] if end > limit // 2 else cut + "..."


def _relevant(hit, focus_text):
    """Concept chunks always count; Pokemon chunks only when that Pokemon is on the team or in the facts."""
    subject = hit["metadata"].get("pokemon") or ""
    return hit["metadata"].get("type") == "concept" or not subject or subject.lower() in focus_text


def _move_owner_clash(advice, team):
    """A sentence naming exactly one team member alongside a move only another member runs."""
    moves = {p["Pokemon"]: {m["name"] for m in p.get("Moves", [])} for p in team.values()}
    for sentence in re.split(r"(?<=[.!?])\s+", advice):
        lowered = sentence.lower()
        named = [n for n in moves if n.lower() in lowered]
        if len(named) != 1:
            continue
        for other, other_moves in moves.items():
            for move in other_moves - moves[named[0]]:
                if re.search(rf"\b{re.escape(move.lower())}\b", lowered):
                    return f"a claim that {named[0]} uses {move}, which only {other} runs"
    return None


def verify(advice, context, briefing, team=None):
    """Returns why the advice can't be shown, or None if it is grounded in the context."""
    unknown = _numbers(advice) - _numbers(context) - FREE_NUMBERS
    if unknown:
        return f"numbers not in the facts: {', '.join(sorted(unknown))}"
    lowered = context.lower()
    invented = [n for n in find_pokemon(advice) if n.lower() not in lowered]
    if invented:
        return f"Pokemon that are not on the team or in the facts: {', '.join(invented)}"
    # With a single matchup every sentence is about that opponent, named or not
    only = len(briefing.matchups) == 1
    for m in briefing.matchups:
        for sentence in re.split(r"(?<=[.!?])\s+", advice):
            about = only or m.opponent.lower() in sentence.lower()
            if not about or not RECOMMEND.search(sentence) or CAUTION.search(sentence):
                continue
            for x in m.losses:
                if x["name"].lower() in sentence.lower():
                    return f"a claim that {x['name']} handles {m.opponent}, but it loses to {m.opponent} one on one"
    return _move_owner_clash(advice, team or {})


class CoachAgent:
    def __init__(self, model_name=None):
        self.client, self.model = get_agent_client()
        if model_name:
            self.model = model_name

    def _context(self, query, team_context, named_context, facts):
        """The user message: retrieved guides, the team, named sets and engine facts, then the question."""
        team_str = "### USER TEAM\n"
        for p in team_context.values():
            moves = ", ".join([m['name'] for m in p.get('Moves', [])])
            roles = ", ".join(p.get('Roles', []))
            # Champions has stat points instead of EVs and no Tera
            is_champions = config.format_game(p.get('Format')) == "champions"
            raw_evs = p.get('SP', {}) if is_champions else p.get('EVs', {})
            if isinstance(raw_evs, dict):
                evs = " / ".join(f"{v} {k}" for k, v in raw_evs.items() if v > 0) or "Unknown"
            else:
                evs = str(raw_evs)
            gimmick = "" if is_champions else f"Tera: {p.get('Tera Type', '?')} | "
            spread = "Stat Points" if is_champions else "EVs"
            team_str += (
                f"- {p['Pokemon']} @ {p.get('Item')} | Ability: {p.get('Ability')} | "
                f"{gimmick}Nature: {p.get('Nature', '?')} | {spread}: {evs} | "
                + (f"Roles: {roles} | " if roles else "")
                + f"Speed: {p.get('Speed', '?')} | Moves: {moves}\n"
            )

        # Retrieve strategy guides, keeping only ones about Pokemon in play
        focus_text = (query + team_str + named_context + facts).lower()
        rag_hits = store.query_strategies(query, n_results=4, format_id=config.team_format(team_context))
        rag_hits = [h for h in rag_hits if _relevant(h, focus_text)][:2]
        rag_context = ""
        if rag_hits:
            rag_context = "### SMOGON STRATEGY DATABASE (REFERENCE)\n"
            for hit in rag_hits:
                rag_context += f"SOURCE [{hit['metadata'].get('pokemon')}]: {_trim(hit['text'])}\n\n"

        # Context, facts and the question sit together at the end, where a small model pays the most attention
        return (
            f"{rag_context}{team_str}\n{named_context}\n{facts}\n"
            f"QUESTION: {query}\n"
            "Answer using the ENGINE FACTS above, naming specific members of my team."
        )

    def _advise(self, context, history, feedback=None):
        system = """You are Professor Oak, the legendary Pokemon researcher and mentor.
Help this trainer understand the big picture: win conditions, checks and counters.
Respond in plain prose only. No JSON, no lists. Be concise: 3 to 5 sentences.
Rules:
1. Any claim about speed, damage, KOs, weaknesses or threats must come from ENGINE FACTS. Never invent numbers.
2. Only recommend Pokemon that are on the USER TEAM. Never call a Pokemon an answer to something it loses to.
3. If the facts don't cover something, speak generally instead of guessing."""
        if feedback:
            system += f"\nYour previous answer was rejected because it had {feedback}. Fix that."
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                # Recent turns so follow ups like "what about against rain?" make sense
                *(history or [])[-6:],
                {"role": "user", "content": context},
            ],
            temperature=0.4,  # BALANCED
            max_tokens=350,
            stream=False,
        )
        return (completion.choices[0].message.content or "").strip()

    def run(self, query: str, team_context: dict, history: list = None, named_context: str = "",
            briefing: Briefing = None):
        """Yields the answer as text chunks: the engine check first (when relevant), then verified advice."""
        briefing = briefing or Briefing()
        show_summary = bool(briefing.summary) and (bool(briefing.matchups and named_context) or bool(SUMMARY_RE.search(query)))
        if show_summary:
            yield briefing.summary + "\n\n"

        context = self._context(query, team_context, named_context, briefing.facts)
        feedback = None
        for _ in range(2):
            try:
                advice = self._advise(context, history, feedback)
            except Exception as e:  # LLM down: the engine check still stands on its own
                print(f"Coach failed: {e}")
                return
            feedback = verify(advice, context, briefing, team_context)
            if feedback is None:
                yield advice
                return
        # Both drafts failed the fact check: say so rather than show unverified advice
        yield "_Professor Oak's advice didn't pass the fact check this time, so only the engine's numbers are shown._"
        if not show_summary and briefing.summary:
            yield "\n\n" + briefing.summary

"""
Professor Oak, the strategy agent. Strategy questions get the engine's briefing (one on one
verdicts vs named opponents and top threats, win conditions, shared weaknesses). For questions
about threats, opponents or win conditions the verdicts are shown first as an "Engine check";
the LLM's advice is shown only if it passes a verifier, with one retry.
"""
import re

from .client import get_agent_client, ollama_available
from .grounded import FREE_NUMBERS, _numbers
from metamatch import config
from metamatch.engine.briefing import Briefing
from metamatch.engine.names import find_pokemon
from metamatch.rag import store

# Chunks are 300 to 900 characters plus a header line; the cap guards against odd long ones
RAG_CHARS = 1000
OFFLINE_NOTE = "_Professor Oak is offline (Ollama isn't running), so only the engine's numbers are shown. Start Ollama for his advice._"
# Questions where the engine's verdicts are the core of the answer
SUMMARY_RE = re.compile(r"\b(threats?|counters?|struggle\w*|win ?con\w*|weakness\w*|weak to)", re.I)
RECOMMEND = re.compile(r"\b(answer|counter|handle|best|deal with|check|beat|use|great|ideal|recommend|switch|option|"
                       r"take (?:out|down)|viable|good|strong|effective|key|reliable|bring|send|lead with|pivot)", re.I)
# Double negatives that read like caution but recommend ("don't hesitate", "does not fear"): removed before checking
POSITIVE_IDIOM = re.compile(r"\b(?:don't|do not|never) (?:hesitate|be afraid|worry)\w*|\bno reason not to\b|\bnot afraid\b|"
                            r"\b(?:does not|doesn't|don't|do not|need not|needn't) (?:fear|mind|care about)\b|\bnot (?:only|just)\b|"
                            r"\bwithout (?:fear|risk)\b|\bno risk\b", re.I)
NEGATOR = re.compile(r"\b(?:not|never|no|avoid\w*|don't|doesn't|isn't|aren't|won't|cannot|can't|shouldn't|wouldn't|"
                     r"stop|skip|instead of|rather than|unlike|except|over|than|nor)\b|n't\b", re.I)
# Wording that puts the clause's own subject on the losing side, so it isn't a recommendation
LOSS = re.compile(r"\b(?:lose|loses|losing|lost to|struggles?|struggling|weak|vulnerable|threat\w*|careful|risk\w*|ohko\w*|"
                  r"dies|faints?|outclassed|walled|danger\w*|liability|keep \w+ (?:away|out|back)|stay away)\b", re.I)
CLAUSE = re.compile(r"[;,]|\b(?:but|however|while|whereas|although|though|and|so|instead|rather|because|since|unless)\b", re.I)


def recommends_loser(sentence, losers, members):
    """A team member that the sentence recommends against this opponent although it loses the one on one, or None.
    Each un-negated recommend word is credited to the nearest member in its clause; "over X" or "instead of X"
    marks X as the alternative, not the pick."""
    sentence = POSITIVE_IDIOM.sub(" ", sentence)
    for clause in CLAUSE.split(sentence):
        low = clause.lower()
        spots = []
        for n in members:
            for m in re.finditer(rf"\b{re.escape(n.lower())}\b", low):
                before = low[:m.start()].split()[-2:]
                if not set(before) & {"over", "than", "of", "not", "unlike", "except", "avoid", "avoiding"}:
                    spots.append((m.start(), n))
        if not spots or LOSS.search(clause):
            continue
        for cue in RECOMMEND.finditer(clause):
            head = clause[:cue.start()].split()[-3:]
            if any(NEGATOR.fullmatch(w.strip(".,!?").lower()) or w.lower().endswith("n't") for w in head):
                continue
            nearest = min(spots, key=lambda s: abs(s[0] - cue.start()))[1]
            if nearest in losers:
                return nearest
    return None


def _trim(text, limit=RAG_CHARS):
    """Cuts text to `limit` characters at the last sentence end."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = cut.rfind(". ")
    return cut[:end + 1] if end > limit // 2 else cut + "..."


def _species_key(name):
    """'Absol-Mega' and 'Absol' share a key, so a guide on the Mega counts for a team running Absol."""
    return re.sub(r"[^a-z0-9]", "", (name or "").split("-Mega")[0].lower())


def _relevant(hit, focus_names):
    """Concept chunks always count; Pokemon chunks only when that Pokemon is on the team, named or in the facts.
    focus_names: canonical names (planner resolver), so 'Mega Absol' matches a chunk about 'Absol-Mega'."""
    subject = hit["metadata"].get("pokemon") or ""
    if hit["metadata"].get("type") == "concept" or subject in ("", "Concept", "General"):
        return True
    return _species_key(subject) in {_species_key(n) for n in focus_names}


def _source_label(meta):
    """'Kingambit, Set Swords Dance (smogon analysis)' for the sources line under an answer."""
    kind = {"smogon_analysis": "Smogon analysis", "smogon_stats": "ladder stats", "pokechamp": "community guide",
            "concepts": "concept note"}.get(meta.get("source"), "reference")
    subject = meta.get("pokemon")
    where = meta.get("section") or meta.get("title") or ""
    return f"{subject}, {where} ({kind})" if subject and subject != "Concept" else f"{where} ({kind})"


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
        losers = {x["name"] for x in m.losses}
        members = losers | {x["name"] for x in m.wins} | {p["Pokemon"] for p in (team or {}).values()}
        for sentence in re.split(r"(?<=[.!?])\s+", advice):
            if not (only or m.opponent.lower() in sentence.lower()):
                continue
            loser = recommends_loser(sentence, losers, members)
            if loser:
                return f"a claim that {loser} handles {m.opponent}, but it loses to {m.opponent} one on one"
    return _move_owner_clash(advice, team or {})


class CoachAgent:
    def __init__(self, model_name=None):
        self.client, self.model = get_agent_client()
        if model_name:
            self.model = model_name
        self.sources = []  # references the last answer's prompt used, shown under the advice

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

        # Retrieve references, keeping only ones about Pokemon in play
        asked = find_pokemon(query)
        focus_names = set(asked) | set(find_pokemon(named_context + facts))
        for p in team_context.values():
            focus_names |= {p.get("Pokemon"), p.get("Forme")} - {None}
        rag_hits = store.query_strategies(query, n_results=4, format_id=config.team_format(team_context), names=asked)
        rag_hits = [h for h in rag_hits if _relevant(h, focus_names)][:2]
        self.sources = [_source_label(h["metadata"]) for h in rag_hits]
        rag_context = ""
        if rag_hits:
            rag_context = "### REFERENCES (Smogon analyses, ladder stats, community guides, concept notes)\n"
            for hit in rag_hits:
                rag_context += f"{_trim(hit['text'])}\n\n"

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
            temperature=0.4,
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
        if not ollama_available():
            yield OFFLINE_NOTE
            if not show_summary and briefing.summary:
                yield "\n\n" + briefing.summary
            return
        feedback = None
        for _ in range(2):
            try:
                advice = self._advise(context, history, feedback)
            except Exception as e:  # LLM down: the engine check still stands on its own
                print(f"Coach failed: {e}")
                yield OFFLINE_NOTE
                if not show_summary and briefing.summary:
                    yield "\n\n" + briefing.summary
                return
            feedback = verify(advice, context, briefing, team_context)
            if feedback is None:
                yield advice
                if self.sources:
                    yield "\n\n_References: " + "; ".join(self.sources) + "._"
                return
        # Both drafts failed the fact check: say so rather than show unverified advice
        yield "_Professor Oak's advice didn't pass the fact check this time, so only the engine's numbers are shown._"
        if not show_summary and briefing.summary:
            yield "\n\n" + briefing.summary

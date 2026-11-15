"""
Professor Oak, the strategy agent. Strategy questions get the engine's briefing (one on one
verdicts vs named opponents and top threats, win conditions, shared weaknesses). His advice is
shown only if it passes a verifier, with one retry, and the briefing's "Engine check" goes in the
Engine facts dropdown under it; without passing advice the Engine check is shown on its own.
"""
import re

from .client import chat, ollama_available
from .grounded import FREE_NUMBERS, _numbers
from metamatch import config
from metamatch.engine import rules
from metamatch.engine.briefing import Briefing
from metamatch.engine.names import find_pokemon
from metamatch.rag import store

# Chunks are 300 to 900 characters plus a header line; the cap guards against odd long ones
RAG_CHARS = 1000
OFFLINE_NOTE = "_Professor Oak is offline (Ollama isn't running), so only the engine's numbers are shown. Start Ollama for his advice._"
FAILED_NOTE = "_Professor Oak couldn't answer this time (the model call failed), so only the engine's numbers are shown._"
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
# Softer ways of recommending: "consider using X", "X works to your advantage", "a solid pick"
RECOMMEND_SOFT = re.compile(r"\b(?:consider\w*|using|rely(?:ing)? on|go with|opt for|choose|pick|works? well|advantage|"
                            r"solid|excellent|perfect|favou?rable|anchor)\b", re.I)
# Claims that a member lives through the opponent's attacks: wrong for a member the opponent OHKOs
SURVIVE_CUE = re.compile(r"\b(?:survives?|surviving|withstands?|withstanding|tanks?|tanking|"
                         r"take[sn]? (?:a|the|its|one|that) hits?|lives? (?:through|a|the|one))\b", re.I)
# A clause with no member of its own that still talks about the last one named: "..., making it a viable option",
# "Corviknight, with its bulk, could be a good option"
PRONOUN = re.compile(r"\b(?:it|its|it's|they|them|their|who|which)\b", re.I)
CONTINUES = re.compile(r"^\s*(?:could|can|would|should|will|may|might|is|makes|making|works|provides|gives|offers)\b", re.I)
NOT_THE_PICK = {"over", "than", "of", "not", "unlike", "except", "avoid", "avoiding"}


def _clauses(sentence):
    """(start, text) for each clause, so a clause knows where it sits in the sentence."""
    out, start = [], 0
    for m in CLAUSE.finditer(sentence):
        out.append((start, sentence[start:m.start()]))
        start = m.end()
    out.append((start, sentence[start:]))
    return out


def recommends_loser(sentence, losers, members, ohko=()):
    """A team member that the sentence recommends against this opponent although it loses the one on one, or None.
    Each un-negated recommend word is credited to the nearest member in its clause, or to the last member named
    before it when the clause only refers back to one ("making it a viable option"). A claim that a member survives
    counts when the opponent OHKOs it (`ohko`). "over X" or "instead of X" marks X as the alternative, not the pick."""
    sentence = POSITIVE_IDIOM.sub(" ", sentence)
    low_sentence = sentence.lower()
    named = []
    for n in members:
        for m in re.finditer(rf"\b{re.escape(n.lower())}\b", low_sentence):
            if not set(low_sentence[:m.start()].split()[-2:]) & NOT_THE_PICK:
                named.append((m.start(), n))
    for start, clause in _clauses(sentence):
        if LOSS.search(clause):
            continue
        spots = [(p - start, n) for p, n in named if start <= p < start + len(clause)]
        carried = None
        if not spots and (PRONOUN.search(clause) or CONTINUES.match(clause)):
            earlier = [(p, n) for p, n in named if p < start]
            carried = max(earlier)[1] if earlier else None
        if not spots and not carried:
            continue
        cues = [(c, False) for c in RECOMMEND.finditer(clause)] + [(c, False) for c in RECOMMEND_SOFT.finditer(clause)]
        cues += [(c, True) for c in SURVIVE_CUE.finditer(clause)]
        for cue, survives in cues:
            head = clause[:cue.start()].split()[-3:]
            if any(NEGATOR.fullmatch(w.strip(".,!?").lower()) or w.lower().endswith("n't") for w in head):
                continue
            who = min(spots, key=lambda s: abs(s[0] - cue.start()))[1] if spots else carried
            if who in (ohko if survives else losers):
                return who
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
        ohko = {x["name"] for x in m.losses if x.get("to_be_koed") == 1}
        members = losers | {x["name"] for x in m.wins} | {p["Pokemon"] for p in (team or {}).values()}
        for sentence in re.split(r"(?<=[.!?])\s+", advice):
            if not (only or m.opponent.lower() in sentence.lower()):
                continue
            loser = recommends_loser(sentence, losers, members, ohko)
            if loser:
                return f"a claim that {loser} handles {m.opponent}, but it loses to {m.opponent} one on one"
    return _move_owner_clash(advice, team or {})


class CoachAgent:
    def __init__(self, model_name=None):
        self.model = model_name

    def _context(self, query, team_context, named_context, facts):
        """(user message, source labels): retrieved guides, the team, named sets and engine facts, then the question.
        The labels are returned rather than kept on the agent, because one agent serves every chat session."""
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
        try:
            rag_hits = store.query_strategies(query, n_results=4, format_id=config.team_format(team_context), names=asked)
        except Exception as e:  # the index is optional: without it Oak works from the engine facts alone
            print(f"Retrieval failed: {e}")
            rag_hits = []
        rag_hits = [h for h in rag_hits if _relevant(h, focus_names)][:2]
        sources = list(dict.fromkeys(_source_label(h["metadata"]) for h in rag_hits))
        rag_context = ""
        if rag_hits:
            rag_context = ("### REFERENCES (general notes from Smogon analyses, ladder stats and guides; they describe these "
                           "Pokemon on other teams, so check every move and teammate against USER TEAM before using it)\n")
            for hit in rag_hits:
                rag_context += f"{_trim(hit['text'])}\n\n"

        rules_str = "### RULES (Pokemon Showdown's own text)\n" + "\n".join(f"- {l}" for l in rules.team_rules(team_context, query)) + "\n"

        # Context, facts and the question sit together at the end, where a small model pays the most attention
        return (
            f"{rag_context}{team_str}\n{rules_str}\n{named_context}\n{facts}\n"
            f"QUESTION: {query}\n"
            "Answer using the ENGINE FACTS above, naming specific members of my team."
        ), sources

    def _advise(self, context, feedback=None):
        system = """You are Professor Oak, the legendary Pokemon researcher and mentor.
Help this trainer understand the big picture: win conditions, checks and counters.
Respond in plain prose only. No JSON, no lists. Be concise: 3 to 5 sentences.
Rules:
1. Any claim about speed, damage, KOs, weaknesses or threats must come from ENGINE FACTS. Never invent numbers.
2. Only recommend Pokemon that are on the USER TEAM. Never call a Pokemon an answer to something it loses to.
3. If the facts don't cover something, speak generally instead of guessing."""
        if feedback:
            system += f"\nYour previous answer was rejected because it had {feedback}. Fix that."
        # No earlier turns: replayed answers measured as harmful (the model repeats their mistakes and copies their
        # fact blocks), and follow ups reach this point already resolved by the dialogue state
        return chat([{"role": "system", "content": system}, {"role": "user", "content": context}],
                    temperature=0.4, max_tokens=350, model=self.model)

    def run(self, query: str, team_context: dict, named_context: str = "", briefing: Briefing = None):
        """Yields the answer as text chunks: verified advice with the engine check in the dropdown under it
        (FACTS_MARK), or the engine check on its own when no advice passes."""
        from .grounded import FACTS_MARK
        briefing = briefing or Briefing()

        context, sources = self._context(query, team_context, named_context, briefing.facts)
        if not ollama_available():
            yield OFFLINE_NOTE
            if briefing.summary:
                yield "\n\n" + briefing.summary
            return
        feedback = None
        for _ in range(2):
            try:
                advice = self._advise(context, feedback)
            except Exception as e:  # LLM call failed: the engine check still stands on its own
                print(f"Coach failed: {e}")
                yield OFFLINE_NOTE if not ollama_available(ttl=0) else FAILED_NOTE
                if briefing.summary:
                    yield "\n\n" + briefing.summary
                return
            feedback = verify(advice, context, briefing, team_context)
            if feedback is None:
                yield advice
                if sources:
                    yield "\n\n_References: " + "; ".join(sources) + "._"
                if briefing.summary:
                    yield FACTS_MARK + briefing.summary
                return
        # Both drafts failed the fact check: say so rather than show unverified advice
        yield "_Professor Oak's advice didn't pass the fact check this time, so only the engine's numbers are shown._"
        if briefing.summary:
            yield "\n\n" + briefing.summary

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
from metamatch.rag.chunking import body

# Chunks are 300 to 900 characters plus a header line; the cap guards against odd long ones
RAG_CHARS = 1000
OFFLINE_NOTE = "_Professor Oak is offline (Ollama isn't running), so only the engine's numbers are shown. Start Ollama for his advice._"
# The shared web version has no model to start, so visitors get a plain line instead of setup advice
SHARED_NOTE = "_Professor Oak's own advice is in the version you run on your computer. Here is what the engine found._"


def _offline_note():
    return OFFLINE_NOTE if config.LOCAL_MODE else SHARED_NOTE
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
    if hit["metadata"].get("type") in ("concept", "guide") or subject in ("", "Concept", "General", "Guide"):
        return True
    return _species_key(subject) in {_species_key(n) for n in focus_names}


def _source_label(meta):
    """'Kingambit, Set Swords Dance (smogon analysis)' for the sources line under an answer."""
    kind = {"smogon_analysis": "Smogon analysis", "smogon_stats": "ladder stats", "pokechamp": "community guide",
            "concepts": "concept note"}.get(meta.get("source"), "reference")
    if meta.get("source") == "smogon_guide":
        from metamatch.rag.guides import label
        return label(meta)
    subject = meta.get("pokemon")
    where = meta.get("section") or meta.get("title") or ""
    return f"{subject}, {where} ({kind})" if subject and subject != "Concept" else f"{where} ({kind})"


def _rules_for(team, query):
    """Showdown rule text for what the question names: abilities, items, moves, and the ability and item of any team
    member it names. Every member's rules in every prompt was 350 tokens of mostly unused text."""
    named = {n.lower() for n in find_pokemon(query)}
    members = {k: p for k, p in (team or {}).items()
               if {(p.get("Pokemon") or "").lower(), (p.get("Forme") or "").lower()} & named}
    return rules.team_rules(members, query)


# Small talk and questions the engine answers better than any passage: retrieval would only add noise here
NO_RETRIEVAL = re.compile(r"^\s*(?:thanks?|thank you|thx|ty|ok(?:ay)?|cool|nice|great|got it|hi|hello|hey)\b|"
                          r"\b(?:weak(?:ness|nesses)? to|threats?|rate my team)\b|\bis my team good\W*$", re.I)


def references(query, team, plan=None, facts_text="", format_id=None):
    """The (at most two) retrieved passages Oak is given: ranked only among chunks about concepts, the team, a named
    Pokemon or one in the engine facts (filtering first, not after, measured +4 points of oak@2 on the 2026 11 14 held
    out set). The second slot is only for a concept note or a Pokemon the question names, so it never fills with a
    marginal chunk about some team member."""
    if NO_RETRIEVAL.search(query):
        return []
    asked = find_pokemon(query)
    focus = set(asked) | set(find_pokemon(facts_text))
    for p in (team or {}).values():
        focus |= {p.get("Pokemon"), p.get("Forme")} - {None}
    try:
        hits = store.query_strategies(query, n_results=4, format_id=format_id or config.team_format(team), names=asked,
                                      keep=lambda m: _relevant({"metadata": m}, focus))
    except Exception as e:  # the index is optional: without it Oak works from the engine facts alone
        print(f"Retrieval failed: {e}")
        return []
    asked_keys = {_species_key(n) for n in asked}
    kept = hits[:1]
    for h in hits[1:]:
        m = h["metadata"]
        if m.get("type") == "concept" or _species_key(m.get("pokemon")) in asked_keys:
            kept.append(h)
            break
    return kept


CANT_LINES = ("That one goes beyond what I can work out exactly, I'm afraid.",
              "Hmm, my research can't settle that one exactly.",
              "Now that's a question I can't answer with certainty.")
# A retrieved card is only shown when it is this close to the question (cosine distance, bge small). On 16 open
# questions (2026 11 15) the on topic passages scored 0.20 to 0.34 and "what's the meaning of life" 0.535
CARD_MAX_DISTANCE = 0.34


def _cant_line(recent=()):
    return next((l for l in CANT_LINES if l not in (recent or ())), CANT_LINES[0])


def _card_worthy(hit):
    """Concept notes and Smogon guides, close enough to the question to be worth reading."""
    m = hit["metadata"]
    close = hit.get("distance") is not None and hit["distance"] <= CARD_MAX_DISTANCE
    return m.get("type") in ("concept", "guide") and close


# A Pokemon's own analysis answers "how do I use, play or build around X" and "what's X's role", not a matchup
# ("what can I do vs Iron Valiant"), a decision in a game ("pult locked into draco, now what") or a mechanic
# ("does infiltrator matter on dragapult"): the 2026 11 26 coverage audit found 22 such questions quoted an unrelated
# set or teammate passage about a Pokemon they merely named
USE_RE = re.compile(r"\bhow (?:do|to|should|can|would|does) (?:i |you |we |one )?(?:use|play|run|build|pilot)\b|"
                    r"\b(?:role|job|purpose|playstyle)\b|\bwhat(?:'s| is| does)\b[^?.!]{0,30}\b(?:do|doing|for)\b|"
                    r"\bbuild(?:ing)? (?:a team )?around\b|\b(?:viable|worth using|good on|fit\w* on)\b", re.I)
NOT_USE_RE = re.compile(r"\b(?:vs\.?|versus|against|now|this turn|turn \d+|locked|click|sack|switch(?:es)? (?:to|into)|"
                        r"send (?:in|out)|goes in|matter|work|works|happens?|immune|resist\w*|weak\w*)\b", re.I)


def _named_analysis(hit, asked, query="", how_to_use=False):
    """A Smogon analysis chunk about a Pokemon the question names, when the question asks how to use that Pokemon
    (by the patterns, or `how_to_use` when the classifier read it that way)."""
    m = hit["metadata"]
    if not how_to_use and not (USE_RE.search(query) and not NOT_USE_RE.search(query)):
        return False
    return m.get("source") == "smogon_analysis" and (_species_key(m.get("pokemon")) in asked
                                                       or _species_key(m.get("species")) in asked)


def _voiced(query, hits, asked, state=None, meta=None):
    """Oak's framing line, then the passage's own sentences that answer the question, quoted, with the source
    (agents/retell.py). None when nothing retrieved is worth reading."""
    how_to_use = (meta or {}).get("kind") == "how_to_use"
    hit = next((h for h in hits if _card_worthy(h) or _named_analysis(h, asked, query, how_to_use)), None)
    if not hit:
        return None
    from metamatch.rag.cards import analysis_url
    from .retell import frame, quoted
    m = hit["metadata"]
    line, by = frame(query, m, getattr(state, "recent_openers", ()))
    url = m.get("url") or (analysis_url(m.get("pokemon"), m.get("format")) if m.get("source") == "smogon_analysis" else None)
    note = (f" Written for Gen {m['gen']}: it mentions {m['old_mechanics']}, which the current games don't have."
            if m.get("old_mechanics") else "")
    source = f"_From the {_source_label(m)}.{note}_" + (f" [Read the rest]({url})" if url else "")
    if meta is not None:
        meta.update({"retell": by})
    return f"{line}\n\n> {quoted(query, hit)}\n\n{source}"


def _card(hit):
    """A retrieved passage shown verbatim with where it comes from, and a note when it predates current mechanics."""
    m = hit["metadata"]
    note = (f"\n\n_Written for Gen {m['gen']}: it mentions {m['old_mechanics']}, which the current games don't have._"
            if m.get("old_mechanics") else "")
    link = f" ([source]({m['url']}))" if m.get("url") else ""
    return f"\n\n**{_source_label(m)}**{link}\n\n> {_trim(body(hit['text']))}{note}"


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

    def _context(self, query, team_context, named_context, facts, plan=None):
        """(user message, references used): the question first, then the trainer's team with owners and typings, the
        rule text for what the question names, named opposing sets, engine facts and the references.
        The 2026 11 14 ablations measured each choice: question first beat question last (12 vs 9 of 33 drafts),
        labelled owners stopped "own member as the opponent" errors, and spreads, roles and every member's rule text
        were noise. The references are returned rather than kept on the agent, which serves every chat session."""
        game = config.format_game(config.team_format(team_context))
        lines = []
        for p in team_context.values():
            moves = ", ".join(m['name'] for m in p.get('Moves', []))
            tera = "" if game == "champions" else f", Tera {p.get('Tera Type', '?')}"
            lines.append(f"- Your {p['Pokemon']} ({'/'.join(p.get('Type', []))}) @ {p.get('Item') or 'no item'}, "
                         f"{p.get('Ability')}{tera}, Speed {p.get('Speed', '?')}. Moves: {moves}.")
        team_str = "YOUR TEAM (the trainer's own Pokemon):\n" + "\n".join(lines) + "\n"

        rule_lines = _rules_for(team_context, query)
        rules_str = ("RULES (Pokemon Showdown's own text):\n" + "\n".join(f"- {line}" for line in rule_lines) + "\n") if rule_lines else ""

        hits = references(query, team_context, plan, named_context + facts)
        rag_context = ""
        if hits:
            rag_context = ("REFERENCES (general Smogon notes; they describe these Pokemon on other players' teams, not "
                           "yours):\n" + "\n\n".join(_trim(h["text"]) for h in hits) + "\n")

        return (
            f"QUESTION: {query}\n\n{team_str}\n{rules_str}\n{named_context}\n{facts}\n\n{rag_context}\n"
            f"Answer the QUESTION above."
        ), hits

    def _advise(self, context, feedback=None):
        system = """You are Professor Oak, a warm, experienced Pokemon researcher who explains the big picture.
Answer in 3 to 5 sentences of plain prose. No lists, no headings, no JSON.
Rules:
1. Every claim about speed, damage, KOs, typings, weaknesses or who beats whom must come from the ENGINE FACTS or
YOUR TEAM. Never invent numbers, moves or abilities.
2. Pokemon marked "Your" belong to the trainer; every other Pokemon is an opponent. Only recommend the trainer's own
Pokemon, and never call one an answer to something it loses to.
3. If the facts don't cover something, give general advice instead of guessing."""
        if feedback:
            system += f"\nYour previous answer was rejected because it had {feedback}. Fix that."
        # No earlier turns: replayed answers measured as harmful (the model repeats their mistakes and copies their
        # fact blocks), and follow ups reach this point already resolved by the dialogue state
        return chat([{"role": "system", "content": system}, {"role": "user", "content": context}],
                    temperature=0.2, max_tokens=350, model=self.model)

    def run(self, query: str, team_context: dict, named_context: str = "", briefing: Briefing = None, plan=None,
            state=None, meta=None):
        """Yields the answer for an open strategy question. The engine's facts about the team (one on ones, win
        conditions, cores, shared weaknesses) and sentences from MetaMatch's own concept notes become a numbered packet;
        Oak only picks the facts that answer the question and adds an opener, and the facts are shown word for word.
        Smogon passages go in the dropdown as cited cards, never to the model. METAMATCH_VOICE=legacy keeps the old
        free advice path until the final measurement."""
        from .grounded import voice_mode
        if voice_mode() == "legacy":
            yield from self._legacy_run(query, team_context, named_context, briefing, plan)
            return
        yield self.packet_text(query, team_context, briefing or Briefing(), plan, state, meta)

    def packet_text(self, query, team_context, briefing, plan=None, state=None, meta=None):
        """A question no engine function answers: Oak says so, offers close questions the engine does answer (chips),
        and shows the best matching concept note or Smogon guide passage as a cited card. No model picks facts here:
        in the 2026 11 15 chats that picking put unrelated threat matchups under weakness and weather questions."""
        from .suggest import marker, suggestions
        line = _cant_line(getattr(state, "recent_openers", ()))
        if meta is not None:
            meta.update({"opener": "stock", "facts": "fallback"}, opener=line)
        chips = suggestions(query, plan, team_context)
        found = references(query, team_context, plan, briefing.facts)
        asked = {_species_key(n) for n in find_pokemon(query)}
        # Oak frames the closest passage in his own voice and quotes the sentences that answer the question
        # (agents/retell.py); with nothing worth reading, he says so and offers questions he can answer
        voiced = _voiced(query, found, asked, state, meta)
        if voiced:
            text = voiced
        else:
            # The concept note first: it is written for the current games; a guide adds depth from earlier ones
            hits = sorted((h for h in found if _card_worthy(h) or _named_analysis(h, asked, query)),
                          key=lambda h: h["metadata"].get("type") != "concept")
            text = f"*{line}*"
            if hits:
                text += "\n\nHere's how it has been explained before:" + "".join(_card(h) for h in hits[:2])
        # The chips render right under this line
        text += "\n\n" + ("These I can answer exactly for your team:" if chips else
                          "Try asking about a matchup, a member or your game plan.")
        return text + marker(chips)

    def _legacy_run(self, query, team_context, named_context="", briefing=None, plan=None):
        """The pre restructure path: Oak's checked free advice (kept switchable until the final measurement)."""
        from .grounded import FACTS_MARK
        briefing = briefing or Briefing()

        context, hits = self._context(query, team_context, named_context, briefing.facts, plan)
        sources = list(dict.fromkeys(_source_label(h["metadata"]) for h in hits))
        notes = "".join(f"\n\n**{_source_label(h['metadata'])}**\n\n> {_trim(body(h['text']))}" for h in hits)
        dropdown = ((briefing.summary or "") + notes).strip()
        if not ollama_available():
            yield _offline_note()
            if dropdown:
                yield "\n\n" + dropdown
            return
        feedback = None
        for _ in range(2):
            try:
                advice = self._advise(context, feedback)
            except Exception as e:  # LLM call failed: the engine check still stands on its own
                print(f"Coach failed: {e}")
                yield _offline_note() if not ollama_available(ttl=0) else FAILED_NOTE
                if dropdown:
                    yield "\n\n" + dropdown
                return
            feedback = verify(advice, context, briefing, team_context)
            if feedback is None:
                yield advice
                if sources:
                    yield "\n\n_References: " + "; ".join(sources) + "._"
                if dropdown:
                    yield FACTS_MARK + dropdown
                return
        # Both drafts failed the fact check: say so rather than show unverified advice
        yield "_Professor Oak's advice didn't pass the fact check this time, so only the engine's numbers are shown._"
        if dropdown:
            yield "\n\n" + dropdown

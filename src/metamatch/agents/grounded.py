"""
Presents an engine Verdict. The engine has already worked out the answer; the persona (Clemont, Brock, Oak) only says
it in plain words, and the exact result goes under it in an "Engine facts" dropdown. The voiced text is checked before
it is shown:
  * every number in it must appear in the verdict or facts
  * every Pokemon it names must be in the verdict, the facts or the team
  * no clause may claim a different speed order, KO result, type matchup, team group or yes or no (agents/claims.py)
  * it must not state a different final answer
On failure the model gets one retry, then the result is shown on its own, open.
"""
import re

from . import claims
from .client import get_agent_client, ollama_available
from metamatch.engine.names import find_pokemon

NUMBER = re.compile(r"\d+(?:\.\d+)?")
ANSWER_LINE = re.compile(r"^\s*\**ANSWER\s*:.*$", re.I | re.M)
# Numbers that can't mislead even when the facts don't spell them out
FREE_NUMBERS = {"0", "1", "100"}
# Splits a voiced answer from the engine facts shown in the dropdown under it (the chat tab renders the split)
FACTS_MARK = "\n\n<!--engine-facts-->\n\n"
PERSONAS = {
    "mechanics": "Clemont, an upbeat young inventor who loves explaining exactly how battle mechanics work",
    "builder": "Brock, a calm, friendly breeder who knows what ladder players really run",
    "strategy": "Professor Oak, a warm, experienced researcher who explains the big picture",
}


def _checks_clash(explanation, verdict):
    """A sentence recommending a member that loses to the opponent one on one."""
    from .coach import recommends_loser
    for sentence in re.split(r"(?<=[.!?])\s+", explanation):
        loser = recommends_loser(sentence, set(verdict.losers), set(verdict.members))
        if loser:
            return f"a claim that {loser} handles {verdict.other}, but it loses one on one"
    return None


CLAIM_CHECKS = {"type": claims.type_clash, "speed": claims.speed_clash, "ko": claims.ko_clash, "checks": _checks_clash,
                "team_type": claims.group_clash, "rules": claims.yes_no_clash}


def _numbers(text):
    return {n.rstrip("0").rstrip(".") if "." in n else n for n in NUMBER.findall(text)}


def verify(explanation, verdict):
    """Returns a reason the explanation can't be shown, or None if it is grounded."""
    allowed = _numbers(verdict.statement + " " + " ".join(verdict.facts)) | FREE_NUMBERS
    unknown = _numbers(explanation) - allowed
    if unknown:
        return f"numbers not in the facts: {', '.join(sorted(unknown))}"
    check = CLAIM_CHECKS.get(verdict.intent)
    clash = check(explanation, verdict) if check else None
    if clash:
        return clash
    stated = re.findall(r"ANSWER\s*:\s*(.+)", explanation, re.I)
    if stated and verdict.answer.lower() not in stated[-1].lower():
        return f"contradicts the verdict ({stated[-1].strip()})"
    return None


def verify_voice(text, verdict, team=None):
    """verify() plus the checks a voiced answer needs because the result itself is no longer shown above it."""
    reason = verify(text, verdict)
    if reason:
        return reason
    known = (verdict.statement + " " + " ".join(verdict.facts)).lower()
    members = {(p.get("Forme") or p["Pokemon"]).lower() for p in (team or {}).values()} | \
              {p["Pokemon"].lower() for p in (team or {}).values()}
    invented = [n for n in find_pokemon(text) if n.lower() not in known and n.lower() not in members]
    if invented:
        return f"Pokemon that are not in the result: {', '.join(invented)}"
    # The result has to be said, not just talked around: every Pokemon in the statement must come up
    missing = [n for n in find_pokemon(verdict.statement) if n.lower() not in text.lower()]
    if missing:
        return f"left out {', '.join(missing)}, which the result names"
    return None


META = re.compile(r"\b(?:battle engine|the engine|engine's|the result|the facts|fact here)\b", re.I)
TYPE_WORD = re.compile(r"\b(?:Normal|Fire|Water|Electric|Grass|Ice|Fighting|Poison|Ground|Flying|Psychic|Bug|Rock|Ghost|"
                       r"Dragon|Dark|Steel|Fairy)\b|\bhalf\b|\bquarter\b|\bdouble\b|\d", re.I)


def _claims_something(sentence):
    """A sentence naming a Pokemon, type, move, ability, item, weather or number states a fact, not just a tone."""
    from metamatch.engine import rules
    return bool(TYPE_WORD.search(sentence) or find_pokemon(sentence) or rules.find_named(sentence))


def _trim_voice(text):
    """The sentence that says the answer (with a one or two word opener like "Yes." kept together with it), then only
    sentences that add tone and no facts. In the 2026 11 12 probes every opening sentence was right and every invented
    claim came in a later one; the exact details are in the Engine facts dropdown anyway."""
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s and not META.search(s)]
    if not sentences:
        return ""
    keep = [sentences.pop(0)]
    if len(keep[0].split()) <= 3 and sentences:
        keep.append(sentences.pop(0))
    keep += [s for s in sentences[:1] if not _claims_something(s)]
    return " ".join(keep).strip()


def facts_block(verdict):
    """The exact result as markdown: the statement in bold, then each fact."""
    lines = [f"**{verdict.statement}**"]
    if verdict.facts:
        lines.append("\n".join(f"* {f}" for f in verdict.facts))
    return "\n\n".join(lines)


class GroundedAgent:
    def __init__(self):
        self.client, self.model = get_agent_client()

    def _voice(self, query, verdict, team, feedback=None):
        facts = "\n".join(f"- {f}" for f in verdict.facts) or "- (none)"
        who = PERSONAS.get(verdict.persona, PERSONAS["mechanics"])
        # No team list here: given one, the model adds commentary about members the result doesn't mention, and that
        # commentary is where it invents (the 2026 11 12 audit). The facts already say which members a result concerns.
        system = (
            f"You are {who}. You are talking with a trainer about their team.\n"
            "A battle engine has already worked out the answer to their question. It is correct.\n"
            f"RESULT: {verdict.statement}\n"
            f"FACTS:\n{facts}\n\n"
            "Tell the trainer this answer in your own words, the way you would say it out loud. Rules:\n"
            "1. Say the answer itself first. If one FACT directly explains it, you may add that in one short sentence.\n"
            "2. Keep every Pokemon, number, type, move and yes or no exactly as the RESULT and FACTS give them. "
            "Never move a Pokemon into a different group, never work out a new number, and never add advice, "
            "opinions or anything the FACTS do not say.\n"
            "3. At most two short sentences of plain conversational prose. Never mention the engine, the result or "
            "the facts. No lists, no headings, no ANSWER line."
        )
        if feedback:
            system += f"\nYour previous attempt was rejected because it had {feedback}. Fix that."
        completion = self.client.chat.completions.create(
            model=self.model, temperature=0.0, max_tokens=150, stream=False,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": query}],
        )
        return _trim_voice(ANSWER_LINE.sub("", completion.choices[0].message.content or ""))

    def voice(self, query, verdict, team=None):
        """A checked, voiced answer, or '' when the model is offline or can't produce one that keeps the facts."""
        if not ollama_available():
            return ""
        feedback = None
        for _ in range(2):
            try:
                text = self._voice(query, verdict, team, feedback)
            except Exception as e:  # LLM down: the result still stands on its own
                print(f"Voice failed: {e}")
                return ""
            feedback = verify_voice(text, verdict, team)
            if feedback is None:
                return text
        return ""

    def run(self, query, verdict, team=None):
        """Yields the answer as text chunks: the voiced answer with the exact result after FACTS_MARK, or the
        result alone when no voiced answer passed the check."""
        spoken = self.voice(query, verdict, team)
        if spoken:
            yield spoken + FACTS_MARK + facts_block(verdict)
        else:
            yield facts_block(verdict)
        # Honour a requested final answer line from the verdict itself, never from the LLM
        if re.search(r"ANSWER\s*:", query, re.I):
            yield f"\n\nANSWER: {verdict.answer}"

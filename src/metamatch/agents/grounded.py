"""
Presents an engine Verdict. The verdict sentence is templated; the LLM only adds a short
explanation, which a verifier checks before it is shown:
  * every number in the explanation must appear in the verdict or facts
  * it must not state a different final answer
On failure the LLM gets one retry, then the answer is shown with the facts instead.
"""
import re

from .client import get_agent_client

NUMBER = re.compile(r"\d+(?:\.\d+)?")
ANSWER_LINE = re.compile(r"^\s*\**ANSWER\s*:.*$", re.I | re.M)
# Numbers that can't mislead even when the facts don't spell them out
FREE_NUMBERS = {"0", "1", "100"}
# For type verdicts, wording that implies a different matchup is a contradiction
TYPE_WORDS = {
    "immune": re.compile(r"\bimmun", re.I),
    "resists": re.compile(r"\bresist", re.I),
    "weak": re.compile(r"\bweak|super[\s-]effective", re.I),
    "neutral": re.compile(r"\bneutral", re.I),
}


def _numbers(text):
    return {n.rstrip("0").rstrip(".") if "." in n else n for n in NUMBER.findall(text)}


def verify(explanation, verdict):
    """Returns a reason the explanation can't be shown, or None if it is grounded."""
    allowed = _numbers(verdict.statement + " " + " ".join(verdict.facts)) | FREE_NUMBERS
    unknown = _numbers(explanation) - allowed
    if unknown:
        return f"numbers not in the facts: {', '.join(sorted(unknown))}"
    if verdict.intent == "type":
        clashes = [a for a, pattern in TYPE_WORDS.items() if a != verdict.answer and pattern.search(explanation)]
        if clashes:
            return f"wording that says {clashes[0]} when the result is {verdict.answer}"
    stated = re.findall(r"ANSWER\s*:\s*(.+)", explanation, re.I)
    if stated and verdict.answer.lower() not in stated[-1].lower():
        return f"contradicts the verdict ({stated[-1].strip()})"
    return None


class GroundedAgent:
    def __init__(self):
        self.client, self.model = get_agent_client()

    def _explain(self, query, verdict, feedback=None):
        facts = "\n".join(f"- {f}" for f in verdict.facts) or "- (none)"
        system = (
            "A battle engine has already computed the answer to the player's question.\n"
            f"RESULT: {verdict.statement}\n"
            f"FACTS:\n{facts}\n\n"
            "Write one to three sentences explaining the result to the player. Rules:\n"
            "1. Never contradict the RESULT; it is correct.\n"
            "2. Only use numbers that appear in the RESULT or FACTS.\n"
            "3. Do not repeat the RESULT word for word and do not write an ANSWER line.\n"
            "4. Plain prose, no lists, no JSON."
        )
        if feedback:
            system += f"\nYour previous attempt was rejected because it had {feedback}. Fix that."
        completion = self.client.chat.completions.create(
            model=self.model, temperature=0.0, max_tokens=200, stream=False,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": query}],
        )
        return ANSWER_LINE.sub("", completion.choices[0].message.content or "").strip()

    def explain(self, query, verdict):
        """A verified explanation, or '' when the model can't produce one."""
        feedback = None
        for _ in range(2):
            try:
                text = self._explain(query, verdict, feedback)
            except Exception as e:  # LLM down: the verdict still stands on its own
                print(f"Explanation failed: {e}")
                return ""
            feedback = verify(text, verdict)
            if feedback is None:
                return text
        return ""

    def run(self, query, verdict):
        """Yields the full answer as text chunks (verdict first, so it shows immediately)."""
        yield f"**{verdict.statement}**"
        explanation = self.explain(query, verdict)
        if explanation:
            yield f"\n\n{explanation}"
        elif verdict.facts:
            yield "\n\n" + "\n".join(f"* {f}" for f in verdict.facts)
        # Honour a requested final answer line from the verdict itself, never from the LLM
        if re.search(r"ANSWER\s*:", query, re.I):
            yield f"\n\nANSWER: {verdict.answer}"

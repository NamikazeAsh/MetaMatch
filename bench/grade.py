"""Parses the final 'ANSWER:' line of a reply and grades it against MetaBench ground truth."""
import re

SYNONYMS = {
    "resists": "resists", "resist": "resists", "resistant": "resists", "resisted": "resists",
    "weak": "weak", "weakness": "weak", "super": "weak",
    "immune": "immune", "immunity": "immune",
    "neutral": "neutral",
    "yes": "yes", "no": "no", "tie": "tie",
    "sometimes": "sometimes", "possibly": "sometimes", "maybe": "sometimes", "chance": "sometimes",
}
NUMBER = re.compile(r"\d+(?:\.\d+)?")


def to_id(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def extract_answer(reply):
    """Text after the last 'ANSWER:' marker, or None when the model ignored the format."""
    matches = re.findall(r"ANSWER\s*:\s*(.+)", reply or "", flags=re.IGNORECASE)
    return matches[-1].strip().strip("*`'\". ") if matches else None


def _choice(answer):
    words = re.findall(r"[a-z]+", answer.lower())
    for word in words:
        if word in SYNONYMS:
            return SYNONYMS[word]
    return None


def grade(question, reply):
    """Returns (parsed answer, correct, format_ok)."""
    truth = question["answer"]
    answer = extract_answer(reply)
    if answer is None:
        return None, False, False

    kind = truth["kind"]
    if kind in ("yesno", "speed", "ko", "type"):
        parsed = _choice(answer)
        return parsed, parsed == truth["value"], parsed is not None

    numbers = [float(n) for n in NUMBER.findall(answer)]
    if kind == "range":
        lo, hi = truth["value"]
        tol = truth.get("tolerance", 3.0)
        if len(numbers) >= 2:
            ok = abs(numbers[0] - lo) <= tol and abs(numbers[1] - hi) <= tol
            return numbers[:2], ok, True
        if numbers:
            return numbers[:1], lo - tol <= numbers[0] <= hi + tol, True
        return None, False, False

    if kind == "number":
        if not numbers:
            return None, False, False
        return numbers[0], abs(numbers[0] - truth["value"]) <= truth.get("tolerance", 0), True

    if kind == "name":
        target = to_id(truth["value"])
        return answer, bool(target) and target in to_id(answer), True

    raise ValueError(f"Unknown answer kind: {kind}")

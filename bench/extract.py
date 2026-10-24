"""
Answer extraction for questions without an answer format instruction (the paraphrase set).
The local model reads a reply and reports the answer the reply gives, as an 'ANSWER:' line,
which grade.py then scores. Every arm goes through the same extractor, so it stays fair.
"""
import os
import re

# A different, stronger model than the 3B under test reads the replies; override with BENCH_EXTRACT_MODEL
EXTRACT_MODEL = os.getenv("BENCH_EXTRACT_MODEL", "gemma3:4b")

OPTIONS = {
    "speed": "exactly one of: yes, no, tie (yes means the player's own Pokemon is faster)",
    "yesno": "exactly one of: yes, no",
    "ko": "exactly one of: yes, no, sometimes (sometimes means only some damage rolls KO)",
    "type": "exactly one of: immune, resists, neutral, weak",
    "range": "the damage range as a percentage of the target's HP, <min>-<max>% (not raw HP points)",
    "number": "a single number",
    "name": "the name given",
}

SYSTEM = (
    "You read a reply to a competitive Pokemon question and report the final answer that the REPLY gives. "
    "Do not answer the question yourself and do not use your own knowledge. "
    "If the reply does not clearly give an answer, report none."
)


def extract(client, model, question, reply, kind):
    """Returns an 'ANSWER: ...' line describing the reply's answer (or 'ANSWER: none')."""
    if not reply.strip():
        return "ANSWER: none"
    survive = " Note: if the question asks whether something survives, report whether the attack KOs (yes means it is KOed)." \
        if kind == "ko" and re.search(r"\b(live|lives|survive|survives|tank)\b", question, re.I) else ""
    user = (f"QUESTION:\n{question}\n\nREPLY:\n{reply}\n\n"
            f"What answer does the REPLY give? Answer with {OPTIONS[kind]}.{survive}\n"
            f"Respond with a single line in the form 'ANSWER: <answer>'.")
    completion = client.chat.completions.create(
        model=model, temperature=0.0, max_tokens=40, stream=False,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
    )
    text = completion.choices[0].message.content or ""
    match = re.search(r"ANSWER\s*:.*", text, re.I)
    return match.group(0) if match else f"ANSWER: {text.strip()}"

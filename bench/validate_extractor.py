"""
Checks the answer extractor against replies that were already graded strictly:
strips the 'ANSWER:' line, extracts again, and reports agreement with the strict parse.
Run: python bench/validate_extractor.py raw_llama3b metamatch_phase3 --sample 40
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(BENCH.parent / "src"))
from extract import extract, EXTRACT_MODEL  # noqa: E402
from grade import grade  # noqa: E402
from metamatch.agents.client import get_agent_client  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("arms", nargs="+")
    parser.add_argument("--sample", type=int, default=40)
    args = parser.parse_args()

    questions = {}
    with open(BENCH / "questions.jsonl", encoding="utf-8") as f:
        for line in f:
            q = json.loads(line)
            questions[q["id"]] = q
    client, model = get_agent_client()[0], EXTRACT_MODEL
    rng = random.Random(0)

    for arm in args.arms:
        with open(BENCH / "results" / f"{arm}.jsonl", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f]
        # Only replies that did state an answer can be compared
        rows = [r for r in rows if r["format_ok"]]
        rows = rng.sample(rows, min(args.sample, len(rows)))
        agree = 0
        for r in rows:
            q = questions[r["id"]]
            question = q["question"].split("\n\nEnd your reply")[0]
            reply = re.sub(r"^\s*\**ANSWER\s*:.*$", "", r["reply"], flags=re.I | re.M).strip()
            line = extract(client, model, question, reply, q["answer"]["kind"])
            _, correct, _ = grade(q, line)
            agree += correct == r["correct"]
            if correct != r["correct"]:
                print(f"  {arm} {r['id']} {q['category']}: strict={r['parsed']!r} extracted={line!r}")
        print(f"{arm}: extractor agrees with strict grading on {agree}/{len(rows)}")


if __name__ == "__main__":
    main()

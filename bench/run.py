"""
Runs one MetaBench arm over bench/questions.jsonl and appends graded results to bench/results/<name>.jsonl.
Rerunning resumes where it stopped.

Arms:
  raw        The bare local model with the team pasted in, no grounding.
  template   Planner and engine verdict only, no LLM.
  metamatch  The full MetaMatch agent pipeline. --src picks which checkout's code to import,
             so an older commit can be benchmarked from a worktree.

Examples:
  python bench/run.py --arm raw
  python bench/run.py --arm metamatch --name metamatch_now
  python bench/run.py --arm metamatch --src <worktree>/src --name metamatch_before
"""
import argparse
import json
import sys
import time
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH))
from grade import grade  # noqa: E402
from extract import extract, EXTRACT_MODEL  # noqa: E402

RAW_SYSTEM = "You are a competitive Pokemon expert. Answer the player's question about their team accurately and concisely."


def load_questions(path, limit=None, ids=None):
    with open(path, encoding="utf-8") as f:
        qs = [json.loads(line) for line in f if line.strip()]
    if ids:
        qs = [q for q in qs if q["id"] in ids]
    return qs[:limit] if limit else qs


def stream_text(stream):
    """Joins a response stream: plain text chunks (current code) or OpenAI chunks (older commits)."""
    parts = []
    for c in stream:
        if isinstance(c, str):
            parts.append(c)
        elif c.choices:
            parts.append(c.choices[0].delta.content or "")
    return "".join(parts)


class RawArm:
    def __init__(self):
        from metamatch.agents.client import get_agent_client
        self.client, self.model = get_agent_client()

    def answer(self, q):
        user = f"My team ({q['format']}):\n{q['team']}\n\n{q['question']}" if q["team"] else q["question"]
        completion = self.client.chat.completions.create(
            model=self.model, temperature=0.0, stream=False,
            messages=[{"role": "system", "content": RAW_SYSTEM}, {"role": "user", "content": user}],
        )
        return completion.choices[0].message.content


class MetaMatchArm:
    def __init__(self):
        from metamatch.agents.manager import AgentManager
        from metamatch import team as team_module
        self.manager = AgentManager()
        self.team_module = team_module

    def answer(self, q):
        team, weakness = self.team_module.readTeam(q["team"], q["format"])
        self.team_module.detectRole(team)
        return stream_text(self.manager.get_response(q["question"], team, weakness))


class TemplateArm:
    """Planner + engine verdict with no LLM at all: the ceiling for calc shaped questions."""

    def __init__(self):
        from metamatch import team as team_module
        from metamatch.engine.planner import plan_query
        from metamatch.engine.solvers import solve
        self.team_module, self.plan_query, self.solve = team_module, plan_query, solve

    def answer(self, q):
        team, _ = self.team_module.readTeam(q["team"], q["format"])
        verdict = self.solve(self.plan_query(q["question"], team))
        return f"{verdict.statement}\n\nANSWER: {verdict.answer}" if verdict else ""


ARMS = {"raw": RawArm, "metamatch": MetaMatchArm, "template": TemplateArm}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=list(ARMS), required=True)
    parser.add_argument("--name", help="results file name (defaults to the arm)")
    parser.add_argument("--src", default=str(BENCH.parent / "src"), help="src dir to import metamatch from")
    parser.add_argument("--questions", default=str(BENCH / "questions.jsonl"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--ids", nargs="*")
    args = parser.parse_args()

    sys.path.insert(0, args.src)
    name = args.name or args.arm
    out_path = BENCH / "results" / f"{name}.jsonl"
    out_path.parent.mkdir(exist_ok=True)
    done = set()
    if out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            done = {json.loads(line)["id"] for line in f if line.strip()}

    questions = [q for q in load_questions(args.questions, args.limit, args.ids) if q["id"] not in done]
    arm = ARMS[args.arm]()
    from metamatch.agents.client import get_agent_client
    extractor = (get_agent_client()[0], EXTRACT_MODEL)
    print(f"{name}: {len(questions)} questions to run ({len(done)} already done)", flush=True)

    for i, q in enumerate(questions, 1):
        start = time.time()
        try:
            reply, error = arm.answer(q), None
        except Exception as e:  # keep going; a crash is a wrong answer for that question
            reply, error = "", f"{type(e).__name__}: {e}"
        latency = round(time.time() - start, 2)
        extracted = None
        if "ANSWER" in q["question"]:
            parsed, correct, format_ok = grade(q, reply)
        else:
            # No answer format was requested, so read the answer out of the reply the same way for every arm
            extracted = extract(extractor[0], extractor[1], q["question"], reply, q["answer"]["kind"])
            parsed, correct, format_ok = grade(q, extracted)
        row = {"id": q["id"], "arm": name, "format": q["format"], "category": q["category"],
               "correct": correct, "format_ok": format_ok, "parsed": parsed, "truth": q["answer"]["value"],
               "latency": latency, "error": error, "reply": reply, "extracted": extracted}
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        print(f"[{i}/{len(questions)}] {q['id']} {q['category']:7} {'OK ' if correct else 'BAD'} "
              f"{latency:5.1f}s parsed={parsed!r} truth={q['answer']['value']!r}" + (f" ERROR {error}" if error else ""),
              flush=True)


if __name__ == "__main__":
    main()

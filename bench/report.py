"""
Summarises bench/results/*.jsonl into accuracy tables per arm, format and category, with
bootstrap 95% confidence intervals on overall accuracy.

Run: python bench/report.py
     python bench/report.py --compare template_paraphrase2 metamatch_paraphrase2   (paired difference)
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

RESULTS = Path(__file__).resolve().parent / "results"
RESAMPLES = 10_000


def pct(rows, key="correct"):
    return f"{100 * sum(r[key] for r in rows) / len(rows):.0f}%" if rows else "n/a"


def ci(values, resamples=RESAMPLES, seed=0):
    """Bootstrap 95% percentile interval for the mean of 0/1 (or paired difference) values, in percent."""
    values = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = values[rng.integers(0, len(values), (resamples, len(values)))].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5]) * 100
    return lo, hi


def fmt_ci(rows):
    if not rows:
        return "n/a"
    lo, hi = ci([r["correct"] for r in rows])
    return f"{lo:.0f} to {hi:.0f}"


def compare(arms, a, b):
    """Paired difference b minus a over the questions both arms answered."""
    by_id = {name: {r["id"]: r["correct"] for r in arms[name]} for name in (a, b)}
    shared = sorted(set(by_id[a]) & set(by_id[b]))
    if not shared:
        return f"{a} and {b} share no questions."
    diff = [by_id[b][q] - by_id[a][q] for q in shared]
    lo, hi = ci(diff)
    only_b = sum(d > 0 for d in diff)
    only_a = sum(d < 0 for d in diff)
    verdict = "significant" if lo > 0 or hi < 0 else "not significant (interval includes 0)"
    return (f"{b} vs {a} on {len(shared)} shared questions: {100 * np.mean(diff):+.1f} points, "
            f"95% CI {lo:+.1f} to {hi:+.1f}, {verdict}. "
            f"Right only in {b}: {only_b}; right only in {a}: {only_a}.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", nargs=2, metavar=("BASE", "OTHER"), help="paired bootstrap difference of two arms")
    args = parser.parse_args()

    arms = {}
    for path in sorted(RESULTS.glob("*.jsonl")):
        with open(path, encoding="utf-8") as f:
            arms[path.stem] = [json.loads(line) for line in f if line.strip()]
    if not arms:
        print("No results yet. Run bench/run.py first.")
        return

    categories = sorted({r["category"] for rows in arms.values() for r in rows})
    formats = sorted({r["format"] for rows in arms.values() for r in rows})
    lines = []

    header = ["arm", "n", "overall", "95% CI", *formats, "answer format ok", "avg latency", "errors"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for arm, rows in arms.items():
        by_fmt = [pct([r for r in rows if r["format"] == f]) for f in formats]
        latency = sum(r["latency"] for r in rows) / len(rows)
        errors = sum(1 for r in rows if r["error"])
        lines.append(f"| {arm} | {len(rows)} | {pct(rows)} | {fmt_ci(rows)} | " + " | ".join(by_fmt)
                     + f" | {pct(rows, 'format_ok')} | {latency:.1f}s | {errors} |")

    lines.append("")
    header = ["arm", *categories]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for arm, rows in arms.items():
        by_cat = defaultdict(list)
        for r in rows:
            by_cat[r["category"]].append(r)
        lines.append(f"| {arm} | " + " | ".join(pct(by_cat[c]) for c in categories) + " |")

    if args.compare:
        missing = [a for a in args.compare if a not in arms]
        if missing:
            raise SystemExit(f"No results for: {', '.join(missing)}")
        lines += ["", compare(arms, *args.compare)]

    report = "\n".join(lines)
    print(report)
    (RESULTS / "summary.md").write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

"""Summarises bench/results/*.jsonl into accuracy tables per arm, format and category."""
import json
from collections import defaultdict
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def pct(rows, key="correct"):
    return f"{100 * sum(r[key] for r in rows) / len(rows):.0f}%" if rows else "n/a"


def main():
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

    header = ["arm", "n", "overall", *formats, "answer format ok", "avg latency", "errors"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for arm, rows in arms.items():
        by_fmt = [pct([r for r in rows if r["format"] == f]) for f in formats]
        latency = sum(r["latency"] for r in rows) / len(rows)
        errors = sum(1 for r in rows if r["error"])
        lines.append(f"| {arm} | {len(rows)} | {pct(rows)} | " + " | ".join(by_fmt)
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

    report = "\n".join(lines)
    print(report)
    (RESULTS / "summary.md").write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

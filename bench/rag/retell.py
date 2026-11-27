"""
Oak's voiced passages (agents/retell.py), on every question of a set, through the chat's own path: retrieve
(coach.references), pick the passage Oak would read, frame it, quote the sentences that answer the question.

  python bench/rag/retell.py                                   # held out set, the chat's model
  python bench/rag/retell.py --model gemma3:4b --save runs/frame_gemma.jsonl

The quote is the passage's own words, so it can't misstate it; what's measured is the rest:
  * how many questions had a passage worth reading,
  * how many framing lines the model wrote that passed check_frame (the rest fell back to a template line; the
    chat itself uses the template lines unless METAMATCH_FRAME=model),
  * how many quotes contain a word from the question (a rough relevance check on the chosen sentences),
  * the latency of the framing line.
--save keeps every question, frame and quote for reading by hand.
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "src"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", default="heldout_queries.jsonl")
    ap.add_argument("--model")
    ap.add_argument("--save")
    args = ap.parse_args()
    from metamatch.agents import coach, retell
    from metamatch.engine.names import find_pokemon

    queries = [json.loads(line) for line in open(HERE / args.queries, encoding="utf-8") if line.strip()]
    n = with_passage = by_model = on_topic = 0
    latency, rows = [], []
    for q in queries:
        n += 1
        hits = coach.references(q["query"], {}, format_id=q["format"])
        asked = {coach._species_key(x) for x in find_pokemon(q["query"])}
        hit = next((h for h in hits if coach._card_worthy(h) or coach._named_analysis(h, asked, q["query"])), None)
        if not hit:
            rows.append({"query": q["query"], "passage": None})
            continue
        with_passage += 1
        t0 = time.perf_counter()
        line, by = retell.frame(q["query"], hit["metadata"], model=args.model, use_model=True)
        latency.append(time.perf_counter() - t0)
        by_model += by == "model"
        quote = retell.quoted(q["query"], hit)
        topical = bool(retell._words(q["query"]) & retell._words(quote))
        on_topic += topical
        rows.append({"query": q["query"], "source": hit["metadata"].get("pokemon"), "section": hit["metadata"].get("section"),
                     "frame": line, "by": by, "quote": quote, "shares_a_word": topical})
    latency.sort()
    print(f"{args.queries}: {n} questions, {with_passage} with a passage worth reading")
    print(f"framing lines written by the model and passing the check: {by_model} of {with_passage}; "
          f"the rest used a template line")
    print(f"quotes sharing a word with the question: {on_topic} of {with_passage}")
    if latency:
        print(f"framing latency p50 {latency[len(latency) // 2]:.1f} s  p95 {latency[int(len(latency) * .95)]:.1f} s")
    if args.save:
        out = HERE / args.save
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

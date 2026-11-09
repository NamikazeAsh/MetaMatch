"""
Retrieval benchmark for the RAG store, run through the production path (rag/store.query_strategies).

  python bench/rag/score.py            # scores the index on disk
  python bench/rag/score.py --show     # also prints each miss

queries.jsonl: {"query", "format", "gold": [metadata matches] | "mega_ou" | [], "must": optional key term}.
A hit is gold when its metadata matches one entry (e.g. {"pokemon": "Kingambit"}); with "must", its text
must also contain the term (strict). Queries with gold [] have no right answer: the score counts how many
references Oak would still be served for them. "oak@2" follows Oak's real path: 4 hits, then the
relevance filter, keep 2.
Caveat: the 65 queries were written while the retrieval variants were being designed, so they are a
development set, not a held out one.
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "src"))


def is_gold(hit, gold, must=None):
    meta = hit["metadata"]
    if must and must.lower() not in hit["text"].lower():
        return False
    if gold == "mega_ou":
        return "-Mega" in (meta.get("pokemon") or "") and meta.get("format") == "gen9championsou"
    return any(all(meta.get(k) == v for k, v in g.items()) for g in gold)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    from metamatch.agents.coach import _relevant
    from metamatch.engine.names import find_pokemon
    from metamatch.rag import store

    queries = [json.loads(line) for line in open(HERE / "queries.jsonl", encoding="utf-8") if line.strip()]
    store.get_model()
    n = r1 = r3 = r5 = mrr = s_n = s1 = s3 = oak = nogold = served = 0
    latency, misses = [], []
    for q in queries:
        t0 = time.perf_counter()
        hits = store.query_strategies(q["query"], n_results=10, format_id=q["format"])
        latency.append(time.perf_counter() - t0)
        names = find_pokemon(q["query"])
        oak_hits = [h for h in hits[:4] if _relevant(h, names)][:2]
        if q["gold"] == []:
            nogold += 1
            served += len(oak_hits)
            continue
        n += 1
        ranks = [i for i, h in enumerate(hits) if is_gold(h, q["gold"])]
        if ranks:
            mrr += 1 / (ranks[0] + 1)
            r1 += ranks[0] < 1
            r3 += ranks[0] < 3
            r5 += ranks[0] < 5
        else:
            misses.append((q["query"], [(h["metadata"].get("pokemon"), h["metadata"].get("section")) for h in hits[:3]]))
        if q.get("must"):
            s_n += 1
            strict = [i for i, h in enumerate(hits) if is_gold(h, q["gold"], q["must"])]
            s1 += bool(strict) and strict[0] < 1
            s3 += bool(strict) and strict[0] < 3
        oak += any(is_gold(h, q["gold"]) for h in oak_hits)
    latency.sort()
    print(f"queries {len(queries)} (with gold {n}, strict {s_n}, no gold {nogold})")
    print(f"recall@1 {r1 / n:.2f}  @3 {r3 / n:.2f}  @5 {r5 / n:.2f}  MRR {mrr / n:.3f}")
    print(f"strict@1 {s1 / s_n:.2f}  @3 {s3 / s_n:.2f}  oak@2 {oak / n:.2f}  no gold queries served {served} references")
    print(f"latency p50 {latency[len(latency) // 2] * 1000:.0f} ms  p95 {latency[int(len(latency) * .95)] * 1000:.0f} ms")
    if args.show:
        for query, top in misses:
            print(f"  miss: {query} -> {top}")


if __name__ == "__main__":
    main()

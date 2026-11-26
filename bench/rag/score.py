"""
Retrieval benchmark for the RAG store, run through the production path (rag/store.query_strategies).

  python bench/rag/score.py                                  # dev set (queries.jsonl), index on disk
  python bench/rag/score.py --queries heldout_queries.jsonl  # blind held out set
  python bench/rag/score.py --save runs/base.json            # also keep each query's gold ranks
  python bench/rag/score.py --compare runs/base.json runs/new.json   # paired test between two saved runs
  python bench/rag/score.py --show                           # also prints each miss

Query files: {"query", "format", "gold": [metadata matches] | "mega_ou" | [], "must": optional key term}.
A hit is gold when its metadata matches one entry (e.g. {"pokemon": "Kingambit"}); with "must", its text
must also contain the term (strict). Queries with gold [] have no right answer: the score counts how many
references Oak would still be served for them. "oak@2" follows Oak's real path: the relevance filter
applied before ranking, 4 hits, a second slot only for a concept or a named Pokemon
(agents/coach.references).

Metrics: recall@1/3/5 (the first gold hit is in the top k), MRR, and nDCG@5 with every gold hit in the top 5
counted as relevant (binary gain). --compare runs a paired permutation test on per query reciprocal rank, so
two runs are compared question by question, not just on their averages.
queries.jsonl was written while the retrieval variants were designed, so it's a development set;
heldout_queries.jsonl was written blind by an agent that never saw the code.
"""
import argparse
import json
import math
import random
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
    # A Mega's set is filed under the Mega, with its base species in "species"
    return any(all(meta.get(k) == v or (k == "pokemon" and meta.get("species") == v) for k, v in g.items())
               for g in gold)


def ndcg5(flags):
    """nDCG@5 for a ranked list of booleans (relevant or not), ideal = all relevant hits first."""
    dcg = sum(1 / math.log2(i + 2) for i, f in enumerate(flags[:5]) if f)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(5, sum(flags))))
    return dcg / ideal if ideal else 0.0


def permutation_test(a, b, rounds=10000, seed=0):
    """Two sided p value that two paired score lists differ, by randomly swapping each pair's labels."""
    rng = random.Random(seed)
    diffs = [x - y for x, y in zip(a, b)]
    observed = abs(sum(diffs))
    hits = sum(abs(sum(d if rng.random() < 0.5 else -d for d in diffs)) >= observed for _ in range(rounds))
    return (hits + 1) / (rounds + 1)


def compare(path_a, path_b):
    a, b = (json.loads((Path(p) if Path(p).is_absolute() else HERE / p).read_text(encoding="utf-8"))
            for p in (path_a, path_b))
    shared = [q for q in a if q in b]
    for metric in ("rr", "r1", "ndcg5"):
        xa, xb = [a[q][metric] for q in shared], [b[q][metric] for q in shared]
        p = permutation_test(xb, xa)
        print(f"{metric:6} {sum(xa) / len(xa):.3f} -> {sum(xb) / len(xb):.3f}  "
              f"({(sum(xb) - sum(xa)) / len(xa):+.3f}, p = {p:.3f}, n = {len(shared)})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", default="queries.jsonl")
    ap.add_argument("--save")
    ap.add_argument("--compare", nargs=2)
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    if args.compare:
        compare(*args.compare)
        return
    from metamatch.agents.coach import references
    from metamatch.rag import store

    queries = [json.loads(line) for line in open(HERE / args.queries, encoding="utf-8") if line.strip()]
    store.get_model()
    n = r1 = r3 = r5 = mrr = nd = s_n = s1 = s3 = oak = nogold = served = 0
    latency, misses, per_query = [], [], {}
    for q in queries:
        t0 = time.perf_counter()
        hits = store.query_strategies(q["query"], n_results=10, format_id=q["format"])
        latency.append(time.perf_counter() - t0)
        oak_hits = references(q["query"], {}, format_id=q["format"])
        if q["gold"] == []:
            nogold += 1
            served += len(oak_hits)
            continue
        n += 1
        flags = [is_gold(h, q["gold"]) for h in hits]
        ranks = [i for i, f in enumerate(flags) if f]
        rr = 1 / (ranks[0] + 1) if ranks else 0.0
        mrr += rr
        nd += ndcg5(flags)
        if ranks:
            r1 += ranks[0] < 1
            r3 += ranks[0] < 3
            r5 += ranks[0] < 5
        else:
            misses.append((q["query"], [(h["metadata"].get("pokemon"), h["metadata"].get("section")) for h in hits[:3]]))
        per_query[q["query"]] = {"rr": rr, "r1": float(bool(ranks) and ranks[0] < 1), "ndcg5": ndcg5(flags)}
        if q.get("must"):
            s_n += 1
            strict = [i for i, h in enumerate(hits) if is_gold(h, q["gold"], q["must"])]
            s1 += bool(strict) and strict[0] < 1
            s3 += bool(strict) and strict[0] < 3
        oak += any(is_gold(h, q["gold"]) for h in oak_hits)
    latency.sort()
    print(f"{args.queries}: {len(queries)} queries (with gold {n}, strict {s_n}, no gold {nogold})")
    print(f"recall@1 {r1 / n:.2f}  @3 {r3 / n:.2f}  @5 {r5 / n:.2f}  MRR {mrr / n:.3f}  nDCG@5 {nd / n:.3f}")
    print(f"strict@1 {s1 / max(s_n, 1):.2f}  @3 {s3 / max(s_n, 1):.2f}  oak@2 {oak / n:.2f}  "
          f"no gold queries served {served} references")
    print(f"latency p50 {latency[len(latency) // 2] * 1000:.0f} ms  p95 {latency[int(len(latency) * .95)] * 1000:.0f} ms")
    if args.save:
        out = HERE / args.save if not Path(args.save).is_absolute() else Path(args.save)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(per_query, indent=1), encoding="utf-8")
    if args.show:
        for query, top in misses:
            print(f"  miss: {query} -> {top}")


if __name__ == "__main__":
    main()

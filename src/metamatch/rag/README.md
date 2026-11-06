# Retrieval (RAG)

Professor Oak (and Brock, for one supporting passage) answers strategy questions with passages retrieved from a local index. Every chunk is tagged with its game and format, so a UU team gets UU analyses and a Champions team never sees SV advice.

## Sources

| Source | Scope | File |
| :--- | :--- | :--- |
| Smogon analyses for every SV format (OU, UU, National Dex): overview, each set, other options | One format each | `scraper.py` |
| Concept notes: general singles, SV only, Champions only (`data/knowledge/concepts_*.md`) | Game wide | `build_index.py` |
| Usage cards from Smogon chaos data: spreads, items, abilities, moves, teammates, speed | One Champions format each | `usage_cards.py` |
| Community guides from Pokechamp, reworded and cached in `data/knowledge/pokechamp_guides.json` | Champions | `pokechamp.py` |

## Chunks (`chunking.py`)

* Bodies are split at sentence boundaries into 300 to 900 characters, so each fits `bge-small`'s 512 token window and one prompt slot. Empty sections produce no chunk.
* Each chunk starts with one header line, `Pokemon: X | Section: Y | Format: Z`, which both the embedder and BM25 see (the cheap, non LLM form of contextual retrieval).

## Store (`store.py`)

* **Dense:** `BAAI/bge-small-en-v1.5` vectors in ChromaDB; queries use bge's search instruction prefix.
* **Lexical:** an in memory BM25 index over the same chunks, built once per index and cached.
* **Fusion:** reciprocal rank fusion of both rankings, plus a small boost for chunks about a Pokémon the question names.
* **Scoping:** the format's own chunks plus game wide guides and concepts; an SV format without its own analyses falls back to OU's.
* `query_strategies(query, n_results, format_id, names)` returns `{text, metadata, distance}` hits.
* `index_stale()` is true when the stats on disk are newer than the ones the index was built from; the chat shows a notice.

## Benchmark

`python bench/rag/score.py` scores 65 strategy questions through the production path: recall@1 went from 0.74 (old index, dense only) to 0.94, and the key term reaching the top hit from 0.55 to 0.95. A small cross encoder reranker was tested and rejected (lower recall@1, 870 ms slower).

## Rebuilding

```bash
python -m metamatch.rag.pokechamp            # optional: refresh the Champions guide cache (needs Ollama)
python src/metamatch/rag/build_index.py
```

`python scripts/update_meta.py --rebuild-index` does the same, also when the stats are already current.

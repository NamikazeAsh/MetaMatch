# Retrieval (RAG)

Professor Oak answers strategy questions with passages retrieved from a local ChromaDB index. Each chunk is tagged with its game (`sv`, `champions` or `any`) so a question about a Champions team never retrieves SV advice.

## Sources

| Source | Game | File |
| :--- | :--- | :--- |
| Smogon Gen 9 OU analyses, split into overview, moveset and checks paragraphs | SV | `scraper.py` |
| Hand written strategy concepts (`data/knowledge/concepts.md`) | Any | `build_index.py` |
| Usage cards built from Smogon chaos data: top moves, items, abilities and teammates | Champions | `usage_cards.py` |
| Community guides from Pokechamp, reworded and cached in `data/knowledge/pokechamp_guides.json` | Champions | `pokechamp.py` |

## Store (`store.py`)

* Embeddings: `BAAI/bge-small-en-v1.5` via Sentence Transformers, loaded once and cached.
* `rebuild_index(chunks)` replaces the `data/chroma_db/` collection.
* `query_strategies(query, n_results, max_distance, format_id)` returns the nearest singles chunks for the format's game, dropping anything past an L2 distance of 1.0.

## Rebuilding

```bash
python -m metamatch.rag.pokechamp            # optional: refresh the Champions guide cache
python src/metamatch/rag/build_index.py
```

`python scripts/update_meta.py --rebuild-index` does the same after a monthly stats update.

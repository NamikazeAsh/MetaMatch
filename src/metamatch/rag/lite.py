"""
Retrieval that runs anywhere, including the free web deploy: no Chroma, no torch. The same chunks and the same
ranking as the local store (rag/store.fuse: BM25 plus dense, fused, with the name boost), but the dense half
comes from a static embedding model, minishlab/potion-retrieval-32M (Model2Vec, MIT licensed): a text's vector is
the mean of its word pieces' rows in one table, so encoding is a lookup and an average in numpy.

The model files (about 130 MB, kept as 16 bit floats in memory) and the Smogon analyses (rag/cards cache) are
fetched on first use and cached in gitignored folders, so nothing heavy or copyrighted is committed. The index is
built once per process and reused by every session.
"""
import json
import threading
from functools import lru_cache

from metamatch import config
from metamatch.rag import store

MODEL_REPO = "minishlab/potion-retrieval-32M"
MODEL_URL = "https://huggingface.co/" + MODEL_REPO + "/resolve/main/{}"
MODEL_DIR = config.DATA_DIR / "models" / "potion-retrieval-32M"
MODEL_FILES = ("config.json", "tokenizer.json", "model.safetensors")
_lock = threading.Lock()


def _download():
    import requests
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name in MODEL_FILES:
        path = MODEL_DIR / name
        if path.exists() and path.stat().st_size:
            continue
        with requests.get(MODEL_URL.format(name), stream=True, timeout=60) as r:
            r.raise_for_status()
            tmp = path.with_suffix(path.suffix + ".part")
            with open(tmp, "wb") as f:
                for block in r.iter_content(1 << 20):
                    f.write(block)
            tmp.replace(path)


@lru_cache(maxsize=1)
def _model():
    """(tokenizer, embedding table, normalize flag), loaded once per process."""
    import numpy as np
    from safetensors.numpy import load_file
    from tokenizers import Tokenizer
    with _lock:
        _download()
    table = load_file(str(MODEL_DIR / "model.safetensors"))
    table = next(iter(table.values())).astype(np.float16)
    tokenizer = Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json"))
    tokenizer.no_truncation()
    normalize = json.loads((MODEL_DIR / "config.json").read_text(encoding="utf-8")).get("normalize", True)
    return tokenizer, table, normalize


def encode(texts):
    """Unit vectors for `texts` (float32, one row each): the mean of each text's word piece embeddings."""
    import numpy as np
    tokenizer, table, normalize = _model()
    unk = tokenizer.token_to_id("[UNK]")
    out = np.zeros((len(texts), table.shape[1]), dtype=np.float32)
    for row, enc in enumerate(tokenizer.encode_batch(list(texts), add_special_tokens=False)):
        ids = [i for i in enc.ids if i != unk]
        if ids:
            out[row] = table[ids].astype(np.float32).mean(axis=0)
    if normalize:
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        out /= np.where(norms == 0, 1, norms)
    return out


def chunks():
    """Every chunk the local index holds that can exist here: Smogon analyses (fetched on first use), concept
    notes, Champions usage cards and the reworded Pokechamp guides. Smogon's technique guides are local only."""
    from metamatch.rag import build_index, guides, pokechamp, scraper, usage_cards
    out = scraper.fetch_smogon_strategies(refresh=False)
    out += build_index.load_concepts()
    out += usage_cards.build_chunks()
    out += pokechamp.build_chunks()
    out += guides.build_chunks()   # empty unless this machine cached them
    return build_index.dedupe(out)


@lru_cache(maxsize=1)
def index():
    """(corpus stats for store.fuse, chunk vectors), built once per process."""
    items = chunks()
    ids = [f"lite-{i}" for i in range(len(items))]
    docs = [c["text"] for c in items]
    metas = [c["metadata"] for c in items]
    return store.corpus_stats(ids, docs, metas), encode(docs)


def ready():
    """True once the model and the index are loaded in this process."""
    return index.cache_info().currsize > 0


def query_strategies(query, n_results=3, format_id=None, names=None, keep=None):
    """Same contract as rag/store.query_strategies: [{'id', 'text', 'metadata', 'distance'}], best first."""
    import numpy as np
    corpus, vectors = index()
    format_id = format_id or config.DEFAULT_FORMAT
    allowed = store.allowed_rows(corpus[2], format_id, keep)
    if not allowed:
        return []
    query = store.canonical(query)
    sims = vectors[allowed] @ encode([query])[0]
    order = np.argsort(-sims)[:store.POOL]
    dense_rows = [allowed[j] for j in order]
    distance = {allowed[j]: float(1 - sims[j]) for j in order}
    top = store.fuse(query, allowed, corpus, dense_rows, names, n_results)
    ids, docs, metas = corpus[0], corpus[1], corpus[2]
    return [{"id": ids[i], "text": docs[i], "metadata": metas[i], "distance": distance.get(i)} for i in top]

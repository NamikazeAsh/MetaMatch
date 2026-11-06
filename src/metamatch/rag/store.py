"""
Local RAG store: Chroma for dense vectors (BAAI/bge-small-en-v1.5) plus an in memory BM25 index,
fused with reciprocal rank fusion. Exact terms ("Knock Off", "Tera Fairy") are where the small
embedder is weakest and BM25 strongest; chunks about a Pokemon the question names get a small boost.
Retrieval is scoped to the format: its own analyses and usage cards, plus game wide guides and concepts.
Measured on bench/rag (65 queries): recall@1 0.74 with the old index and plain dense search, 0.97 with
clean chunks, headers, the query prefix, BM25 fusion and the name boost.
"""
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache

import chromadb
from sentence_transformers import SentenceTransformer

from metamatch import config

DB_PATH = config.DATA_DIR / "chroma_db"
INFO_PATH = DB_PATH / "index_info.json"
COLLECTION = "pokemon_strategies"
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
# bge's instruction for short queries against passages (documents are embedded without it)
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
RRF_K, POOL, NAME_BOOST = 60, 50, 0.02

TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = set("the a an of to in on is do does i my how what for with and or vs it be should can are as good best set use run".split())


def get_client():
    DB_PATH.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(DB_PATH))


def get_collection():
    return get_client().get_or_create_collection(name=COLLECTION)


@lru_cache(maxsize=1)
def get_model():
    """The embedding model, loaded once per process."""
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def _stats_month():
    try:
        return json.loads((config.STATS_DIR / "manifest.json").read_text(encoding="utf-8")).get("month")
    except (OSError, ValueError):
        return None


def rebuild_index(chunks):
    """Wipes the index and rebuilds it from `chunks` ({'text', 'metadata'}), recording when and for which stats month."""
    print("Initializing embedding model...")
    model = get_model()
    client = get_client()
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    collection = client.create_collection(name=COLLECTION)
    print(f"Embedding {len(chunks)} chunks...")
    documents = [c["text"] for c in chunks]
    embeddings = model.encode(documents, normalize_embeddings=True, batch_size=16).tolist()
    for start in range(0, len(chunks), 1000):
        end = start + 1000
        collection.add(documents=documents[start:end], embeddings=embeddings[start:end],
                       metadatas=[c["metadata"] for c in chunks[start:end]], ids=[f"id_{i}" for i in range(start, min(end, len(chunks)))])
    INFO_PATH.write_text(json.dumps({"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                     "stats_month": _stats_month(), "chunks": len(chunks)}), encoding="utf-8")
    _corpus.cache_clear()
    print("Index successfully rebuilt.")


def index_info():
    try:
        return json.loads(INFO_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def index_stale():
    """True when the usage stats on disk are newer than the ones the index was built from."""
    built, current = index_info().get("stats_month"), _stats_month()
    return bool(current) and built != current


def _tokens(text):
    return [w for w in TOKEN.findall(text.lower().replace("-", "")) if w not in STOPWORDS]


@lru_cache(maxsize=1)
def _corpus(count):
    """(ids, documents, metadatas, BM25 term stats) for the whole collection; `count` keys the cache to the index."""
    data = get_collection().get(include=["documents", "metadatas"])
    terms = [Counter(_tokens(d)) for d in data["documents"]]
    lengths = [sum(t.values()) for t in terms]
    df = Counter(w for t in terms for w in t)
    n = len(terms) or 1
    idf = {w: math.log(1 + (n - k + 0.5) / (k + 0.5)) for w, k in df.items()}
    return data["ids"], data["documents"], data["metadatas"], terms, lengths, (sum(lengths) / n) or 1, idf


def _bm25(query, rows, corpus, k1=1.2, b=0.75):
    _, _, _, terms, lengths, avg, idf = corpus
    words = _tokens(query)
    scores = {}
    for i in rows:
        s = 0.0
        for w in words:
            f = terms[i].get(w)
            if f:
                s += idf[w] * f * (k1 + 1) / (f + k1 * (1 - b + b * lengths[i] / avg))
        if s > 0:
            scores[i] = s
    return scores


def _formats_for(format_id, metadatas):
    """This format's own chunks plus game wide ones; an SV format without its own analyses falls back to OU's."""
    have = {m.get("format") for m in metadatas}
    formats = {format_id, "any"}
    if format_id not in have and config.format_game(format_id) == "sv":
        formats.add(config.DEFAULT_FORMAT)
    return formats


def query_strategies(query, n_results=3, format_id=None, names=None):
    """
    Top chunks for `query` in `format_id`: singles chunks for the format (its analyses or usage cards)
    plus game wide guides and concepts. `names`: Pokemon the question is about (canonical names);
    found with the planner's resolver when not given. Each hit: {'text', 'metadata', 'distance'}.
    """
    collection = get_collection()
    count = collection.count()
    if not count:
        return []
    format_id = format_id or config.DEFAULT_FORMAT
    game = config.format_game(format_id)
    corpus = _corpus(count)
    ids, docs, metas = corpus[0], corpus[1], corpus[2]
    formats = _formats_for(format_id, metas)
    allowed = [i for i, m in enumerate(metas) if m.get("game") in (game, "any") and m.get("play") == "singles"
               and m.get("format", "any") in formats]
    if not allowed:
        return []

    where = {"$and": [{"game": {"$in": [game, "any"]}}, {"play": "singles"}, {"format": {"$in": sorted(formats)}}]}
    embedding = get_model().encode([QUERY_PREFIX + query], normalize_embeddings=True).tolist()
    dense = collection.query(query_embeddings=embedding, n_results=min(POOL, len(allowed)), where=where)
    position = {cid: i for i, cid in enumerate(ids)}
    dense_rows = [position[cid] for cid in dense["ids"][0] if cid in position]
    distance = {position[cid]: d for cid, d in zip(dense["ids"][0], dense["distances"][0]) if cid in position}

    lexical = _bm25(query, allowed, corpus)
    lexical_rows = sorted(lexical, key=lexical.get, reverse=True)[:POOL]
    score = Counter()
    for ranking in (dense_rows, lexical_rows):
        for rank, i in enumerate(ranking):
            score[i] += 1 / (RRF_K + rank)
    if names is None:
        from metamatch.engine.names import find_pokemon
        names = find_pokemon(query)
    named = {n.lower() for n in names or ()}
    for i in score:
        if (metas[i].get("pokemon") or "").lower() in named:
            score[i] += NAME_BOOST
    top = sorted(score, key=score.get, reverse=True)[:n_results]
    return [{"text": docs[i], "metadata": metas[i], "distance": distance.get(i)} for i in top]

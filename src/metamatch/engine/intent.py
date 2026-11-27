"""
A learned question classifier for the chat: what kind of question a player asked, for the questions the planner's
hand written rules don't place (engine/planner.py). The 2026 11 26 coverage audit found the rules miss most new
phrasings of the same kinds of question; a classifier trained on many phrasings generalizes where regexes can't.

* Normalization: every Pokemon becomes "my pokemon" (on the team) or "their pokemon", and moves, items, abilities and
  types become placeholders, so the label comes from what is asked, never from which Pokemon is named.
* Features: the question's Model2Vec embedding (rag/lite.encode, the model Strategy Search already ships) plus a few
  cue words (now, this turn, vs, or, rising, legal...).
* Model: multinomial logistic regression (softmax, L2), trained by scripts/train_intent.py and stored in
  data/json/intent_model.json. numpy only, so it runs on the free web deploy too.
* Abstain: below the confidence threshold tuned on held out data, the chat asks "did you mean" instead of guessing.
"""
import json
import re
from functools import lru_cache

from metamatch import config

PATH = config.JSON_DIR / "intent_model.json"

KINDS = ("speed", "ko", "damage", "type", "stat", "usage", "team_type", "checks", "switchins", "matchup", "member",
         "score", "threats", "gameplan", "win", "lead", "tera", "archetype", "weather", "sets", "teammate", "compare",
         "rules", "how_to_use", "meta_trends", "in_battle", "out_of_scope", "smalltalk", "learn")

TYPES = ("normal", "fire", "water", "electric", "grass", "ice", "fighting", "poison", "ground", "flying", "psychic",
         "bug", "rock", "ghost", "dragon", "dark", "steel", "fairy", "stellar")
THEIRS = re.compile(r"\b(?:their|opposing|opp|opponent'?s?|enemy|vs\.?|versus|against|the other)\s+(?:\w+\s+)?$", re.I)
MINE = re.compile(r"\b(?:my|our|mine)\s+(?:\w+\s+)?$", re.I)
OWNER_WORD = re.compile(r"\b(?:my|our|their|opposing|opp|opponent'?s?|enemy|your)\s+$", re.I)
# Cue words the embedding alone can underweight: a question's frame, not its subject
CUES = [re.compile(p, re.I) for p in (
    r"\b(?:now|right now|this turn|turn \d+|next turn)\b", r"\b(?:vs\.?|versus|against)\b", r"\bor\b",
    r"\b(?:outspeed\w*|faster|slower|speed)\b", r"\b(?:ohko|2hko|ko|survive\w*|tank\w*|live)\b", r"\b(?:damage|calc|%)",
    r"\b(?:weak\w*|resist\w*|immune|super effective)\b", r"\b(?:rising|falling|trend\w*|this month|lately|dominant)\b",
    r"\b(?:legal|banned|allowed)\b", r"\b(?:how does|how do|does)\b.*\bwork\b", r"\b(?:switch\w*|sack|click|send)\b",
    r"\b(?:set|item|ev|evs|nature|spread)\b", r"\b(?:replace|add|partner\w*|teammate\w*)\b", r"\b(?:rate|score|good|viable)\b",
    r"\b(?:threat\w*|beat\w*|counter\w*|check\w*|hole\w*)\b", r"\b(?:lead\w*)\b", r"\b(?:win ?con\w*|sweep\w*)\b",
    r"\b(?:tera\w*)\b", r"\b(?:rain|sun|sand|snow|stall|hyper offense|trick room)\b", r"\b(?:usage|common|popular|usually)\b",
    r"\b(?:vgc|doubles|go|worlds|hack\w*|weather today)\b", r"^\s*(?:hi|hey|hello|thanks?|thx|ty|cool|nice)\b",
    r"\b(?:how (?:do|to|should) i (?:use|play|build))\b", r"\bmy team\b", r"\bjob|role\b")]


def normalize(text, team=None):
    """The question with Pokemon, moves, items, abilities and types swapped for placeholders."""
    from metamatch.engine import rules
    from metamatch.engine.names import find_pokemon_spans
    mine = set()
    for p in (team or {}).values():
        mine |= {(p.get("Pokemon") or "").lower(), (p.get("Forme") or "").lower()}
    mine.discard("")
    out, last, spans = [], 0, []
    for start, end, name in find_pokemon_spans(text):
        if start < last:
            continue
        before = text[:start]
        own = name.lower() in mine or name.split("-")[0].lower() in {m.split("-")[0] for m in mine}
        if OWNER_WORD.search(before):
            word = "pokemon"   # "my gambit", "their dragapult": the player's own word already says whose it is
        elif THEIRS.search(before):
            word = "their pokemon"
        elif MINE.search(before):
            word = "my pokemon"
        else:
            word = "my pokemon" if own else "their pokemon"
        out += [text[last:start], word]
        last = end
    text = "".join(out) + text[last:]
    for pattern, kind, _ in rules._patterns():
        if kind in ("move", "item", "ability"):
            text = pattern.sub(kind, text)
    text = re.sub(r"\b(?:%s)\b" % "|".join(TYPES), "type", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip().lower()


def cue_vector(text):
    return [1.0 if c.search(text) else 0.0 for c in CUES]


def hashed_words(texts, dims=None):
    """Unit length counts of each question's words and word pairs, hashed into `dims` buckets: the word order the
    embedding (an average) can't see. On the dev split they took accuracy from 0.83 to 0.87 (2026 11 27)."""
    import zlib
    import numpy as np
    dims = dims or HASH_DIMS
    out = np.zeros((len(texts), dims), dtype=np.float32)
    for i, t in enumerate(texts):
        w = re.findall(r"[a-z0-9']+", t)
        for g in w + [a + "_" + b for a, b in zip(w, w[1:])]:
            out[i, zlib.crc32(g.encode()) % dims] += 1
        n = np.linalg.norm(out[i])
        if n:
            out[i] /= n
    return out


def features(texts):
    """Rows of [embedding, cues, hashed words and word pairs] for normalized questions."""
    import numpy as np
    from metamatch.rag import lite
    emb = lite.encode(list(texts))
    cues = np.asarray([cue_vector(t) for t in texts], dtype=np.float32) * CUE_SCALE
    return np.hstack([emb, cues, hashed_words(texts)]).astype(np.float32)


CUE_SCALE = 0.35   # cue features sit on a scale near the unit length embedding's
HASH_DIMS = 1024


@lru_cache(maxsize=1)
def _model():
    import numpy as np
    data = json.loads(PATH.read_text(encoding="utf-8"))
    return (data["kinds"], np.asarray(data["W"], dtype=np.float32), np.asarray(data["b"], dtype=np.float32),
            float(data["threshold"]))


def available():
    try:
        _model()
        return True
    except (OSError, ValueError, KeyError):
        return False


def softmax(z):
    import numpy as np
    z = z - z.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)


def classify(text, team=None):
    """{kind, confidence, top: [(kind, p) x3], sure, normalized} for a question."""
    kinds, W, b, threshold = _model()
    norm = normalize(text, team)
    p = softmax(features([norm]) @ W + b)[0]
    order = p.argsort()[::-1][:3]
    top = [(kinds[i], float(p[i])) for i in order]
    return {"kind": top[0][0], "confidence": top[0][1], "top": top, "sure": top[0][1] >= threshold, "normalized": norm}

"""
Trains the chat's question classifier (src/metamatch/engine/intent.py): multinomial logistic regression on the
Model2Vec embedding of each normalized question plus cue words, saved to data/json/intent_model.json.

  python scripts/train_intent.py              # dev report, then the final model trained on everything
  python scripts/train_intent.py --dev-only   # dev report only, nothing written

Training data: data/intent/*.jsonl, one question per line, {"text", "kind", "team"}. "team" is "A" or "B" (the two
sample teams in data/intent/teams.json) or a Showdown paste. 15% of each kind is held out (fixed seed) to measure
accuracy and to choose the confidence below which the chat asks "did you mean" instead of guessing.
"""
import argparse
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from metamatch.engine import intent  # noqa: E402
from metamatch.team import readTeam  # noqa: E402

DATA = ROOT / "data" / "intent"
SEED, DEV_SHARE = 0, 0.15
EPOCHS, LR, L2 = 400, 0.05, 1e-4
TARGET_PRECISION = 0.95   # confident answers must be right this often on the dev split (unsure ones still get answered, with chips)


def _teams():
    pastes = json.loads((DATA / "teams.json").read_text(encoding="utf-8"))
    out = {}
    for key, (paste, fmt) in pastes.items():
        out[key] = readTeam(paste, fmt)[0]
    return out


def load():
    teams = _teams()
    rows = []
    for path in sorted(DATA.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r["kind"] not in intent.KINDS:
                raise SystemExit(f"{path.name}: unknown kind {r['kind']!r}")
            team = r.get("team", "A")
            if team in teams:
                team = teams[team]
            else:
                team = readTeam(team, r.get("format", "gen9ou"))[0]
            rows.append((intent.normalize(r["text"], team), r["kind"], path.stem))
    return rows


def train(X, y, k, weights, epochs=EPOCHS, lr=LR, l2=L2, seed=SEED):
    """Softmax regression by full batch Adam, class weighted so rare kinds count as much as common ones."""
    rng = np.random.default_rng(seed)
    W = rng.normal(0, 0.01, (X.shape[1], k)).astype(np.float32)
    b = np.zeros(k, dtype=np.float32)
    Y = np.eye(k, dtype=np.float32)[y]
    sw = weights[y][:, None]
    m = [np.zeros_like(W), np.zeros_like(b)]
    v = [np.zeros_like(W), np.zeros_like(b)]
    for t in range(1, epochs + 1):
        P = intent.softmax(X @ W + b)
        G = (P - Y) * sw / sw.sum()
        grads = [X.T @ G + l2 * W, G.sum(axis=0)]
        for i, (param, g) in enumerate(((W, grads[0]), (b, grads[1]))):
            m[i] = 0.9 * m[i] + 0.1 * g
            v[i] = 0.999 * v[i] + 0.001 * g * g
            step = lr * (m[i] / (1 - 0.9 ** t)) / (np.sqrt(v[i] / (1 - 0.999 ** t)) + 1e-8)
            param -= step
    return W, b


def _weights(y, k):
    counts = np.bincount(y, minlength=k).astype(np.float32)
    return np.where(counts > 0, counts.sum() / (k * np.maximum(counts, 1)), 0).astype(np.float32)


def threshold_for(p_max, correct, target=TARGET_PRECISION):
    """The lowest confidence at which the answers above it are right at least `target` of the time."""
    order = np.argsort(-p_max)
    best = 1.0
    hits = 0
    for n, i in enumerate(order, 1):
        hits += correct[i]
        if hits / n >= target:
            best = float(p_max[i])
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev-only", action="store_true")
    args = ap.parse_args()
    rows = load()
    kinds = list(intent.KINDS)
    index = {k: i for i, k in enumerate(kinds)}
    print(f"{len(rows)} questions: " + ", ".join(f"{k} {n}" for k, n in sorted(Counter(r[1] for r in rows).items())))
    by_kind = defaultdict(list)
    for i, r in enumerate(rows):
        by_kind[r[1]].append(i)
    rng = random.Random(SEED)
    dev = set()
    for k, ids in by_kind.items():
        rng.shuffle(ids)
        dev |= set(ids[:max(1, int(len(ids) * DEV_SHARE))])
    X = intent.features([r[0] for r in rows])
    y = np.asarray([index[r[1]] for r in rows])
    tr = np.asarray([i for i in range(len(rows)) if i not in dev])
    dv = np.asarray(sorted(dev))
    W, b = train(X[tr], y[tr], len(kinds), _weights(y[tr], len(kinds)))
    P = intent.softmax(X[dv] @ W + b)
    pred = P.argmax(axis=1)
    correct = (pred == y[dv]).astype(int)
    thr = threshold_for(P.max(axis=1), correct)
    sure = P.max(axis=1) >= thr
    print(f"dev: accuracy {correct.mean():.3f} on {len(dv)}; threshold {thr:.3f}: answers {sure.mean():.0%} "
          f"of questions at accuracy {correct[sure].mean():.3f}, asks 'did you mean' on the rest")
    per = defaultdict(lambda: [0, 0])
    for t, ok in zip(y[dv], correct):
        per[kinds[t]][0] += ok
        per[kinds[t]][1] += 1
    print("  " + ", ".join(f"{k} {a}/{n}" for k, (a, n) in sorted(per.items())))
    confused = Counter((kinds[t], kinds[p]) for t, p in zip(y[dv], pred) if t != p)
    print("  most confused:", ", ".join(f"{a}->{b} {n}" for (a, b), n in confused.most_common(8)))
    if args.dev_only:
        return
    W, b = train(X, y, len(kinds), _weights(y, len(kinds)))
    digest = hashlib.sha1("".join(f"{r[0]}|{r[1]}" for r in rows).encode()).hexdigest()[:12]
    out = {"kinds": kinds, "W": np.round(W, 5).tolist(), "b": np.round(b, 5).tolist(), "threshold": round(thr, 4),
           "trained_on": len(rows), "data_hash": digest, "dev_accuracy": round(float(correct.mean()), 4)}
    intent.PATH.write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"written {intent.PATH.relative_to(ROOT)} ({intent.PATH.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

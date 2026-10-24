import json
import re
import sys
from pathlib import Path

# Add 'src' directory to path so "import metamatch" works
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(SRC_DIR))

from metamatch import config
from metamatch.utils import fetch_pokemon_data, calculate_speed

# One chunk per Pokemon built straight from Smogon chaos data, so every number the
# LLM sees is real ladder data (spreads, items, moves, teammates, speed).
STAT_NAMES = ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]
SPEED_PLUS = {"Timid", "Jolly", "Hasty", "Naive"}
SPEED_MINUS = {"Brave", "Relaxed", "Quiet", "Sassy"}
MIN_USAGE = 1.0   # percent of teams
TOP_N = 4


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def load_display_names(format_id):
    """Maps chaos slugs ('rockyhelmet') to display names ('Rocky Helmet') using the Smogon moveset file."""
    names = {}
    path = config.moveset_path(format_id)
    if path.exists():
        pat = re.compile(r"^\| (.+?) \d+\.\d+%\s*\|$")
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                m = pat.match(line.strip())
                if m and ":" not in m.group(1):
                    names[_norm(m.group(1))] = m.group(1)
    return names


def _top(counts, n=TOP_N, total=None, names=None):
    """
    Returns [(name, pct)] for the n most used entries of a chaos counts dict.
    pct is a share of `total` (defaults to the dict's own sum).
    """
    total = total or sum(counts.values()) or 1
    names = names or {}
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:n]
    return [(names.get(_norm(k), k), v / total * 100) for k, v in ranked if k and k != "nothing"]


def _fmt_spread(spread):
    """'Jolly:2/32/0/0/0/32' -> 'Jolly 2 HP / 32 Atk / 32 Spe'."""
    nature, _, vals = spread.partition(":")
    parts = [f"{v} {s}" for v, s in zip(vals.split("/"), STAT_NAMES) if v != "0"]
    return f"{nature} " + " / ".join(parts)


def _speed_line(name, spreads, game):
    data = fetch_pokemon_data(name)
    if not data or not spreads:
        return ""
    nature, _, vals = spreads[0][0].partition(":")
    spe = int(vals.split("/")[5])
    mod = 1.1 if nature in SPEED_PLUS else 0.9 if nature in SPEED_MINUS else 1.0
    speed = calculate_speed(data["stats"]["speed"], ev=spe, nature_mod=mod, game=game)
    level = 50 if game == "champions" else 100
    return f"Speed with its most common spread: {speed} (Level {level})."


def build_chunks(games=("champions",)):
    chunks = []
    for fmt_id, fmt in config.FORMATS.items():
        if fmt["game"] not in games:
            continue
        path = config.STATS_DIR / (fmt["stats"] + ".json")
        if not path.exists():
            print(f"Skipping {fmt['label']} usage cards: {path.name} not downloaded")
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f).get("data", {})
        names = load_display_names(fmt_id)

        for name, p in data.items():
            usage = p.get("usage", 0) * 100
            if usage < MIN_USAGE:
                continue
            # Abilities sum to the Pokemon's total weight, so moves become "% of sets running it"
            weight = sum(p.get("Abilities", {}).values()) or 1
            spreads = _top(p.get("Spreads", {}), 3)
            moves = _top(p.get("Moves", {}), 6, total=weight, names=names)
            teammates = sorted(p.get("Teammates", {}).items(), key=lambda x: x[1], reverse=True)[:5]
            text = (
                f"{fmt['label'].upper()} LADDER USAGE DATA (Smogon stats): {name}. "
                f"Used on {usage:.1f}% of teams. "
                f"Spreads: " + ", ".join(f"{_fmt_spread(s)} ({pct:.0f}%)" for s, pct in spreads) + ". "
                f"Items: " + ", ".join(f"{i} ({pct:.0f}%)" for i, pct in _top(p.get("Items", {}), names=names)) + ". "
                f"Abilities: " + ", ".join(f"{a} ({pct:.0f}%)" for a, pct in _top(p.get("Abilities", {}), 2, names=names)) + ". "
                f"Moves: " + ", ".join(f"{m} ({pct:.0f}%)" for m, pct in moves) + ". "
                f"Common teammates: " + ", ".join(t for t, _ in teammates) + ". "
                + _speed_line(name, spreads, fmt["game"])
            )
            chunks.append({
                "pokemon": name,
                "category": "Usage",
                "text": text,
                "metadata": {
                    "pokemon": name, "type": "usage", "source": "smogon_stats",
                    "game": fmt["game"], "play": "singles", "format": fmt_id,
                },
            })
    print(f"Built {len(chunks)} usage cards.")
    return chunks

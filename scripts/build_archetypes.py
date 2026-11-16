"""
Builds data/json/archetypes.json: who plays rain, sun and sand, and which walls stall teams are built from, measured
from Smogon's teammate data, so "how do I play against rain" is answered with the user's own one on ones against the
real rain roster instead of general advice.

Rosters use the 1500 rated chaos file: at 1825 small archetypes come from a handful of players (Pelipper's weighted
sample was 118.6 at 1825 against 27,372 at 1500 in October 2026, and Hippowdon's 1825 partners were one copied team).
Snow, Trick Room, screens and Spikes stacking are left out: their rosters were not stable month to month.

  python scripts/build_archetypes.py                    # downloads the current month's gen9ou-1500 chaos file
  python scripts/build_archetypes.py --file <path>      # or reads a local copy
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from metamatch import config  # noqa: E402

OUT = config.DATA_DIR / "json" / "archetypes.json"
WEATHER = {"rain": ("drizzle", "Rain"), "sun": ("drought", "Sun"), "sand": ("sandstream", "Sand")}
RECOVERY = {"recover", "roost", "slackoff", "softboiled", "shoreup", "synthesis", "moonlight", "morningsun",
            "strengthsap", "wish", "milkdrink", "rest", "painsplit", "lifedew"}
# Walls that heal without a recovery move (Poison Heal with Protect), added by hand
EXTRA_WALLS = {"gen9ou": ["Gliscor"]}
MIN_SETTER_USAGE, MIN_LIFT, MIN_SHARE, PARTNERS = 0.004, 2.0, 0.08, 6
# Sand partners beyond Excadrill did not hold up across months, so sand needs a stronger link
MIN_LIFT_BY = {"sand": 3.0}


def weight(e):
    return sum(e.get("Abilities", {}).values()) or 1


def share(e, key, option):
    return e.get(key, {}).get(option, 0) / weight(e)


def lift(d, a, b):
    ea, eb = d.get(a), d.get(b)
    if not ea or not eb or not eb.get("usage"):
        return 0.0
    return (ea["Teammates"].get(b, 0) / weight(ea)) / eb["usage"]


def defensive(e):
    """Share of spreads with 100 or fewer EVs in both attacking stats."""
    total = low = 0
    for spread, count in e.get("Spreads", {}).items():
        evs = spread.split(":")[1].split("/")
        total += count
        low += count if int(evs[1]) <= 100 and int(evs[3]) <= 100 else 0
    return low / total if total else 0.0


def roster(d, setters, min_lift=MIN_LIFT):
    """Partners of the setters, usage weighted: (name, share of the setters' teams, lift)."""
    total = sum(d[s]["usage"] for s in setters) or 1
    agg = {}
    for s in setters:
        w = d[s]["usage"] / total
        for b in d[s]["Teammates"]:
            if b in setters or b not in d:
                continue
            a = agg.setdefault(b, [0.0, 0.0])
            a[0] += w * d[s]["Teammates"][b] / weight(d[s])
            a[1] += w * lift(d, s, b)
    rows = [(b, round(p, 3), round(L, 1)) for b, (p, L) in agg.items() if L >= min_lift and p >= MIN_SHARE]
    return sorted(rows, key=lambda r: -r[1])[:PARTNERS]


def build(d, format_id):
    out = {}
    for key, (ability, weather) in WEATHER.items():
        setters = [n for n, e in d.items() if e["usage"] >= MIN_SETTER_USAGE and share(e, "Abilities", ability) >= 0.5]
        if setters:
            setters.sort(key=lambda n: -d[n]["usage"])
            out[key] = {"weather": weather, "setters": [[s, round(d[s]["usage"] * 100, 2)] for s in setters],
                        "partners": roster(d, setters, MIN_LIFT_BY.get(key, MIN_LIFT))}
    walls = [n for n, e in d.items() if e["usage"] >= MIN_SETTER_USAGE
             and sum(share(e, "Moves", m) for m in RECOVERY if m in e.get("Moves", {})) >= 0.6 and defensive(e) >= 0.6]
    extra = [w for w in EXTRA_WALLS.get(format_id, []) if w in d and w not in walls]
    walls += extra
    # Walls that share teams with other walls are the stall core; hand added walls are always kept
    together = {w: sum(d[w]["Teammates"].get(o, 0) / weight(d[w]) for o in walls if o != w) for w in walls}
    core = sorted((w for w in walls if w not in extra), key=lambda w: -together[w])[:8] + extra
    out["stall"] = {"walls": [[w, round(d[w]["usage"] * 100, 2), round(together[w], 2)] for w in core]}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="a local gen9ou-1500 chaos JSON")
    ap.add_argument("--month", help="YYYY-MM to download (defaults to the stats month on disk)")
    args = ap.parse_args()
    month = args.month or json.loads((config.STATS_DIR / "manifest.json").read_text(encoding="utf-8")).get("month")
    if args.file:
        raw = json.loads(Path(args.file).read_text(encoding="utf-8"))
    else:
        url = f"https://www.smogon.com/stats/{month}/chaos/gen9ou-1500.json"
        print(f"Downloading {url}")
        with urllib.request.urlopen(url, timeout=120) as r:
            raw = json.load(r)
    data = {"gen9ou": {"month": month, "source": "gen9ou-1500", **build(raw["data"], "gen9ou")}}
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    for k, v in data["gen9ou"].items():
        if isinstance(v, dict):
            names = [s[0] for s in v.get("setters", [])] + [p[0] for p in v.get("partners", [])] + [w[0] for w in v.get("walls", [])]
            print(f"{k}: {', '.join(names)}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

"""
Builds data/json/learnsets.json, the moves every Pokemon can learn, for Move Search's "Can learn it" results.
Read from Pokemon Showdown's data (MIT licensed):

  data/learnsets.ts                  sv: moves with a generation 9 source; past: moves only earlier generations
                                     teach, which National Dex allows
  data/mods/champions/learnsets.ts   champions: Pokemon Champions' own movepools
  data/pokedex.ts                    prevo and changesFrom (an evolution learns its pre-evolution's moves, a forme
                                     like Rotom-Wash its base form's) and baseSpecies (a Mega has no entry of its own)

Moves are stored as one space separated string of ids per Pokemon to keep the file small.

  python scripts/build_learnsets.py                 # downloads the three files from the Showdown repo
  python scripts/build_learnsets.py --src-dir dir   # or reads local copies named like data_learnsets.ts
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/"
FILES = ["data/learnsets.ts", "data/mods/champions/learnsets.ts", "data/pokedex.ts"]
OUT = ROOT / "data" / "json" / "learnsets.json"

ENTRY = re.compile(r"^\t\"?([a-z0-9]+)\"?: \{")
LEARNSET_OPEN = re.compile(r"^\t\tlearnset: \{")
INHERIT = re.compile(r"^\t\tinherit: true,")
MOVE = re.compile(r'^\t\t\t"?([a-z0-9]+)"?: \[(.*)\],')
BLOCK_CLOSE = re.compile(r"^\t\t\},")
DEX_FIELD = re.compile(r'^\t\t(prevo|changesFrom|baseSpecies): "((?:[^"\\]|\\.)*)",')


def to_id(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_learnsets(text):
    """{species id: {move id: [sources like "9M", "8L1"]}}, plus the ids marked inherit: true (a mod's entry
    that adds to the base game's instead of replacing it)."""
    out, inherit, cur, inside = {}, set(), None, False
    for line in text.splitlines():
        m = ENTRY.match(line)
        if m:
            cur, inside = m.group(1), False
            continue
        if cur is None:
            continue
        if INHERIT.match(line):
            inherit.add(cur)
        elif LEARNSET_OPEN.match(line):
            inside = True
            out.setdefault(cur, {})
        elif inside and BLOCK_CLOSE.match(line):
            inside = False
        elif inside:
            mv = MOVE.match(line)
            if mv:
                out[cur][mv.group(1)] = re.findall(r'"([^"]+)"', mv.group(2))
    return out, inherit


def parse_pokedex(text):
    """{species id: {"prevo": id, "changesFrom": id, "baseSpecies": id}} for the entries that have them."""
    out, cur = {}, None
    for line in text.splitlines():
        m = ENTRY.match(line)
        if m:
            cur = m.group(1)
            continue
        f = DEX_FIELD.match(line) if cur else None
        if f:
            out.setdefault(cur, {})[f.group(1)] = to_id(f.group(2))
    return out


def build(texts):
    main, _ = parse_learnsets(texts["data/learnsets.ts"])
    champions, inherit = parse_learnsets(texts["data/mods/champions/learnsets.ts"])
    sv, past = {}, {}
    for sid, moves in main.items():
        gen9 = sorted(m for m, src in moves.items() if any(s.startswith("9") for s in src))
        older = sorted(m for m, src in moves.items() if not any(s.startswith("9") for s in src))
        if gen9:
            sv[sid] = " ".join(gen9)
        if older:
            past[sid] = " ".join(older)
    champ = {}
    for sid, moves in champions.items():
        own = set(moves)
        if sid in inherit:   # adds to the base game's movepool
            own |= set(sv.get(sid, "").split())
        champ[sid] = " ".join(sorted(m for m in own if m))
    return {"source": "Pokemon Showdown data/learnsets.ts, data/mods/champions/learnsets.ts, data/pokedex.ts (MIT)",
            "sv": dict(sorted(sv.items())), "past": dict(sorted(past.items())), "champions": dict(sorted(champ.items())),
            "dex": dict(sorted(parse_pokedex(texts["data/pokedex.ts"]).items()))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src-dir", help="folder with local copies (data/learnsets.ts saved as data_learnsets.ts)")
    args = ap.parse_args()
    texts = {}
    for path in FILES:
        if args.src_dir:
            texts[path] = (Path(args.src_dir) / path.replace("/", "_")).read_text(encoding="utf-8")
        else:
            import requests
            r = requests.get(BASE + path, timeout=120)
            r.raise_for_status()
            texts[path] = r.text
    data = build(texts)
    sizes = {k: len(data[k]) for k in ("sv", "past", "champions", "dex")}
    if sizes["sv"] < 700 or sizes["champions"] < 150 or sizes["dex"] < 800:
        sys.exit(f"Too few entries parsed {sizes}, refusing to write")
    OUT.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{sizes} written to {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

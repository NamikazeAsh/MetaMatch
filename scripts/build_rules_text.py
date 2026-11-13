"""
Builds data/json/rules_text.json, the rules lookup behind mechanics answers: every ability's, item's and move's
description from Pokemon Showdown's text files (data/text/*.ts), plus the move flags (slicing, punch, reflectable...)
from data/moves.ts and the 'breakable' flag (ignored by Mold Breaker) from data/abilities.ts. Pokemon Showdown is MIT
licensed. Only the current generation's text is kept; per generation overrides nested inside an entry are skipped.

  python scripts/build_rules_text.py                 # downloads the five files from the Showdown repo
  python scripts/build_rules_text.py --src-dir dir   # or reads local copies named like data_text_moves.ts
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/"
FILES = ["data/text/abilities.ts", "data/text/items.ts", "data/text/moves.ts", "data/moves.ts", "data/abilities.ts"]
OUT = ROOT / "data" / "json" / "rules_text.json"

ENTRY = re.compile(r'^\t"?([a-z0-9]+)"?: \{')
TEXT_FIELD = re.compile(r'^\t\t(name|shortDesc|desc): "((?:[^"\\]|\\.)*)",')
DATA_FIELD = re.compile(r'^\t\t(name|type|category|isNonstandard): "((?:[^"\\]|\\.)*)",')
FLAGS = re.compile(r"^\t\tflags: \{(.*)\},")
BASE_POWER = re.compile(r"^\t\tbasePower: (\d+),")
# Move flags an ability, item or rule keys on
MOVE_FLAGS = {"contact", "sound", "punch", "bite", "bullet", "pulse", "slicing", "wind", "reflectable", "powder",
              "dance", "heal", "bypasssub"}


def _entries(text, field_re):
    """{id: {field: value}} for one table, reading only fields at the entry's own depth."""
    out, current = {}, None
    for line in text.splitlines():
        m = ENTRY.match(line)
        if m:
            current = out.setdefault(m.group(1), {})
            continue
        if current is None:
            continue
        f = field_re.match(line)
        if f and f.group(1) not in current:
            current[f.group(1)] = json.loads(f'"{f.group(2)}"')
            continue
        flags = FLAGS.match(line)
        if flags and "flags" not in current:
            current["flags"] = sorted(re.findall(r"([a-z]+): 1", flags.group(1)))
            continue
        bp = BASE_POWER.match(line)
        if bp and "basePower" not in current:
            current["basePower"] = int(bp.group(1))
    return out


def build(texts):
    """texts: {repo path: file text}. Returns the rules_text.json payload."""
    ability_text = _entries(texts["data/text/abilities.ts"], TEXT_FIELD)
    item_text = _entries(texts["data/text/items.ts"], TEXT_FIELD)
    move_text = _entries(texts["data/text/moves.ts"], TEXT_FIELD)
    move_data = _entries(texts["data/moves.ts"], DATA_FIELD)
    ability_data = _entries(texts["data/abilities.ts"], DATA_FIELD)

    def text_of(entry):
        out = {"short": entry.get("shortDesc") or entry.get("desc", "")}
        if entry.get("desc") and entry["desc"] != out["short"]:
            out["desc"] = entry["desc"]
        return out

    abilities = {}
    for key, entry in ability_text.items():
        if not entry.get("name") or entry["name"] == "No Ability" or not (entry.get("shortDesc") or entry.get("desc")):
            continue
        abilities[entry["name"]] = {**text_of(entry),
                                    "breakable": "breakable" in ability_data.get(key, {}).get("flags", [])}
    items = {e["name"]: text_of(e) for e in item_text.values() if e.get("name") and (e.get("shortDesc") or e.get("desc"))}
    moves = {}
    for key, entry in move_text.items():
        data = move_data.get(key, {})
        if not entry.get("name") or not (entry.get("shortDesc") or entry.get("desc")) or data.get("isNonstandard") in ("CAP", "LGPE"):
            continue
        moves[entry["name"]] = {**text_of(entry), "type": data.get("type"), "category": data.get("category"),
                                "basePower": data.get("basePower", 0),
                                "flags": [f for f in data.get("flags", []) if f in MOVE_FLAGS]}
    return {"source": "Pokemon Showdown data/text and data (MIT)", "abilities": dict(sorted(abilities.items())),
            "items": dict(sorted(items.items())), "moves": dict(sorted(moves.items()))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src-dir", help="folder with local copies (data/text/moves.ts saved as data_text_moves.ts)")
    args = ap.parse_args()
    texts = {}
    for path in FILES:
        if args.src_dir:
            texts[path] = (Path(args.src_dir) / path.replace("/", "_")).read_text(encoding="utf-8")
        else:
            import requests
            r = requests.get(BASE + path, timeout=60)
            r.raise_for_status()
            texts[path] = r.text
    data = build(texts)
    sizes = {k: len(data[k]) for k in ("abilities", "items", "moves")}
    if sizes["abilities"] < 250 or sizes["items"] < 400 or sizes["moves"] < 800:
        sys.exit(f"Too few entries parsed {sizes}, refusing to write")
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{sizes} written to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

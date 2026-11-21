"""
Builds data/json/rules_text.json, the rules lookup behind mechanics answers: every ability's, item's and move's
description from Pokemon Showdown's text files (data/text/*.ts), plus the move flags (slicing, punch, reflectable...),
priority, whether the user switches out and whether it lays a hazard on the foe's side from data/moves.ts, and the
'breakable' flag (ignored by Mold Breaker) from data/abilities.ts. engine/moves.py reads the pivots, hazards and
priority moves from here. Pokemon Showdown is MIT
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
PRIORITY = re.compile(r"^\t\tpriority: (-?\d+),")
SELF_SWITCH = re.compile(r"^\t\tselfSwitch: ")
SIDE_CONDITION = re.compile(r"^\t\tsideCondition: ")
TARGET = re.compile(r'^\t\ttarget: "(\w+)",')
HEAL = re.compile(r"^\t\theal: \[(\d+), (\d+)\],")
STATUS = re.compile(r"^\t\tstatus: '(\w+)',")
# A secondary effect block: "secondary: {" or "secondaries: [", with its chance and status a level or two deeper
SECONDARY_OPEN = re.compile(r"^\t\tsecondar(?:y: \{|ies: \[)\s*$")
SECONDARY_CHANCE = re.compile(r"^\t\t\t\t?chance: (\d+),")
SECONDARY_STATUS = re.compile(r"^\t\t\t\t?status: '(\w+)',")
BLOCK_CLOSE = re.compile(r"^\t\t[}\]],")
# Move flags an ability, item or rule keys on
MOVE_FLAGS = {"contact", "sound", "punch", "bite", "bullet", "pulse", "slicing", "wind", "reflectable", "powder",
              "dance", "heal", "bypasssub"}


def _entries(text, field_re):
    """{id: {field: value}} for one table, reading only fields at the entry's own depth."""
    out, current, secondary = {}, None, None
    for line in text.splitlines():
        m = ENTRY.match(line)
        if m:
            current, secondary = out.setdefault(m.group(1), {}), None
            continue
        if current is None:
            continue
        # Inside a secondary effect: the first status it inflicts, with its chance (Scald: 30% burn)
        if secondary is not None:
            if BLOCK_CLOSE.match(line):
                if secondary.get("status") and "inflicts" not in current:
                    current["inflicts"] = {"status": secondary["status"], "chance": secondary.get("chance", 100)}
                secondary = None
                continue
            c, s = SECONDARY_CHANCE.match(line), SECONDARY_STATUS.match(line)
            if c and "status" not in secondary:
                secondary["chance"] = int(c.group(1))
            if s and "status" not in secondary:
                secondary["status"] = s.group(1)
            continue
        if SECONDARY_OPEN.match(line):
            secondary = {}
            continue
        heal = HEAL.match(line)
        if heal and "heal" not in current:
            current["heal"] = int(heal.group(1)) / int(heal.group(2))
            continue
        status = STATUS.match(line)
        if status and "inflicts" not in current:
            current["inflicts"] = {"status": status.group(1), "chance": 100}   # the move's whole point (Will-O-Wisp)
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
            continue
        pri = PRIORITY.match(line)
        if pri and "priority" not in current:
            current["priority"] = int(pri.group(1))
            continue
        if SELF_SWITCH.match(line):
            current["selfSwitch"] = True
        elif SIDE_CONDITION.match(line):
            current["sideCondition"] = True
        target = TARGET.match(line)
        if target and "target" not in current:
            current["target"] = target.group(1)
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
        if data.get("priority"):
            moves[entry["name"]]["priority"] = data["priority"]
        if data.get("selfSwitch"):
            moves[entry["name"]]["switches"] = True          # the user switches out (U-turn, Parting Shot...)
        if data.get("sideCondition") and data.get("target") == "foeSide":
            moves[entry["name"]]["hazard"] = True            # lays a hazard on the foe's side
        # Heals the user itself (Slack Off 1/2): not Heal Pulse or Floral Healing, which heal the target
        if data.get("heal") and data.get("target") in ("self", "allies", "adjacentAllyOrSelf"):
            moves[entry["name"]]["heals"] = round(data["heal"], 4)
        if data.get("inflicts"):
            moves[entry["name"]]["inflicts"] = data["inflicts"]   # {"status": "brn", "chance": 30}
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

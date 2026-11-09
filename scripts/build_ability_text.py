"""
Builds data/json/ability_text.json: every ability's one line description from Pokemon Showdown's ability text
(data/text/abilities.ts, MIT licensed), for the ability hovers in the app. Only the current generation's text is
kept; per generation overrides inside an entry are skipped.

  python scripts/build_ability_text.py                  # downloads abilities.ts from the Showdown repo
  python scripts/build_ability_text.py --src path.ts    # or reads a local copy
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data/text/abilities.ts"
OUT = ROOT / "data" / "json" / "ability_text.json"

ENTRY = re.compile(r"^\t([a-z0-9]+): \{")
FIELD = re.compile(r'^\t\t(name|shortDesc): "((?:[^"\\]|\\.)*)",')


def parse(text):
    """{name: shortDesc} from abilities.ts; fields nested deeper than an entry (gen overrides) are ignored."""
    out, name, short = {}, None, None
    for line in text.splitlines():
        if ENTRY.match(line):
            if name and short:
                out[name] = short
            name, short = None, None
            continue
        m = FIELD.match(line)
        if m:
            value = json.loads(f'"{m.group(2)}"')
            if m.group(1) == "name":
                name = value
            elif short is None:
                short = value
    if name and short:
        out[name] = short
    out.pop("No Ability", None)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", help="local abilities.ts instead of downloading it")
    args = ap.parse_args()
    if args.src:
        text = Path(args.src).read_text(encoding="utf-8")
    else:
        import requests
        r = requests.get(URL, timeout=60)
        r.raise_for_status()
        text = r.text
    data = parse(text)
    if len(data) < 250:
        sys.exit(f"Only {len(data)} abilities parsed, refusing to write")
    OUT.write_text(json.dumps(dict(sorted(data.items())), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(data)} abilities written to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

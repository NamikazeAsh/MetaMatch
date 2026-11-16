"""
Builds data/json/team_score_ladder.json: the team score (engine/team_score.py) of real ladder teams, per format, so a
user's score can be placed as a percentile ("better covered than 58% of 147 ladder teams").

Teams come from the team previews in locally saved replays (data/replays/pool, gitignored), deduplicated, with every
member on its most common set. Sets are inferred, so the table describes ladder team building, not exact teams.
Run: python scripts/build_team_score_table.py   (needs the calc sidecar; about two minutes per format)
"""
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from metamatch import config  # noqa: E402
from metamatch.auditor import load_chaos_data  # noqa: E402
from metamatch.engine.completer import member_from_set  # noqa: E402
from metamatch.engine.sets import likely_set  # noqa: E402
from metamatch.engine.team_score import TABLE, score_team  # noqa: E402

FORMATS = ["gen9ou"]


def previews(format_id):
    """Distinct six Pokemon team previews from the saved replays of one format."""
    data = load_chaos_data(format_id) or {}
    seen, teams = set(), []
    for path in sorted(glob.glob(str(ROOT / "data" / "replays" / "pool" / f"{format_id}-*.json"))):
        log = json.load(open(path, encoding="utf-8")).get("log", "")
        for side in ("p1", "p2"):
            names = [re.split(r",", line.split("|")[3])[0].strip() for line in log.split("\n")
                     if line.startswith(f"|poke|{side}|")]
            key = tuple(sorted(names))
            if len(names) == 6 and key not in seen and all(n in data for n in names):
                seen.add(key)
                teams.append(names)
    return teams


def ladder_team(names, format_id):
    team = {}
    for i, name in enumerate(names):
        s = likely_set(name, format_id)
        if not s:
            return None
        team[f"p{i}"] = member_from_set(s, format_id)
    return team


def main():
    out = {}
    for format_id in FORMATS:
        totals = []
        for names in previews(format_id):
            team = ladder_team(names, format_id)
            if team:
                totals.append(score_team(team, format_id).total)
        out[format_id] = sorted(totals)
        print(f"{format_id}: {len(totals)} teams, median {totals[len(totals) // 2] if totals else None}")
    TABLE.write_text(json.dumps(out), encoding="utf-8")
    print(f"wrote {TABLE}")


if __name__ == "__main__":
    main()

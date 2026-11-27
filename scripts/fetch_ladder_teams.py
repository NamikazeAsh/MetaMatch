"""
Builds data/json/ladder_teams.json, a corpus of real ladder teams for "Teams like yours" and real game precedents.
It pages Pokemon Showdown's public replay search, keeps recent games (rated games above a cutoff where the format
has enough of them), downloads each replay once into data/replays/ladder/ (gitignored), and parses it with the
Replay Auditor's parser. Only facts are written: each side's six (Megas as the forme they became), its lead, the
rating, the upload time, the replay id (which links back to the public replay) and who knocked out whom.

  python scripts/fetch_ladder_teams.py                       # crawl the default formats, then build
  python scripts/fetch_ladder_teams.py --formats gen9ou --teams 3000
  python scripts/fetch_ladder_teams.py --build-only          # rebuild the JSON from the replays on disk
"""
import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from metamatch.replay.protocol import UnsupportedReplay, _same_species, parse_battle  # noqa: E402

HOST = "https://replay.pokemonshowdown.com"
CACHE = ROOT / "data" / "replays" / "ladder"
OUT = ROOT / "data" / "json" / "ladder_teams.json"
HEADERS = {"User-Agent": "MetaMatch ladder team sampler (one request per second)"}
# Showdown's replay format id for each MetaMatch format, and the lowest rating kept. Only OU uploads enough rated
# games to filter on rating; the others keep every recent game.
FORMATS = {"gen9ou": ("gen9ou", 1500), "gen9uu": ("gen9uu", 0), "gen9natdex": ("gen9nationaldex", 0),
           "gen9championsou": ("gen9championsou", 0), "gen9championsuu": ("gen9championsuu", 0)}


def _get(url, delay):
    time.sleep(delay)
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
        except (requests.RequestException, ValueError):
            pass
        time.sleep(5 * (attempt + 1))
    return None


def _players(folder):
    """{player: games on disk} for a format's cached replays."""
    counts = Counter()
    for path in folder.glob("*.json"):
        try:
            counts.update(json.loads(path.read_text(encoding="utf-8")).get("players") or [])
        except (OSError, ValueError):
            continue
    return counts


def crawl(format_id, teams, days, delay, per_player):
    """Download recent replays for a format into the cache until about `teams` team records exist with at most
    `per_player` games from any one player. A few players upload every game they play (one was in 1,123 of 1,309
    OU replays), so without the cap the corpus would mostly sample their teams."""
    showdown_id, min_rating = FORMATS[format_id]
    folder = CACHE / format_id
    folder.mkdir(parents=True, exist_ok=True)
    have = {p.stem for p in folder.glob("*.json")}
    games = _players(folder)
    useful = lambda: sum(min(n, per_player) for n in games.values())   # noqa: E731
    oldest = time.time() - days * 86400
    before = None
    while useful() < teams:
        url = f"{HOST}/search.json?format={showdown_id}" + (f"&before={before}" if before else "")
        page = _get(url, delay)
        if not page:
            break
        for row in page:
            if useful() >= teams:
                break
            if row["id"] in have or row.get("private") or (row.get("rating") or 0) < min_rating:
                continue
            if all(games[p] >= per_player for p in row.get("players") or []):
                continue   # both players are already sampled enough
            data = _get(f"{HOST}/{row['id']}.json", delay)
            if data and data.get("log"):
                (folder / f"{row['id']}.json").write_text(json.dumps(data), encoding="utf-8")
                have.add(row["id"])
                games.update(data.get("players") or [])
        before = page[-1]["uploadtime"]
        print(f"  {format_id}: {useful()} usable teams from {len(games)} players, back to "
              f"{time.strftime('%Y-%m-%d', time.gmtime(before))}", flush=True)
        if len(page) < 51 or before < oldest:
            break
    return useful()


def _name(species):
    """A forme name as teams list it: Terastal formes fold back ('Ogerpon-Wellspring-Tera', 'Terapagos-Stellar')."""
    species = (species or "").replace("-*", "")
    if species.endswith("-Tera"):
        return species[:-5]
    if species.startswith("Terapagos"):
        return "Terapagos"
    return species


def _team(battle, side):
    """The side's six as the formes they played as: a Pokemon that was sent out takes its final forme (a Mega,
    or Urshifu-* resolved), one that never came in keeps its preview name."""
    seen = list(battle.mons[side].values())
    team = []
    for species in battle.preview[side] or [m.first_species for m in seen]:
        match = next((m for m in seen if _same_species(species, m.first_species)), None)
        if match:
            seen.remove(match)
        team.append(_name(match.species if match else species))
    return team


def records(data):
    """Two team records (one per side) for a replay, or none for a game that can't be parsed."""
    try:
        battle = parse_battle(data.get("log", ""), data.get("players"), data.get("formatid", ""), data.get("format", ""))
    except (UnsupportedReplay, Exception):   # noqa: BLE001 (a bad log never stops a build)
        return []
    out = []
    for side in ("p1", "p2"):
        team = _team(battle, side)
        if len(team) < 3:
            continue
        lead = next((_name(m.species) for m in battle.mons[side].values() if m.first_turn == 0), None)
        kos = [[f["turn"], _name(battle.name(f["by"])), _name(f["species"])] for f in battle.faints
               if f.get("by") and f["by"][:2] == side and f["side"] != side and f["cause"] in ("move", "indirect")]
        players = data.get("players") or []
        out.append({"id": data["id"], "side": side, "rating": data.get("rating") or 0,
                    "time": data.get("uploadtime") or 0, "team": team, "lead": lead, "kos": kos,
                    "_player": players[0 if side == "p1" else 1] if len(players) == 2 else None})
    return out


def build(formats, cap, per_player):
    """Write ladder_teams.json from every cached replay, newest first: at most `per_player` records from any one
    player, one per distinct team of theirs, and `cap` records per format. Player names are not written, only a short one way tag per player."""
    corpus = {}
    for format_id in formats:
        rows = []
        for path in (CACHE / format_id).glob("*.json"):
            try:
                rows += records(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        rows.sort(key=lambda r: -r["time"])
        kept, per, seen = [], Counter(), set()
        for r in rows:
            who = r.pop("_player")
            key = (who, frozenset(r["team"]))
            if key in seen or (who and per[who] >= per_player):
                continue
            seen.add(key)
            per[who] += 1
            # A short one way tag, not the name: benchmarks keep each player's teams on one side of a split
            r["p"] = hashlib.sha1((who or "").lower().encode()).hexdigest()[:8]
            kept.append(r)
        corpus[format_id] = kept[:cap]
        print(f"  {format_id}: {len(corpus[format_id])} teams from {len(per)} players")
    OUT.write_text(json.dumps({"source": "Pokemon Showdown public replays (facts only, linked by id)",
                               "built": time.strftime("%Y-%m-%d"), "formats": corpus}, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    print(f"written to {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--formats", default=",".join(FORMATS))
    ap.add_argument("--teams", type=int, default=3000, help="usable team records to collect per format")
    ap.add_argument("--per-player", type=int, default=3, help="most games kept from any one player")
    ap.add_argument("--days", type=int, default=60, help="stop paging past this many days back")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    ap.add_argument("--cap", type=int, default=5000, help="team records per format in the JSON")
    ap.add_argument("--build-only", action="store_true")
    args = ap.parse_args()
    formats = [f for f in args.formats.split(",") if f in FORMATS]
    if not args.build_only:
        for format_id in formats:
            print(f"crawling {format_id}")
            crawl(format_id, args.teams, args.days, args.delay, args.per_player)
    build(formats, args.cap, args.per_player)


if __name__ == "__main__":
    main()

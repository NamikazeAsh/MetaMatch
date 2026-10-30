"""Replay Auditor: parses Showdown replays and analyses them with the battle engine."""
import re
from dataclasses import dataclass, field

import requests

from .protocol import Battle, UnsupportedReplay, parse_battle, parse_hp
from .rules import Flag, find_flags

REPLAY_HOST = "https://replay.pokemonshowdown.com"
# 'gen9ou-2704032656', 'smogtours-gen9ou-984081', private 'gen9ou-2704032656-abc123pw'
REPLAY_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-\d+(?:-[a-z0-9]+pw)?$")


class ReplayError(Exception):
    """A replay that can't be fetched or analysed, with a message fit to show the user."""


def parse_replay_link(text):
    """(replay id, side) from a replay link or bare id; side is 'p2' for '?p2' links, else None."""
    text = (text or "").strip()
    if not text:
        raise ReplayError("Paste a replay link first.")
    path, _, query = text.partition("?")
    replay_id = re.sub(r"\.(json|log)$", "", path.rstrip("/").split("/")[-1].lower())
    if not REPLAY_ID_RE.match(replay_id):
        raise ReplayError("That doesn't look like a Showdown replay link "
                          "(expected something like replay.pokemonshowdown.com/gen9ou-1234567890).")
    side = "p2" if re.search(r"(^|&)p2($|&|=)", query.split("#")[0]) else None
    return replay_id, side


def fetch_replay(url):
    """Replay JSON for a link or id. Raises ReplayError with a specific reason."""
    replay_id, _ = parse_replay_link(url)
    try:
        response = requests.get(f"{REPLAY_HOST}/{replay_id}.json", timeout=10)
    except requests.RequestException:
        raise ReplayError("Couldn't reach Pokémon Showdown. Check your connection and try again.")
    if response.status_code == 404:
        raise ReplayError("Replay not found. If it's private, paste the full link including the part ending in 'pw'.")
    if response.status_code != 200:
        raise ReplayError(f"Pokémon Showdown returned an error ({response.status_code}). Try again in a moment.")
    try:
        return response.json()
    except ValueError:
        raise ReplayError("Pokémon Showdown sent back something that isn't a replay.")


@dataclass
class Analysis:
    battle: Battle
    flags: dict = field(default_factory=dict)   # side -> [Flag]


def analyze(data):
    """Analysis of replay JSON for both sides, so switching perspective needs no refetch."""
    try:
        battle = parse_battle(data.get("log", ""), data.get("players"),
                              data.get("formatid", ""), data.get("format", ""))
    except UnsupportedReplay as e:
        raise ReplayError(str(e))
    return Analysis(battle, {side: find_flags(battle, side) for side in ("p1", "p2")})


__all__ = ["Analysis", "Battle", "Flag", "ReplayError", "UnsupportedReplay", "analyze", "fetch_replay",
           "parse_battle", "parse_hp", "parse_replay_link"]

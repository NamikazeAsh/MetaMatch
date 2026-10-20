import os
from pathlib import Path

# Base project directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Data Directories
DATA_DIR = BASE_DIR / "data"
JSON_DIR = DATA_DIR / "json"
STATS_DIR = DATA_DIR / "stats"
USER_DIR = DATA_DIR / "user"

# Assets Directory
ASSETS_DIR = BASE_DIR / "assets"
IMAGES_DIR = ASSETS_DIR / "images"

# Supported formats. "stats" is the Smogon stats file stem (usage .txt and chaos .json),
# "sets" is the pkmn.github.io sets file stem (None if not published), "game" picks mechanics.
FORMATS = {
    "gen9ou":          {"label": "OU",           "stats": "gen9ou-1825",          "sets": "gen9ou",          "game": "sv"},
    "gen9uu":          {"label": "UU",           "stats": "gen9uu-1760",          "sets": "gen9uu",          "game": "sv"},
    "gen9natdex":      {"label": "NatDex",       "stats": "gen9nationaldex-1760", "sets": "gen9nationaldex", "game": "sv"},
    "gen9championsou": {"label": "Champions OU", "stats": "gen9championsou-1760", "sets": None,              "game": "champions"},
    "gen9championsuu": {"label": "Champions UU", "stats": "gen9championsuu-1760", "sets": None,              "game": "champions"},
}
DEFAULT_FORMAT = "gen9ou"

# Champions replaces EVs with stat points: 66 total, 32 max per stat, level 50, IVs fixed at 31
CHAMPIONS_SP_TOTAL = 66
CHAMPIONS_SP_MAX = 32


def format_info(format_id):
    return FORMATS.get(format_id, FORMATS[DEFAULT_FORMAT])


def format_game(format_id):
    return format_info(format_id)["game"]


def format_by_label(label):
    """Maps a UI label like 'Champions OU' back to its format id."""
    return next((fid for fid, f in FORMATS.items() if f["label"] == label), DEFAULT_FORMAT)


def format_from_stats_stem(stem):
    """Maps a stats file stem like 'gen9championsou-1760' to its format id, or None."""
    return next((fid for fid, f in FORMATS.items() if f["stats"] == stem), None)


def team_format(team):
    """Format id stored on an analysed team (see team.readTeam). Older saved teams default to OU."""
    for p in (team or {}).values():
        if isinstance(p, dict) and p.get("Format") in FORMATS:
            return p["Format"]
    return DEFAULT_FORMAT


# Ensure directories exist
JSON_DIR.mkdir(parents=True, exist_ok=True)
STATS_DIR.mkdir(parents=True, exist_ok=True)
USER_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

"""
Offline Pokedex exported from the pinned @smogon/calc package (see export_dex.js).
Gives types, base stats, Mega formes, moves and display names for SV and Champions
without PokeAPI, and matches exactly what the damage calc uses.
"""
import json
import re
from functools import lru_cache

from metamatch import config

# PokeAPI stat names, which the rest of the app already uses for "Base Stats"
POKEAPI_STATS = {"hp": "hp", "atk": "attack", "def": "defense", "spa": "special-attack", "spd": "special-defense", "spe": "speed"}


def to_id(name):
    """Showdown style id: 'Landorus-Therian' -> 'landorustherian'."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


class Dex:
    def __init__(self, data):
        self.species_data = data["species"]
        self.move_data = data["moves"]
        self.item_data = data["items"]
        self._species = {to_id(n): n for n in self.species_data}
        self._moves = {to_id(n): n for n in self.move_data}
        self._items = {to_id(n): n for n in self.item_data}
        self._abilities = {to_id(n): n for n in data.get("abilities", [])}

    def species(self, name):
        """{'name', 'types', 'baseStats', 'abilities', ...} or None."""
        display = self._species.get(to_id(name))
        return {"name": display, **self.species_data[display]} if display else None

    def move(self, name):
        display = self._moves.get(to_id(name))
        return {"name": display, **self.move_data[display]} if display else None

    def move_name(self, name):
        return self._moves.get(to_id(name))

    def item_name(self, name):
        return self._items.get(to_id(name))

    def ability_name(self, name):
        return self._abilities.get(to_id(name))

    def mega_forme(self, species_name, item):
        """The forme a held Mega Stone turns this species into, or None."""
        display = self._items.get(to_id(item))
        stones = self.item_data.get(display, {}).get("megaStone", {}) if display else {}
        species = self.species(species_name)
        return stones.get(species["name"]) if species else None


@lru_cache(maxsize=2)
def get_dex(game="sv"):
    """Dex for 'sv' or 'champions', or None if the export hasn't been generated."""
    path = config.JSON_DIR / f"dex_{game}.json"
    try:
        with open(path, encoding="utf-8") as f:
            return Dex(json.load(f))
    except (OSError, json.JSONDecodeError):
        return None


def dex_for_format(format_id):
    return get_dex(config.format_game(format_id))


def pokeapi_stats(base_stats):
    """Calc stat keys ('spe') -> the PokeAPI keys ('speed') stored on analysed teams."""
    return {POKEAPI_STATS[k]: v for k, v in base_stats.items()}

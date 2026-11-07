"""
Pokémon sprites for every page: Pokémon HOME renders from Showdown's sprite server, the set MetaFlash uses.

Each sprite is downloaded once into static/sprites and then served by Streamlit's static file server, so pages
stop calling PokeAPI for every image. Formes without a HOME render yet (the new Champions Megas) fall back to
Showdown's dex art, then its pixel sprite, and only then to the base species.
"""
from pathlib import Path

import requests

from metamatch.engine.dex import to_id
from metamatch.meta_pulse import _base_species

SPRITE_DIR = Path(__file__).parent / "static" / "sprites"
URL_PREFIX = "app/static/sprites/"
REMOTE = "https://play.pokemonshowdown.com/sprites/"
SOURCES = ("home-centered", "dex", "gen5")
TIMEOUT = 5

_saved: set[str] = set()
_missing: set[str] = set()   # ids with no sprite anywhere, remembered for this run only


def sprite_ids(name: str) -> tuple[str, str]:
    """(forme id, base species id) in Showdown's sprite naming, e.g. Urshifu-Rapid-Strike -> urshifu-rapidstrike."""
    base = _base_species().get(name)
    if base and name.startswith(base + "-"):
        return f"{to_id(base)}-{to_id(name[len(base) + 1:])}", to_id(base)
    return to_id(name), to_id(base or name)


def _download(sprite_id: str) -> bool:
    for source in SOURCES:
        try:
            r = requests.get(f"{REMOTE}{source}/{sprite_id}.png", timeout=TIMEOUT)
        except requests.RequestException:
            return False
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
            SPRITE_DIR.mkdir(parents=True, exist_ok=True)
            (SPRITE_DIR / f"{sprite_id}.png").write_bytes(r.content)
            return True
    _missing.add(sprite_id)
    return False


def _on_disk(sprite_id: str) -> bool:
    """True once the sprite is saved locally, downloading it on first use."""
    if sprite_id in _saved or (SPRITE_DIR / f"{sprite_id}.png").exists():
        _saved.add(sprite_id)
        return True
    if sprite_id in _missing or not _download(sprite_id):
        return False
    _saved.add(sprite_id)
    return True


def get_sprite(name: str) -> str | None:
    """A URL for the sprite of `name`: the local copy, Showdown's own URL when offline, None when none exists."""
    if not name:
        return None
    forme, base = sprite_ids(name)
    for sprite_id in dict.fromkeys((forme, base)):
        if _on_disk(sprite_id):
            return URL_PREFIX + sprite_id + ".png"
    return None if forme in _missing else f"{REMOTE}home-centered/{forme}.png"

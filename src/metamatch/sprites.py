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


def sprite_file(name: str) -> Path | None:
    """The local sprite file for `name` (downloaded on first use), for documents that embed the image itself."""
    if not name:
        return None
    for sprite_id in dict.fromkeys(sprite_ids(name)):
        if _on_disk(sprite_id):
            return SPRITE_DIR / f"{sprite_id}.png"
    return None


# --- Item, Tera and type icons -------------------------------------------------------------------
# Same idea as the sprites: downloaded once into the gitignored static/sprites folder, never shipped in the repo.
ITEM_DIR = SPRITE_DIR / "items"
TERA_DIR = SPRITE_DIR / "tera"
TYPE_DIR = SPRITE_DIR / "types"
ITEM_SHEET = REMOTE + "itemicons-sheet.png"   # 24 px icons, 16 per row, indexed by each item's spritenum
ITEM_DATA = "https://play.pokemonshowdown.com/data/items.js"
TYPE_ICON = "https://raw.githubusercontent.com/duiker101/pokemon-type-svg-icons/master/icons/{}.svg"
_icon_cache: dict = {}


def _fetch(url):
    try:
        r = requests.get(url, timeout=TIMEOUT)
        return r.content if r.status_code == 200 else None
    except requests.RequestException:
        return None


def _spritenums():
    """{item id: spritenum} from Showdown's item data, saved beside the icons after the first download."""
    import json
    import re
    if "spritenums" in _icon_cache:
        return _icon_cache["spritenums"]
    path = ITEM_DIR / "spritenums.json"
    nums = {}
    if path.exists():
        nums = json.loads(path.read_text(encoding="utf-8"))
    else:
        raw = _fetch(ITEM_DATA)
        if raw:
            nums = {m.group(1): int(m.group(2)) for m in
                    re.finditer(r"(\w+):\{[^{}]*?spritenum:(\d+)", raw.decode("utf-8", errors="replace"))}
            ITEM_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(nums), encoding="utf-8")
    _icon_cache["spritenums"] = nums
    return nums


def get_item_icon(item):
    """URL of a held item's icon, cut from Showdown's item sheet, or None."""
    if not item:
        return None
    item_id = to_id(item)
    path = ITEM_DIR / f"{item_id}.png"
    if not path.exists():
        num = _spritenums().get(item_id)
        if num is None:
            return None
        sheet_path = ITEM_DIR / "sheet.png"
        if not sheet_path.exists():
            raw = _fetch(ITEM_SHEET)
            if not raw:
                return None
            ITEM_DIR.mkdir(parents=True, exist_ok=True)
            sheet_path.write_bytes(raw)
        from PIL import Image
        with Image.open(sheet_path) as sheet:
            x, y = (num % 16) * 24, (num // 16) * 24
            sheet.convert("RGBA").crop((x, y, x + 24, y + 24)).save(path)
    return URL_PREFIX + f"items/{item_id}.png"


def get_tera_icon(tera_type):
    """URL of Showdown's Tera crystal icon for a type, or None."""
    if not tera_type:
        return None
    path = TERA_DIR / f"{tera_type}.png"
    if not path.exists():
        raw = _fetch(f"{REMOTE}types/Tera{tera_type}.png")
        if not raw:
            return None
        TERA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return URL_PREFIX + f"tera/{tera_type}.png"


def get_type_icon(type_name):
    """A data URI of the round type symbol (white glyph, drawn on a type coloured circle by the caller), or None.
    SVGs are inlined because Streamlit serves .svg static files as plain text."""
    import base64
    if not type_name:
        return None
    key = f"type:{type_name}"
    if key not in _icon_cache:
        path = TYPE_DIR / f"{type_name.lower()}.svg"
        if not path.exists():
            raw = _fetch(TYPE_ICON.format(type_name.lower()))
            if not raw:
                return None
            TYPE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        _icon_cache[key] = "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode()
    return _icon_cache[key]

"""
Most likely set for an opponent, inferred from Smogon chaos usage data.

Chaos files only store per field distributions (spreads, items, abilities, moves,
tera), not whole sets, so each field is picked independently. Anything the user
already knows (a revealed item, ability or move) overrides the prior.
"""
from metamatch import config
from metamatch.auditor import load_chaos_data
from metamatch.engine.dex import dex_for_format, to_id
from metamatch.utils import calculate_speed

STATS = ["hp", "atk", "def", "spa", "spd", "spe"]
SPEED_PLUS = {"Timid", "Jolly", "Hasty", "Naive"}
SPEED_MINUS = {"Brave", "Relaxed", "Quiet", "Sassy"}


def _ranked(counts, total):
    return [(k, v / total) for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True) if k and k != "nothing"]


def _parse_spread(spread):
    """'Jolly:0/252/0/0/4/252' -> ('Jolly', {'hp': 0, 'atk': 252, ...})."""
    nature, _, vals = spread.partition(":")
    return nature, {s: int(v) for s, v in zip(STATS, vals.split("/"))}


def chaos_entry(name, format_id):
    """(chaos key, entry) for a Pokemon, matching names loosely, or (None, None)."""
    data = load_chaos_data(format_id) or {}
    if name in data:
        return name, data[name]
    target = to_id(name)
    for key, entry in data.items():
        if to_id(key) == target:
            return key, entry
    return None, None


def speed_distribution(name, format_id, entry=None):
    """[(speed stat, share of sets)] grouped by final Speed, most common first (ignores Scarf)."""
    if entry is None:
        _, entry = chaos_entry(name, format_id)
    dex = dex_for_format(format_id)
    species = dex.species(name) if dex else None
    if not entry or not species:
        return []
    game = config.format_game(format_id)
    total = sum(entry.get("Abilities", {}).values()) or 1
    speeds = {}
    for spread, weight in entry.get("Spreads", {}).items():
        nature, evs = _parse_spread(spread)
        mod = 1.1 if nature in SPEED_PLUS else 0.9 if nature in SPEED_MINUS else 1.0
        spe = calculate_speed(species["baseStats"]["spe"], evs["spe"], 31, mod, "", game)
        speeds[spe] = speeds.get(spe, 0) + weight / total
    return sorted(speeds.items(), key=lambda x: x[1], reverse=True)


def likely_set(name, format_id, known=None):
    """
    Most likely set for `name` in `format_id`, or None if it has no usage data.
    known: optional {'item', 'ability', 'moves': [...]} revealed facts that override the prior.
    """
    known = known or {}
    key, entry = chaos_entry(name, format_id)
    dex = dex_for_format(format_id)
    if not entry or not dex:
        return None

    total = sum(entry.get("Abilities", {}).values()) or 1
    spreads = _ranked(entry.get("Spreads", {}), total)
    items = _ranked(entry.get("Items", {}), total)
    abilities = _ranked(entry.get("Abilities", {}), total)
    moves = _ranked(entry.get("Moves", {}), total)
    teras = _ranked(entry.get("Tera Types", {}), total)

    nature, evs = _parse_spread(spreads[0][0]) if spreads else ("Serious", {s: 0 for s in STATS})

    if known.get("item"):
        item, item_share = known["item"], 1.0
    elif items:
        item, item_share = dex.item_name(items[0][0]) or items[0][0], items[0][1]
    else:
        item, item_share = None, 0.0

    if known.get("ability"):
        ability, ability_share = known["ability"], 1.0
    elif abilities:
        ability, ability_share = dex.ability_name(abilities[0][0]) or abilities[0][0], abilities[0][1]
    else:
        ability, ability_share = None, 0.0

    move_list = [(m, 1.0) for m in known.get("moves", [])]
    known_ids = {to_id(m) for m in known.get("moves", [])}
    for slug, share in moves:
        if len(move_list) >= 4:
            break
        display = dex.move_name(slug)
        if display and to_id(display) not in known_ids:
            move_list.append((display, share))

    return {
        "name": key,
        "usage": entry.get("usage", 0),
        "nature": nature,
        "evs": evs,
        "spread_share": spreads[0][1] if spreads else 0.0,
        "item": item,
        "item_share": item_share,
        "ability": ability,
        "ability_share": ability_share,
        "moves": move_list,
        "tera": (teras[0][0].capitalize(), teras[0][1]) if teras else None,
        "speeds": speed_distribution(key, format_id, entry),
    }


def calc_spec(s):
    """A likely_set result as a calc_server Pokemon spec."""
    spec = {"name": s["name"], "nature": s["nature"], "evs": s["evs"]}
    if s.get("item"):
        spec["item"] = s["item"]
    if s.get("ability"):
        spec["ability"] = s["ability"]
    return spec


def describe_spread(s, game):
    """'Jolly 252 Atk / 4 SpD / 252 Spe' style label for a likely set."""
    labels = {"hp": "HP", "atk": "Atk", "def": "Def", "spa": "SpA", "spd": "SpD", "spe": "Spe"}
    parts = [f"{v} {labels[k]}" for k, v in s["evs"].items() if v]
    unit = " SP" if game == "champions" else ""
    return f"{s['nature']} {' / '.join(parts)}{unit}"

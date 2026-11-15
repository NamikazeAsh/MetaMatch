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


# Nature -> (raised stat, lowered stat); neutral natures are absent
NATURE_EFFECT = {"Lonely": ("atk", "def"), "Brave": ("atk", "spe"), "Adamant": ("atk", "spa"), "Naughty": ("atk", "spd"),
                 "Bold": ("def", "atk"), "Relaxed": ("def", "spe"), "Impish": ("def", "spa"), "Lax": ("def", "spd"),
                 "Timid": ("spe", "atk"), "Hasty": ("spe", "def"), "Jolly": ("spe", "spa"), "Naive": ("spe", "spd"),
                 "Modest": ("spa", "atk"), "Mild": ("spa", "def"), "Quiet": ("spa", "spe"), "Rash": ("spa", "spd"),
                 "Calm": ("spd", "atk"), "Gentle": ("spd", "def"), "Sassy": ("spd", "spe"), "Careful": ("spd", "spa")}
BOOST_ABILITIES = {"protosynthesis", "quarkdrive"}


def speed_is_best_stat(base, nature, evs, game):
    """True when Speed is the highest of Atk, Def, SpA, SpD, Spe for this spread, which is when Protosynthesis or
    Quark Drive boosts Speed (ties go to the earlier stat, so Speed has to be strictly highest)."""
    up, down = NATURE_EFFECT.get(nature, (None, None))
    stats = {}
    for s in ("atk", "def", "spa", "spd", "spe"):
        mod = 1.1 if s == up else 0.9 if s == down else 1.0
        stats[s] = calculate_speed(base[s], evs.get(s, 0), 31, mod, "", game)
    return all(stats["spe"] > v for s, v in stats.items() if s != "spe")


def booster_speed_share(entry, species, game, total):
    """Share of a Pokemon's ladder sets whose Booster Energy raises Speed: Booster's item share times the share of
    spreads where Speed is the best stat. 0 unless its usual ability is Protosynthesis or Quark Drive."""
    abilities = entry.get("Abilities", {})
    if not abilities or not species or max(abilities, key=abilities.get) not in BOOST_ABILITIES:
        return 0.0
    booster = entry.get("Items", {}).get("boosterenergy", 0) / total
    if not booster:
        return 0.0
    spreads = entry.get("Spreads", {})
    weight = sum(spreads.values()) or 1
    fast = sum(w for raw, w in spreads.items() if speed_is_best_stat(species["baseStats"], *_parse_spread(raw), game))
    return booster * fast / weight


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
    twin = _stats_twin(name, format_id)
    return chaos_entry(twin, format_id) if twin else (None, None)


def _stats_twin(name, format_id):
    """The base species Smogon files a forme under when the two are the same Pokemon in battle: cosmetic formes
    (Gastrodon-East) and formes with the base's types and stats (Keldeo-Resolute, Maushold-Four). None otherwise,
    so Rotom-Heat never borrows Rotom's set."""
    dex = dex_for_format(format_id)
    if not dex or "-" not in (name or ""):
        return None
    forme = dex.species(name)
    base_name = forme.get("baseSpecies") if forme else name.split("-")[0]
    base = dex.species(base_name) if base_name else None
    if not base or to_id(base["name"]) == to_id(name):
        return None
    if forme and (forme.get("types") != base.get("types") or forme.get("baseStats") != base.get("baseStats")):
        return None
    return base["name"]


def speed_spreads(name, format_id, entry=None):
    """{speed stat: [(raw spread, share of sets)]}: the ladder spreads behind each final Speed (ignores Scarf)."""
    if entry is None:
        _, entry = chaos_entry(name, format_id)
    dex = dex_for_format(format_id)
    species = dex.species(name) if dex else None
    if not entry or not species:
        return {}
    game = config.format_game(format_id)
    total = sum(entry.get("Abilities", {}).values()) or 1
    groups = {}
    for spread, weight in entry.get("Spreads", {}).items():
        nature, evs = _parse_spread(spread)
        mod = 1.1 if nature in SPEED_PLUS else 0.9 if nature in SPEED_MINUS else 1.0
        spe = calculate_speed(species["baseStats"]["spe"], evs["spe"], 31, mod, "", game)
        groups.setdefault(spe, []).append((spread, weight / total))
    return groups


def speed_distribution(name, format_id, entry=None):
    """[(speed stat, share of sets)] grouped by final Speed, most common first (ignores Scarf)."""
    speeds = {spe: sum(share for _, share in spreads) for spe, spreads in speed_spreads(name, format_id, entry).items()}
    return sorted(speeds.items(), key=lambda x: x[1], reverse=True)


STAT_LABELS = {"hp": "HP", "atk": "Atk", "def": "Def", "spa": "SpA", "spd": "SpD", "spe": "Spe"}


def spread_label(spread, format_id=None):
    """'Impish:248/0/228/0/0/32' -> 'Impish 248 HP / 228 Def / 32 Spe' (Champions stat points end in ' SP')."""
    nature, evs = _parse_spread(spread)
    points = " / ".join(f"{v} {STAT_LABELS[k]}" for k, v in evs.items() if v)
    unit = " SP" if points and format_id and config.format_game(format_id) == "champions" else ""
    return f"{nature} {points}{unit}" if points else f"{nature}, no investment"


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
        "scarf_share": 1.0 if to_id(item or "") == "choicescarf" and known.get("item") else
                       0.0 if known.get("item") else dict(items).get("choicescarf", 0.0),
        "speeds": speed_distribution(key, format_id, entry),
        # Booster Energy that lands on Speed (x1.5), mixed in like Choice Scarf; a revealed item settles it
        "booster_share": (0.0 if known.get("item") and to_id(known["item"]) != "boosterenergy" else
                          booster_speed_share(entry, dex.species(key), config.format_game(format_id), total)),
    }


def calc_spec(s):
    """A likely_set result as a calc_server Pokemon spec."""
    spec = {"name": s["name"], "nature": s["nature"], "evs": s["evs"]}
    if s.get("item"):
        spec["item"] = s["item"]
    if s.get("ability"):
        spec["ability"] = s["ability"]
    # Details a question stated for this set (solvers._stated_set): Tera, stat boosts, IVs
    for key in ("teraType", "boosts", "ivs"):
        if s.get(key):
            spec[key] = s[key]
    return spec


def describe_spread(s, game):
    """'Jolly 252 Atk / 4 SpD / 252 Spe' style label for a likely set."""
    labels = {"hp": "HP", "atk": "Atk", "def": "Def", "spa": "SpA", "spd": "SpD", "spe": "Spe"}
    parts = [f"{v} {labels[k]}" for k, v in s["evs"].items() if v]
    unit = " SP" if game == "champions" else ""
    return f"{s['nature']} {' / '.join(parts)}{unit}"

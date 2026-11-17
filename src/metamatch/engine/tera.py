"""
Recommended Tera types for a Pokemon, from two sources shown side by side:
  * Smogon's analysis sets (what strong players advise), per set, from the Strategy Dex cache
    (strategy_data.py keeps each set's teratypes)
  * the ladder (what players actually run), the Tera Types shares in this month's chaos stats
Champions has no Terastallization, so both are empty there.
"""
from metamatch import config

LADDER_MIN = 0.04   # ladder Tera types below this share are noise
LADDER_TOP = 3


def _label(format_id):
    return config.format_info(format_id)["label"]


def smogon(name, format_id):
    """[(set name, [Tera types])] from Smogon's sets for this format, in Smogon's order."""
    if config.format_game(format_id) != "sv":
        return []
    from metamatch.strategy_data import load_strategy_data
    entry = load_strategy_data().get(name) or {}
    suffix = f" ({_label(format_id)})"
    out = []
    for set_name, s in (entry.get("sets") or {}).items():
        if set_name.endswith(suffix) and s.get("teratypes"):
            out.append((set_name[:-len(suffix)], list(dict.fromkeys(s["teratypes"]))))
    return out


def closest(name, format_id, moves=(), item=None):
    """(set name, [Tera types]) of the Smogon set most like the team's (shared moves, plus the item), or None.
    Gholdengo's Nasty Plot sets want Tera Fairy and its Scarf set Ghost or Steel, so the set matters."""
    from metamatch.strategy_data import load_strategy_data
    sets = (load_strategy_data().get(name) or {}).get("sets") or {}
    suffix = f" ({_label(format_id)})"
    mine = {m.lower() for m in moves}
    best, score = None, -1
    for set_name, types in smogon(name, format_id):
        s = sets.get(set_name + suffix) or {}
        items = s.get("item") if isinstance(s.get("item"), list) else [s.get("item")]
        points = len(mine & {m.lower() for m in s.get("moves", [])}) + (1.5 if item and item in items else 0)
        if points > score:
            best, score = (set_name, types), points
    return best


def smogon_types(name, format_id):
    """Every Tera type any of Smogon's sets for this format recommend, first mention first."""
    return list(dict.fromkeys(t for _, types in smogon(name, format_id) for t in types))


def ladder(name, format_id, top=LADDER_TOP):
    """[(Tera type, share of ladder sets)], most used first, without the rare ones."""
    if config.format_game(format_id) != "sv":
        return []
    from metamatch.engine.sets import chaos_entry
    entry = chaos_entry(name, format_id)[1] or {}
    counts = entry.get("Tera Types") or {}
    total = sum(counts.values())
    if not total:
        return []
    ranked = sorted(((t.capitalize(), n / total) for t, n in counts.items()), key=lambda x: -x[1])
    return [(t, share) for t, share in ranked if share >= LADDER_MIN][:top]


def ladder_share(name, format_id, tera):
    """Share of ladder sets running `tera`, or None without data."""
    from metamatch.engine.sets import chaos_entry
    entry = chaos_entry(name, format_id)[1] or {}
    counts = entry.get("Tera Types") or {}
    total = sum(counts.values())
    return (counts.get((tera or "").lower(), 0) / total) if total else None


def standing(name, format_id, tera):
    """'smogon' when Smogon recommends the team's Tera, 'ladder' when at least the ladder runs it often, 'rare' when
    neither does, None without data. The guide marks an unusual pick, it never calls one wrong."""
    picks = smogon_types(name, format_id)
    share = ladder_share(name, format_id, tera)
    if not picks and share is None:
        return None
    if tera in picks:
        return "smogon"
    if share is not None and share >= 0.10:
        return "ladder"
    return "rare"

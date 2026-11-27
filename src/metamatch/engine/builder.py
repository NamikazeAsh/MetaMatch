"""
Quick Match builder: a full set for each picked Pokemon and the team as a Showdown paste. Sets are the ladder's most
common one by default, or a Smogon Strategy Dex set with its spread and move picks filled in from ladder usage.
"""
from metamatch import config
from metamatch.engine.dex import dex_for_format, to_id
from metamatch.engine.sets import CHOICE_ITEMS, CHOICE_STATUS_OK, chaos_entry, likely_set
from metamatch.engine.spread_lab import STATS, ladder_spreads, showdown_block
from metamatch.recommender import holds_mega_stone, is_mega

LADDER = "Most common on the ladder"


def paste_species(name):
    """The name a paste uses: a Mega forme ('Charizard-Mega-Y') is written as its base species holding the stone."""
    return name.split("-Mega")[0] if is_mega(name) else name


def _first(x):
    """The first option Smogon lists; its data writes a missing ability or item as 'None'."""
    x = (x[0] if x else None) if isinstance(x, list) else x
    return x if x and x != "None" else None


def smogon_options(name, strat_data, label):
    """Smogon set names for this format ('Wallbreaker (NatDex)'). A Mega keeps only sets holding a stone, a
    non Mega drops them, so each pick matches the forme chosen."""
    sets = ((strat_data or {}).get(paste_species(name)) or {}).get("sets") or {}
    out = []
    for set_name, info in sets.items():
        if not set_name.endswith(f"({label})"):
            continue
        item = _first(info.get("item")) or ""
        if holds_mega_stone(item) != is_mega(name):
            continue
        # Charizard-Mega-Y keeps the Charizardite Y sets, not the X ones
        suffix = name.rsplit("-Mega", 1)[-1].lstrip("-") if is_mega(name) else ""
        if suffix and not item.endswith(f" {suffix}"):
            continue
        out.append(set_name)
    return out


def _ladder_moves(name, format_id):
    """{move id: share} from this month's ladder for `name`."""
    _, entry = chaos_entry(name, format_id)
    moves = (entry or {}).get("Moves") or {}
    total = sum((entry or {}).get("Abilities", {}).values()) or 1
    return {to_id(m): w / total for m, w in moves.items()}


def _from_smogon(name, format_id, info):
    """A Smogon set filled in from the ladder: its four most used moves, and a ladder spread with its nature."""
    nature = _first(info.get("nature")) or "Serious"
    spreads = ladder_spreads(name, format_id, n=10)
    evs = next((e for n, e, _ in spreads if n == nature), spreads[0][1] if spreads else {s: 0 for s in STATS})
    share = _ladder_moves(name, format_id)
    moves = list(dict.fromkeys(m for m in info.get("moves") or [] if m))
    # Smogon flattens slash options into one list, so a Choice set can list Stealth Rock as an option for
    # another set; the same rule as the ladder set: a Choice item keeps only attacks, Trick and Switcheroo, and
    # Assault Vest only attacks
    item_id = to_id(_first(info.get("item")) or "")
    allowed = CHOICE_STATUS_OK if item_id in CHOICE_ITEMS else set() if item_id == "assaultvest" else None
    dex = dex_for_format(format_id)
    if allowed is not None and dex:
        moves = [m for m in moves if (dex.move(m) or {}).get("category") != "Status" or to_id(m) in allowed]
    ranked = sorted(moves, key=lambda m: (-share.get(to_id(m), -1), moves.index(m)))
    teras = info.get("teratypes")
    return {"item": _first(info.get("item")), "ability": _first(info.get("ability")), "nature": nature, "evs": evs,
            "moves": ranked[:4], "tera": _first(teras)}


def member_set(name, format_id, smogon=None):
    """{species, item, ability, nature, evs, moves, tera} for one member, or None with no data. `smogon` is a
    Strategy Dex set ({moves, item, ability, nature, teratypes}) to use instead of the ladder's most common set."""
    ladder = likely_set(name, format_id)
    if smogon:
        s = _from_smogon(name, format_id, smogon)
        # Fill what the Smogon set leaves out (often the ability) from the ladder
        for key in ("item", "ability"):
            s[key] = s[key] or (ladder or {}).get(key)
    elif not ladder:
        return None
    else:
        s = {"item": ladder["item"], "ability": ladder["ability"], "nature": ladder["nature"], "evs": ladder["evs"],
             "moves": [m for m, _ in ladder["moves"]], "tera": (ladder.get("tera") or (None,))[0],
             "all_ratings": ladder.get("all_ratings", False)}
    if not config.has_tera(format_id):
        s["tera"] = None
    return {"species": paste_species(name), **s}


def team_paste(sets, format_id):
    """The team as Showdown text, one block per member."""
    level = 50 if config.format_game(format_id) == "champions" else None
    return "\n\n".join(showdown_block(s["species"], s.get("item"), s.get("ability"), s["nature"], s["evs"],
                                      s["moves"], level=level, tera=s.get("tera")) for s in sets if s)

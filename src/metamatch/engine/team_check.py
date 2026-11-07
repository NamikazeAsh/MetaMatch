"""
Team Check: legality in plain English (species, abilities, moves, spreads, Tera, clauses) and conversions
between SV EVs and Champions stat points. Learnsets and full ability lists aren't bundled (the calc's dex
keeps one ability per species), so moves and abilities are checked to exist, not that the Pokemon gets them.
"""
import math
import re

from metamatch import config
from metamatch.engine.dex import dex_for_format, to_id

TYPES = {"Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison", "Ground", "Flying", "Psychic",
         "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy", "Stellar"}
NATURES = {"Hardy", "Lonely", "Brave", "Adamant", "Naughty", "Bold", "Docile", "Relaxed", "Impish", "Lax", "Timid", "Hasty",
           "Serious", "Jolly", "Naive", "Modest", "Mild", "Quiet", "Bashful", "Rash", "Calm", "Gentle", "Sassy", "Careful", "Quirky"}
STAT_ORDER = ("HP", "Atk", "Def", "SpA", "SpD", "Spe")


def ev_to_sp(ev):
    """EVs to Champions stat points (1 SP is about 8 EVs), capped at 32 per stat."""
    return min(32, math.ceil(ev / 8))


def sp_to_ev(sp):
    return min(252, sp * 8)


def _base_name(name):
    return re.split(r"-Mega", name or "")[0]


def check(team, format_id):
    """[(level, message)] with level 'ok', 'fix' or 'note', fixes first."""
    dex = dex_for_format(format_id)
    game = config.format_game(format_id)
    label = config.format_info(format_id)["label"]
    out = []
    if not dex:
        return [("note", "The bundled dex for this format is missing, so legality can't be checked.")]
    members = list(team.values())
    if len(members) < 6:
        out.append(("note", f"The team has {len(members)} Pokémon. Most formats expect 6."))
    for p in members:
        name = p["Pokemon"]
        species = dex.species(name)
        if not species:
            out.append(("fix", f"{name} isn't in the {label} dex."))
            continue
        # The bundled dex only lists each species' first ability, so this checks the ability exists, not who can have it
        ability = p.get("Ability")
        if ability and not dex.ability_name(ability):
            out.append(("fix", f"{name}: {ability} isn't an ability in {label}."))
        moves = [m["name"] for m in p.get("Moves", [])]
        unknown = [m for m in moves if not dex.move_name(m)]
        if unknown:
            out.append(("fix", f"{name}: {', '.join(unknown)} isn't a move in {label}."))
        if not moves:
            out.append(("fix", f"{name} has no moves."))
        elif len(moves) > 4:
            out.append(("fix", f"{name} has {len(moves)} moves. The limit is 4."))
        dupes = {m for m in moves if moves.count(m) > 1}
        if dupes:
            out.append(("fix", f"{name} lists {', '.join(sorted(dupes))} twice."))
        item = p.get("Item")
        if item and not dex.item_name(item):
            out.append(("fix", f"{name}: {item} isn't an item in {label}."))
        nature = p.get("Nature")
        if nature and nature not in NATURES:
            out.append(("fix", f"{name}: {nature} isn't a nature."))
        if game == "champions":
            sp = p.get("SP") or {}
            over = [f"{v} {k}" for k, v in sp.items() if v > 32]
            if over:
                out.append(("fix", f"{name} has {', '.join(over)}. Champions allows at most 32 stat points in one stat."))
            if sum(sp.values()) > 66:
                out.append(("fix", f"{name} has {sum(sp.values())} stat points. Champions allows 66 in total."))
        else:
            evs = p.get("EVs") or {}
            over = [f"{v} {k}" for k, v in evs.items() if v > 252]
            if over:
                out.append(("fix", f"{name} has {', '.join(over)}. The most one stat can take is 252 EVs."))
            if sum(evs.values()) > 510:
                out.append(("fix", f"{name} has {sum(evs.values())} EVs. The total limit is 510."))
            tera = p.get("Tera Type")
            if tera and tera not in TYPES:
                out.append(("fix", f"{name}: {tera} isn't a Tera type."))
            if p.get("Forme", "").find("-Mega") > 0 and format_id != "gen9natdex":
                out.append(("fix", f"{name} holds a Mega Stone, but Mega Evolution isn't allowed in {label}."))

    bases = [_base_name(p.get("Forme") or p["Pokemon"]) for p in members]
    dupes = sorted({b for b in bases if bases.count(b) > 1})
    if dupes:
        out.append(("fix", f"Species Clause: only one of each Pokémon. {', '.join(dupes)} appears more than once."))
    megas = [p["Pokemon"] for p in members if "-Mega" in (p.get("Forme") or "")]
    if len(megas) > 1:
        out.append(("note", f"{len(megas)} Mega Stones ({', '.join(megas)}). Only one Pokémon can Mega Evolve per battle."))
    if game == "champions":
        items = [p.get("Item") for p in members if p.get("Item")]
        repeated = sorted({i for i in items if items.count(i) > 1})
        if repeated:
            out.append(("note", f"{', '.join(repeated)} is held more than once. Bring 3 play uses Item Clause (each item once)."))

    fixes = [x for x in out if x[0] == "fix"]
    if not fixes:
        out.insert(0, ("ok", f"Legal for {label}: species, abilities, moves, items and spreads all check out."))
    return sorted(out, key=lambda x: {"fix": 0, "note": 1, "ok": 2}[x[0]])


def convert_paste(text, to_champions):
    """A Showdown paste with every 'EVs:' line converted between SV EVs and Champions stat points."""
    def convert(m):
        parts = []
        for chunk in m.group(1).split("/"):
            bits = chunk.strip().split(" ")
            if len(bits) >= 2 and bits[0].isdigit():
                v = int(bits[0])
                v = ev_to_sp(v) if to_champions else sp_to_ev(v)
                if v:
                    parts.append(f"{v} {bits[1]}")
        return "EVs: " + " / ".join(parts) if parts else ""
    lines = [re.sub(r"^EVs:\s*(.*)$", convert, line) for line in text.splitlines()]
    if to_champions:
        lines = [line for line in lines if not line.startswith("Tera Type:")]
    return "\n".join(lines)


def report_markdown(team, format_id, paste, checks, board_rows=None):
    """A shareable Markdown report: the team, its checks and (optionally) its Threat Board summary."""
    label = config.format_info(format_id)["label"]
    lines = [f"# MetaMatch team report ({label})", "", "## Team", "", "```", paste.strip(), "```", "", "## Team Check", ""]
    mark = {"ok": "OK", "fix": "Fix", "note": "Note"}
    lines += [f"- **{mark[level]}:** {msg}" for level, msg in checks]
    if board_rows:
        lines += ["", "## Threat Board", "", "| Threat | Usage | Answers |", "| --- | --- | --- |"]
        lines += [f"| {r['name']} | {r['usage']:g}% | {', '.join(r['answers']) or 'none'} |" for r in board_rows]
    lines += ["", "Made with MetaMatch. Every matchup is worked out by the Smogon damage calculator."]
    return "\n".join(lines)

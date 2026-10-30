"""
Mistake and note flags for one side of a parsed Battle, built only from logged actions.

A mistake is clear and checkable from the log; a note is worth knowing but not necessarily
wrong. Every flag is dated to the turn it happened.
"""
from dataclasses import dataclass

from .protocol import DELAYED_MOVES, HAZARD_DAMAGE, REMOVAL_MOVES, SETUP_MOVES

WEATHER_NAMES = {"RainDance": "rain", "SunnyDay": "sun", "Sandstorm": "sand", "Snow": "snow", "Snowscape": "snow",
                 "Hail": "hail", "DesolateLand": "harsh sun", "PrimordialSea": "heavy rain", "DeltaStream": "strong winds"}


@dataclass
class Flag:
    turn: int
    kind: str        # 'mistake' or 'note'
    title: str
    detail: str


def _events(battle):
    """Every logged event in order, across turns."""
    for turn in battle.turns:
        yield from turn.log


def _turn(battle, number):
    return next((t for t in battle.turns if t.number == number), None)


def hazard_remover_lost(battle, me):
    """Our only hazard remover fainted with hazards up, and those hazards then did damage."""
    flags = []
    mons = battle.mons[me]
    removers = {i for i, m in mons.items() if REMOVAL_MOVES & set(m.moves)}
    for f in battle.faints:
        if f["side"] != me or f["ident"] not in removers:
            continue
        t = _turn(battle, f["turn"])
        hazards = t.hazards.get(me) if t else None
        if not hazards:
            continue
        # Another remover still alive afterwards means the job wasn't lost
        if any(not mons[i].fainted for i in removers if i != f["ident"]):
            continue
        later = sum(e["amount"] for e in _events(battle) if e["kind"] == "damage" and e["side"] == me
                    and e["turn"] > f["turn"] and e.get("source") in HAZARD_DAMAGE)
        if later <= 0:
            continue
        flags.append(Flag(f["turn"], "mistake", f"Lost your hazard remover ({f['species']})",
                          f"{f['species']} fainted with {', '.join(hazards)} up and nothing else to remove them. "
                          f"Your team then took {later}% more hazard damage."))
    return flags


def setup_sweep(battle, me):
    """An opposing Pokémon set up and then KO'd two or more of ours in the same stint."""
    flags = []
    them = "p2" if me == "p1" else "p1"
    active = {"p1": None, "p2": None}
    stint = None   # [ident, setup turn, setup move, KO'd species]

    def close():
        if stint and len(stint[3]) >= 2:
            name = battle.name(stint[0])
            flags.append(Flag(stint[1], "mistake", f"Let {name} set up",
                              f"{name} used {stint[2]} on turn {stint[1]}, then KO'd {', '.join(stint[3])} "
                              f"before it left the field."))

    for e in _events(battle):
        kind = e["kind"]
        if kind == "switch" and e["side"] == them:
            if stint and e["ident"] != stint[0]:
                close()
                stint = None
            active[them] = e["ident"]
        elif kind == "move" and e["side"] == them and not e.get("called") and e.get("move") in SETUP_MOVES:
            if not stint or stint[0] != e["ident"]:
                close()
                stint = [e["ident"], e["turn"], e["move"], []]
        elif kind == "faint":
            if stint and e["ident"] == stint[0]:
                close()
                stint = None
            elif stint and e["side"] == me and e.get("by") == stint[0]:
                stint[3].append(battle.name(e["ident"]))
    close()
    return flags


def magic_bounce(battle, me):
    """Our hazard or status move was bounced back."""
    flags = []
    for b in battle.bounced:
        if b["side"] != me:
            continue
        bouncer = battle.mon(b["bouncer"])
        known = bouncer and bouncer.ability == "Magic Bounce" and (bouncer.ability_turn or b["turn"]) < b["turn"]
        name = battle.name(b["bouncer"])
        detail = f"{battle.name(b['ident'])}'s {b['move']} was reflected by {name}'s Magic Bounce"
        detail += ", which it had already revealed." if known else "."
        flags.append(Flag(b["turn"], "mistake" if known else "note", f"{b['move']} bounced back", detail))
    return flags


def immune_target(battle, me):
    """Our move had no effect on a target that was already in at the start of the turn."""
    flags = []
    for i in battle.immune:
        if i["side"] != me or i["move"] in DELAYED_MOVES:
            continue    # Future Sight lands turns later, on whoever is in by then
        t = _turn(battle, i["turn"])
        start = (t.start.get(i["target"][:2]) or {}) if t else {}
        if start.get("ident") != i["target"]:
            continue    # it switched in, so the move was aimed at something else
        target = battle.mon(i["target"])
        name = battle.name(i["target"])
        user = battle.name(i["ident"])
        # Terastallizing, Mega Evolving or Protean that turn changed its typing after you chose the move
        tera_now = target and target.tera_turn == i["turn"]
        changed = target and (tera_now or target.typechange_turn == i["turn"] or start.get("species") != target.species)
        balloon = target and target.item == "Air Balloon" and not i["source"]
        if i["source"] or balloon:
            source = i["source"] or "its Air Balloon"
            seen = target.ability_turn if i["source"] else target.item_turn
            known = target and (i["source"] is None or target.ability == i["source"]) and seen is not None and seen < i["turn"]
            kind = "mistake" if known else "note"
            detail = f"{user}'s {i['move']} did nothing to {name} because of {source}"
            detail += ", which it had already revealed." if known else "."
        elif changed:
            kind = "note"
            how = f"Terastallized into {target.tera}" if tera_now else "changed type"
            detail = f"{name} {how} that turn, so {user}'s {i['move']} no longer affected it."
        else:
            kind = "mistake"
            detail = f"{user}'s {i['move']} cannot affect {name}'s typing."
        flags.append(Flag(i["turn"], kind, f"{i['move']} into an immune target", detail))
    return flags


def hazard_chip(battle, me):
    """One note for every Pokémon that fainted to hazards or lost a quarter of its HP or more to them."""
    worn = []
    for f in battle.faints:
        mon = battle.mon(f["ident"])
        if f["side"] == me and (f["cause"] == "hazard" or (mon and mon.hazard_damage >= 25)):
            worn.append((f["turn"], f"{f['species']} ({mon.hazard_damage if mon else 0}%"
                         + (f", fainted to {f['source']})" if f["cause"] == "hazard" else ")")))
    if not worn:
        return []
    return [Flag(worn[0][0], "note", "Hazards wore your team down",
                 "Hazard damage before fainting: " + ", ".join(w for _, w in worn)
                 + ". Heavy-Duty Boots or earlier removal would have saved that HP.")]


def destiny_bond(battle, me):
    """We KO'd a Pokémon that had Destiny Bond up."""
    flags = []
    for f in battle.faints:
        if f["side"] != me or f["cause"] != "destiny_bond":
            continue
        user = battle.mon(f["by"])
        seen = user and user.moves.get("Destiny Bond", f["turn"]) < f["turn"]
        name = battle.name(f["by"])
        detail = f"{f['species']} went down with {name} through Destiny Bond"
        detail += f", which {name} had already used earlier." if seen else "."
        flags.append(Flag(f["turn"], "mistake" if seen else "note", "Caught by Destiny Bond", detail))
    return flags


def weather_war(battle, me):
    """Both sides set weather during the game."""
    by_side = {}
    for w in battle.weather_history:
        if w["side"]:
            by_side.setdefault(w["side"], []).append(w)
    if len(by_side) < 2:
        return []
    first = min(w["turn"] for ws in by_side.values() for w in ws)
    names = {side: sorted({WEATHER_NAMES.get(w["weather"], w["weather"]) for w in ws}) for side, ws in by_side.items()}
    them = "p2" if me == "p1" else "p1"
    return [Flag(first, "note", "Weather war",
                 f"You set {', '.join(names.get(me, []))} and your opponent set {', '.join(names.get(them, []))}; "
                 "the weather changed hands during the game.")]


RULES = [hazard_remover_lost, setup_sweep, magic_bounce, immune_target, hazard_chip, destiny_bond, weather_war]


def find_flags(battle, me):
    """All flags for side `me`, mistakes first, then by turn."""
    flags = [f for rule in RULES for f in rule(battle, me)]
    return sorted(flags, key=lambda f: (f.kind != "mistake", f.turn))

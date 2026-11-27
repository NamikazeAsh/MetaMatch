"""
Answers planned questions directly from the engine (calc, dex, chaos usage data).
Each solver returns a Verdict: the short answer, a templated sentence stating it, and
the supporting facts. The LLM only ever explains a Verdict, it never produces one.
"""
import re
from dataclasses import dataclass, field, replace

from metamatch import config
from metamatch.engine import calc, constraints, mechanics
from metamatch.engine.dex import dex_for_format, to_id
from metamatch.engine.packet import Fact, cap, hits as hits_text, mon, pct as pct_text
from metamatch.engine.sets import calc_spec, chaos_entry, describe_spread, likely_set, spread_label

STAT_NAMES = {"hp": "HP", "atk": "Attack", "def": "Defense", "spa": "Special Attack", "spd": "Special Defense", "spe": "Speed"}
CALC_STAT_KEYS = {"HP": "hp", "Atk": "atk", "Def": "def", "SpA": "spa", "SpD": "spd", "Spe": "spe"}

# One ordinary attack per type, used to detect ability based immunities through the calc
PROBE_MOVES = {
    "Normal": "Hyper Voice", "Fire": "Flamethrower", "Water": "Surf", "Electric": "Thunderbolt",
    "Grass": "Energy Ball", "Ice": "Ice Beam", "Fighting": "Close Combat", "Poison": "Sludge Bomb",
    "Ground": "Earthquake", "Flying": "Air Slash", "Psychic": "Psychic", "Bug": "X-Scissor",
    "Rock": "Stone Edge", "Ghost": "Shadow Ball", "Dragon": "Dragon Pulse", "Dark": "Dark Pulse",
    "Steel": "Flash Cannon", "Fairy": "Moonblast",
}


@dataclass
class Verdict:
    intent: str
    answer: str                     # short canonical answer: "yes", "no", "tie", "weak", "29-34.6%", "Leftovers"...
    statement: str                  # templated sentence stating the answer
    facts: list = field(default_factory=list)
    persona: str = "mechanics"      # which agent persona presents it
    subject: str = ""               # the player's Pokemon, for contradiction checks
    other: str = ""                 # the opposing Pokemon
    survive: bool = False           # KO question phrased as "does X survive"
    ask_slower: bool = False        # speed question phrased as "is X slower": "yes" means subject is slower
    subject_is_player: bool = True  # False when the question's subject is the opponent ("does Dragapult outspeed me")
    hits: int = 1                   # KO verdicts: the number of hits the question asked about
    losers: list = field(default_factory=list)  # checks verdicts: members that lose one on one
    members: list = field(default_factory=list)  # checks verdicts: the whole team
    groups: dict = field(default_factory=dict)   # team_type verdicts: {"immune"|"resist"|"neutral"|"weak": [members]}
    speeds: tuple = ()                           # speed verdicts: (player's Speed, opponent's Speed)
    # The answer packet view (engine/packet.py): the answer in plain words with owner words, and typed facts; facts
    # with role "why" are the ones the model may explain. `statement` and `facts` stay as the exact engine wording
    plain: str = ""
    typed: list = field(default_factory=list)


def _pct(x):
    return f"{x * 100:.0f}%"


def user_spec(p, game, details=None, dex=None):
    """A team member as a calc_server Pokemon spec (Champions uses stat points as 'evs'), with any set
    details the question states for it applied."""
    raw = p.get("SP") if game == "champions" else p.get("EVs")
    spec = {"name": p.get("Forme") or p["Pokemon"],
            "evs": {CALC_STAT_KEYS[k]: v for k, v in (raw or {}).items() if k in CALC_STAT_KEYS}}
    if p.get("IVs") and game != "champions":
        spec["ivs"] = {CALC_STAT_KEYS[k]: v for k, v in p["IVs"].items() if k in CALC_STAT_KEYS}
    if p.get("Nature"):
        spec["nature"] = p["Nature"]
    if p.get("Item"):
        spec["item"] = p["Item"]
    ability = p.get("Mega Ability") or p.get("Ability")
    if ability:
        spec["ability"] = ability
    return constraints.apply(spec, details, dex, game) if details else spec


def _opponent(plan, dex):
    """(display name, calc spec, likely set) for the plan's opponent, with explicit set details applied."""
    s = likely_set(plan.opponent, plan.format_id)
    if s:
        spec = calc_spec(s)
        name = s["name"]
    else:
        species = dex.species(plan.opponent) if dex else None
        if not species:
            return None, None, None
        name, spec = species["name"], {"name": species["name"]}
    spec = constraints.apply(spec, plan.opp_overrides, dex, config.format_game(plan.format_id))
    return name, spec, s


def _mine(plan, dex, game):
    return user_spec(plan.user, game, plan.user_overrides, dex)


def _calc_field(plan, defender_side=None, situation=()):
    """calc Field for the stated weather and terrain, plus screens and hazards on the defender's side."""
    f = dict(plan.conditions)
    flags = {flag: True for flag in set(plan.screens.get("defender", ())) | set(plan.screens.get(defender_side, ()))}
    for c in situation:
        if c.side == defender_side and c.kind == "stealth_rock":
            flags["isSR"] = True
        elif c.side == defender_side and c.kind == "spikes":
            flags["spikes"] = c.value
    if defender_side and flags:
        f["defenderSide"] = flags
    return f or None


QP_ABILITIES = {"Protosynthesis", "Quark Drive"}


def _situation(plan, specs):
    """The counted conditions with every side the question left unsaid filled in for this question:
    Tailwind and paralysis go to the subject, a burn to the attacker, HP, poison and hazards to the defender.
    specs: side -> calc spec, so a stated Protosynthesis lands on the side that has it."""
    attacker = "opponent" if plan.attacker == "opponent" or not plan.user else "user"
    defender = "user" if attacker == "opponent" else "opponent"
    defaults = {"tailwind": plan.subject, "hp": defender, "stealth_rock": defender, "spikes": defender,
                "brn": attacker, "psn": defender, "par": plan.subject,
                "qp": plan.subject if plan.intent == "speed" else attacker}
    out = []
    for c in plan.situation:
        side = c.side or defaults.get(c.value if c.kind == "status" else c.kind)
        if c.kind == "qp" and specs.get(side, {}).get("ability") not in QP_ABILITIES:
            side = next((s for s in ("user", "opponent") if specs.get(s, {}).get("ability") in QP_ABILITIES), side)
        out.append(replace(c, side=side))
    return out


def _with_state(spec, side, situation, plan):
    """A spec with this side's stated status, HP and boost switches applied (a copy)."""
    if not spec:
        return spec
    spec = dict(spec)
    if plan.no_boosts:
        spec["boostedStat"] = None   # "no boosts": Booster Energy, sun or terrain don't trigger Protosynthesis either
    for c in situation:
        if c.side not in (side, "both"):
            continue
        if c.kind == "status":
            spec["status"] = c.value
        elif c.kind == "hp":
            spec["hpPercent"] = c.value
        elif c.kind == "qp":
            spec["qpActive"] = True
            spec.pop("boostedStat", None)
    return spec


def _speed_field(plan, side, situation):
    """calc Field for one side's Speed: the stated weather and terrain, plus that side's Tailwind."""
    f = dict(_calc_field(plan) or {})
    if any(c.kind == "tailwind" and c.side in (side, "both") for c in situation):
        f["attackerSide"] = {"isTailwind": True}
    return f or None


def _counting(situation, names):
    """' Counted from the question: a critical hit and Kingambit at 50% HP.' or ''."""
    said = [constraints.describe(c, names) for c in situation]
    return f" Counted from the question: {_join(said)}." if said else ""


def _spread_text(spec, game):
    return describe_spread({"nature": spec.get("nature", "Serious"), "evs": spec.get("evs") or {}}, game)


def _spread_label(plan, s, spec, game):
    """How the opponent's spread was chosen, for the verdict sentence (closing bracket added by the caller)."""
    if constraints.stated_spread(plan.opp_overrides):
        return f"running the stated spread ({_spread_text(spec, game)}"
    return f"running its most common spread ({describe_spread(s, game) if s else 'an uninvested spread'}"


# A Choice Scarf share this large gets its own line in a Speed answer, even when Scarf isn't the most common item
SCARF_NOTE = 0.1


def _stats(game, spec, move):
    r = calc.calculate({"game": game, "attacker": spec, "defender": spec, "move": move})
    return r["attacker_stats"] if r else None


def _any_move(spec_moves, dex):
    """A move that exists in this game's dex, for stat only calc requests."""
    for m in spec_moves:
        if dex.move_name(m):
            return dex.move_name(m)
    return next(iter(dex.move_data))


def display_name(name):
    """'Garchomp-Mega-Z' -> 'Mega Garchomp Z', everything else unchanged."""
    if "-Mega" not in (name or ""):
        return name
    base, _, suffix = name.partition("-Mega")
    return f"Mega {base} {suffix.strip('-')}".strip()


def _user_name(p):
    return display_name(p["Forme"]) if p.get("Forme") else p["Pokemon"]


def own_field(team, member=None):
    """(setter, label, calc Field) for the weather or terrain an ability on the team sets on entry ("sand",
    Tyranitar), or None. With `member`, only one that changes that member's Speed is useful to callers, which
    compare the Speed with and without it; the setter is None when the member sets it itself."""
    from metamatch.engine import synergy
    for key, cond in synergy.CONDITIONS.items():
        for p in (team or {}).values():
            abilities = {a for a in (p.get("Ability"), p.get("Mega Ability")) if a}
            if abilities & set(cond.get("ability_setters", {})):
                label = key.lower() if key in synergy.WEATHER else cond["label"]
                return (None if p["Pokemon"] == member else p["Pokemon"]), label, dict(cond["field"])
    return None


def solve_speed(plan, dex, game):
    p = plan.user
    name, spec, s = _opponent(plan, dex)
    if not name:
        return None
    move = _any_move([m["name"] for m in p.get("Moves", [])], dex)
    mine = _mine(plan, dex, game)
    situation = _situation(plan, {"user": mine, "opponent": spec})
    mine = _with_state(mine, "user", situation, plan)
    spec = _with_state(spec, "opponent", situation, plan)
    stated = plan.opp_overrides.get("item")
    opp_speed_spec = mechanics.opponent_speed_spec(spec, stated)
    if plan.raw_stats:
        stated = None
        us = (_stats(game, mine, move) or {}).get("spe")
        them = (_stats(game, spec, move) or {}).get("spe")
    else:
        us = mechanics.final_speed(mine, game, move, _speed_field(plan, "user", situation))
        them = mechanics.final_speed(opp_speed_spec, game, move, _speed_field(plan, "opponent", situation))
    if not us or not them:
        return None
    name = display_name(name)
    # Under Trick Room the slower Pokemon moves first, and "outspeed" means "moves first"
    trick_room = any(c.kind == "trick_room" for c in situation)
    first = us < them if trick_room else us > them
    order = "tie" if us == them else "yes" if first else "no"
    words = ({"yes": "moves before", "no": "moves after"} if trick_room else {"yes": "outspeeds", "no": "is slower than"})
    verb = {**words, "tie": "speed ties with"}[order]
    label = _spread_label(plan, s, spec, game)
    # "with Choice Scarf" only when the item itself moved the number, not Tailwind or paralysis
    plain_us = us if plan.raw_stats or not situation else mechanics.final_speed(
        {k: v for k, v in mine.items() if k not in ("status", "qpActive")}, game, move, _calc_field(plan))
    held = f" with {mine['item']}" if mine.get("item") and plain_us != (_stats(game, mine, move) or {}).get("spe") else ""
    theirs = f" @ {stated}" if stated in mechanics.OPP_SPEED_ITEMS else ""
    statement = f"{_user_name(p)} ({us} Speed{held}) {verb} {name}{theirs} {label}, {them} Speed)."
    # The answer is about the question's subject and comparison: "Does Dragapult outspeed my Tusk?"
    subject, other, faster = _user_name(p), name, first and us != them
    if plan.subject == "opponent":
        subject, other, faster = name, _user_name(p), not first and us != them
        verb = {"yes": words["no"], "no": words["yes"], "tie": "speed ties with"}[order]
        statement = (f"{name}{theirs} {label}, {them} Speed) {verb} "
                     f"{_user_name(p)} ({us} Speed{held}).")
    if trick_room:
        statement = "Under Trick Room the slower Pokémon moves first: " + statement
    statement += _counting([c for c in situation if c.kind != "trick_room"], {"user": _user_name(p), "opponent": name})
    slower = (not first) if plan.subject == "user" else first
    answer = "tie" if us == them else ("yes" if (slower if plan.speed_ask == "slower" else faster) else "no")
    told = constraints.stated_spread(plan.opp_overrides)
    which = "the stated spread" if told else "its most common spread"
    if stated in mechanics.OPP_SPEED_ITEMS:
        which += f" and the stated {stated}"
    facts = [f"{_user_name(p)} Speed: {us}.", f"{name} Speed with {which}: {them}."]
    me, opp = mon(_user_name(p), True), mon(name, False)
    typed = [Fact("speed", f"{cap(me)} has {us} Speed{held}.", {"side": "user", "speed": us}),
             Fact("speed", f"{cap(opp)} has {them} Speed with {which}.", {"side": "opponent", "speed": them}, role="why")]
    # Ladder shares compare against plain spreads, so they only hold when nothing the question states changes the
    # opponent's Speed: no field effect, no stated spread, and no stated Speed item (a Scarf answer that also said
    # "outspeeds 100% of its sets" would contradict itself)
    plain = (not trick_room and not any(c.side in ("opponent", "both") for c in situation)
             and stated not in mechanics.OPP_SPEED_ITEMS and not plan.opp_overrides.get("boosts"))
    if s and s["speeds"] and not told and plain:
        # Choice Scarf and Booster Energy sets mixed in at their ladder shares, as the Threat Board and guide do
        scarf, booster = s.get("scarf_share", 0.0), s.get("booster_share", 0.0)
        faster = mechanics.scarf_adjusted_share(us, s["speeds"], scarf, booster)
        tied = mechanics.scarf_adjusted_tie(us, s["speeds"], scarf, booster)
        facts.append(f"Across all {name} sets on the ladder, {_user_name(p)} outspeeds {_pct(faster)} and ties {_pct(tied)}.")
        typed.append(Fact("speed", f"{cap(me)} outspeeds {_pct(faster)} of ladder {name} sets"
                                   + (f" and ties {_pct(tied)}." if tied >= 0.005 else "."),
                          {"outspeeds_share": round(faster, 3), "ties_share": round(tied, 3)}))
    # A Scarf share worth knowing, even when Scarf isn't its most common item (23% of Champions Dragapult)
    scarf_share = s.get("scarf_share", 0.0) if s else 0.0
    if (s and scarf_share >= SCARF_NOTE and "item" not in plan.opp_overrides and not plan.opp_overrides.get("no_speed_item")
            and stated not in mechanics.OPP_SPEED_ITEMS):
        facts.append(f"{_pct(scarf_share)} of {name} carry Choice Scarf, reaching {int(them * 1.5)} Speed.")
        typed.append(Fact("usage", f"{_pct(scarf_share)} of ladder {name} sets hold Choice Scarf, which takes it to "
                                   f"{int(them * 1.5)} Speed.", {"item": "Choice Scarf", "share": scarf_share,
                                                                 "speed": int(them * 1.5)}, role="why"))
    if s and s.get("item") == "Booster Energy" and not stated and not plan.raw_stats and opp_speed_spec is not spec:
        boosted = mechanics.final_speed(spec, game, move, _speed_field(plan, "opponent", situation))
        if boosted and boosted != them:
            facts.append(f"{_pct(s['item_share'])} of {name} carry Booster Energy, which raises its Speed to {boosted}.")
            typed.append(Fact("usage", f"{_pct(s['item_share'])} of ladder {name} sets hold Booster Energy, which raises its "
                                       f"Speed to {boosted}.", {"item": "Booster Energy", "share": s["item_share"],
                                                                "speed": boosted}, role="why"))
    if trick_room:
        typed.append(Fact("rule", "Under Trick Room the slower Pokemon moves first.", {"trick_room": True}))
    # The answer in plain words, from the player's side
    if us == them:
        said = f"{cap(me)} and {opp} tie at {us} Speed, so either can move first."
    elif first:
        said = f"{cap(me)} moves before {opp}: {us} Speed against {them}."
    else:
        said = f"{cap(opp)} moves before {me}: {them} Speed against {us}."
    if trick_room:
        said = "Under Trick Room, " + said[0].lower() + said[1:]
    # The team's own weather or terrain (set by an ability on entry): Sand Rush Excadrill behind Sand Stream
    # Tyranitar is far faster than its plain Speed says, so give that number too
    own = None if (plan.raw_stats or trick_room or plan.conditions) else own_field(plan.team, _user_name(p))
    if own:
        setter, label, fld = own
        us_f = mechanics.final_speed(mine, game, move, fld)
        them_f = mechanics.final_speed(opp_speed_spec, game, move, fld)
        if us_f and them_f and us_f != us:
            where = f"With {mon(setter, True)}'s {label} up" if setter else f"With its own {label} up"
            if us_f == them_f:
                line = f"{where}, {me} and {opp} tie at {us_f} Speed."
            elif us_f > them_f:
                line = f"{where}, {me} has {us_f} Speed and moves before {opp} ({them_f})."
            else:
                line = f"{where}, {me} has {us_f} Speed, still behind {opp} ({them_f})."
            said += " " + line
            statement += f" {where}, {_user_name(p)} has {us_f} Speed against {name}'s {them_f}."
            facts.append(f"{where}: {_user_name(p)} {us_f} Speed, {name} {them_f}.")
            # The answer now carries both numbers; a voiced "why" restating one of them ("Iron Valiant has a higher
            # Speed") would read as contradicting the other, so no fact is offered as the why
            typed = [Fact("speed", line[0].upper() + line[1:], {"field": label, "speed": us_f, "opponent": them_f},
                          role="why")] + [replace(f, role="context") for f in typed]
    # Contradiction checks read the answer as "subject is faster than other", inverted when ask_slower
    return Verdict("speed", answer, statement, facts, subject=subject, other=other,
                   ask_slower=plan.speed_ask == "slower", subject_is_player=plan.subject != "opponent", speeds=(us, them),
                   plain=said, typed=typed)


def _attack(plan, dex, game):
    """Runs the calc for the planned attack. Returns (attacker name, defender name, move, result, opp set)."""
    p = plan.user
    name, opp_spec, s = _opponent(plan, dex)
    if not name:
        return None
    mine = _mine(plan, dex, game) if p else None
    if plan.raw_stats:  # "ignoring items and abilities": both sides bare
        bare = lambda spec: {k: v for k, v in spec.items() if k not in ("item", "ability")} if spec else spec
        mine, opp_spec = bare(mine), bare(opp_spec)
    situation = _situation(plan, {"user": mine or {}, "opponent": opp_spec})
    mine = _with_state(mine, "user", situation, plan)
    opp_spec = _with_state(opp_spec, "opponent", situation, plan)
    shown = display_name(name)
    if plan.attacker == "opponent" or not p:
        attacker, defender, defender_side = (shown, opp_spec), ((_user_name(p), mine) if p else None), "user"
        moves = [plan.move] if plan.move else (plan.opp_overrides.get("moves") or [m for m, _ in (s or {}).get("moves", [])])
    else:
        attacker, defender, defender_side = (_user_name(p), mine), (shown, opp_spec), "opponent"
        moves = [plan.move] if plan.move else (plan.user_overrides.get("moves")
                                               or [m["name"] for m in p.get("Moves", []) if m.get("category") != "Status"])
    # "Its strongest move" means its strongest attack: status moves never count
    moves = [m for m in moves if m == plan.move or (dex.move(m) or {}).get("category") != "Status"]
    if not defender or not moves:
        return None
    f = _calc_field(plan, defender_side, situation)
    crit = {"moveOptions": {"isCrit": True}} if any(c.kind == "crit" for c in situation) else {}
    results = calc.calculate_many([{"game": game, "attacker": attacker[1], "defender": defender[1], "move": m,
                                    **({"field": f} if f else {}), **crit} for m in moves])
    scored = [(m, r) for m, r in zip(moves, results) if r]
    if not scored:
        return None
    move, result = max(scored, key=lambda x: x[1]["percent"][1])
    # Only conditions on the side that matters stay counted: rocks on the attacker's side change nothing here
    situation = [c for c in situation if c.kind not in ("stealth_rock", "spikes") or c.side == defender_side]
    names = {defender_side: defender[0], ("opponent" if defender_side == "user" else "user"): attacker[0]}
    return Attack(attacker[0], defender[0], move, result, s, attacker[1], defender[1], situation, names,
                  _chipped(defender[1], defender_side, situation, dex))


@dataclass
class Attack:
    attacker: str
    defender: str
    move: str
    result: dict
    opp_set: dict | None
    attacker_spec: dict
    defender_spec: dict
    situation: list
    names: dict           # side -> Pokemon shown, for describing the counted conditions
    chipped: bool         # the defender starts below full HP (stated HP, or hazards it takes)


def _chipped(spec, side, situation, dex):
    """True when the defender isn't at full HP when hit, so Sturdy and Focus Sash can't save it."""
    if spec.get("hpPercent", 100) < 100:
        return True
    if spec.get("item") == "Heavy-Duty Boots" or spec.get("ability") in ("Magic Guard", "Mountaineer"):
        return False
    types = (dex.species(spec["name"]) or {}).get("types", []) if dex else []
    grounded = "Flying" not in types and spec.get("ability") != "Levitate" and spec.get("item") != "Air Balloon"
    return any(c.side == side and (c.kind == "stealth_rock" or (c.kind == "spikes" and grounded)) for c in situation)


def _hp_facts(attack):
    pct = attack.defender_spec.get("hpPercent")
    if not pct or pct >= 100:
        return []
    return [f"Damage percentages are of max HP; {attack.defender} starts at {pct}% "
            f"({attack.result.get('defender_cur_hp')} of {attack.result['defender_stats']['hp']} HP)."]


def _ko_hits(ko_text):
    """(hits, guaranteed) from calc text like 'guaranteed 2HKO' or '31.6% chance to OHKO'."""
    m = re.search(r"(guaranteed|chance to) (O|\d+)HKO", ko_text or "")
    if not m:
        return None, False
    return (1 if m.group(2) == "O" else int(m.group(2))), m.group(1) == "guaranteed"


def _attack_words(plan, attack, game):
    """(attacker, defender, damage clause, typed facts) for a calc answer, with owner words, whole percentages and
    the knockout count in plain words ('in 2 or 3 hits')."""
    att_mine = plan.attacker == "user"
    a, d = mon(attack.attacker, att_mine), mon(attack.defender, not att_mine)
    r, move = attack.result, attack.move
    lo, hi = r["percent"]
    worst = mechanics.hits_to_ko(r, attack.attacker_spec, attack.defender_spec, move, game=game)
    best = mechanics.hits_to_ko(r, attack.attacker_spec, attack.defender_spec, move, game=game, roll=1)
    if not hi:
        clause = f"{cap(a)}'s {move} does no damage to {d}"
        typed = [Fact("damage", f"{clause}.", {"move": move, "pct": [0, 0], "immune": True}, role="why")]
    else:
        clause = f"{cap(a)}'s {move} does {pct_text(lo, hi)} of {d}'s HP"
        count = hits_text(worst, best)
        typed = [Fact("damage", f"{clause}.", {"move": move, "pct": [lo, hi]}, role="why", detail=r.get("desc", ""))]
        if count:
            typed.append(Fact("ko", f"From full HP, {a}'s {move} knocks out {d} {count}.",
                              {"move": move, "hits": worst, "hits_best": best}, role="why"))
    if attack.opp_set and not constraints.stated_spread(plan.opp_overrides) and "item" not in plan.opp_overrides:
        s = attack.opp_set
        typed.append(Fact("stated", f"{cap(mon(s['name'], False))} is assumed on its most common set: {s['item']}, "
                                    f"{s['ability']}.", {"basis": "most common set"}))
    return a, d, clause, typed


def solve_ko(plan, dex, game):
    attack = _attack(plan, dex, game)
    if not attack:
        return None
    att, dfn, move, r, s = attack.attacker, attack.defender, attack.move, attack.result, attack.opp_set
    lo, hi = r["percent"]
    answer, effect = mechanics.ko_answer(r, plan.ko_hits, attack.attacker_spec, attack.defender_spec, move,
                                         full_hp=not attack.chipped)
    if plan.survive:
        answer = {"yes": "no", "no": "yes", "sometimes": "sometimes"}[answer]
        outcome = {"yes": f"{dfn} survives", "no": f"{dfn} does not survive", "sometimes": f"{dfn} survives only some rolls"}[answer]
    else:
        n = "OHKO" if plan.ko_hits == 1 else f"{plan.ko_hits}HKO"
        outcome = {"yes": f"it {n}s", "no": f"it does not {n}", "sometimes": f"it {n}s only on some damage rolls"}[answer]
    held = f" (it survives a full HP hit at 1 HP with {effect})" if effect and effect != "Disguise" else         " (Disguise takes the first hit)" if effect else ""
    if not hi:
        # "does 0-0%, so it survives" reads like a bug: say it is an immunity, as the damage answer does
        from metamatch.team import ABILITY_IMMUNITIES
        ability = (s or {}).get("ability") if dfn != _user_name(plan.user or {"Pokemon": ""}) else (plan.user or {}).get("Ability")
        why = f"{dfn}'s {ability} makes it immune" if (ability or "").lower() in ABILITY_IMMUNITIES else f"{dfn} is immune to it"
        statement = f"{att}'s {move} does no damage to {dfn}: {why}, so {outcome}." + _counting(attack.situation, attack.names)
    else:
        statement = f"{att}'s {move} does {lo}-{hi}% to {dfn}{held}, so {outcome}." + _counting(attack.situation, attack.names)
    facts = [f"Calc: {r['desc']}"] if r["desc"] else []
    facts += _hp_facts(attack)
    if effect and effect != "Disguise":
        facts.append(f"{dfn} at full HP keeps {effect}; hazards or earlier chip would remove it.")
    if s and not constraints.stated_spread(plan.opp_overrides) and "item" not in plan.opp_overrides:
        facts.append(f"{s['name']} assumed on its most common set: {describe_spread(s, game)} @ {s['item']}, {s['ability']}.")
    a, d, clause, typed = _attack_words(plan, attack, game)
    if effect:
        typed.append(Fact("rule", f"At full HP, {d} lives one hit on 1 HP with {effect}." if effect != "Disguise" else
                                  f"{cap(d)}'s Disguise takes the first hit.", {"effect": effect}, role="why"))
    n = "one hit" if plan.ko_hits == 1 else f"{plan.ko_hits} hits"
    if plan.survive:
        said = {"yes": f"Yes, {d} survives: {clause[0].lower() + clause[1:]}.",
                "no": f"No, {d} does not survive: {clause[0].lower() + clause[1:]}.",
                "sometimes": f"Only on some rolls: {clause[0].lower() + clause[1:]}."}[answer]
    else:
        said = {"yes": f"Yes, it knocks out {d} in {n}: {clause[0].lower() + clause[1:]}.",
                "no": f"No, it does not knock out {d} in {n}: {clause[0].lower() + clause[1:]}.",
                "sometimes": f"Only on some rolls: {clause[0].lower() + clause[1:]}."}[answer]
    return Verdict("ko", answer, statement, facts, subject=att, other=dfn, survive=plan.survive, hits=plan.ko_hits,
                   plain=said, typed=typed)


def solve_damage(plan, dex, game):
    attack = _attack(plan, dex, game)
    if not attack:
        return None
    att, dfn, move, r, s = attack.attacker, attack.defender, attack.move, attack.result, attack.opp_set
    lo, hi = r["percent"]
    ko = f" ({r['ko']})" if r["ko"] else ""
    if not hi:
        # "does 0-0%" reads like a bug: say it is an immunity, and whose ability grants it when one does
        from metamatch.team import ABILITY_IMMUNITIES
        ability = (s or {}).get("ability") if attack.defender != _user_name(plan.user or {"Pokemon": ""}) else (plan.user or {}).get("Ability")
        why = f", whose {ability} makes it immune" if (ability or "").lower() in ABILITY_IMMUNITIES else ", which is immune to it"
        statement = f"{att}'s {move} does no damage to {dfn}{why}." + _counting(attack.situation, attack.names)
    else:
        statement = f"{att}'s {move} does {lo}-{hi}% to {dfn}{ko}." + _counting(attack.situation, attack.names)
    facts = [f"Calc: {r['desc']}"] if r["desc"] else []
    facts += _hp_facts(attack)
    if s and not constraints.stated_spread(plan.opp_overrides) and "item" not in plan.opp_overrides:
        facts.append(f"{s['name']} assumed on its most common set: {describe_spread(s, game)} @ {s['item']}, {s['ability']}.")
    a, d, clause, typed = _attack_words(plan, attack, game)
    said = clause + (f": {d} is immune." if not hi else ".")
    return Verdict("damage", f"{lo}-{hi}%", statement, facts, plain=said, typed=typed)


def _type_profile(plan):
    """One team member's weaknesses, resistances and immunities across every type, abilities and Air Balloon
    included (the team's own Damage From table, the one the Matchup Matrices tab shows)."""
    p = plan.user
    name = _user_name(p)
    taken = {t: (p.get("Damage From") or {}).get(t.lower(), 1.0) for t in TYPE_NAMES}
    groups = {"weak": [t for t in TYPE_NAMES if taken[t] > 1], "resist": [t for t in TYPE_NAMES if 0 < taken[t] < 1],
              "immune": [t for t in TYPE_NAMES if taken[t] == 0]}
    def listed(types):
        return _join(f"{t} ({taken[t]:g}x)" for t in types)
    typing = "/".join(p.get("Type", []))
    weak = groups["weak"]
    who = cap(mon(name, True))
    facts = [f"Weak to: {listed(weak) or 'nothing'}.", f"Resists: {listed(groups['resist']) or 'nothing'}.",
             f"Immune to: {_join(groups['immune']) or 'nothing'}."]
    ask = plan.team_ask if plan.team_ask in ("resist", "immune") else "weak"
    asked = groups[ask]
    verb = {"weak": "is weak to", "resist": "resists", "immune": "is immune to"}[ask]
    none = {"weak": "has no weaknesses", "resist": "resists nothing", "immune": "has no immunities"}[ask]
    statement = f"{name} ({typing}) {verb} {listed(asked) if ask != 'immune' else _join(asked)}." if asked \
        else f"{name} ({typing}) {none}."
    plain = f"{who} {verb} {_join(asked)} attacks." if asked else f"{who} {none}."
    typed = [Fact("type", f"{who} is {typing} type.", {"types": p.get("Type", [])}, role="why")]
    for mult in sorted({taken[t] for t in weak}, reverse=True):
        same = [t for t in weak if taken[t] == mult]
        typed.append(Fact("type", f"{_join(same)} attacks do {mult:g} times damage to it.",
                          {"weak": {t: mult for t in same}}, role="why"))
    if groups["immune"]:
        typed.append(Fact("type", f"{who} is immune to {_join(groups['immune'])} attacks.",
                          {"immune": groups["immune"]}, role="why"))
    if groups["resist"]:
        typed.append(Fact("type", f"{who} resists {_join(groups['resist'])} attacks.",
                          {"resist": groups["resist"]}))
    return Verdict("type", ", ".join(asked) or "none", statement, facts, plain=plain, typed=typed)


def solve_type(plan, dex, game):
    chart = dex.type_chart
    t = plan.atk_type
    if not t:
        return _type_profile(plan) if plan.user is not None else None
    # The question is about the named team member, else a named opponent, else the only team member
    if plan.user is not None and (plan.user_named or not plan.opponent):
        p = plan.user
        name, types, spec = _user_name(p), p.get("Type", []), _mine(plan, dex, game)
        ability = spec.get("ability")
    else:
        name, spec, s = _opponent(plan, dex)
        if not name:
            return None
        types, ability = dex.species(name)["types"], spec.get("ability")
        name = display_name(name)
    # A Terastallized Pokemon takes hits as its Tera type alone (Stellar keeps its own types)
    tera = spec.get("teraType")
    if tera and tera != "Stellar":
        types = [tera]
    mult = 1.0
    for d in types:
        mult *= chart.get(t, {}).get(d, 1.0)
    via = ""
    probe = PROBE_MOVES.get(t)
    if mult > 0 and probe and dex.move_name(probe):
        r = calc.calculate({"game": game, "attacker": {"name": "Garchomp"}, "defender": spec, "move": probe})
        if r and r["range"][1] == 0:
            item = spec.get("item")
            bare = calc.calculate({"game": game, "attacker": {"name": "Garchomp"}, "move": probe,
                                   "defender": {k: v for k, v in spec.items() if k != "item"}}) if item else None
            if bare and bare["range"][1] > 0:
                via = f" while holding {item}"
            else:
                via = f" thanks to {ability}" if ability else ""
            mult = 0.0
    answer = "immune" if mult == 0 else "resists" if mult < 1 else "weak" if mult > 1 else "neutral"
    phrase = {"immune": f"is immune to {t} attacks{via}", "resists": f"resists {t} attacks ({mult:g}x)",
              "weak": f"is weak to {t} attacks ({mult:g}x)", "neutral": f"takes neutral damage from {t} attacks (1x)"}[answer]
    typing = f"Tera {tera}" if tera and tera != "Stellar" else "/".join(types)
    statement = f"{name} ({typing}{', ' + ability if ability else ''}) {phrase}."
    facts = [f"{t} vs {d}: {chart.get(t, {}).get(d, 1.0):g}x." for d in types]
    mine = plan.user is not None and (plan.user_named or not plan.opponent)
    who = mon(name, mine)
    plain_phrase = {"immune": f"is immune to {t} attacks{via}", "resists": f"resists {t} attacks: they do {mult:g} times damage",
                    "weak": f"is weak to {t} attacks: they do {mult:g} times damage",
                    "neutral": f"takes normal damage from {t} attacks"}[answer]
    typed = [Fact("type", f"{cap(who)} is {typing} type" + (f" with {ability}." if ability else "."),
                  {"types": types, "ability": ability}, role="why")]
    typed += [Fact("type", f"{t} attacks do {chart.get(t, {}).get(d, 1.0):g} times damage to {d} types.",
                   {"attack": t, "defend": d, "mult": chart.get(t, {}).get(d, 1.0)}, role="why") for d in types]
    return Verdict("type", answer, statement, facts, plain=f"{cap(who)} {plain_phrase}.", typed=typed)


def solve_stat(plan, dex, game):
    if plan.stat_target == "opponent":
        name, spec, s = _opponent(plan, dex)
        if not name:
            return None
        who, item = display_name(name), spec.get("item")
        how = (f" ({_spread_text(spec, game)})" if constraints.stated_spread(plan.opp_overrides) else
               f" on its most common spread ({describe_spread(s, game)})" if s else " uninvested")
        moves = [m for m, _ in (s or {}).get("moves", [])]
    else:
        p = plan.user
        spec, who, item, how = _mine(plan, dex, game), _user_name(p), p.get("Item"), ""
        moves = [m["name"] for m in p.get("Moves", [])]
    stats = _stats(game, spec, _any_move(moves, dex))
    if not stats:
        return None
    value = stats[plan.stat]
    level = 50 if game == "champions" else 100
    statement = f"{who}'s {STAT_NAMES[plan.stat]} stat is {value} at level {level}{how}."
    facts = [f"All stats: " + ", ".join(f"{STAT_NAMES[k]} {v}" for k, v in stats.items()) + "."]
    if plan.stat == "spe" and (item or "").lower() == "choice scarf":
        facts.append(f"With Choice Scarf it moves at {int(value * 1.5)}.")
    whose = mon(who, plan.stat_target != "opponent")
    typed = [Fact("stat", f"{cap(whose)}'s stats: " + ", ".join(f"{STAT_NAMES[k]} {v}" for k, v in stats.items()) + ".",
                  {"stats": stats})]
    if plan.stat == "spe" and (item or "").lower() == "choice scarf":
        typed.append(Fact("stat", f"With Choice Scarf, {whose} moves at {int(value * 1.5)} Speed.",
                          {"speed": int(value * 1.5)}, role="why"))
    said = f"{cap(whose)}'s {STAT_NAMES[plan.stat]} is {value} at level {level}."
    return Verdict("stat", str(value), statement, facts, plain=said, typed=typed)


USAGE_FIELDS = {"item": "Items", "ability": "Abilities", "move": "Moves", "tera": "Tera Types", "spread": "Spreads",
                "teammates": "Teammates"}
ORDINALS = ["", "most common", "second most common", "third most common", "fourth most common", "fifth most common",
            "sixth most common", "seventh most common", "eighth most common", "ninth most common", "tenth most common"]


def _usual_set(target, plan, game):
    """'What does Raging Bolt usually run': the whole most common set, not just its item."""
    s = likely_set(target, plan.format_id)
    if not s:
        return None
    label = config.format_info(plan.format_id)["label"]
    moves = ", ".join(m for m, _ in s["moves"])
    statement = (f"The most common {s['name']} set in {label} is {s['item']} ({_pct(s['item_share'])}), {s['ability']}, "
                 f"{describe_spread(s, game)}, with {moves}.")
    facts = ["Move shares: " + ", ".join(f"{m} {_pct(share)}" for m, share in s["moves"]) + ".",
             f"{describe_spread(s, game)} is on {_pct(s['spread_share'])} of sets."]
    if s.get("tera") and game != "champions":
        facts.append(f"Most common Tera: {s['tera'][0]} ({_pct(s['tera'][1])}).")
    from metamatch.engine.packet import spread_words
    lad = f"ladder {s['name']}"
    unit = "stat points" if game == "champions" else "EVs"
    typed = [Fact("usage", f"{_pct(s['item_share'])} of {lad} sets hold {s['item']}.", {"item": s["item"],
                                                                                        "share": s["item_share"]}, role="why"),
             Fact("usage", f"The usual ability of {lad} is {s['ability']}.", {"ability": s["ability"]}),
             Fact("usage", "Move shares on " + f"{lad} sets: " + ", ".join(f"{m} {_pct(sh)}" for m, sh in s["moves"]) + ".",
                  {"moves": s["moves"]}, role="why"),
             Fact("usage", f"The most common spread, on {_pct(s['spread_share'])} of {lad} sets, is "
                           f"{spread_words(s['nature'], s['evs'], unit)}.", {"spread_share": s["spread_share"]},
                  detail=describe_spread(s, game))]
    if s.get("tera") and game != "champions":
        typed.append(Fact("usage", f"The most common Tera type on {lad} sets is {s['tera'][0]}, on {_pct(s['tera'][1])}.",
                          {"tera": s["tera"][0], "share": s["tera"][1]}))
    said = (f"Ladder {s['name']} most often runs {s['item']} and {s['ability']}, with "
            f"{_join([m for m, _ in s['moves']])}.")
    return Verdict("usage", s["item"] or s["name"], statement, facts, persona="builder", plain=said, typed=typed)


def _usage_rank(target, plan):
    """'Is Great Tusk still top 10': its usage rank this month and last, from MetaFlash's history (top 100)."""
    from metamatch import meta_pulse
    label = config.format_info(plan.format_id)["label"]
    board = meta_pulse.leaderboard(plan.format_id, n=100)
    if not board:
        return None
    row = next((r for r in board if to_id(r["name"]) == to_id(target)), None)
    if row is None:
        said = f"{target} is outside the top {len(board)} on the {label} ladder this month."
        typed = [Fact("usage", said, {"rank": None}, role="why")]
    else:
        said = f"{row['name']} is #{row['rank']} on the {label} ladder this month, on {row['usage']:.1f}% of teams."
        prev = row.get("prev_rank")
        if prev:
            move = ("up from" if prev > row["rank"] else "down from" if prev < row["rank"] else "the same as")
            said += f" That's {move} #{prev} last month."
        elif row.get("has_prev"):
            said += " It wasn't in last month's top 100."
        typed = [Fact("usage", said, {"rank": row["rank"], "usage": row["usage"], "prev_rank": prev}, role="why")]
    return Verdict("usage", str(row["rank"]) if row else "unranked", said, [said], persona="builder", plain=said,
                   typed=typed)


def solve_usage(plan, dex, game):
    target = plan.opponent or (plan.user["Forme"] if plan.user.get("Forme") else plan.user["Pokemon"])
    if plan.usage_field == "set":
        return _usual_set(target, plan, game)
    if plan.usage_field == "rank":
        return _usage_rank(target, plan)
    key, entry = chaos_entry(target, plan.format_id)
    if not entry:
        return None
    total = sum(entry.get("Abilities", {}).values()) or 1
    counts = entry.get(USAGE_FIELDS[plan.usage_field], {})
    everything = sorted(((k, v / total) for k, v in counts.items() if k and k != "nothing" and v > 0),
                        key=lambda x: x[1], reverse=True)
    ranked = everything[:3]
    if not ranked:
        return None

    def display(k):
        if plan.usage_field == "item":
            return dex.item_name(k) or k
        if plan.usage_field == "ability":
            return dex.ability_name(k) or k
        if plan.usage_field == "move":
            return dex.move_name(k) or k
        if plan.usage_field == "tera":
            return k.capitalize()
        if plan.usage_field == "spread":
            return spread_label(k, plan.format_id)
        return k

    label = config.format_info(plan.format_id)["label"]
    noun = {"item": "held item", "ability": "ability", "move": "move", "tera": "Tera type", "spread": "spread",
            "teammates": "teammate"}[plan.usage_field]
    top, share = ranked[0]
    facts = [f"Top {noun}s: " + ", ".join(f"{display(k)} {_pct(v)}" for k, v in ranked) + "."]
    lad = f"ladder {key}"
    unit = "of its teams" if plan.usage_field == "teammates" else f"of {lad} sets"

    def words(k):
        # Spreads in words for the model ("Jolly nature with 252 Attack..."), not "Jolly 252 Atk / 252 Spe"
        if plan.usage_field != "spread":
            return display(k)
        from metamatch.engine.packet import spread_words
        from metamatch.engine.sets import _parse_spread
        return spread_words(*_parse_spread(k), "stat points" if game == "champions" else "EVs")
    if plan.usage_field == "spread":
        # Spreads in words are long: one fact each
        top_facts = [Fact("usage", f"{_pct(v)} {unit} use {words(k)}.", {"field": "spread", "spread": display(k),
                                                                          "share": round(v, 3)}, role="why" if i < 2 else "context")
                     for i, (k, v) in enumerate(ranked)]
    else:
        top_facts = [Fact("usage", f"Top {noun}s, as a share {unit}: " + "; ".join(f"{words(k)} {_pct(v)}" for k, v in ranked)
                          + ".", {"field": plan.usage_field, "ranked": [(display(k), round(v, 3)) for k, v in ranked]},
                          role="why", detail=facts[0])]
    if plan.usage_option:
        # One named option: its own share and rank, with the top options for scale
        want = to_id(plan.usage_option)
        rank, hit = next(((i + 1, kv) for i, kv in enumerate(everything) if to_id(kv[0]) == want), (None, None))
        if hit is None:
            statement = f"{plan.usage_option} doesn't show up on {key} sets in {label}'s usage stats."
            return Verdict("usage", "0%", statement, facts, persona="builder",
                           plain=f"{plan.usage_option} doesn't show up on {lad} sets in {label}.", typed=top_facts)
        place = ORDINALS[rank] if rank < len(ORDINALS) else f"number {rank}"
        statement = (f"{plan.usage_option} is on {_pct(hit[1])} of {key} sets in {label}, "
                     f"the {place} {noun}." + ("" if rank == 1 else f" The most common is {display(top)} ({_pct(share)})."))
        said = (f"{plan.usage_option} is on {_pct(hit[1])} of {lad} sets, the {place} {noun}."
                + ("" if rank == 1 else f" The most common is {display(top)}, on {_pct(share)}."))
        return Verdict("usage", _pct(hit[1]), statement, facts, persona="builder", plain=said, typed=top_facts)
    if plan.usage_field == "teammates":
        statement = f"The most common teammate of {key} in {label} is {display(top)} (on {_pct(share)} of its teams)."
        facts = ["Top teammates (share of its teams): " + ", ".join(f"{display(k)} {_pct(v)}" for k, v in ranked) + "."]
        said = f"{display(top)} is the most common teammate of {lad}, on {_pct(share)} of its teams."
    else:
        statement = f"The most common {noun} on {key} in {label} is {display(top)} ({_pct(share)} of sets)."
        said = f"The most common {noun} on {lad} sets is {display(top)}, on {_pct(share)} of them."
    if plan.usage_field == "tera":
        # Smogon's recommendation first (what strong players advise), then the ladder (what players run)
        advice = _smogon_tera(plan, key)
        if advice:
            said = f"{advice} {said}"
            statement = f"{advice} {statement}"
            facts.insert(0, advice)
            top_facts = [Fact("usage", advice, {"field": "tera", "source": "smogon"}, role="why")] + top_facts
    # "What tera does my Hatterene have": the player's own set first, then what Smogon and the ladder run
    own_key = {"tera": "Tera Type", "item": "Item", "ability": "Ability"}.get(plan.usage_field)
    if own_key and plan.user is not None and plan.user_named and not plan.opponent and plan.user.get(own_key):
        value = plan.user[own_key]
        mine = f"Your {_user_name(plan.user)} runs {'Tera ' + value if plan.usage_field == 'tera' else value}."
        own_fact = Fact("set", mine, {"field": plan.usage_field, "value": value}, role="why")
        if re.search(r"\b(?:should|best|recommend\w*|better|ideal)\b", plan.query or "", re.I):
            # "What tera should my Gholdengo run": the recommendation leads, their own pick follows as context
            said, statement = f"{said} {mine}", f"{statement} {mine}"
            facts.append(mine)
            top_facts = top_facts + [own_fact]
        else:
            said, statement = f"{mine} {said}", f"{mine} {statement}"
            facts.insert(0, mine)
            top_facts = [own_fact] + top_facts
    return Verdict("usage", display(top), statement, facts, persona="builder", plain=said, typed=top_facts)


def _smogon_tera(plan, name):
    """'Smogon recommends Tera Ghost or Fairy on its Boots Pivot set.' For a team member, the Smogon set closest to
    the member's own; for any other Pokemon, up to two of Smogon's sets. '' when Smogon lists none."""
    from metamatch.engine import tera
    def either(types):
        return " or ".join([", ".join(types[:-1]), types[-1]]) if len(types) > 1 else types[0]
    mine = plan.user is not None and not plan.opponent and plan.user_named
    if mine:
        moves = [m["name"] for m in plan.user.get("Moves", []) if m.get("name")]
        best = tera.closest(name, plan.format_id, moves, plan.user.get("Item"))
        return f"Smogon recommends Tera {either(best[1])} on its {best[0]} set, the one closest to yours." if best else ""
    sets = tera.smogon(name, plan.format_id)[:2]
    if not sets:
        return ""
    parts = [f"Tera {either(types)} on its {set_name} set" for set_name, types in sets]
    return "Smogon recommends " + " and ".join(parts) + "."


def solve_speed_spread(plan, dex, game):
    """'What EVs does my X need to outspeed Y': the least Speed investment (and nature, if needed) that clears Y."""
    from metamatch.engine.speed_board import price, price_text, speed_curve
    if any(c.kind == "trick_room" for c in plan.situation):
        return None
    base = solve_speed(plan, dex, game)
    if not base or not base.speeds:
        return None
    us, them = base.speeds
    curve = speed_curve(plan.user, plan.format_id)
    if not curve:
        return None
    cost = price(curve, them + 1)
    me, name = _user_name(plan.user), base.other if plan.subject != "opponent" else base.subject
    if cost is None:
        statement = f"{me} can't reach {them + 1} Speed to outspeed {name}. {price_text(curve, cost)}."
    elif cost[0] == "own" and cost[1] <= curve["current"]:
        statement = f"{me} already outspeeds {name} ({them} Speed) with your spread ({us} Speed)."
        if cost[1] < curve["current"]:
            statement += f" {price_text(curve, cost)}."
    else:
        statement = f"To outspeed {name} ({them} Speed), {me} needs {them + 1} Speed: {price_text(curve, cost)}."
    facts = [f for f in base.facts if "Across all" not in f]
    facts.append(f"{me} runs {curve['current']} Spe {curve['unit']} now, with {max(curve['free'], 0)} {curve['unit']} unspent.")
    typed = [f for f in base.typed if "ladder sets" not in f.text]
    typed.append(Fact("set", f"Your {me} runs {curve['current']} Speed {curve['unit']} now, with "
                             f"{max(curve['free'], 0)} {curve['unit']} unspent.",
                      {"current": curve["current"], "free": curve["free"]}, role="why"))
    said = statement.replace(f"{me} ", f"Your {me} ", 1) if statement.startswith(me) else statement
    return Verdict("speed_spread", price_text(curve, cost, short=True), statement, facts, persona="builder",
                   subject=me, other=name, plain=said, typed=typed)


def _join(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""


def _stated_set(plan, dex, game):
    """The opponent's most common set with every detail the question states applied (item, ability, nature, EVs,
    Tera, boosts, moves), shaped like sets.likely_set so the Threat Board can use it. None without usage data."""
    s = likely_set(plan.opponent, plan.format_id)
    if not s or not plan.opp_overrides:
        return s
    spec = constraints.apply(calc_spec(s), plan.opp_overrides, dex, game)
    out = dict(s, nature=spec.get("nature", s["nature"]), evs=spec.get("evs", s["evs"]), item=spec.get("item"),
               ability=spec.get("ability", s.get("ability")))
    for key in ("teraType", "boosts", "ivs"):
        if spec.get(key):
            out[key] = spec[key]
    if plan.opp_overrides.get("moves"):
        out["moves"] = [(m, 1.0) for m in plan.opp_overrides["moves"]]
    if any(k in plan.opp_overrides for k in ("item", "nature", "evs", "max", "min", "uninvested", "no_speed_item")):
        # A stated spread or item has one Speed, not the ladder's spread of Speeds
        speed = mechanics.final_speed(calc_spec(out), game, _any_move([m for m, _ in out["moves"]], dex))
        out["speeds"], out["scarf_share"], out["booster_share"] = ([(speed, 1.0)] if speed else []), 0.0, 0.0
    return out


def solve_matchup(plan, dex, game):
    """'Does my Kingambit beat Gholdengo': the one on one between the named member and the opponent's set."""
    from metamatch.engine.threat_board import row_for_set
    member = plan.user
    row = row_for_set(plan.team or {"m": member}, _stated_set(plan, dex, game), plan.format_id)
    cell = row.cells.get(member["Pokemon"]) if row else None
    if not cell:
        return None
    me, name = _user_name(member), display_name(row.name)
    if to_id(member["Pokemon"]) == to_id(row.name):
        name = f"the opposing {name}"
    verb = {"win": "beats", "lose": "loses to"}.get(cell.verdict, "trades evenly with")
    statement = f"Your {me} {verb} {name} one on one."
    basis = "its most common set, with the details the question states" if plan.opp_overrides else "its most common set"
    facts = [f"Your {me} vs {name}: {cell.reason}."]
    others = [m for m in row.answers if m != member["Pokemon"]]
    if cell.verdict != "win":
        facts.append(f"Teammates that beat {name} one on one: {_join(others)}." if others
                     else f"No teammate beats {name} one on one either.")
    facts.append(f"{name[0].upper() + name[1:]} assumed on {basis}; switching, hazards and setup are not counted.")
    answer = {"win": "yes", "lose": "no"}.get(cell.verdict, "even")
    from metamatch.engine.facts import basis_fact, exchange_facts
    typed = exchange_facts(cell.exchange, member["Pokemon"], display_name(row.name), cell.verdict)
    for f in typed[1:]:
        if f.kind == "damage":
            f.role = "why"
    if cell.verdict != "win":
        typed.append(Fact("matchup", f"Teammates that beat {mon(display_name(row.name), False)} one on one: "
                                     f"{_join([mon(m, True) for m in others])}." if others else
                                     f"No teammate beats {mon(display_name(row.name), False)} one on one either.",
                          {"answers": others}))
    typed.append(basis_fact(display_name(row.name), basis))
    said = f"Your {me} {verb} {mon(display_name(row.name), False)} one on one."
    return Verdict("matchup", answer, statement, facts, persona="strategy", subject=me, other=name,
                   losers=[member["Pokemon"]] if cell.verdict == "lose" else [], members=[member["Pokemon"]],
                   plain=said, typed=typed)


def solve_checks(plan, dex, game):
    """'What checks X on my team': every member against X's most common set (or the set the question states),
    one on one (engine/threat_board.py)."""
    from metamatch.engine.threat_board import row_for_set
    row = row_for_set(plan.team, _stated_set(plan, dex, game), plan.format_id)
    if not row:
        return None
    name, answers, losses = display_name(row.name), row.answers, row.losses
    # A mirror ("what checks Kingambit" on a team with Kingambit) says whose copy is whose
    mine = lambda m: f"your {m}" if to_id(m) == to_id(row.name) else m  # noqa: E731
    them = f"the opposing {name}" if any(to_id(m) == to_id(row.name) for m in row.cells) else name
    if answers:
        statement = f"{_join([mine(m) for m in answers])} {'beats' if len(answers) == 1 else 'beat'} {them} one on one."
    else:
        statement = f"Nobody on your team beats {them} one on one."
    ohko = [m for m in losses if (row.cells[m].exchange or {}).get("to_be_koed") == 1]
    if ohko:
        statement += f" {them[0].upper() + them[1:]} OHKOs {_join([mine(m) for m in ohko])}."
    facts = [f"{mine(m)[0].upper() + mine(m)[1:]} vs {them}: {row.cells[m].reason}." for m in answers + losses]
    if row.checks_data:
        facts.append(f"Smogon's checks data also lists {_join(row.checks_data)} as "
                     f"{'a check' if len(row.checks_data) == 1 else 'checks'} to {name}.")
    basis = "its most common set, with the details the question states" if plan.opp_overrides else "its most common set"
    facts.append(f"{name} assumed on {basis}; switching, hazards and setup are not counted.")
    from metamatch.engine.facts import basis_fact, exchange_facts
    opp = mon(name, False)
    typed = []
    for m in answers + losses:
        for f in exchange_facts(row.cells[m].exchange, m, name, row.cells[m].verdict):
            # The model may explain the strongest answer's two hits; the rest are context
            if m == (answers or losses)[0] and f.kind == "damage":
                f.role = "why"
            typed.append(f)
    typed.append(basis_fact(name, basis))
    if answers:
        said = f"{cap(_join([mon(m, True) for m in answers]))} {'beats' if len(answers) == 1 else 'beat'} {opp} one on one."
    else:
        said = f"Nobody on your team beats {opp} one on one."
    if ohko:
        said += f" {cap(opp)} knocks out {_join([mon(m, True) for m in ohko])} in one hit."
    # Matchups are Oak's topic ("how do I beat X" and "what checks X" alike), as the chat's help cards say
    return Verdict("checks", ", ".join(answers) or "none", statement, facts, other=name, persona="strategy",
                   losers=losses, members=list(row.cells), plain=said, typed=typed)


ASK_VERBS = {"immune": ("is immune to {t} attacks", "are immune to {t} attacks"),
             "resist": ("resists {t} attacks", "resist {t} attacks"),
             "neutral": ("takes neutral damage from {t} attacks", "take neutral damage from {t} attacks"),
             "weak": ("is weak to {t} attacks", "are weak to {t} attacks")}
TYPE_NAMES = list(PROBE_MOVES)
# A move counts as one of the opponent's usual attacks when at least this share of its sets run it
USUAL_MOVE_SHARE = 0.2


def _group(mult):
    return "immune" if mult == 0 else "resist" if mult < 1 else "weak" if mult > 1 else "neutral"


def _taken(p, t, dex):
    """(multiplier, note) a team member takes from type `t`: its Damage From table, which counts immunity abilities,
    Air Balloon and damage scaling abilities; the note names what changed the plain type chart value."""
    mult = (p.get("Damage From") or {}).get(t.lower(), 1.0)
    chart = 1.0
    for d in p.get("Type", []):
        chart *= dex.type_chart.get(t, {}).get(d, 1.0)
    if mult == chart:
        return mult, ""
    item = p.get("Item") or ""
    via = item if t == "Ground" and mult == 0 and item.lower() == "air balloon" else (p.get("Mega Ability") or p.get("Ability"))
    return mult, f" via {via}" if via else ""


def _members(entries):
    return _join(f"{n} ({m:g}x{note})" for n, m, note in entries)


def _type_line(t, team, dex, label=None):
    """'Water: resisted by A (0.5x) and B (0.5x); weak: C (2x); neutral: D (1x)' plus the groups by name."""
    groups = {"immune": [], "resist": [], "neutral": [], "weak": []}
    for p in team.values():
        mult, note = _taken(p, t, dex)
        groups[_group(mult)].append((_user_name(p), mult, note))
    phrases = {"immune": ("is immune", "are immune"), "resist": ("resists it", "resist it"),
               "weak": ("is weak to it", "are weak to it"), "neutral": ("takes neutral damage", "take neutral damage")}
    parts = [f"{_members(groups[g])} {phrases[g][len(groups[g]) > 1]}" for g in ("immune", "resist", "weak", "neutral") if groups[g]]
    return f"{label or t}: " + "; ".join(parts) + ".", groups


def _type_fact(label, groups, why=True):
    """'Against Water attacks: your Venusaur and your Dragapult resist them; your Torkoal is weak to them.'"""
    words = {"immune": ("is immune", "are immune"), "resist": ("resists them", "resist them"),
             "weak": ("is weak to them", "are weak to them"), "neutral": ("takes normal damage", "take normal damage")}
    parts = []
    for g in ("immune", "resist", "weak", "neutral"):
        names = [n for n, _, _ in groups[g]]
        if names:
            parts.append(f"{_join([mon(n, True) for n in names])} {words[g][len(names) > 1]}")
    return Fact("type", f"Against {label} attacks: " + "; ".join(parts) + ".",
                {"attack": label, "groups": {g: [n for n, _, _ in e] for g, e in groups.items()}},
                role="why" if why else "context")


def _asked(groups, ask):
    """Names in the asked group; 'resist' also counts immunities."""
    keys = ("immune", "resist") if ask == "resist" else (ask,)
    return [n for k in keys for n, _, _ in groups[k]]


def _usual_attacks(name, format_id, dex):
    """[(move, type)] for the opponent's damaging moves on at least USUAL_MOVE_SHARE of its sets, one per type."""
    s = likely_set(name, format_id)
    if not s:
        return None, []
    out, seen = [], set()
    _, entry = chaos_entry(name, format_id)
    total = sum((entry or {}).get("Abilities", {}).values()) or 1
    moves = sorted(((dex.move_name(k), v / total) for k, v in (entry or {}).get("Moves", {}).items() if dex.move_name(k)),
                   key=lambda x: x[1], reverse=True) if entry else [(m, share) for m, share in s["moves"]]
    for move, share in moves:
        data = dex.move(move) or {}
        if share < USUAL_MOVE_SHARE or data.get("category") == "Status" or not data.get("type"):
            continue
        if data["type"] not in seen:
            seen.add(data["type"])
            out.append((move, data["type"]))
    return s["name"], out


def solve_team_type(plan, dex, game):
    """Which members are weak to, neutral to, resist or are immune to a type, to an opponent's usual attacks, or
    (with neither named) the team's shared weaknesses. Straight from the type chart and abilities; no calc."""
    team = plan.team
    ask = plan.team_ask
    if plan.atk_type:
        line, groups = _type_line(plan.atk_type, team, dex)
        names = _asked(groups, ask)
        one, many = ASK_VERBS[ask]
        phrase = (one if len(names) == 1 else many).format(t=plan.atk_type)
        statement = f"{_join(names)} {phrase}." if names else f"Nobody on your team {one.format(t=plan.atk_type)}."
        if ask == "resist" and groups["immune"]:
            statement += f" ({_join(n for n, _, _ in groups['immune'])} {'is' if len(groups['immune']) == 1 else 'are'} immune.)"
        said = (f"{cap(_join([mon(n, True) for n in names]))} {phrase}." if names
                else f"Nobody on your team {one.format(t=plan.atk_type)}.")
        return Verdict("team_type", ", ".join(names) or "none", statement, [line],
                       groups={g: [n for n, _, _ in entries] for g, entries in groups.items()},
                       plain=said, typed=[_type_fact(plan.atk_type, groups)])
    if plan.opponent:
        name, attacks = _usual_attacks(plan.opponent, plan.format_id, dex)
        if not attacks:
            return None
        name = display_name(name)
        facts, safe, typed = [], None, []
        for move, t in attacks:
            line, groups = _type_line(t, team, dex, label=f"{move} ({t})")
            facts.append(line)
            typed.append(_type_fact(f"{mon(name, False)}'s {move} ({t})", groups))
            got = set(_asked(groups, "resist"))
            safe = got if safe is None else safe & got
        order = [_user_name(p) for p in team.values()]
        safe = [n for n in order if n in (safe or set())]
        listed = _join(f"{m} ({t})" for m, t in attacks)
        statement = (f"{_join(safe)} {'resists' if len(safe) == 1 else 'resist'} all of {name}'s usual attacks ({listed})." if safe else
                     f"Nobody on your team resists all of {name}'s usual attacks ({listed}).")
        facts.append(f"{name}'s usual attacks are its damaging moves on at least {_pct(USUAL_MOVE_SHARE)} of sets.")
        said = (f"{cap(_join([mon(n, True) for n in safe]))} {'resists' if len(safe) == 1 else 'resist'} all of "
                f"{mon(name, False)}'s usual attacks." if safe else
                f"Nobody on your team resists all of {mon(name, False)}'s usual attacks.")
        return Verdict("team_type", ", ".join(safe) or "none", statement, facts, other=name, plain=said, typed=typed)
    from metamatch.engine.briefing import team_weaknesses
    shared = team_weaknesses(team)
    resisted = {t for p in team.values() for t in TYPE_NAMES if (p.get("Damage From") or {}).get(t.lower(), 1.0) < 1}
    unresisted = [t for t in TYPE_NAMES if t not in resisted]
    weak_types = [w.split(":")[0] for w in shared]
    statement = (f"Your team's shared weaknesses are {_join(weak_types)}." if weak_types else
                 "No type hits two or more of your Pokemon super effectively without as many of them resisting it.")
    facts = list(shared)
    if unresisted:
        facts.append(f"Nobody on your team resists {_join(unresisted)}.")
    facts.append("A shared weakness hits at least two members super effectively and more members than resist it.")
    typed = []
    for t in weak_types:
        _, groups = _type_line(t, team, dex)
        typed.append(_type_fact(t, groups))
    if unresisted:
        typed.append(Fact("type", f"Nobody on your team resists {_join(unresisted)} attacks.", {"unresisted": unresisted}))
    return Verdict("team_type", ", ".join(weak_types) or "none", statement, facts, plain=statement, typed=typed)


def solve_rules(plan, dex, game):
    """What the named abilities, items, moves or weather do, from Showdown's text, and what that means for the team.
    Yes or no rules questions the data settles exactly (a move flag, a Mold Breaker bypass, a weather or ability
    multiplier) get that answer first."""
    from metamatch.engine import rules
    from metamatch.team import ABILITY_IMMUNITIES, ABILITY_SCALES
    named = [(k, n) for k, n in plan.rules if rules.entry(k, n)]
    if not named:
        return None
    decided = rules.yes_no(plan.query, named, ABILITY_SCALES, ABILITY_IMMUNITIES)
    facts = []
    for kind, name in named:
        line = rules.text_line(kind, name, full=True)
        if line:
            facts.append(line)
    facts += rules.team_lines(named, plan.team)
    # Rule text is Showdown's own wording; the team lines say which of the trainer's members it touches
    from metamatch.engine.packet import first_sentences
    typed = [Fact("rule", first_sentences(f), {"source": "Showdown"}, role="why" if i < 2 else "context", detail=f)
             for i, f in enumerate(facts)]
    if decided:
        answer, reason = decided
        return Verdict("rules", answer, f"{answer.capitalize()}. {reason}", facts,
                       plain=f"{answer.capitalize()}. {reason}", typed=typed)
    effect = rules.weather_effect(named)
    if effect:
        return Verdict("rules", effect, effect, facts, plain=effect, typed=typed)
    kind, name = named[0]
    statement = rules.text_line(kind, name)
    return Verdict("rules", name, statement, [f for f in facts if f != rules.text_line(kind, name, full=True)
                                               or rules.entry(kind, name).get("desc")], plain=statement, typed=typed)


def solve_learn(plan, dex, game):
    """'Can Gholdengo learn Shell Smash': whether the Pokemon can have the move in this format (engine/learnsets.py,
    Champions' own movepools there), and how often ladder sets run it when it can."""
    from metamatch.engine.learnsets import learns
    who = plan.user if plan.user is not None and plan.user_named else None
    name = (who.get("Forme") or who["Pokemon"]) if who else plan.opponent
    if not name or not plan.move:
        return None
    pool = learns(name, plan.format_id)
    if not pool:
        return None
    label = config.format_info(plan.format_id)["label"]
    can = to_id(plan.move) in pool
    said = f"{'Yes' if can else 'No'}: {name} {'can' if can else 'can’t'} learn {plan.move} in {label}."
    said = said.replace("’", "'")
    typed = [Fact("learnset", said, {"pokemon": name, "move": plan.move, "learns": can}, role="why")]
    if can:
        key, entry = chaos_entry(name, plan.format_id)
        if entry:
            total = sum(entry.get("Abilities", {}).values()) or 1
            share = next((v / total for k, v in (entry.get("Moves") or {}).items() if to_id(k) == to_id(plan.move)), 0)
            typed.append(Fact("usage", f"{round(share * 100)}% of ladder {key} sets run it.", {"share": round(share, 3)}))
    return Verdict("learn", "yes" if can else "no", said, [f.text for f in typed], persona="mechanics", plain=said,
                   typed=typed)


SOLVERS = {"speed": solve_speed, "ko": solve_ko, "damage": solve_damage, "type": solve_type, "stat": solve_stat,
           "usage": solve_usage, "checks": solve_checks, "team_type": solve_team_type, "rules": solve_rules,
           "speed_spread": solve_speed_spread, "matchup": solve_matchup, "learn": solve_learn}


def solve(plan):
    """Verdict for a plan, or None when the question is open ended or the engine lacks data."""
    solver = SOLVERS.get(plan.intent)
    if solver is None:
        # Team strategy answers (win condition, leads, threats, game plan) live with the Coach Guide
        from metamatch.engine.team_answers import SOLVERS as TEAM_SOLVERS
        from metamatch.engine.build_answers import SOLVERS as BUILD_SOLVERS
        from metamatch.engine.archetypes import SOLVERS as ARCHETYPE_SOLVERS
        solver = TEAM_SOLVERS.get(plan.intent) or BUILD_SOLVERS.get(plan.intent) or ARCHETYPE_SOLVERS.get(plan.intent)
    dex = dex_for_format(plan.format_id)
    if not solver or not dex:
        return None
    try:
        verdict = solver(plan, dex, config.format_game(plan.format_id))
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        print(f"Solver {plan.intent} failed: {e}")
        return None
    # Rules and team type questions name items and moves as subjects, not as set details for a matchup
    if verdict and plan.intent not in ("usage", "rules", "team_type", "win", "lead", "threats", "gameplan", "tera",
                                              "member", "compare", "teammate", "roles", "score", "archetype", "weather",
                                              "speed_tiers", "audit"):
        # Stated versus assumed: say what came from the question, and what the engine could not count
        for who, details in (("your Pokemon", plan.user_overrides), ("the opponent", plan.opp_overrides)):
            if constraints.summary(details):
                verdict.facts.append(f"Stated in the question for {who}: {constraints.summary(details)}.")
        if plan.unhandled:
            verdict.statement += f" This does not count {', '.join(plan.unhandled)}."
    return verdict

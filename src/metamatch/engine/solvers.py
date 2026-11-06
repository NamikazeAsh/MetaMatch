"""
Answers planned questions directly from the engine (calc, dex, chaos usage data).
Each solver returns a Verdict: the short answer, a templated sentence stating it, and
the supporting facts. The LLM only ever explains a Verdict, it never produces one.
"""
import re
from dataclasses import dataclass, field

from metamatch import config
from metamatch.engine import calc, constraints, mechanics
from metamatch.engine.dex import dex_for_format
from metamatch.engine.sets import calc_spec, chaos_entry, describe_spread, likely_set

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


def _pct(x):
    return f"{x * 100:.0f}%"


def user_spec(p, game, details=None, dex=None):
    """A team member as a calc_server Pokemon spec (Champions uses stat points as 'evs'), with any set
    details the question states for it applied."""
    raw = p.get("SP") if game == "champions" else p.get("EVs")
    spec = {"name": p.get("Forme") or p["Pokemon"],
            "evs": {CALC_STAT_KEYS[k]: v for k, v in (raw or {}).items() if k in CALC_STAT_KEYS}}
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


def _calc_field(plan, defender_side=None):
    """calc Field for the stated weather and terrain, plus screens on the defender's side."""
    f = dict(plan.conditions)
    flags = set(plan.screens.get("defender", ())) | set(plan.screens.get(defender_side, ()))
    if defender_side and flags:
        f["defenderSide"] = {flag: True for flag in flags}
    return f or None


def _spread_text(spec, game):
    return describe_spread({"nature": spec.get("nature", "Serious"), "evs": spec.get("evs") or {}}, game)


def _spread_label(plan, s, spec, game):
    """How the opponent's spread was chosen, for the verdict sentence (closing bracket added by the caller)."""
    if constraints.stated_spread(plan.opp_overrides):
        return f"running the stated spread ({_spread_text(spec, game)}"
    return f"running its most common spread ({describe_spread(s, game) if s else 'an uninvested spread'}"


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


def solve_speed(plan, dex, game):
    p = plan.user
    name, spec, s = _opponent(plan, dex)
    if not name:
        return None
    move = _any_move([m["name"] for m in p.get("Moves", [])], dex)
    mine = _mine(plan, dex, game)
    stated = plan.opp_overrides.get("item")
    if plan.raw_stats:
        stated = None
        us = (_stats(game, mine, move) or {}).get("spe")
        them = (_stats(game, spec, move) or {}).get("spe")
    else:
        us = mechanics.final_speed(mine, game, move, _calc_field(plan))
        them = mechanics.final_speed(mechanics.opponent_speed_spec(spec, stated), game, move, _calc_field(plan))
    if not us or not them:
        return None
    name = display_name(name)
    order = "yes" if us > them else "no" if us < them else "tie"
    verb = {"yes": "outspeeds", "no": "is slower than", "tie": "speed ties with"}[order]
    label = _spread_label(plan, s, spec, game)
    held = f" with {mine['item']}" if mine.get("item") and us != (_stats(game, mine, move) or {}).get("spe") else ""
    theirs = f" @ {stated}" if stated in mechanics.OPP_SPEED_ITEMS else ""
    statement = f"{_user_name(p)} ({us} Speed{held}) {verb} {name}{theirs} {label}, {them} Speed)."
    # The answer is about the question's subject and comparison: "Does Dragapult outspeed my Tusk?"
    subject, other, faster = _user_name(p), name, us > them
    if plan.subject == "opponent":
        subject, other, faster = name, _user_name(p), them > us
        verb = {"yes": "is slower than", "no": "outspeeds", "tie": "speed ties with"}[order]
        statement = (f"{name}{theirs} {label}, {them} Speed) {verb} "
                     f"{_user_name(p)} ({us} Speed{held}).")
    slower = (them > us) if plan.subject == "user" else (us > them)
    answer = "tie" if us == them else ("yes" if (slower if plan.speed_ask == "slower" else faster) else "no")
    told = constraints.stated_spread(plan.opp_overrides)
    which = "the stated spread" if told else "its most common spread"
    facts = [f"{_user_name(p)} Speed: {us}.", f"{name} Speed with {which}: {them}."]
    if s and s["speeds"] and not told:
        faster = sum(share for spe, share in s["speeds"] if spe < us)
        tied = sum(share for spe, share in s["speeds"] if spe == us)
        facts.append(f"Across all {name} sets on the ladder, {_user_name(p)} outspeeds {_pct(faster)} and ties {_pct(tied)}.")
    if s and s.get("item") == "Choice Scarf" and "item" not in plan.opp_overrides and not plan.opp_overrides.get("no_speed_item"):
        facts.append(f"{_pct(s['item_share'])} of {name} carry Choice Scarf, reaching {int(them * 1.5)} Speed.")
    # Contradiction checks read the answer as "subject is faster than other", inverted when ask_slower
    return Verdict("speed", answer, statement, facts, subject=subject, other=other,
                   ask_slower=plan.speed_ask == "slower", subject_is_player=plan.subject != "opponent")


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
    f = _calc_field(plan, defender_side)
    results = calc.calculate_many([{"game": game, "attacker": attacker[1], "defender": defender[1], "move": m,
                                    **({"field": f} if f else {})} for m in moves])
    scored = [(m, r) for m, r in zip(moves, results) if r]
    if not scored:
        return None
    move, result = max(scored, key=lambda x: x[1]["percent"][1])
    return attacker[0], defender[0], move, result, s, attacker[1], defender[1]


def _ko_hits(ko_text):
    """(hits, guaranteed) from calc text like 'guaranteed 2HKO' or '31.6% chance to OHKO'."""
    m = re.search(r"(guaranteed|chance to) (O|\d+)HKO", ko_text or "")
    if not m:
        return None, False
    return (1 if m.group(2) == "O" else int(m.group(2))), m.group(1) == "guaranteed"


def solve_ko(plan, dex, game):
    attack = _attack(plan, dex, game)
    if not attack:
        return None
    att, dfn, move, r, s, att_spec, dfn_spec = attack
    lo, hi = r["percent"]
    answer, effect = mechanics.ko_answer(r, plan.ko_hits, att_spec, dfn_spec, move)
    if plan.survive:
        answer = {"yes": "no", "no": "yes", "sometimes": "sometimes"}[answer]
        outcome = {"yes": f"{dfn} survives", "no": f"{dfn} does not survive", "sometimes": f"{dfn} survives only some rolls"}[answer]
    else:
        n = "OHKO" if plan.ko_hits == 1 else f"{plan.ko_hits}HKO"
        outcome = {"yes": f"it {n}s", "no": f"it does not {n}", "sometimes": f"it {n}s only on some damage rolls"}[answer]
    held = f" (it survives a full HP hit at 1 HP with {effect})" if effect and effect != "Disguise" else         " (Disguise takes the first hit)" if effect else ""
    statement = f"{att}'s {move} does {lo}-{hi}% to {dfn}{held}, so {outcome}."
    facts = [f"Calc: {r['desc']}"] if r["desc"] else []
    if effect:
        facts.append(f"{dfn} at full HP keeps {effect}; hazards or earlier chip would remove it.")
    if s and not constraints.stated_spread(plan.opp_overrides) and "item" not in plan.opp_overrides:
        facts.append(f"{s['name']} assumed on its most common set: {describe_spread(s, game)} @ {s['item']}, {s['ability']}.")
    return Verdict("ko", answer, statement, facts, subject=att, other=dfn, survive=plan.survive, hits=plan.ko_hits)


def solve_damage(plan, dex, game):
    attack = _attack(plan, dex, game)
    if not attack:
        return None
    att, dfn, move, r, s, _, _ = attack
    lo, hi = r["percent"]
    ko = f" ({r['ko']})" if r["ko"] else ""
    statement = f"{att}'s {move} does {lo}-{hi}% to {dfn}{ko}."
    facts = [f"Calc: {r['desc']}"] if r["desc"] else []
    if s and not constraints.stated_spread(plan.opp_overrides) and "item" not in plan.opp_overrides:
        facts.append(f"{s['name']} assumed on its most common set: {describe_spread(s, game)} @ {s['item']}, {s['ability']}.")
    return Verdict("damage", f"{lo}-{hi}%", statement, facts)


def solve_type(plan, dex, game):
    chart = dex.type_chart
    t = plan.atk_type
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
    return Verdict("type", answer, statement, facts)


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
    return Verdict("stat", str(value), statement, facts)


USAGE_FIELDS = {"item": "Items", "ability": "Abilities", "move": "Moves", "tera": "Tera Types", "spread": "Spreads"}


def solve_usage(plan, dex, game):
    target = plan.opponent or (plan.user["Forme"] if plan.user.get("Forme") else plan.user["Pokemon"])
    key, entry = chaos_entry(target, plan.format_id)
    if not entry:
        return None
    total = sum(entry.get("Abilities", {}).values()) or 1
    counts = entry.get(USAGE_FIELDS[plan.usage_field], {})
    ranked = sorted(((k, v / total) for k, v in counts.items() if k and k != "nothing"), key=lambda x: x[1], reverse=True)[:3]
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
        return k

    label = config.format_info(plan.format_id)["label"]
    noun = {"item": "held item", "ability": "ability", "move": "move", "tera": "Tera type", "spread": "spread"}[plan.usage_field]
    top, share = ranked[0]
    statement = f"The most common {noun} on {key} in {label} is {display(top)} ({_pct(share)} of sets)."
    facts = [f"Top {noun}s: " + ", ".join(f"{display(k)} {_pct(v)}" for k, v in ranked) + "."]
    return Verdict("usage", display(top), statement, facts, persona="builder")


def _join(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""


def solve_checks(plan, dex, game):
    """'What checks X on my team': every member against X's most common set, one on one (engine/threat_board.py)."""
    from metamatch.engine.threat_board import threat_row
    row = threat_row(plan.team, plan.opponent, plan.format_id)
    if not row:
        return None
    name, answers, losses = display_name(row.name), row.answers, row.losses
    if answers:
        statement = f"{_join(answers)} {'beats' if len(answers) == 1 else 'beat'} {name} one on one."
    else:
        statement = f"Nobody on your team beats {name} one on one."
    ohko = [m for m in losses if (row.cells[m].exchange or {}).get("to_be_koed") == 1]
    if ohko:
        statement += f" {name} OHKOs {_join(ohko)}."
    facts = [f"{m} vs {name}: {row.cells[m].reason}." for m in answers + losses]
    if row.checks_data:
        facts.append(f"Smogon's checks data also lists {_join(row.checks_data)} as checks to {name}.")
    facts.append(f"{name} assumed on its most common set; switching, hazards and setup are not counted.")
    return Verdict("checks", ", ".join(answers) or "none", statement, facts, other=name,
                   losers=losses, members=list(row.cells))


SOLVERS = {"speed": solve_speed, "ko": solve_ko, "damage": solve_damage,
           "type": solve_type, "stat": solve_stat, "usage": solve_usage, "checks": solve_checks}


def solve(plan):
    """Verdict for a plan, or None when the question is open ended or the engine lacks data."""
    solver = SOLVERS.get(plan.intent)
    dex = dex_for_format(plan.format_id)
    if not solver or not dex:
        return None
    try:
        verdict = solver(plan, dex, config.format_game(plan.format_id))
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        print(f"Solver {plan.intent} failed: {e}")
        return None
    if verdict and plan.intent != "usage":
        # Stated versus assumed: say what came from the question, and what the engine could not count
        for who, details in (("your Pokemon", plan.user_overrides), ("the opponent", plan.opp_overrides)):
            if constraints.summary(details):
                verdict.facts.append(f"Stated in the question for {who}: {constraints.summary(details)}.")
        if plan.unhandled:
            verdict.statement += f" This does not count {', '.join(plan.unhandled)}."
    return verdict

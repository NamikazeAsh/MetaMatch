"""
Answers planned questions directly from the engine (calc, dex, chaos usage data).
Each solver returns a Verdict: the short answer, a templated sentence stating it, and
the supporting facts. The LLM only ever explains a Verdict, it never produces one.
"""
import re
from dataclasses import dataclass, field

from metamatch import config
from metamatch.engine import calc
from metamatch.engine.dex import dex_for_format, to_id
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


def _pct(x):
    return f"{x * 100:.0f}%"


def user_spec(p, game):
    """A team member as a calc_server Pokemon spec (Champions uses stat points as 'evs')."""
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
    return spec


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
    overrides = plan.opp_overrides
    for key in ("item", "ability", "nature"):
        if overrides.get(key):
            spec[key] = overrides[key]
    if overrides.get("evs"):
        spec["evs"] = {k: overrides["evs"].get(k, 0) for k in ("hp", "atk", "def", "spa", "spd", "spe")}
    return name, spec, s


def _stats(game, spec, move):
    r = calc.calculate({"game": game, "attacker": spec, "defender": spec, "move": move})
    return r["attacker_stats"] if r else None


def _any_move(spec_moves, dex):
    """A move that exists in this game's dex, for stat only calc requests."""
    for m in spec_moves:
        if dex.move_name(m):
            return dex.move_name(m)
    return next(iter(dex.move_data))


def _user_name(p):
    return f"{p['Pokemon']} (Mega {p['Forme']})" if p.get("Forme") else p["Pokemon"]


def solve_speed(plan, dex, game):
    p = plan.user
    name, spec, s = _opponent(plan, dex)
    if not name:
        return None
    move = _any_move([m["name"] for m in p.get("Moves", [])], dex)
    us = (_stats(game, user_spec(p, game), move) or {}).get("spe")
    them = (_stats(game, spec, move) or {}).get("spe")
    if not us or not them:
        return None
    answer = "yes" if us > them else "no" if us < them else "tie"
    verb = {"yes": "outspeeds", "no": "is slower than", "tie": "speed ties with"}[answer]
    spread = describe_spread(s, game) if s else "an uninvested spread"
    statement = f"{_user_name(p)} ({us} Speed) {verb} {name} running its most common spread ({spread}, {them} Speed)."
    facts = [f"{_user_name(p)} Speed: {us}.", f"{name} Speed with its most common spread: {them}."]
    if s and s["speeds"]:
        faster = sum(share for spe, share in s["speeds"] if spe < us)
        tied = sum(share for spe, share in s["speeds"] if spe == us)
        facts.append(f"Across all {name} sets on the ladder, {_user_name(p)} outspeeds {_pct(faster)} and ties {_pct(tied)}.")
    if (p.get("Item") or "").lower() == "choice scarf":
        facts.append(f"Holding Choice Scarf, {_user_name(p)} actually reaches {int(us * 1.5)} Speed.")
    if s and s.get("item") == "Choice Scarf":
        facts.append(f"{_pct(s['item_share'])} of {name} carry Choice Scarf, reaching {int(them * 1.5)} Speed.")
    return Verdict("speed", answer, statement, facts)


def _attack(plan, dex, game):
    """Runs the calc for the planned attack. Returns (attacker name, defender name, move, result, opp set)."""
    p = plan.user
    name, opp_spec, s = _opponent(plan, dex)
    if not name:
        return None
    mine = user_spec(p, game) if p else None
    if plan.attacker == "opponent" or not p:
        attacker, defender = (name, opp_spec), ((_user_name(p), mine) if p else None)
        moves = [plan.move] if plan.move else [m for m, _ in (s or {}).get("moves", [])]
    else:
        attacker, defender = (_user_name(p), mine), (name, opp_spec)
        moves = [plan.move] if plan.move else [m["name"] for m in p.get("Moves", []) if m.get("category") != "Status"]
    if not defender or not moves:
        return None
    results = calc.calculate_many([{"game": game, "attacker": attacker[1], "defender": defender[1], "move": m} for m in moves])
    scored = [(m, r) for m, r in zip(moves, results) if r]
    if not scored:
        return None
    move, result = max(scored, key=lambda x: x[1]["percent"][1])
    return attacker[0], defender[0], move, result, s


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
    att, dfn, move, r, s = attack
    lo, hi = r["percent"]
    if plan.ko_hits == 1:
        answer = "yes" if lo >= 100 else "no" if hi < 100 else "sometimes"
    else:
        hits, sure = _ko_hits(r["ko"])
        if hits is None or hits > plan.ko_hits:
            answer = "no"
        else:
            answer = "yes" if hits < plan.ko_hits or sure else "sometimes"
    if plan.survive:
        answer = {"yes": "no", "no": "yes", "sometimes": "sometimes"}[answer]
        outcome = {"yes": f"{dfn} survives", "no": f"{dfn} does not survive", "sometimes": f"{dfn} survives only some rolls"}[answer]
    else:
        n = "OHKO" if plan.ko_hits == 1 else f"{plan.ko_hits}HKO"
        outcome = {"yes": f"it {n}s", "no": f"it does not {n}", "sometimes": f"it {n}s only on some damage rolls"}[answer]
    statement = f"{att}'s {move} does {lo}-{hi}% to {dfn}, so {outcome}."
    facts = [f"Calc: {r['desc']}"] if r["desc"] else []
    if s and not plan.opp_overrides:
        facts.append(f"{s['name']} assumed on its most common set: {describe_spread(s, game)} @ {s['item']}, {s['ability']}.")
    return Verdict("ko", answer, statement, facts)


def solve_damage(plan, dex, game):
    attack = _attack(plan, dex, game)
    if not attack:
        return None
    att, dfn, move, r, s = attack
    lo, hi = r["percent"]
    ko = f" ({r['ko']})" if r["ko"] else ""
    statement = f"{att}'s {move} does {lo}-{hi}% to {dfn}{ko}."
    facts = [f"Calc: {r['desc']}"] if r["desc"] else []
    if s and not plan.opp_overrides:
        facts.append(f"{s['name']} assumed on its most common set: {describe_spread(s, game)} @ {s['item']}, {s['ability']}.")
    return Verdict("damage", f"{lo}-{hi}%", statement, facts)


def solve_type(plan, dex, game):
    chart = dex.type_chart
    t = plan.atk_type
    # The question is about the named team member, else a named opponent, else the only team member
    if plan.user is not None and (plan.user_named or not plan.opponent):
        p = plan.user
        name, types, spec = _user_name(p), p.get("Type", []), user_spec(p, game)
        ability = p.get("Mega Ability") or p.get("Ability")
    else:
        name, spec, s = _opponent(plan, dex)
        if not name:
            return None
        types, ability = dex.species(name)["types"], spec.get("ability")
    mult = 1.0
    for d in types:
        mult *= chart.get(t, {}).get(d, 1.0)
    via = ""
    probe = PROBE_MOVES.get(t)
    if mult > 0 and probe and dex.move_name(probe):
        r = calc.calculate({"game": game, "attacker": {"name": "Garchomp"}, "defender": spec, "move": probe})
        if r and r["range"][1] == 0:
            mult, via = 0.0, f" thanks to {ability}" if ability else ""
    answer = "immune" if mult == 0 else "resists" if mult < 1 else "weak" if mult > 1 else "neutral"
    phrase = {"immune": f"is immune to {t} attacks{via}", "resists": f"resists {t} attacks ({mult:g}x)",
              "weak": f"is weak to {t} attacks ({mult:g}x)", "neutral": f"takes neutral damage from {t} attacks (1x)"}[answer]
    statement = f"{name} ({'/'.join(types)}{', ' + ability if ability else ''}) {phrase}."
    facts = [f"{t} vs {d}: {chart.get(t, {}).get(d, 1.0):g}x." for d in types]
    return Verdict("type", answer, statement, facts)


def solve_stat(plan, dex, game):
    p = plan.user
    move = _any_move([m["name"] for m in p.get("Moves", [])], dex)
    stats = _stats(game, user_spec(p, game), move)
    if not stats:
        return None
    value = stats[plan.stat]
    level = 50 if game == "champions" else 100
    statement = f"{_user_name(p)}'s {STAT_NAMES[plan.stat]} stat is {value} at level {level}."
    facts = [f"All stats: " + ", ".join(f"{STAT_NAMES[k]} {v}" for k, v in stats.items()) + "."]
    if plan.stat == "spe" and (p.get("Item") or "").lower() == "choice scarf":
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


SOLVERS = {"speed": solve_speed, "ko": solve_ko, "damage": solve_damage,
           "type": solve_type, "stat": solve_stat, "usage": solve_usage}


def solve(plan):
    """Verdict for a plan, or None when the question is open ended or the engine lacks data."""
    solver = SOLVERS.get(plan.intent)
    dex = dex_for_format(plan.format_id)
    if not solver or not dex:
        return None
    try:
        return solver(plan, dex, config.format_game(plan.format_id))
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        print(f"Solver {plan.intent} failed: {e}")
        return None

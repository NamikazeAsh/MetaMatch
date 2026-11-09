"""
What a member's ability does for the game plan, in one line, measured with the calc where it can be.

The rules restate Pokemon Showdown's ability text (data/text/abilities.ts, MIT licensed). Numbers come from
@smogon/calc against the format's 12 most used Pokemon (the same threats the team engine lines use) and the top
25's ladder Speeds:
  * a situation the ability waits for (Supreme Overlord with teammates down, Moxie after a KO, Speed Boost after a
    turn, Guts once Flame Orb burns it) is calculated with and without that situation
  * an always on damage ability (Sharpness, Huge Power, Adaptability...) is calculated with and without the ability
A measured line only appears when the number actually moves. Weather and terrain abilities belong to the team
engines in synergy.py, so they're left out here.
"""
from dataclasses import dataclass

from metamatch import config
from metamatch.engine import calc, mechanics
from metamatch.engine.dex import dex_for_format

NEUTRAL = "Run Away"          # no effect on damage or Speed, for the "without it" numbers
ALLIES_DOWN = 3
STAT_WORDS = {"atk": "Attack", "def": "Defense", "spa": "Special Attack", "spd": "Special Defense", "spe": "Speed"}

AFTER_KO = {"Moxie": "atk", "Chilling Neigh": "atk", "As One (Glastrier)": "atk", "Grim Neigh": "spa",
            "As One (Spectrier)": "spa", "Soul-Heart": "spa", "Beast Boost": None}   # None: its highest stat
PASSIVE = {"Huge Power", "Pure Power", "Adaptability", "Sheer Force", "Tough Claws", "Technician", "Sharpness",
           "Iron Fist", "Strong Jaw", "Mega Launcher", "Punk Rock", "Transistor", "Dragon's Maw", "Rocky Payload",
           "Gorilla Tactics", "Hustle", "Steelworker", "Steely Spirit", "Water Bubble", "Aerilate", "Pixilate",
           "Refrigerate", "Galvanize", "Tinted Lens", "Reckless", "Sword of Ruin", "Beads of Ruin", "Neuroforce",
           "Fairy Aura", "Dark Aura", "Scrappy", "Mind's Eye", "Protean", "Libero"}
STATUS_BOOST = {"Guts": {"Flame Orb": "brn", "Toxic Orb": "tox"}, "Toxic Boost": {"Toxic Orb": "tox"},
                "Flare Boost": {"Flame Orb": "brn"}}
ORB_WORDS = {"brn": "burns", "tox": "poisons"}
CONTRARY = {"Leaf Storm": {"spa": 2}, "Overheat": {"spa": 2}, "Draco Meteor": {"spa": 2}, "Fleur Cannon": {"spa": 2},
            "Psycho Boost": {"spa": 2}, "Make It Rain": {"spa": 1}, "Superpower": {"atk": 1, "def": 1}}
SINGLE_USE = {"White Herb", "Mental Herb", "Power Herb", "Focus Sash", "Booster Energy", "Electric Seed",
              "Grassy Seed", "Psychic Seed", "Misty Seed", "Air Balloon", "Red Card", "Eject Button", "Eject Pack",
              "Weakness Policy", "Throat Spray", "Room Service", "Adrenaline Orb", "Blunder Policy"}

# Status moves that never target the opposing Pokemon, so Prankster's Dark type immunity doesn't touch them
NO_TARGET = {"Reflect", "Light Screen", "Aurora Veil", "Stealth Rock", "Spikes", "Toxic Spikes", "Sticky Web",
             "Tailwind", "Trick Room", "Haze", "Court Change", "Rain Dance", "Sunny Day", "Sandstorm", "Snowscape",
             "Chilly Reception", "Swords Dance", "Nasty Plot", "Calm Mind", "Bulk Up", "Dragon Dance", "Quiver Dance",
             "Shell Smash", "Coil", "Curse", "Iron Defense", "Amnesia", "Agility", "Rock Polish", "Shift Gear",
             "Victory Dance", "Tidy Up", "Protect", "Detect", "Substitute", "Recover", "Roost", "Slack Off",
             "Soft-Boiled", "Moonlight", "Morning Sun", "Synthesis", "Shore Up", "Wish", "Rest", "Healing Wish",
             "Lunar Dance", "Destiny Bond", "Baton Pass", "Teleport", "Shed Tail", "Copycat"}

# Rules with no number: (sentence, worth naming on a lead card)
RULES = {
    "Intimidate": ("Lowers the opposing Pokémon's Attack with Intimidate when it comes in", True),
    "Magic Bounce": ("Bounces hazards and status moves back at the user with Magic Bounce", True),
    "Unaware": ("Unaware ignores the opponent's stat boosts, so setup doesn't help them against it", False),
    "Multiscale": ("Multiscale halves the damage it takes while at full HP", False),
    "Shadow Shield": ("Shadow Shield halves the damage it takes while at full HP", False),
    "Magic Guard": ("Magic Guard means only attacks can hurt it: no hazard, status or recoil damage", False),
    "Good as Gold": ("Good as Gold makes it immune to the opponent's status moves", False),
    "Disguise": ("Disguise blocks the first hit it takes", False),
    "Zero to Hero": ("Zero to Hero turns it into Hero Palafin after it switches out once", False),
}


@dataclass
class AbilityLine:
    name: str           # team member
    ability: str
    text: str
    measured: bool      # backed by a calc number
    lead: bool = False  # a lead job: what it does the moment it comes in
    gain: float = 0.0   # extra 2HKOs, or Speed share points, for ranking


def _ability(p):
    return p.get("Mega Ability") or p.get("Ability") or ""


def _moves(p, dex):
    out = []
    for m in p.get("Moves", []):
        data = dex.move(m["name"]) if dex else None
        if data:
            out.append(data)
    return out


def _count(moves, off, on, game, threats):
    """(best move, 2HKOs with `off`, with `on`) over the damaging moves ({name: base power}); None unless `on` adds
    a 2HKO and reaches at least two, so a line never rests on a single matchup. Ties go to the stronger move."""
    if not moves or not threats:
        return None
    reqs = [{"game": game, "attacker": spec, "defender": d, "move": mv}
            for mv in moves for _, d in threats for spec in (off, on)]
    results = calc.calculate_many(reqs)
    count = {}
    for req, r in zip(reqs, results):
        n = mechanics.hits_to_ko(r, req["attacker"], req["defender"], req["move"]) if r else None
        count.setdefault(req["move"], [0, 0])[int(req["attacker"] is on)] += int(n is not None and n <= 2)
    best = max(count, key=lambda mv: (count[mv][1] - count[mv][0], count[mv][1], moves[mv]))
    lo, hi = count[best]
    return (best, lo, hi) if hi > lo and hi >= 2 else None


def _speed(spec, on, game, move, meta):
    from metamatch.engine.synergy import _share
    before, after = mechanics.final_speed(spec, game, move), mechanics.final_speed(on, game, move)
    if not before or not after or after <= before:
        return None
    return after, _share(before, meta), _share(after, meta)


def _pct(x):
    return f"{int(x * 100)}%"


def _hits(best, lo, hi, n):
    return f"{best} 2HKO {hi} of the {n} most used Pokémon, up from {lo}"


def _measured(p, ab, spec, moves, game, ctx):
    """The measured line for a situational or always on ability, or None."""
    damaging = {m["name"]: m.get("basePower") or 0 for m in moves if m.get("category") != "Status"}
    threats, n = ctx["threats"], len(ctx["threats"])
    any_move = (list(damaging) or [m["name"] for m in moves] or ["Tackle"])[0]
    speed_words = lambda after, a, b: (f"takes it to {after} Speed: outspeeds {_pct(b)} of the top {ctx['n_speed']}'s ladder sets, "
                                       f"up from {_pct(a)}")
    if ab == "Supreme Overlord":
        r = _count(damaging, spec, dict(spec, alliesFainted=ALLIES_DOWN), game, threats)
        return r and AbilityLine(p["Pokemon"], ab, f"With {ALLIES_DOWN} teammates down, Supreme Overlord lets "
                                 + _hits(*r, n), True, gain=r[2] - r[1])
    if ab in AFTER_KO:
        stat = AFTER_KO[ab]
        if stat is None:
            res = calc.calculate({"game": game, "attacker": spec, "defender": spec, "move": any_move})
            stats = (res or {}).get("attacker_stats") or {}
            stat = max(("atk", "def", "spa", "spd", "spe"), key=lambda s: stats.get(s, 0)) if stats else None
        on = dict(spec, boosts={**(spec.get("boosts") or {}), stat: 1}) if stat else None
        if stat == "spe":
            r = _speed(spec, on, game, any_move, ctx["meta"])
            return r and AbilityLine(p["Pokemon"], ab, f"After a KO, {ab} " + speed_words(*r), True,
                                     gain=100 * (r[2] - r[1]))
        if stat in ("atk", "spa"):
            r = _count(damaging, spec, on, game, threats)
            return r and AbilityLine(p["Pokemon"], ab, f"After a KO, {ab}'s {STAT_WORDS[stat]} boost lets "
                                     + _hits(*r, n), True, gain=r[2] - r[1])
        return None
    if ab == "Speed Boost":
        r = _speed(spec, dict(spec, boosts={**(spec.get("boosts") or {}), "spe": 1}), game, any_move, ctx["meta"])
        return r and AbilityLine(p["Pokemon"], ab, "After one turn, Speed Boost " + speed_words(*r), True,
                                 gain=100 * (r[2] - r[1]))
    if ab == "Unburden" and p.get("Item") and (p["Item"] in SINGLE_USE or p["Item"].endswith(" Berry")):
        on = {k: v for k, v in spec.items() if k != "item"}
        r = _speed(spec, dict(on, abilityOn=True), game, any_move, ctx["meta"])
        return r and AbilityLine(p["Pokemon"], ab, f"Once its {p['Item']} is used, Unburden "
                                 + speed_words(*r), True, gain=100 * (r[2] - r[1]))
    if ab == "Contrary":
        for mv, boosts in CONTRARY.items():
            if mv in damaging:
                r = _count(damaging, spec, dict(spec, boosts=boosts), game, threats)
                stat = next(iter(boosts))
                hits = _hits(*r, n) if not r or r[0] != mv else "the next " + _hits(*r, n)
                return r and AbilityLine(p["Pokemon"], ab, f"After one {mv}, Contrary's +{boosts[stat]} "
                                         f"{STAT_WORDS[stat]} lets " + hits, True, gain=r[2] - r[1])
        return None
    if ab in STATUS_BOOST:
        status = STATUS_BOOST[ab].get(p.get("Item"))
        if status:
            r = _count(damaging, spec, dict(spec, status=status), game, threats)
            return r and AbilityLine(p["Pokemon"], ab, f"Once {p['Item']} {ORB_WORDS[status]} it, {ab} lets "
                                     + _hits(*r, n), True, gain=r[2] - r[1])
        return None
    if ab in PASSIVE:
        r = _count(damaging, dict(spec, ability=NEUTRAL), spec, game, threats)
        if r:
            best, lo, hi = r
            return AbilityLine(p["Pokemon"], ab, f"{ab} lets {best} 2HKO {hi} of the {n} most used Pokémon, "
                               f"{lo} without it", True, gain=hi - lo)
    return None


def _rule(p, ab, moves):
    """The rule line for an ability the calc can't put a number on, or None."""
    status = [m["name"] for m in moves if m.get("category") == "Status"]
    if ab == "Prankster" and status:
        shown = status[:3]
        aimed = [m for m in shown if m not in NO_TARGET]
        dark = f", though {_and(aimed)} {'fails' if len(aimed) == 1 else 'fail'} on Dark types" if aimed else ""
        return AbilityLine(p["Pokemon"], ab, f"Prankster gives {_and(shown)} priority{dark}", False, lead=True)
    flying = [m["name"] for m in moves if m.get("type") == "Flying" and m.get("category") != "Status"]
    if ab == "Gale Wings" and flying:
        return AbilityLine(p["Pokemon"], ab, f"Gale Wings gives {_and(flying)} priority at full HP", False)
    if ab == "Regenerator":
        pivots = {"U-turn", "Volt Switch", "Flip Turn", "Parting Shot", "Teleport", "Chilly Reception"}
        return AbilityLine(p["Pokemon"], ab, "Heals a third of its HP with Regenerator each time it switches out",
                           False, lead=bool(pivots & {m["name"] for m in moves}))
    if ab == "Poison Heal" and p.get("Item") == "Toxic Orb":
        return AbilityLine(p["Pokemon"], ab, "Once Toxic Orb poisons it, Poison Heal restores 1/8 of its HP each turn",
                           False)
    if ab in RULES:
        text, lead = RULES[ab]
        return AbilityLine(p["Pokemon"], ab, text, False, lead=lead)
    return None


def _and(names):
    names = list(dict.fromkeys(names))
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""


def ability_lines(team, format_id=None, names=None):
    """{member: AbilityLine} for the members in `names` (all when None) whose ability has something to say."""
    from metamatch.engine import synergy
    from metamatch.engine.solvers import user_spec
    format_id = format_id or config.team_format(team)
    game, dex = config.format_game(format_id), dex_for_format(format_id)
    if not dex:
        return {}
    ctx = None
    out = {}
    for p in team.values():
        if names is not None and p["Pokemon"] not in names:
            continue
        ab = _ability(p)
        moves = _moves(p, dex)
        line = _rule(p, ab, moves)
        if line is None and calc.available():
            if ctx is None:
                ctx = {"threats": synergy._threat_specs(team, format_id), "meta": synergy._meta(team, format_id),
                       "n_speed": synergy.N_SPEED}
            line = _measured(p, ab, user_spec(p, game), moves, game, ctx)
        if line:
            out[p["Pokemon"]] = line
    return out

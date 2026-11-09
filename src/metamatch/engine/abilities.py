"""
What a member's ability does for the game plan, in one line, measured with the calc where it can be.

Any ability is measured by switching it off: the calc runs the member's attacks against the format's 12 most used
Pokemon, those Pokemon's attacks against the member, and its final Speed, once with its real ability and once with
an ability that does nothing. Whatever moves is the line, so every ability the calc models is covered with no list
to keep up to date (Huge Power, Sharpness, Multiscale, Levitate, Thick Fat, Sturdy, the Ruin abilities...).

Only two kinds of ability need curating here:
  * triggers the calc can't know about: how many teammates are down (Supreme Overlord), a KO (Moxie), a Flame Orb
    burn (Guts), a turn passing (Speed Boost), a used item (Unburden), a stat drop flipped (Contrary)
  * abilities that work outside damage and Speed (Intimidate, Regenerator, Magic Bounce, Prankster...), stated as
    rules restating Pokemon Showdown's ability text (data/text/abilities.ts, MIT licensed)
A measured line only appears when the number moves. Weather and terrain abilities belong to the team engines in
synergy.py, so they're left out here. Every ability's own Showdown description is in ability_text.json for hovers.
"""
import json
from dataclasses import dataclass
from functools import lru_cache

from metamatch import config
from metamatch.engine import calc, mechanics
from metamatch.engine.dex import dex_for_format

NEUTRAL = "Run Away"          # no effect on damage or Speed, for the "without it" numbers
ALLIES_DOWN = 3
STAT_WORDS = {"atk": "Attack", "def": "Defense", "spa": "Special Attack", "spd": "Special Defense", "spe": "Speed"}
TEXT_PATH = config.JSON_DIR / "ability_text.json"

# Triggers: the ability waits for a situation the calc is told about explicitly
AFTER_KO = {"Moxie": "atk", "Chilling Neigh": "atk", "As One (Glastrier)": "atk", "Grim Neigh": "spa",
            "As One (Spectrier)": "spa", "Soul-Heart": "spa", "Beast Boost": None}   # None: its highest stat
STATUS_BOOST = {"Guts": {"Flame Orb": "brn", "Toxic Orb": "tox"}, "Toxic Boost": {"Toxic Orb": "tox"},
                "Flare Boost": {"Flame Orb": "brn"}}
ORB_WORDS = {"brn": "burns", "tox": "poisons"}
CONTRARY = {"Leaf Storm": {"spa": 2}, "Overheat": {"spa": 2}, "Draco Meteor": {"spa": 2}, "Fleur Cannon": {"spa": 2},
            "Psycho Boost": {"spa": 2}, "Make It Rain": {"spa": 1}, "Superpower": {"atk": 1, "def": 1}}
SINGLE_USE = {"White Herb", "Mental Herb", "Power Herb", "Focus Sash", "Booster Energy", "Electric Seed",
              "Grassy Seed", "Psychic Seed", "Misty Seed", "Air Balloon", "Red Card", "Eject Button", "Eject Pack",
              "Weakness Policy", "Throat Spray", "Room Service", "Adrenaline Orb", "Blunder Policy"}
# Damage halved only at full HP: measured on the first hit alone, since later hits land at full damage
FIRST_HIT_ONLY = {"Multiscale", "Shadow Shield", "Tera Shell"}

# Status moves that never target the opposing Pokemon, so Prankster's Dark type immunity doesn't touch them
NO_TARGET = {"Reflect", "Light Screen", "Aurora Veil", "Stealth Rock", "Spikes", "Toxic Spikes", "Sticky Web",
             "Tailwind", "Trick Room", "Haze", "Court Change", "Rain Dance", "Sunny Day", "Sandstorm", "Snowscape",
             "Chilly Reception", "Swords Dance", "Nasty Plot", "Calm Mind", "Bulk Up", "Dragon Dance", "Quiver Dance",
             "Shell Smash", "Coil", "Curse", "Iron Defense", "Amnesia", "Agility", "Rock Polish", "Shift Gear",
             "Victory Dance", "Tidy Up", "Protect", "Detect", "Substitute", "Recover", "Roost", "Slack Off",
             "Soft-Boiled", "Moonlight", "Morning Sun", "Synthesis", "Shore Up", "Wish", "Rest", "Healing Wish",
             "Lunar Dance", "Destiny Bond", "Baton Pass", "Teleport", "Shed Tail", "Copycat"}

# Outside damage and Speed: (sentence, worth naming on a lead card). Checked after the calc for the ones it might
# model (Disguise, Multiscale), so a measured line wins when the calc shows one.
RULES = {
    "Intimidate": ("Lowers the opposing Pokémon's Attack with Intimidate when it comes in", True),
    "Magic Bounce": ("Bounces hazards and status moves back at the user with Magic Bounce", True),
    "Unaware": ("Unaware ignores the opponent's stat boosts, so setup doesn't help them against it", False),
    "Magic Guard": ("Magic Guard means only attacks can hurt it: no hazard, status or recoil damage", False),
    "Good as Gold": ("Good as Gold makes it immune to the opponent's status moves", False),
    "Zero to Hero": ("Zero to Hero turns it into Hero Palafin after it switches out once", False),
    "Multiscale": ("Multiscale halves the damage it takes while at full HP", False),
    "Shadow Shield": ("Shadow Shield halves the damage it takes while at full HP", False),
    "Disguise": ("Disguise blocks the first hit it takes", False),
    "Purifying Salt": ("Purifying Salt halves the damage Ghost moves do to it and blocks status conditions", False),
}
# Immunities: measured first, and stated as a rule when they never change a KO against the top threats
IMMUNE = {"Flash Fire": "Fire", "Well-Baked Body": "Fire", "Water Absorb": "Water", "Storm Drain": "Water",
          "Dry Skin": "Water", "Volt Absorb": "Electric", "Lightning Rod": "Electric", "Motor Drive": "Electric",
          "Levitate": "Ground", "Earth Eater": "Ground", "Sap Sipper": "Grass"}
NO_CALC_EFFECT = {"Intimidate", "Magic Bounce", "Unaware", "Magic Guard", "Good as Gold", "Zero to Hero",
                  "Regenerator", "Prankster", "Gale Wings", "Poison Heal"}


@dataclass
class AbilityLine:
    name: str           # team member
    ability: str
    text: str
    measured: bool      # backed by a calc number
    lead: bool = False  # a lead job: what it does the moment it comes in
    gain: float = 0.0   # matchups gained (Speed: share points scaled to the 12 threats), for ranking


@lru_cache(maxsize=1)
def descriptions():
    """{ability name: Showdown's short description}, from scripts/build_ability_text.py; {} when not built."""
    try:
        with open(TEXT_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def describe(ability):
    """Showdown's one line description of an ability, or ''."""
    return descriptions().get(ability or "", "")


def _ability(p):
    return p.get("Mega Ability") or p.get("Ability") or ""


def _moves(p, dex):
    out = []
    for m in p.get("Moves", []):
        data = dex.move(m["name"]) if dex else None
        if data:
            out.append(data)
    return out


def _engine_abilities():
    """Weather and terrain abilities the team engines already cover."""
    from metamatch.engine import synergy
    out = set()
    for cond in synergy.CONDITIONS.values():
        out |= set(cond.get("ability_setters", {})) | set(cond.get("abilities", {}))
    return out


def _count(moves, off, on, game, threats):
    """(best move, 2HKOs with `off`, with `on`) over the damaging moves ({name: base power}); None unless `on` adds
    a 2HKO and reaches at least two, so a line never rests on a single matchup. Ties go to the stronger move."""
    if not moves or not threats:
        return None
    reqs = [{"game": game, "attacker": spec, "defender": t["spec"], "move": mv}
            for mv in moves for t in threats for spec in (off, on)]
    results = calc.calculate_many(reqs)
    count = {}
    for req, r in zip(reqs, results):
        n = mechanics.hits_to_ko(r, req["attacker"], req["defender"], req["move"]) if r else None
        count.setdefault(req["move"], [0, 0])[int(req["attacker"] is on)] += int(n is not None and n <= 2)
    best = max(count, key=lambda mv: (count[mv][1] - count[mv][0], count[mv][1], moves[mv]))
    lo, hi = count[best]
    return (best, lo, hi) if hi > lo and hi >= 2 else None


def _survives(r, attacker, defender, move, hits):
    """True when `hits` uses of the move can never KO the defender from full HP (highest roll)."""
    if not r or r["range"][1] <= 0:
        return True
    effect = mechanics.survival_effect(r, attacker, defender, move)
    return mechanics._total(r, hits, effect)[1] < r["defender_stats"]["hp"]


def _hits_needed(r, attacker, defender, move, cap=8):
    """Fewest uses of the move that can KO from full HP (highest roll), or cap + 1 when it never can."""
    return next((h for h in range(1, cap + 1) if not _survives(r, attacker, defender, move, h)), cap + 1)


def _defense(off, on, game, threats, first_hit_only):
    """How the ability changes what the threats need to KO it, or None if nothing moves:
      (1 or 2, threats it survives that many hits from without it, with it): none of their attacks can KO in that many
      ('slower', 0, threats that need more hits): for walls too bulky for one or two hits to matter (Flash Fire)."""
    reqs = [{"game": game, "attacker": t["spec"], "defender": spec, "move": mv}
            for t in threats for mv in t["moves"] for spec in (off, on)]
    if not reqs:
        return None
    results = calc.calculate_many(reqs)
    fastest = {}          # (threat, with the ability) -> fewest hits any of its attacks needs
    for req, r in zip(reqs, results):
        key = (req["attacker"]["name"], req["defender"] is on)
        fastest[key] = min(fastest.get(key, 99), _hits_needed(r, req["attacker"], req["defender"], req["move"]))
    best = None
    for hits in ((1,) if first_hit_only else (1, 2)):
        lo = sum(1 for (_, side), n in fastest.items() if not side and n > hits)
        hi = sum(1 for (_, side), n in fastest.items() if side and n > hits)
        if hi > lo and (best is None or hi - lo > best[2] - best[1]):
            best = (hits, lo, hi)
    if best or first_hit_only:
        return best
    slower = sum(1 for (name, side), n in fastest.items() if side and n > fastest.get((name, False), 99))
    return ("slower", 0, slower) if slower >= 2 else None


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


def _trigger(p, ab, spec, damaging, any_move, game, ctx):
    """The measured line for an ability that waits for a situation, or None."""
    threats, n = ctx["threats"], len(ctx["threats"])
    speed_words = lambda after, a, b: (f"takes it to {after} Speed: outspeeds {_pct(b)} of the top {ctx['n_speed']}'s "
                                       f"ladder sets, up from {_pct(a)}")
    line = lambda text, gain: AbilityLine(p["Pokemon"], ab, text, True, gain=gain)
    if ab == "Supreme Overlord":
        r = _count(damaging, spec, dict(spec, alliesFainted=ALLIES_DOWN), game, threats)
        return r and line(f"With {ALLIES_DOWN} teammates down, Supreme Overlord lets " + _hits(*r, n), r[2] - r[1])
    if ab in AFTER_KO:
        stat = AFTER_KO[ab]
        if stat is None:
            res = calc.calculate({"game": game, "attacker": spec, "defender": spec, "move": any_move})
            stats = (res or {}).get("attacker_stats") or {}
            stat = max(("atk", "def", "spa", "spd", "spe"), key=lambda s: stats.get(s, 0)) if stats else None
        on = dict(spec, boosts={**(spec.get("boosts") or {}), stat: 1}) if stat else None
        if stat == "spe":
            r = _speed(spec, on, game, any_move, ctx["meta"])
            return r and line(f"After a KO, {ab} " + speed_words(*r), n * (r[2] - r[1]))
        if stat in ("atk", "spa"):
            r = _count(damaging, spec, on, game, threats)
            return r and line(f"After a KO, {ab}'s {STAT_WORDS[stat]} boost lets " + _hits(*r, n), r[2] - r[1])
        return None
    if ab == "Speed Boost":
        r = _speed(spec, dict(spec, boosts={**(spec.get("boosts") or {}), "spe": 1}), game, any_move, ctx["meta"])
        return r and line("After one turn, Speed Boost " + speed_words(*r), n * (r[2] - r[1]))
    if ab == "Unburden":
        if not p.get("Item") or not (p["Item"] in SINGLE_USE or p["Item"].endswith(" Berry")):
            return None
        on = {k: v for k, v in spec.items() if k != "item"}
        r = _speed(spec, dict(on, abilityOn=True), game, any_move, ctx["meta"])
        return r and line(f"Once its {p['Item']} is used, Unburden " + speed_words(*r), n * (r[2] - r[1]))
    if ab == "Contrary":
        for mv, boosts in CONTRARY.items():
            if mv in damaging:
                r = _count(damaging, spec, dict(spec, boosts=boosts), game, threats)
                stat = next(iter(boosts))
                hits = (_hits(*r, n) if r[0] != mv else "the next " + _hits(*r, n)) if r else ""
                return r and line(f"After one {mv}, Contrary's +{boosts[stat]} {STAT_WORDS[stat]} lets " + hits,
                                  r[2] - r[1])
        return None
    if ab in STATUS_BOOST:
        status = STATUS_BOOST[ab].get(p.get("Item"))
        if not status:
            return None
        r = _count(damaging, spec, dict(spec, status=status), game, threats)
        return r and line(f"Once {p['Item']} {ORB_WORDS[status]} it, {ab} lets " + _hits(*r, n), r[2] - r[1])
    return False      # not a trigger ability


def _switched_off(p, ab, spec, damaging, any_move, game, ctx):
    """The ability's biggest effect on offense, defense or Speed, found by running the calc without it; or None."""
    threats, n = ctx["threats"], len(ctx["threats"])
    without = dict(spec, ability=NEUTRAL)
    prefix = "With Booster Energy, " if ab in ("Protosynthesis", "Quark Drive") and p.get("Item") == "Booster Energy" else ""
    options = []
    r = _count(damaging, without, spec, game, threats)
    if r:
        best, lo, hi = r
        options.append((hi - lo, f"{prefix}{ab} lets {best} 2HKO {hi} of the {n} most used Pokémon, {lo} without it"))
    d = _defense(without, spec, game, threats, ab in FIRST_HIT_ONLY)
    if d and d[0] == "slower":
        k = d[2]
        options.append((k / 2, f"{prefix}{ab} means {k} of the {n} most used Pokémon need more hits to KO it"))
    elif d:
        hits, lo, hi = d
        what = "survive any single hit" if hits == 1 else "survive two hits"
        options.append((hi - lo, f"{prefix}{ab} lets it {what} from {hi} of the {n} most used Pokémon, {lo} without it"))
    s = _speed(without, spec, game, any_move, ctx["meta"])
    if s:
        after, a, b = s
        options.append((n * (b - a), f"{prefix}{ab} takes it to {after} Speed: outspeeds {_pct(b)} of the top "
                                     f"{ctx['n_speed']}'s ladder sets, {_pct(a)} without it"))
    if not options:
        return None
    gain, text = max(options, key=lambda o: o[0])
    return AbilityLine(p["Pokemon"], ab, text, True, gain=gain)


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
    if ab in IMMUNE:
        return AbilityLine(p["Pokemon"], ab, f"{ab} makes it immune to {IMMUNE[ab]} moves", False)
    return None


def _and(names):
    names = list(dict.fromkeys(names))
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""


def _threats(team, format_id):
    """The 12 most used Pokemon not on the team: name, calc spec and damaging moves of their likely set."""
    from metamatch.engine import synergy
    from metamatch.engine.sets import calc_spec, likely_set
    from metamatch.engine.threat_board import top_threats
    dex = dex_for_format(format_id)
    names = [p["Pokemon"] for p in team.values()] + [p.get("Forme") for p in team.values() if p.get("Forme")]
    out = []
    for name, _ in top_threats(format_id, exclude=names, n=synergy.N_THREATS):
        s = likely_set(name, format_id)
        if s:
            moves = [m for m, _ in s["moves"] if (dex.move(m) or {}).get("category") not in (None, "Status")]
            out.append({"name": s["name"], "spec": calc_spec(s), "moves": moves})
    return out


def ability_lines(team, format_id=None, names=None):
    """{member: AbilityLine} for the members in `names` (all when None) whose ability has something to say."""
    from metamatch.engine import synergy
    from metamatch.engine.solvers import user_spec
    format_id = format_id or config.team_format(team)
    game, dex = config.format_game(format_id), dex_for_format(format_id)
    if not dex:
        return {}
    skip = _engine_abilities()
    ctx, out = None, {}
    for p in team.values():
        if names is not None and p["Pokemon"] not in names:
            continue
        ab = _ability(p)
        booster = ab in ("Protosynthesis", "Quark Drive") and p.get("Item") == "Booster Energy"
        if not ab or (ab in skip and not booster):     # Booster Energy needs no sun or terrain, so it's measured here
            continue
        moves = _moves(p, dex)
        line = None
        if ab in NO_CALC_EFFECT:
            line = _rule(p, ab, moves)
        elif calc.available():
            if ctx is None:
                ctx = {"threats": _threats(team, format_id), "meta": synergy._meta(team, format_id),
                       "n_speed": synergy.N_SPEED}
            spec = user_spec(p, game)
            damaging = {m["name"]: m.get("basePower") or 0 for m in moves if m.get("category") != "Status"}
            any_move = (list(damaging) or [m["name"] for m in moves] or ["Tackle"])[0]
            line = _trigger(p, ab, spec, damaging, any_move, game, ctx)
            if line is False:
                line = _switched_off(p, ab, spec, damaging, any_move, game, ctx)
            line = line or _rule(p, ab, moves)
        if line:
            out[p["Pokemon"]] = line
    return out

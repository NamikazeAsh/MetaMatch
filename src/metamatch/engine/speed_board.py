"""
Speed Tiers from real ladder spreads: the format's most used Pokemon with the Speed of every spread players
run (and how often each holds Choice Scarf), against each team member's final Speed from the calc.
"""
from dataclasses import dataclass, field

from metamatch import config
from metamatch.engine import mechanics
from metamatch.engine.dex import dex_for_format, to_id
from metamatch.engine.sets import likely_set, speed_spreads, spread_label
from metamatch.engine.solvers import user_spec
from metamatch.engine.threat_board import top_threats


@dataclass
class MetaSpeed:
    name: str
    usage: float                                     # share of teams, 0 to 100
    speeds: list = field(default_factory=list)       # [(speed, share 0..1)], most common first
    scarf_share: float = 0.0
    spreads: dict = field(default_factory=dict)      # {speed: [(spread label, share 0..1)]}, top few per speed

    @property
    def usual(self):
        return self.speeds[0][0] if self.speeds else 0


def _any_move(p, dex):
    for m in p.get("Moves", []):
        if dex.move_name(m["name"]):
            return dex.move_name(m["name"])
    return next(iter(dex.move_data))


def member_speeds(team, format_id):
    """{member: final Speed with its item and ability} from the calc, falling back to the parsed stat."""
    dex = dex_for_format(format_id)
    game = config.format_game(format_id)
    out = {}
    for p in team.values():
        speed = mechanics.final_speed(user_spec(p, game), game, _any_move(p, dex)) if dex else None
        out[p["Pokemon"]] = speed or p.get("Speed", 0)
    return out


def meta_speeds(format_id, n=25, exclude=()):
    rows = []
    for name, usage in top_threats(format_id, exclude=exclude, n=n):
        s = likely_set(name, format_id)
        if s and s.get("speeds"):
            rows.append(MetaSpeed(s["name"], round(usage * 100, 1), list(s["speeds"]), s.get("scarf_share", 0.0),
                                  spreads_by_speed(s["name"], format_id)))
    return rows


def spreads_by_speed(name, format_id, top=3, floor=0.005):
    """{speed: [(readable spread, share of sets)]}: the most run spreads behind each of a Pokemon's Speeds,
    leaving out ones on under half a percent of its sets."""
    out = {}
    for spe, group in speed_spreads(name, format_id).items():
        kept = [(spread_label(raw, format_id), share) for raw, share in sorted(group, key=lambda x: -x[1]) if share >= floor]
        out[spe] = kept[:top]
    return out


def speed_curve(p, format_id):
    """A member's final Speed (item and ability included) at every Speed investment, with its own nature and,
    when that isn't a Speed nature, with the Speed nature that lowers the same stat. None without the calc.
    {"unit", "current", "free", "own": [(investment, speed)], "fast": (nature, [(investment, speed)]) or None}"""
    from metamatch.engine import calc
    from metamatch.engine.spread_lab import NATURES, _budget
    dex = dex_for_format(format_id)
    if not dex or not calc.available():
        return None
    game = config.format_game(format_id)
    spec = user_spec(p, game)
    budget, cap = _budget(game)
    steps = list(range(0, cap + 1, 1 if game == "champions" else 4))
    evs = spec.get("evs", {})
    move = _any_move(p, dex)

    def curve(nature):
        reqs = [{"game": game, "attacker": dict(spec, nature=nature, evs=dict(evs, spe=v)),
                 "defender": dict(spec), "move": move} for v in steps]
        return [(v, r["attacker_speed"]) for v, r in zip(steps, calc.calculate_many(reqs)) if r and r.get("attacker_speed")]

    nature = spec.get("nature") or "Serious"
    up, down = next(((u, d) for (u, d), n in NATURES.items() if n == nature), (None, None))
    fast = None
    if up != "spe":
        if not down or down == "spe":
            base = p.get("Base Stats") or {}
            down = "spa" if base.get("attack", 0) >= base.get("special-attack", 0) else "atk"
        fast = NATURES[("spe", down)]
    return {"unit": "SP" if game == "champions" else "EVs", "current": evs.get("spe", 0), "item": spec.get("item", ""),
            "free": budget - sum(evs.values()), "own": curve(nature), "fast": (fast, curve(fast)) if fast else None}


def price(curve, target):
    """What reaching `target` final Speed takes: ("own", investment), ("fast", investment, nature) or None."""
    if not curve:
        return None
    hit = next((v for v, s in curve["own"] if s >= target), None)
    if hit is not None:
        return ("own", hit)
    if curve["fast"]:
        nature, rows = curve["fast"]
        hit = next((v for v, s in rows if s >= target), None)
        if hit is not None:
            return ("fast", hit, nature)
    return None


def price_text(curve, cost, short=False):
    """A cost from price() in words: '+40 Spe EVs', 'needs a Jolly nature and 252 Spe EVs', 'out of reach'."""
    if not cost:
        scarf = "" if to_id(curve.get("item") or "") == "choicescarf" else "Choice Scarf, "
        return "out of reach" if short else f"Out of reach with EVs and nature alone: it needs {scarf}Tailwind or a Speed boost"
    unit, current = curve["unit"], curve["current"]
    if cost[0] == "fast":
        return f"{cost[2]}, {cost[1]} {unit}" if short else f"Needs a {cost[2]} nature and {cost[1]} Spe {unit}"
    more = cost[1] - current
    if more == 0:
        return "your spread" if short else "Your current spread"
    if more < 0:
        return f"{more} {unit}" if short else f"{-more} fewer Spe {unit} than you run would still do it"
    over = more - max(curve["free"], 0)
    moved = f", {over} taken from other stats" if over > 0 and not short else ""
    return f"+{more} {unit}" if short else f"+{more} Spe {unit}{moved}"


def outspeed_share(speed, meta):
    """Share of `meta`'s ladder sets a Pokemon at `speed` outspeeds, Choice Scarf mixed in at its usage share."""
    return mechanics.scarf_adjusted_share(speed, meta.speeds, meta.scarf_share)


def tie_share(speed, meta):
    return sum(share for spe, share in meta.speeds if spe == speed) * (1 - meta.scarf_share)


def is_member(name, team):
    ids = {to_id(p.get("Pokemon")) for p in team.values()} | {to_id(p.get("Forme")) for p in team.values()}
    return to_id(name) in ids

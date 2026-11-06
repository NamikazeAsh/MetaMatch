"""
Speed Tiers from real ladder spreads: the format's most used Pokemon with the Speed of every spread players
run (and how often each holds Choice Scarf), against each team member's final Speed from the calc.
"""
from dataclasses import dataclass, field

from metamatch import config
from metamatch.engine import mechanics
from metamatch.engine.dex import dex_for_format, to_id
from metamatch.engine.sets import likely_set
from metamatch.engine.solvers import user_spec
from metamatch.engine.threat_board import top_threats


@dataclass
class MetaSpeed:
    name: str
    usage: float                                     # share of teams, 0 to 100
    speeds: list = field(default_factory=list)       # [(speed, share 0..1)], most common first
    scarf_share: float = 0.0

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
            rows.append(MetaSpeed(s["name"], round(usage * 100, 1), list(s["speeds"]), s.get("scarf_share", 0.0)))
    return rows


def outspeed_share(speed, meta):
    """Share of `meta`'s ladder sets a Pokemon at `speed` outspeeds, Choice Scarf mixed in at its usage share."""
    return mechanics.scarf_adjusted_share(speed, meta.speeds, meta.scarf_share)


def tie_share(speed, meta):
    return sum(share for spe, share in meta.speeds if spe == speed) * (1 - meta.scarf_share)


def is_member(name, team):
    ids = {to_id(p.get("Pokemon")) for p in team.values()} | {to_id(p.get("Forme")) for p in team.values()}
    return to_id(name) in ids

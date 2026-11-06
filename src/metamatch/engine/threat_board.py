"""
Threat Board: the format's most used Pokemon against every member of a team, one on one, from the damage
calc (engine/briefing.py exchange verdicts). For each threat it lists which members answer it and which
lose, so a team's real holes show up as threats nobody answers. Smogon's Checks and Counters data, where
the month has any, is shown beside the engine verdicts as a second opinion, never as the verdict.
"""
from dataclasses import dataclass, field

from metamatch import config
from metamatch.auditor import load_chaos_data
from metamatch.engine.briefing import _reason, _verdict, exchange
from metamatch.engine.dex import dex_for_format, to_id
from metamatch.engine.sets import likely_set

# A Checks and Counters entry counts once it has enough encounters and usually KOs or forces the threat out
CC_MIN_N, CC_MIN_P = 10, 0.5


@dataclass
class Cell:
    verdict: str          # "win", "lose" or "even"
    reason: str           # "faster; Earthquake 69-82% (2HKO); takes Iron Head 43-51% (3HKO)"
    exchange: dict = None

    @property
    def parts(self):
        """The verdict split for display: speed, the best hit each way, and who finishes with priority."""
        return exchange_parts(self.exchange) if self.exchange else {}


def _hko(n):
    return "OHKO" if n == 1 else f"{n}HKO" if n else ""


def exchange_parts(x):
    """{'speed', 'dealt', 'dealt_ko', 'taken', 'taken_ko', 'priority'} for one exchange (briefing.exchange)."""
    share = x["outspeeds"]
    speed = "Faster" if share >= 0.95 else "Slower" if share <= 0.05 else f"Faster than {share * 100:.0f}% of sets"
    priority = ""
    if x.get("priority", (0, None))[1] and x["to_ko"] == x["to_be_koed"]:
        priority = f"Finishes first with {x['priority'][1]}"
    elif x.get("opp_priority", (0, None))[1] and x["to_ko"] == x["to_be_koed"]:
        priority = f"It finishes first with {x['opp_priority'][1]}"

    def hit(pair):
        move, r = pair
        lo, hi = r["percent"]
        return f"{move} {lo:g} to {hi:g}%"
    return {"speed": speed, "priority": priority,
            "dealt": hit(x["dealt"]) if x.get("dealt") else "No damaging move", "dealt_ko": _hko(x.get("to_ko")),
            "taken": hit(x["taken"]) if x.get("taken") else "Takes no damage", "taken_ko": _hko(x.get("to_be_koed"))}


@dataclass
class ThreatRow:
    name: str
    usage: float                                  # share of teams, 0 to 100
    cells: dict = field(default_factory=dict)     # member name -> Cell
    checks_data: list = field(default_factory=list)  # Smogon Checks and Counters names on this team

    @property
    def answers(self):
        """Members that beat it one on one, strongest first (fewest hits to KO it)."""
        wins = [(n, c) for n, c in self.cells.items() if c.verdict == "win"]
        wins.sort(key=lambda nc: (nc[1].exchange or {}).get("to_ko") or 99)
        return [n for n, _ in wins]

    @property
    def losses(self):
        losing = [(n, c) for n, c in self.cells.items() if c.verdict == "lose"]
        losing.sort(key=lambda nc: (nc[1].exchange or {}).get("to_be_koed") or 99)
        return [n for n, _ in losing]


def checks_and_counters(name, format_id, members):
    """Team members Smogon's Checks and Counters data lists against `name` (empty when the month has none)."""
    entry = (load_chaos_data(format_id) or {}).get(name) or {}
    ids = {to_id(m): m for m in members}
    found = []
    for checker, stats in (entry.get("Checks and Counters") or {}).items():
        if to_id(checker) in ids and stats.get("n", 0) >= CC_MIN_N and stats.get("p", 0) >= CC_MIN_P:
            found.append(ids[to_id(checker)])
    return found


def top_threats(format_id, exclude=(), n=12, min_usage=0.01):
    """(name, usage share) for the most used Pokemon in the format that have usage data, minus `exclude`."""
    data = load_chaos_data(format_id) or {}
    skip = {to_id(x) for x in exclude}
    ranked = sorted(data.items(), key=lambda kv: kv[1].get("usage", 0), reverse=True)
    return [(name, e.get("usage", 0)) for name, e in ranked
            if to_id(name) not in skip and e.get("usage", 0) >= min_usage][:n]


def member_names(team):
    return [p.get("Pokemon") for p in team.values()]


def threat_row(team, name, format_id, usage=None):
    """One row of the board: every member against `name`'s most common set. None without usage data or the calc."""
    opp_set = likely_set(name, format_id)
    dex = dex_for_format(format_id)
    if not opp_set or not dex:
        return None
    game = config.format_game(format_id)
    row = ThreatRow(opp_set["name"], round((usage if usage is not None else opp_set.get("usage", 0)) * 100, 1))
    for p in team.values():
        x = exchange(p, opp_set, game, dex)
        if x is None:
            continue
        row.cells[p["Pokemon"]] = Cell(_verdict(x), _reason(x), x)
    if not row.cells:
        return None
    row.checks_data = checks_and_counters(opp_set["name"], format_id, member_names(team))
    return row


def threat_board(team, n=12, format_id=None):
    """Rows for the format's top `n` threats (team members excluded), most used first."""
    format_id = format_id or config.team_format(team)
    rows = []
    for name, usage in top_threats(format_id, exclude=member_names(team) + [p.get("Forme") for p in team.values()], n=n):
        row = threat_row(team, name, format_id, usage)
        if row:
            rows.append(row)
    return rows


def coverage(rows):
    """(answered threats, total, usage weighted share answered) for a board."""
    if not rows:
        return 0, 0, 0.0
    answered = [r for r in rows if r.answers]
    total_usage = sum(r.usage for r in rows) or 1
    return len(answered), len(rows), sum(r.usage for r in answered) / total_usage

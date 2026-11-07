"""
Spread Lab: the least investment (EVs, or Champions stat points) that hits a set of benchmarks:
  * outspeed:  beat a target's Speed (its most common spread, or every common spread, optionally with Choice Scarf)
  * ko:        a move guaranteed to OHKO or 2HKO a target on its most common set
  * survive:   always live a target's move from full HP
Damage dealt only rises with attacking investment and damage taken only falls with HP and defenses, so each
requirement is a binary search on its own stat. Survive checks share HP, so for every HP value the least
Defense and Special Defense are searched in batches and the cheapest total wins. Every nature that raises a
needed stat (or none) is tried, and the result is rechecked with the calc before it is returned.
"""
from dataclasses import dataclass, field

from metamatch import config
from metamatch.engine import calc, mechanics
from metamatch.engine.dex import dex_for_format
from metamatch.engine.sets import calc_spec, likely_set

STATS = ("hp", "atk", "def", "spa", "spd", "spe")
LABELS = {"hp": "HP", "atk": "Atk", "def": "Def", "spa": "SpA", "spd": "SpD", "spe": "Spe"}
NATURES = {("atk", "def"): "Lonely", ("atk", "spa"): "Adamant", ("atk", "spd"): "Naughty", ("atk", "spe"): "Brave",
           ("def", "atk"): "Bold", ("def", "spa"): "Impish", ("def", "spd"): "Lax", ("def", "spe"): "Relaxed",
           ("spa", "atk"): "Modest", ("spa", "def"): "Mild", ("spa", "spd"): "Rash", ("spa", "spe"): "Quiet",
           ("spd", "atk"): "Calm", ("spd", "def"): "Gentle", ("spd", "spa"): "Careful", ("spd", "spe"): "Sassy",
           ("spe", "atk"): "Timid", ("spe", "def"): "Hasty", ("spe", "spa"): "Jolly", ("spe", "spd"): "Naive"}
NEUTRAL = "Serious"


@dataclass
class Benchmark:
    kind: str                 # "outspeed", "ko" or "survive"
    target: str               # the other Pokemon
    move: str = ""            # ko: your move; survive: its move
    hits: int = 1             # ko: 1 for OHKO, 2 for 2HKO
    every_spread: bool = True  # outspeed: beat every common spread, not just the most common one
    scarf: bool = False       # outspeed: even if it holds Choice Scarf

    def label(self):
        if self.kind == "outspeed":
            who = f"every common {self.target} spread" if self.every_spread else f"{self.target}'s usual spread"
            return f"Outspeed {who}" + (" with Choice Scarf" if self.scarf else "")
        if self.kind == "ko":
            return f"{'OHKO' if self.hits == 1 else f'{self.hits}HKO'} {self.target} with {self.move}"
        return f"Survive {self.target}'s {self.move}"


@dataclass
class Result:
    ok: bool
    nature: str = ""
    evs: dict = field(default_factory=dict)
    used: int = 0
    budget: int = 0
    checks: list = field(default_factory=list)   # (label, passed, detail)
    problem: str = ""                            # why it can't be done


def _grid(game):
    return list(range(0, 33)) if game == "champions" else list(range(0, 253, 4))


def _budget(game):
    return (66, 32) if game == "champions" else (508, 252)


def _spec(base, nature, evs):
    spec = dict(base)
    spec["nature"] = nature
    spec["evs"] = {k: evs.get(k, 0) for k in STATS}
    return spec


def _target_speed(b, format_id):
    s = likely_set(b.target, format_id)
    if not s or not s.get("speeds"):
        return None
    speeds = [spe for spe, share in s["speeds"] if share >= 0.02] or [s["speeds"][0][0]]
    target = max(speeds) if b.every_spread else s["speeds"][0][0]
    return int(target * 1.5) if b.scarf else target


def _first_ok(values, ok):
    """Index of the smallest value with ok(value), assuming ok only flips from False to True; None if never."""
    if not ok(values[-1]):
        return None
    lo, hi = 0, len(values) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if ok(values[mid]):
            hi = mid
        else:
            lo = mid + 1
    return lo


def _move_category(dex, move):
    return (dex.move(move) or {}).get("category")


class Lab:
    def __init__(self, base, benchmarks, format_id):
        self.base, self.benchmarks, self.format_id = base, benchmarks, format_id
        self.game = config.format_game(format_id)
        self.dex = dex_for_format(format_id)
        self.grid = _grid(self.game)
        self.sets = {b.target: likely_set(b.target, format_id) for b in benchmarks}
        self.probe = next((m for b in benchmarks if b.kind == "ko" for m in [b.move]), None) or next(iter(self.dex.move_data))

    # Each requirement as a test on a full spread
    def speed_ok(self, spec, needed):
        speed = mechanics.final_speed(spec, self.game, self.probe)
        return speed is not None and speed > needed

    def ko_requests(self, spec, b):
        return {"game": self.game, "attacker": spec, "defender": calc_spec(self.sets[b.target]), "move": b.move}

    def ko_ok(self, spec, b, result):
        return bool(result) and mechanics.ko_answer(result, b.hits, spec, calc_spec(self.sets[b.target]), b.move)[0] == "yes"

    def survive_requests(self, spec, b):
        return {"game": self.game, "attacker": calc_spec(self.sets[b.target]), "defender": spec, "move": b.move}

    def survive_ok(self, spec, b, result):
        if not result:
            return False
        return mechanics.ko_answer(result, 1, calc_spec(self.sets[b.target]), spec, b.move)[0] == "no"

    def solve_nature(self, nature):
        """Least EVs per stat for this nature, or (None, reason)."""
        evs = {k: 0 for k in STATS}
        # Speed
        speeds = [(b, _target_speed(b, self.format_id)) for b in self.benchmarks if b.kind == "outspeed"]
        if speeds:
            if any(t is None for _, t in speeds):
                return None, "no speed data for " + next(b.target for b, t in speeds if t is None)
            needed = max(t for _, t in speeds)
            i = _first_ok(self.grid, lambda v: self.speed_ok(_spec(self.base, nature, {**evs, "spe": v}), needed))
            if i is None:
                return None, f"can't reach {needed + 1} Speed"
            evs["spe"] = self.grid[i]
        # Knockouts, each on its own attacking stat
        for b in (b for b in self.benchmarks if b.kind == "ko"):
            stat = "atk" if _move_category(self.dex, b.move) == "Physical" else "spa"
            def ok(v, b=b, stat=stat):
                spec = _spec(self.base, nature, {**evs, stat: max(evs[stat], v)})
                return self.ko_ok(spec, b, calc.calculate(self.ko_requests(spec, b)))
            i = _first_ok(self.grid, ok)
            if i is None:
                return None, "no spread guarantees it"
            evs[stat] = max(evs[stat], self.grid[i])
        # Survival: for every HP value, the least Def and SpD that pass every hit of that category, in batches
        survive = [b for b in self.benchmarks if b.kind == "survive"]
        if survive:
            best = None
            for hp in self.grid:
                cost, extra = hp, {"hp": hp}
                for stat, cat in (("def", "Physical"), ("spd", "Special")):
                    group = [b for b in survive if _move_category(self.dex, b.move) == cat]
                    if not group:
                        continue
                    def ok(v, stat=stat, group=group, extra=extra):
                        spec = _spec(self.base, nature, {**evs, **extra, stat: v})
                        results = calc.calculate_many([self.survive_requests(spec, b) for b in group])
                        return all(self.survive_ok(spec, b, r) for b, r in zip(group, results))
                    i = _first_ok(self.grid, ok)
                    if i is None:
                        cost = None
                        break
                    extra[stat] = self.grid[i]
                    cost += self.grid[i]
                if cost is not None and (best is None or cost < best[0]):
                    best = (cost, extra)
                if best and hp >= best[0]:
                    break   # more HP can't make a cheaper total
            if best is None:
                return None, "no spread survives it" if len(survive) == 1 else "no spread survives all of these hits"
            evs.update(best[1])
        return evs, ""

    def natures(self):
        """Natures to try: neutral, plus each raising a needed stat while lowering an unneeded attacking stat."""
        needed = set()
        for b in self.benchmarks:
            if b.kind == "outspeed":
                needed.add("spe")
            elif b.kind == "ko":
                needed.add("atk" if _move_category(self.dex, b.move) == "Physical" else "spa")
            else:
                needed |= {"hp", "def" if _move_category(self.dex, b.move) == "Physical" else "spd"}
        dump = [s for s in ("atk", "spa") if s not in needed] or [s for s in ("atk", "spa", "def", "spd") if s not in needed]
        out = [NEUTRAL]
        for plus in sorted(needed - {"hp"}):
            for minus in dump:
                if (plus, minus) in NATURES:
                    out.append(NATURES[(plus, minus)])
        return list(dict.fromkeys(out))

    def run(self):
        """The best spread for every benchmark that can be met at all; the rest are listed as impossible."""
        budget, _ = _budget(self.game)
        missing = [b.target for b in self.benchmarks if not self.sets.get(b.target)]
        if missing:
            return Result(False, budget=budget, problem=f"no usage data for {', '.join(missing)} in this format")
        impossible = []
        if len(self.benchmarks) > 1:
            for b in self.benchmarks:
                alone = Lab(self.base, [b], self.format_id)._solve()
                if not alone.ok:
                    impossible.append((b.label(), False, alone.problem))
        feasible = [b for b in self.benchmarks if b.label() not in {x[0] for x in impossible}]
        if not feasible:
            return Result(False, budget=budget, checks=impossible, problem="none of these can be met")
        result = Lab(self.base, feasible, self.format_id)._solve()
        result.checks += impossible
        return result

    def _solve(self):
        budget, cap = _budget(self.game)
        best, reasons = None, []
        for nature in self.natures():
            evs, why = self.solve_nature(nature)
            if evs is None:
                reasons.append(why)
                continue
            used = sum(evs.values())
            if used <= budget and (best is None or used < best[1]):
                best = (nature, used, evs)
            elif used > budget:
                reasons.append(f"needs {used} of {budget} with {nature}")
        if not best:
            return Result(False, budget=budget, problem=reasons[0] if reasons else "no spread fits")
        nature, used, evs = best
        return Result(True, nature, evs, used, budget, self.recheck(nature, evs))

    def recheck(self, nature, evs):
        """Every benchmark rerun once on the final spread, with the numbers to show."""
        spec = _spec(self.base, nature, evs)
        out = []
        for b in self.benchmarks:
            if b.kind == "outspeed":
                mine, needed = mechanics.final_speed(spec, self.game, self.probe), _target_speed(b, self.format_id)
                out.append((b.label(), bool(mine and mine > needed), f"{mine} Speed vs {needed}"))
            elif b.kind == "ko":
                r = calc.calculate(self.ko_requests(spec, b))
                ok = self.ko_ok(spec, b, r)
                out.append((b.label(), ok, f"{r['percent'][0]:g} to {r['percent'][1]:g}%" if r else "no calc"))
            else:
                r = calc.calculate(self.survive_requests(spec, b))
                ok = self.survive_ok(spec, b, r)
                out.append((b.label(), ok, f"takes {r['percent'][0]:g} to {r['percent'][1]:g}%" if r else "no calc"))
        return out


def spread_text(nature, evs, game):
    parts = " / ".join(f"{v} {LABELS[k]}" for k, v in evs.items() if v)
    return f"{nature} {parts or 'no investment'}" + (" (stat points)" if game == "champions" else "")


def showdown_block(name, item, ability, nature, evs, moves):
    lines = [f"{name}{' @ ' + item if item else ''}"]
    if ability:
        lines.append(f"Ability: {ability}")
    spread = " / ".join(f"{v} {LABELS[k]}" for k, v in evs.items() if v)
    if spread:
        lines.append(f"EVs: {spread}")
    lines.append(f"{nature} Nature")
    lines += [f"- {m}" for m in moves]
    return "\n".join(lines)


def ladder_spreads(name, format_id, n=5):
    """The most common spreads for `name` as (nature, evs, share), from the month's usage data."""
    from metamatch.engine.sets import chaos_entry
    _, entry = chaos_entry(name, format_id)
    if not entry:
        return []
    total = sum(entry.get("Abilities", {}).values()) or 1
    out = []
    for spread, w in sorted(entry.get("Spreads", {}).items(), key=lambda kv: kv[1], reverse=True)[:n]:
        nature, _, vals = spread.partition(":")
        out.append((nature, dict(zip(STATS, (int(v) for v in vals.split("/")))), w / total))
    return out


def check_spread(base, nature, evs, benchmarks, format_id):
    """Which benchmarks a given spread already hits: [(label, passed, detail)]."""
    return Lab(base, benchmarks, format_id).recheck(nature, evs)

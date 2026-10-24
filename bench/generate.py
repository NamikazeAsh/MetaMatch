"""
Generates MetaBench questions with ground truth from the official @smogon/calc data
(via the calc sidecar and its exported dex) and the raw Smogon chaos files.
Nothing here uses MetaMatch's own reasoning code, so the benchmark can't grade itself.

Run: python bench/generate.py   (writes bench/questions.jsonl, deterministic for a given seed)
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from metamatch import config  # noqa: E402
from metamatch.engine import calc  # noqa: E402
from metamatch.engine.dex import get_dex, to_id  # noqa: E402

STATS = ["hp", "atk", "def", "spa", "spd", "spe"]
STAT_LABELS = {"hp": "HP", "atk": "Atk", "def": "Def", "spa": "SpA", "spd": "SpD", "spe": "Spe"}
FORMATS = ["gen9ou", "gen9championsou"]
POOL_SIZE = 40
PER_FORMAT = {"speed": 12, "ko": 12, "damage": 10, "type": 10, "usage": 8, "stat": 8}

# One ordinary attack per type, used to detect ability based immunities through the calc
PROBE_MOVES = {
    "Normal": "Hyper Voice", "Fire": "Flamethrower", "Water": "Surf", "Electric": "Thunderbolt",
    "Grass": "Energy Ball", "Ice": "Ice Beam", "Fighting": "Close Combat", "Poison": "Sludge Bomb",
    "Ground": "Earthquake", "Flying": "Air Slash", "Psychic": "Psychic", "Bug": "X-Scissor",
    "Rock": "Stone Edge", "Ghost": "Shadow Ball", "Dragon": "Dragon Pulse", "Dark": "Dark Pulse",
    "Steel": "Flash Cannon", "Fairy": "Moonblast",
}

INSTRUCTIONS = {
    "yesno": "End your reply with a final line that is exactly 'ANSWER: yes' or 'ANSWER: no'.",
    "speed": "End your reply with a final line that is exactly 'ANSWER: yes', 'ANSWER: no' or 'ANSWER: tie'.",
    "ko": "End your reply with a final line that is exactly 'ANSWER: yes', 'ANSWER: no' or 'ANSWER: sometimes' (sometimes means only some damage rolls KO).",
    "range": "End your reply with a final line in the form 'ANSWER: <min>-<max>%'.",
    "type": "End your reply with a final line that is exactly 'ANSWER: immune', 'ANSWER: resists', 'ANSWER: neutral' or 'ANSWER: weak'.",
    "name": "End your reply with a final line in the form 'ANSWER: <name>'.",
    "number": "End your reply with a final line in the form 'ANSWER: <number>'.",
}


def load_chaos(format_id):
    path = config.STATS_DIR / (config.format_info(format_id)["stats"] + ".json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["data"]


def ranked(counts, total):
    return [(k, v / total) for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True) if k and k != "nothing"]


class Mon:
    """A Pokemon's most common ladder set, straight from the chaos file."""

    def __init__(self, name, entry, dex, game):
        self.name, self.entry, self.dex, self.game = name, entry, dex, game
        total = sum(entry["Abilities"].values()) or 1
        self.spreads = ranked(entry["Spreads"], total)
        self.items = ranked(entry["Items"], total)
        self.abilities = ranked(entry["Abilities"], total)
        self.moves = ranked(entry["Moves"], total)
        self.teras = ranked(entry.get("Tera Types", {}), total)
        nature, _, vals = self.spreads[0][0].partition(":")
        self.nature = nature
        self.evs = {s: int(v) for s, v in zip(STATS, vals.split("/"))}
        self.item = dex.item_name(self.items[0][0]) if self.items else None
        self.ability = dex.ability_name(self.abilities[0][0]) if self.abilities else None
        self.move_names = [dex.move_name(m) for m, _ in self.moves if dex.move_name(m)]
        self.species = dex.species(name)

    def as_user(self):
        """How a player names their own Pokemon: base species, plus a note when it Mega Evolves."""
        base = self.species.get("baseSpecies") if "-Mega" in self.name else None
        return f"{base} (after Mega Evolving)" if base else self.name

    def spec(self):
        spec = {"name": self.name, "nature": self.nature, "evs": self.evs}
        if self.item:
            spec["item"] = self.item
        if self.ability:
            spec["ability"] = self.ability
        return spec

    def attacks(self):
        return [m for m in self.move_names if self.dex.move(m)["category"] != "Status"]

    def spread_text(self):
        unit = " SP" if self.game == "champions" else ""
        parts = [f"{v} {STAT_LABELS[s]}" for s, v in self.evs.items() if v]
        return f"{self.nature} nature, {' / '.join(parts)}{unit}"

    def paste(self, moves=None):
        """Showdown export of this set. Megas are written as the base species holding the stone."""
        base = self.species.get("baseSpecies") if "-Mega" in self.name else None
        header = base or self.name
        lines = [f"{header} @ {self.item}" if self.item else header]
        if self.ability and not base:
            lines.append(f"Ability: {self.ability}")
        if self.game != "champions" and self.teras:
            lines.append(f"Tera Type: {self.teras[0][0].capitalize()}")
        lines.append("EVs: " + " / ".join(f"{v} {STAT_LABELS[s]}" for s, v in self.evs.items() if v))
        lines.append(f"{self.nature} Nature")
        chosen = list(moves or [])
        for m in self.move_names:
            if len(chosen) >= 4:
                break
            if m not in chosen:
                chosen.append(m)
        lines += [f"- {m}" for m in chosen[:4]]
        return "\n".join(lines)


def build_pool(format_id):
    game = config.format_game(format_id)
    dex = get_dex(game)
    chaos = load_chaos(format_id)
    top = sorted(chaos.items(), key=lambda x: x[1].get("usage", 0), reverse=True)
    pool = []
    for name, entry in top:
        if not dex.species(name) or not entry.get("Spreads"):
            continue
        mon = Mon(name, entry, dex, game)
        if len(mon.move_names) >= 4 and mon.attacks():
            pool.append(mon)
        if len(pool) >= POOL_SIZE:
            break
    return pool, dex, game


def calc_one(game, attacker, defender, move):
    return calc.calculate({"game": game, "attacker": attacker, "defender": defender, "move": move})


def stats_of(game, mon):
    # Any legal move works: we only want the computed stats
    r = calc_one(game, mon.spec(), mon.spec(), mon.attacks()[0])
    return r["attacker_stats"] if r else None


def question(qid, format_id, category, team, text, answer, kind, meta=None):
    return {
        "id": qid, "format": format_id, "category": category, "team": team,
        "question": f"{text}\n\n{INSTRUCTIONS[kind]}", "answer": {"kind": kind, **answer}, "meta": meta or {},
    }


def gen_speed(rng, pool, game, format_id, label, n):
    out, tries = [], 0
    while len(out) < n and tries < 500:
        tries += 1
        a, b = rng.sample(pool, 2)
        sa, sb = stats_of(game, a), stats_of(game, b)
        if not sa or not sb:
            continue
        diff = sa["spe"] - sb["spe"]
        # Keep it interesting: close races, but not all ties
        if abs(diff) > 40 or (diff == 0 and any(q["answer"]["value"] == "tie" for q in out)):
            continue
        truth = "yes" if diff > 0 else "no" if diff < 0 else "tie"
        text = (f"In {label}, does my {a.as_user()} outspeed {b.name} if {b.name} runs its most common ladder spread? "
                f"Ignore items, abilities and field effects.")
        out.append(question(None, format_id, "speed", a.paste(), text, {"value": truth}, "speed",
                            {"user_speed": sa["spe"], "opp_speed": sb["spe"], "opp_spread": b.spread_text()}))
    return out


def gen_ko(rng, pool, game, format_id, label, n):
    out, tries, counts = [], 0, {"yes": 0, "no": 0, "sometimes": 0}
    cap = n // 3 + 1
    while len(out) < n and tries < 2000:
        tries += 1
        a, b = rng.sample(pool, 2)
        move = rng.choice(a.attacks())
        r = calc_one(game, a.spec(), b.spec(), move)
        if not r:
            continue
        lo, hi = r["percent"]
        truth = "yes" if lo >= 100 else "no" if hi < 100 else "sometimes"
        if counts[truth] >= cap:
            continue
        counts[truth] += 1
        text = (f"In {label}, does my {a.as_user()}'s {move} OHKO a full health {b.name} running its most common "
                f"spread, item and ability? Assume no boosts, no Tera and no field effects.")
        out.append(question(None, format_id, "ko", a.paste([move]), text, {"value": truth}, "ko",
                            {"percent": r["percent"], "desc": r["desc"]}))
    return out


def gen_damage(rng, pool, game, format_id, label, n):
    out, tries = [], 0
    while len(out) < n and tries < 500:
        tries += 1
        a, b = rng.sample(pool, 2)
        move = rng.choice(a.attacks())
        r = calc_one(game, a.spec(), b.spec(), move)
        if not r or r["percent"][1] <= 0:
            continue
        b_set = f"{b.name} @ {b.item}, {b.ability}, {b.spread_text()}"
        text = (f"In {label}, what percentage of its HP does my {a.as_user()}'s {move} do to this {b_set}? "
                f"Assume no boosts, no Tera and no field effects. Give the damage roll range.")
        out.append(question(None, format_id, "damage", a.paste([move]), text,
                            {"value": r["percent"], "tolerance": 3.0}, "range", {"desc": r["desc"]}))
    return out


def gen_type(rng, pool, dex, game, format_id, label, n):
    chart = dex_type_chart(game)
    out, tries, seen = [], 0, set()
    counts = {"immune": 0, "resists": 0, "neutral": 0, "weak": 0}
    cap = n // 4 + 1
    while len(out) < n and tries < 2000:
        tries += 1
        b = rng.choice(pool)
        atk_type = rng.choice(list(chart))
        if (b.name, atk_type) in seen:
            continue
        mult = 1.0
        for t in b.species["types"]:
            mult *= chart[atk_type][t]
        probe = PROBE_MOVES[atk_type]
        if mult > 0 and dex.move(probe):
            r = calc_one(game, {"name": "Garchomp"}, b.spec(), probe)
            if r and r["range"][1] == 0:
                mult = 0.0
        truth = "immune" if mult == 0 else "resists" if mult < 1 else "weak" if mult > 1 else "neutral"
        if counts[truth] >= cap:
            continue
        counts[truth] += 1
        seen.add((b.name, atk_type))
        text = (f"In {label}, my {b.as_user()} has the ability {b.ability}. Is it immune to, resistant to, neutral to "
                f"or weak to {atk_type} type attacks? Ignore Tera.")
        out.append(question(None, format_id, "type", b.paste(), text, {"value": truth}, "type",
                            {"multiplier": mult}))
    return out


def gen_usage(rng, pool, dex, format_id, label, n):
    out = []
    for mon in rng.sample(pool, len(pool)):
        if len(out) >= n:
            break
        # Only ask when the top item clearly leads, so the answer is unambiguous
        if len(mon.items) < 2 or mon.items[0][1] - mon.items[1][1] < 0.10 or not mon.item:
            continue
        text = f"In {label}, what is the most common held item on {mon.name} according to Smogon usage stats?"
        # The set goes in as the team so every arm knows which format is being asked about
        out.append(question(None, format_id, "usage", mon.paste(), text, {"value": mon.item}, "name",
                            {"share": round(mon.items[0][1], 3), "runner_up": mon.items[1][0]}))
    return out


def gen_stat(rng, pool, game, format_id, label, n):
    out = []
    # Prefer Megas in Champions, since their stats are the most often misremembered
    ordered = sorted(rng.sample(pool, len(pool)), key=lambda m: "-Mega" not in m.name)
    for mon in ordered[:n]:
        stats = stats_of(game, mon)
        if not stats:
            continue
        level = 50 if game == "champions" else 100
        mega = " after Mega Evolving" if "-Mega" in mon.name else ""
        text = f"In {label} (level {level}), what is my {mon.species.get('baseSpecies', mon.name)}'s Speed stat{mega}?"
        out.append(question(None, format_id, "stat", mon.paste(), text, {"value": stats["spe"], "tolerance": 1}, "number",
                            {"forme": mon.name}))
    return out


def dex_type_chart(game):
    with open(config.JSON_DIR / f"dex_{game}.json", encoding="utf-8") as f:
        return json.load(f)["typeChart"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default=str(ROOT / "bench" / "questions.jsonl"))
    args = parser.parse_args()
    if not calc.available():
        sys.exit("The damage calc is required: run `npm install` in src/metamatch/engine")

    rng = random.Random(args.seed)
    questions = []
    for format_id in FORMATS:
        label = config.format_info(format_id)["label"]
        label = f"Gen 9 {label}" if config.format_game(format_id) == "sv" else label
        pool, dex, game = build_pool(format_id)
        questions += gen_speed(rng, pool, game, format_id, label, PER_FORMAT["speed"])
        questions += gen_ko(rng, pool, game, format_id, label, PER_FORMAT["ko"])
        questions += gen_damage(rng, pool, game, format_id, label, PER_FORMAT["damage"])
        questions += gen_type(rng, pool, dex, game, format_id, label, PER_FORMAT["type"])
        questions += gen_usage(rng, pool, dex, format_id, label, PER_FORMAT["usage"])
        questions += gen_stat(rng, pool, game, format_id, label, PER_FORMAT["stat"])

    for i, q in enumerate(questions, 1):
        q["id"] = f"q{i:03d}"
    with open(args.out, "w", encoding="utf-8") as f:
        for q in questions:
            f.write(json.dumps(q) + "\n")

    summary = {}
    for q in questions:
        key = (q["format"], q["category"])
        summary[key] = summary.get(key, 0) + 1
    for (fmt, cat), count in sorted(summary.items()):
        print(f"{fmt:18} {cat:8} {count}")
    print(f"{len(questions)} questions -> {args.out}")


if __name__ == "__main__":
    main()

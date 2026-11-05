"""
Builds the frozen MetaBench fresh set (bench/questions_fresh.jsonl) from the October 2026 snapshot alone.

Independence: nothing here imports metamatch. Stats, natures, the Choice Scarf multiplier, type
effectiveness and ability immunities are computed in this file; damage rolls come from the raw
@smogon/calc package through bench/fresh_calc.js; usage facts come from the snapshotted chaos files
in bench/fixtures/stats_2026_10. Hand written items live in bench/fresh_handwritten.jsonl and are
merged as is.

Parts:
  generated    80 items, six kinds as in generate.py, Pokemon ranked 41 to 80 in the filtered usage pool
  hard         ~80 items: Scarf, opponent as subject, no move named, Sturdy and Sash, regional and Rotom
               formes, weather, terrain and screens, defensive Tera, nicknames (gen9ou, fully stated sets)
  handwritten  ~40 casual player style items with hand derived keys

Run: python bench/generate_fresh.py            (writes bench/questions_fresh.jsonl)
     python bench/generate_fresh.py --check    (rebuilds in memory and compares with the frozen file)
"""
import argparse
import collections
import hashlib
import itertools
import json
import random
import subprocess
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
SNAP = BENCH / "fixtures" / "stats_2026_10"
CALC_JS = BENCH / "fresh_calc.js"
HANDWRITTEN = BENCH / "fresh_handwritten.jsonl"
OUT = BENCH / "questions_fresh.jsonl"
SEED = 20261105

FORMATS = {
    "gen9ou": {"stats": "gen9ou-1825.json", "game": "sv", "label": "Gen 9 OU", "level": 100},
    "gen9championsou": {"stats": "gen9championsou-1760.json", "game": "champions", "label": "Champions OU", "level": 50},
}
STATS = ["hp", "atk", "def", "spa", "spd", "spe"]
LABELS = {"hp": "HP", "atk": "Atk", "def": "Def", "spa": "SpA", "spd": "SpD", "spe": "Spe"}
POOL_START, POOL_END = 40, 80  # filtered usage ranks 41 to 80; generate.py used the top 40
PER_FORMAT = {"speed": 8, "ko": 8, "damage": 7, "type": 7, "usage": 5, "stat": 5}

# Nature -> (raised stat, lowered stat)
NATURES = {
    "Hardy": (None, None), "Docile": (None, None), "Serious": (None, None), "Bashful": (None, None), "Quirky": (None, None),
    "Lonely": ("atk", "def"), "Brave": ("atk", "spe"), "Adamant": ("atk", "spa"), "Naughty": ("atk", "spd"),
    "Bold": ("def", "atk"), "Relaxed": ("def", "spe"), "Impish": ("def", "spa"), "Lax": ("def", "spd"),
    "Timid": ("spe", "atk"), "Hasty": ("spe", "def"), "Jolly": ("spe", "spa"), "Naive": ("spe", "spd"),
    "Modest": ("spa", "atk"), "Mild": ("spa", "def"), "Quiet": ("spa", "spe"), "Rash": ("spa", "spd"),
    "Calm": ("spd", "atk"), "Gentle": ("spd", "def"), "Sassy": ("spd", "spe"), "Careful": ("spd", "spa"),
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

# Moves whose damage depends on hidden state, turn order, randomness, HP, weight or charging, plus
# always crit moves (they contradict "no crits"). Any damaging move with base power 1 or less is also dropped.
DROP_MOVES = {
    "Bullet Seed", "Icicle Spear", "Rock Blast", "Scale Shot", "Population Bomb", "Pin Missile", "Tail Slap",
    "Bone Rush", "Water Shuriken", "Triple Axel", "Triple Kick", "Arm Thrust", "Double Slap", "Fury Attack",
    "Fury Swipes", "Comet Punch", "Barrage", "Spike Cannon", "Bolt Beak", "Fishious Rend", "Payback", "Avalanche",
    "Revenge", "Assurance", "Stomping Tantrum", "Lash Out", "Retaliate", "Temper Flare", "Rage Fist", "Last Respects",
    "Stored Power", "Power Trip", "Upper Hand", "Steel Roller", "Spit Up", "Beat Up", "Present", "Magnitude",
    "Natural Gift", "Fling", "Fury Cutter", "Rollout", "Ice Ball", "Trump Card", "Punishment", "Eruption",
    "Water Spout", "Dragon Energy", "Crush Grip", "Wring Out", "Hard Press", "Final Gambit", "Endeavor",
    "Super Fang", "Ruination", "Nature's Madness", "Counter", "Mirror Coat", "Metal Burst", "Comeuppance",
    "Seismic Toss", "Night Shade", "Psywave", "Electro Ball", "Gyro Ball", "Grass Knot", "Low Kick", "Heavy Slam",
    "Heat Crash", "Pursuit", "Echoed Voice", "Round", "Tera Blast", "Future Sight", "Doom Desire", "Sky Drop",
    "Shell Trap", "Beak Blast", "Belch", "Synchronoise", "Dream Eater", "Snore", "Surging Strikes", "Wicked Blow",
    "Flower Trick", "Frost Breath", "Storm Throw", "Zippy Zap", "Solar Beam", "Solar Blade", "Meteor Beam",
    "Electro Shot", "Sky Attack", "Razor Wind", "Skull Bash", "Freeze Shock", "Ice Burn", "Focus Punch",
    "Smelling Salts", "Wake-Up Slap", "Hex", "Venoshock", "Barb Barrage", "Infernal Parade", "Bitter Malice",
    "Brine", "Fake Out", "First Impression", "Burning Jealousy", "Lunge", "Acrobatics", "Hydro Steam", "Psyblade",
    "Weather Ball", "Terrain Pulse", "Expanding Force", "Rising Voltage", "Grav Apple", "Misty Explosion",
    "Explosion", "Self-Destruct", "Steel Beam", "Mind Blown", "Struggle", "Dragon Darts", "Raging Bull",
}
# Abilities that make "no boosts, no field effects" ambiguous or that the calc only models with extra flags
AMBIG_ABILITIES = {
    "Protean", "Libero", "Analytic", "Stakeout", "Download", "Intrepid Sword", "Dauntless Shield", "Drought",
    "Drizzle", "Sand Stream", "Snow Warning", "Orichalcum Pulse", "Hadron Engine", "Electric Surge", "Psychic Surge",
    "Grassy Surge", "Misty Surge", "Seed Sower", "Sand Spit", "Intimidate", "Disguise", "Ice Face", "Tera Shell",
    "Wonder Guard", "Neutralizing Gas", "Zero to Hero", "Illusion", "Imposter", "Mimicry", "Forecast", "Costar",
    "Commander", "Supersweet Syrup", "Moody", "Rivalry", "Stance Change", "Schooling", "Power Construct",
    "Battle Bond", "Gulp Missile", "Flower Gift", "Sturdy", "Unburden", "Slow Start", "Truant", "Defeatist",
}
AMBIG_ITEMS = {"Booster Energy", "Focus Sash", "Room Service", "Adrenaline Orb", "White Herb", "Mirror Herb"}

ABILITY_IMMUNE = {
    "Levitate": "Ground", "Earth Eater": "Ground", "Flash Fire": "Fire", "Well-Baked Body": "Fire",
    "Water Absorb": "Water", "Storm Drain": "Water", "Dry Skin": "Water", "Volt Absorb": "Electric",
    "Lightning Rod": "Electric", "Motor Drive": "Electric", "Sap Sipper": "Grass",
}
# Abilities that scale a type's damage without making it 0: the type question becomes a matter of taste, so drop
ABILITY_PARTIAL = {
    "Thick Fat": {"Fire", "Ice"}, "Heatproof": {"Fire"}, "Water Bubble": {"Fire"}, "Purifying Salt": {"Ghost"},
    "Dry Skin": {"Fire"}, "Fluffy": {"Fire"},
}
FILTER_LIKE = {"Filter", "Solid Rock", "Prism Armor"}
MOLD_BREAKERS = {"Mold Breaker", "Teravolt", "Turboblaze"}

# ---------------------------------------------------------------- snapshot and own mechanics


def sha256_text(path):
    """Hash with line endings normalised, so a CRLF checkout does not change the frozen hash."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify_snapshot():
    manifest = json.loads((SNAP / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["files"].items():
        if sha256_text(SNAP / name) != digest:
            sys.exit(f"Snapshot file changed: {name}")
    return manifest


def to_id(text):
    return "".join(c for c in (text or "").lower() if c.isalnum())


class Dex:
    def __init__(self, game):
        data = json.loads((SNAP / f"dex_{game}.json").read_text(encoding="utf-8"))
        self.game = game
        self.species_data, self.move_data, self.item_data = data["species"], data["moves"], data["items"]
        self.chart = data["typeChart"]  # attacking type -> defending type -> multiplier
        self._species = {to_id(n): n for n in self.species_data}
        self._moves = {to_id(n): n for n in self.move_data}
        self._items = {to_id(n): n for n in self.item_data}
        self._abilities = {to_id(n): n for n in data["abilities"]}

    def species(self, name):
        display = self._species.get(to_id(name))
        return {"name": display, **self.species_data[display]} if display else None

    def move(self, name):
        display = self._moves.get(to_id(name))
        return {"name": display, **self.move_data[display]} if display else None

    def move_name(self, name):
        return self._moves.get(to_id(name))

    def item_name(self, name):
        return self._items.get(to_id(name))

    def ability_name(self, name):
        return self._abilities.get(to_id(name))


def calc_stat(game, stat, base, ev, nature, level):
    """Game stat formula with 31 IVs. In Champions 'ev' is stat points and the level is fixed at 50."""
    plus, minus = NATURES[nature]
    if game == "champions":
        if stat == "hp":
            return 1 if base == 1 else base + ev + 75
        raw = base + ev + 20
    else:
        core = (2 * base + 31 + ev // 4) * level // 100
        if stat == "hp":
            return 1 if base == 1 else core + level + 10
        raw = core + 5
    if plus == stat and minus != stat:
        return raw * 110 // 100
    if minus == stat and plus != stat:
        return raw * 90 // 100
    return raw


def all_stats(dex, name, nature, evs, level):
    base = dex.species(name)["baseStats"]
    return {s: calc_stat(dex.game, s, base[s], evs.get(s, 0), nature, level) for s in STATS}


def scarf(speed):
    # Choice Scarf is a 1.5x chain modifier; the game rounds .5 down, so this is a floor
    return speed * 3 // 2


def type_mult(dex, atk_type, def_types):
    mult = 1.0
    for t in def_types:
        mult *= dex.chart[atk_type][t]
    return mult


def type_verdict(dex, atk_type, def_types, ability, item=None):
    """'immune' / 'resists' / 'neutral' / 'weak', or None when an ability or item makes it a judgement call."""
    mult = type_mult(dex, atk_type, def_types)
    if ability in ("Tera Shell", "Wonder Guard") or (ability in FILTER_LIKE and mult > 1):
        return None
    if atk_type in ABILITY_PARTIAL.get(ability, set()):
        return None
    if atk_type == "Ground" and item in ("Air Balloon", "Iron Ball"):
        return None
    if mult > 0 and ABILITY_IMMUNE.get(ability) == atk_type:
        mult = 0.0
    return "immune" if mult == 0 else "resists" if mult < 1 else "weak" if mult > 1 else "neutral"


def run_calc(requests):
    """Batch of damage requests through the raw @smogon/calc bridge."""
    if not requests:
        return []
    proc = subprocess.run(["node", str(CALC_JS)], input=json.dumps(requests), capture_output=True, text=True,
                          encoding="utf-8", check=True)
    return json.loads(proc.stdout)


def evs_text(evs, game="sv"):
    unit = " SP" if game == "champions" else ""
    return " / ".join(f"{evs[s]} {LABELS[s]}" for s in STATS if evs.get(s)) + unit


def art(word):
    return f"an {word}" if word[:1].upper() in "AEIOU" else f"a {word}"


def question(fmt, category, split, tags, team, text, kind, answer, meta):
    return {"id": None, "format": fmt, "category": category, "split": split, "tags": tags, "team": team,
            "question": f"{text}\n\n{INSTRUCTIONS[kind]}", "answer": {"kind": kind, **answer}, "meta": meta}


def classify_ko(lo, hi, hp, margin=0.02):
    """'yes' if every roll KOs with margin, 'no' if no roll comes near, else None (dropped)."""
    if lo >= hp * (1 + margin):
        return "yes"
    if hi <= hp * (1 - margin):
        return "no"
    return None


def usable_move(dex, name):
    m = dex.move(name)
    return bool(m) and m["category"] != "Status" and m["basePower"] > 1 and m["name"] not in DROP_MOVES


# ---------------------------------------------------------------- part 1: generated, usage ranks 41 to 80


def ranked(counts, total):
    return [(k, v / total) for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True) if k and k != "nothing"]


class Mon:
    """A Pokemon's most common ladder set from the snapshotted chaos file."""

    def __init__(self, name, entry, dex, game, level):
        self.name, self.dex, self.game, self.level = name, dex, game, level
        total = sum(entry["Abilities"].values()) or 1
        raw_items = sorted(entry["Items"].items(), key=lambda x: x[1], reverse=True)
        self.top_item_raw = raw_items[0][0] if raw_items else ""
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
        self.is_mega = "-Mega" in self.species["name"]
        self.base = self.species.get("baseSpecies") if self.is_mega else None

    def as_user(self):
        return f"{self.base} (after Mega Evolving)" if self.base else self.name

    def stats(self):
        return all_stats(self.dex, self.name, self.nature, self.evs, self.level)

    def spec(self):
        spec = {"name": self.species["name"], "nature": self.nature, "evs": self.evs}
        if self.item:
            spec["item"] = self.item
        if self.ability:
            spec["ability"] = self.ability
        return spec

    def attacks(self):
        return [m for m in self.move_names if usable_move(self.dex, m)]

    def spread_text(self):
        return f"{self.nature} nature, {evs_text(self.evs, self.game)}"

    def clean(self):
        """True when the set has nothing that makes a no boost, no field calc ambiguous."""
        return self.ability not in AMBIG_ABILITIES and self.item not in AMBIG_ITEMS

    def paste(self, moves=None):
        header = self.base or self.name
        lines = [f"{header} @ {self.item}" if self.item else header]
        if self.ability and not self.base:
            lines.append(f"Ability: {self.ability}")
        if self.game != "champions" and self.teras:
            lines.append(f"Tera Type: {self.teras[0][0].capitalize()}")
        lines.append("EVs: " + " / ".join(f"{self.evs[s]} {LABELS[s]}" for s in STATS if self.evs[s]))
        lines.append(f"{self.nature} Nature")
        chosen = list(moves or [])
        for m in self.move_names:
            if len(chosen) >= 4:
                break
            if m not in chosen:
                chosen.append(m)
        lines += [f"- {m}" for m in chosen[:4]]
        return "\n".join(lines)


def build_pool(fmt):
    info = FORMATS[fmt]
    dex = Dex(info["game"])
    chaos = json.loads((SNAP / info["stats"]).read_text(encoding="utf-8"))["data"]
    top = sorted(chaos.items(), key=lambda x: x[1].get("usage", 0), reverse=True)
    pool = []
    for name, entry in top:
        if not dex.species(name) or not entry.get("Spreads"):
            continue
        mon = Mon(name, entry, dex, info["game"], info["level"])
        if len(mon.move_names) >= 4 and any(dex.move(m)["category"] != "Status" for m in mon.move_names):
            pool.append(mon)
        if len(pool) >= POOL_END:
            break
    return pool[POOL_START:POOL_END], dex


def gen_part1(rng):
    out = []
    for fmt, info in FORMATS.items():
        pool, dex = build_pool(fmt)
        game, label = info["game"], info["label"]
        tag = ["usage_rank_41_80"]

        # speed: no ties (dropped), close races
        made, seen, counts = 0, set(), {"yes": 0, "no": 0}
        for _ in range(3000):
            if made >= PER_FORMAT["speed"]:
                break
            a, b = rng.sample(pool, 2)
            if (a.name, b.name) in seen:
                continue
            sa, sb = a.stats()["spe"], b.stats()["spe"]
            diff = sa - sb
            if diff == 0:
                DROPS['speed_tie'] += 1
            if diff == 0 or abs(diff) > 40:
                continue
            truth = "yes" if diff > 0 else "no"
            if counts[truth] >= PER_FORMAT["speed"] // 2:
                continue
            seen.add((a.name, b.name))
            counts[truth] += 1
            made += 1
            text = (f"In {label}, does my {a.as_user()} outspeed {b.name} if {b.name} runs its most common ladder spread? "
                    f"Ignore items, abilities and field effects.")
            out.append(question(fmt, "speed", "generated", tag, a.paste(), text, "speed", {"value": truth},
                                {"user_speed": sa, "opp_speed": sb, "opp_spread": b.spread_text()}))

        # ko and damage: one calc batch over candidate triples, then pick
        cands = []
        for a, b in itertools.permutations(pool, 2):
            if not (a.clean() and b.clean()) or not b.item or b.top_item_raw in ("", "nothing"):
                DROPS["ambiguous_set_pair"] += 1
                continue
            for m in a.attacks():
                cands.append((a, b, m))
        rng.shuffle(cands)
        cands = cands[:400]
        res = run_calc([{"game": game, "attacker": a.spec(), "defender": b.spec(), "move": m} for a, b, m in cands])
        ko_made, ko_counts, dmg_made, used = 0, {"yes": 0, "no": 0}, 0, set()
        for (a, b, m), r in zip(cands, res):
            if not r["ok"] or r["range"][1] <= 0 or (a.name, b.name) in used:
                continue
            check_stats(r, a, b)
            hp = r["maxHP"]
            lo, hi = r["range"]
            pct = [lo * 1000 // hp / 10, hi * 1000 // hp / 10]
            if ko_made < PER_FORMAT["ko"]:
                truth = classify_ko(lo, hi, hp)
                if truth is None:
                    DROPS["ko_straddles_or_within_2pct"] += 1
                if truth and ko_counts[truth] < PER_FORMAT["ko"] // 2:
                    ko_counts[truth] += 1
                    ko_made += 1
                    used.add((a.name, b.name))
                    text = (f"In {label}, does my {a.as_user()}'s {m} OHKO a full health {b.name} running its most common "
                            f"spread, item and ability? Assume no boosts, no Tera and no field effects.")
                    out.append(question(fmt, "ko", "generated", tag, a.paste([m]), text, "ko", {"value": truth},
                                        {"percent": pct, "defender_set": f"{b.item}, {b.ability}, {b.spread_text()}"}))
                    continue
            if dmg_made < PER_FORMAT["damage"]:
                dmg_made += 1
                used.add((a.name, b.name))
                b_set = f"{b.name} @ {b.item}, {b.ability}, {b.spread_text()}"
                text = (f"In {label}, what percentage of its HP does my {a.as_user()}'s {m} do to this {b_set}? "
                        f"Assume no boosts, no Tera and no field effects. Give the damage roll range.")
                out.append(question(fmt, "damage", "generated", tag, a.paste([m]), text, "range",
                                    {"value": pct, "tolerance": 3.0}, {"range_hp": [lo, hi], "max_hp": hp}))
            if ko_made >= PER_FORMAT["ko"] and dmg_made >= PER_FORMAT["damage"]:
                break

        # type
        made, seen, counts = 0, set(), {"immune": 0, "resists": 0, "neutral": 0, "weak": 0}
        types = list(dex.chart)
        for _ in range(5000):
            if made >= PER_FORMAT["type"]:
                break
            b = rng.choice(pool)
            t = rng.choice(types)
            if (b.name, t) in seen or not b.ability:
                continue
            truth = type_verdict(dex, t, b.species["types"], b.ability, b.item)
            if truth is None:
                DROPS["type_ability_or_item_ambiguous"] += 1
            if truth is None or counts[truth] >= PER_FORMAT["type"] // 4 + 1:
                continue
            seen.add((b.name, t))
            counts[truth] += 1
            made += 1
            text = (f"In {label}, my {b.as_user()} has the ability {b.ability}. Is it immune to, resistant to, neutral to "
                    f"or weak to {t} type attacks? Ignore Tera.")
            out.append(question(fmt, "type", "generated", tag, b.paste(), text, "type", {"value": truth},
                                {"types": b.species["types"], "multiplier": type_mult(dex, t, b.species["types"])}))

        # usage: top item must lead the runner up by 10 points and not be "nothing"
        made = 0
        for mon in rng.sample(pool, len(pool)):
            if made >= PER_FORMAT["usage"]:
                break
            if len(mon.items) < 2 or not mon.item or mon.top_item_raw in ("", "nothing"):
                continue
            if mon.items[0][1] - mon.items[1][1] < 0.10:
                continue
            made += 1
            text = f"In {label}, what is the most common held item on {mon.name} according to Smogon usage stats?"
            out.append(question(fmt, "usage", "generated", tag, mon.paste(), text, "name", {"value": mon.item},
                                {"share": round(mon.items[0][1], 3), "runner_up": mon.items[1][0]}))

        # stat: Megas first in Champions, as in generate.py
        ordered = sorted(rng.sample(pool, len(pool)), key=lambda m: not m.is_mega)
        for mon in ordered[:PER_FORMAT["stat"]]:
            mega = " after Mega Evolving" if mon.is_mega else ""
            name = mon.base or mon.name
            text = f"In {label} (level {info['level']}), what is my {name}'s Speed stat{mega}?"
            out.append(question(fmt, "stat", "generated", tag, mon.paste(), text, "number",
                                {"value": mon.stats()["spe"], "tolerance": 1}, {"forme": mon.species["name"]}))
    return out


STAT_MISMATCHES = []
DROPS = collections.Counter()  # candidates rejected for ambiguity, reported on stderr


def check_stats(r, a, b):
    """Cross check: our own stat formula must agree with the calc on both Pokemon."""
    for mon, key in ((a, "attacker_stats"), (b, "defender_stats")):
        mine = mon.stats() if isinstance(mon, Mon) else mon.stats()
        if mine != r[key]:
            STAT_MISMATCHES.append((mon.name, mine, r[key]))


# ---------------------------------------------------------------- part 2: hard items, fully stated gen9ou sets


class Set:
    def __init__(self, name, item, ability, nature, evs, moves, tera=None, nick=None):
        self.name, self.item, self.ability, self.nature, self.moves, self.tera, self.nick = (
            name, item, ability, nature, moves, tera, nick)
        self.evs = {s: 0 for s in STATS}
        for part in evs.split("/"):
            v, s = part.split()
            self.evs[{v2: k for k, v2 in LABELS.items()}[s]] = int(v)
        self.dex = DEX_SV

    def stats(self):
        return all_stats(self.dex, self.name, self.nature, self.evs, 100)

    def spec(self, tera=False):
        spec = {"name": self.name, "nature": self.nature, "evs": self.evs, "item": self.item, "ability": self.ability}
        if tera and self.tera:
            spec["teraType"] = self.tera
        return spec

    def with_(self, **kw):
        s = Set.__new__(Set)
        s.__dict__.update(self.__dict__)
        s.evs = dict(self.evs)
        s.__dict__.update(kw)
        return s

    def paste(self):
        head = f"{self.nick} ({self.name})" if self.nick else self.name
        lines = [f"{head} @ {self.item}", f"Ability: {self.ability}"]
        if self.tera:
            lines.append(f"Tera Type: {self.tera}")
        lines += ["EVs: " + evs_text(self.evs), f"{self.nature} Nature"] + [f"- {m}" for m in self.moves]
        return "\n".join(lines)

    def text(self, moves=True):
        """Inline description of a fully stated opponent set."""
        out = f"{self.name} @ {self.item} (Ability: {self.ability}, {self.nature} nature, {evs_text(self.evs)}"
        if moves:
            out += ", moves: " + ", ".join(self.moves)
        return out + ")"

    def attacks(self):
        return [m for m in self.moves if usable_move(self.dex, m)]


DEX_SV = Dex("sv")
SETS = {s.name: s for s in [
    Set("Great Tusk", "Heavy-Duty Boots", "Protosynthesis", "Jolly", "252 Atk / 4 Def / 252 Spe",
        ["Headlong Rush", "Close Combat", "Ice Spinner", "Rapid Spin"], "Steel"),
    Set("Dragapult", "Choice Specs", "Infiltrator", "Timid", "252 SpA / 4 SpD / 252 Spe",
        ["Draco Meteor", "Shadow Ball", "Flamethrower", "U-turn"], "Ghost"),
    Set("Gholdengo", "Choice Scarf", "Good as Gold", "Timid", "252 SpA / 4 SpD / 252 Spe",
        ["Make It Rain", "Shadow Ball", "Focus Blast", "Trick"], "Steel"),
    Set("Kingambit", "Leftovers", "Supreme Overlord", "Adamant", "252 HP / 252 Atk / 4 SpD",
        ["Kowtow Cleave", "Sucker Punch", "Iron Head", "Swords Dance"], "Dark"),
    Set("Garchomp", "Rocky Helmet", "Rough Skin", "Jolly", "252 Atk / 4 SpD / 252 Spe",
        ["Earthquake", "Outrage", "Stone Edge", "Swords Dance"], "Steel"),
    Set("Iron Valiant", "Life Orb", "Quark Drive", "Timid", "252 SpA / 4 SpD / 252 Spe",
        ["Moonblast", "Psyshock", "Aura Sphere", "Shadow Ball"], "Fairy"),
    Set("Corviknight", "Leftovers", "Pressure", "Impish", "248 HP / 168 Def / 92 SpD",
        ["Brave Bird", "Body Press", "Roost", "U-turn"], "Dragon"),
    Set("Rotom-Wash", "Leftovers", "Levitate", "Bold", "252 HP / 212 Def / 44 Spe",
        ["Hydro Pump", "Volt Switch", "Will-O-Wisp", "Pain Split"], "Steel"),
    Set("Rotom-Heat", "Choice Scarf", "Levitate", "Timid", "252 SpA / 4 SpD / 252 Spe",
        ["Overheat", "Volt Switch", "Thunderbolt", "Trick"], "Fire"),
    Set("Samurott-Hisui", "Focus Sash", "Sharpness", "Jolly", "252 Atk / 4 SpD / 252 Spe",
        ["Ceaseless Edge", "Razor Shell", "Sucker Punch", "Aqua Jet"], "Ghost"),
    Set("Slowking-Galar", "Heavy-Duty Boots", "Regenerator", "Sassy", "252 HP / 4 Def / 252 SpD",
        ["Sludge Bomb", "Flamethrower", "Psychic", "Chilly Reception"], "Water"),
    Set("Moltres-Galar", "Heavy-Duty Boots", "Berserk", "Timid", "252 SpA / 4 SpD / 252 Spe",
        ["Fiery Wrath", "Hurricane", "Nasty Plot", "Agility"], "Dark"),
    Set("Weavile", "Choice Band", "Pressure", "Jolly", "252 Atk / 4 SpD / 252 Spe",
        ["Knock Off", "Icicle Crash", "Ice Shard", "Ice Spinner"], "Ice"),
    Set("Dragonite", "Heavy-Duty Boots", "Multiscale", "Adamant", "252 Atk / 4 Def / 252 Spe",
        ["Extreme Speed", "Earthquake", "Fire Punch", "Dragon Dance"], "Normal"),
    Set("Heatran", "Leftovers", "Flash Fire", "Calm", "252 HP / 4 SpA / 252 SpD",
        ["Magma Storm", "Earth Power", "Stealth Rock", "Protect"], "Grass"),
    Set("Toxapex", "Black Sludge", "Regenerator", "Bold", "252 HP / 252 Def / 4 SpD",
        ["Surf", "Toxic", "Recover", "Haze"], "Fairy"),
    Set("Skarmory", "Rocky Helmet", "Sturdy", "Impish", "252 HP / 252 Def / 4 SpD",
        ["Brave Bird", "Body Press", "Spikes", "Roost"], "Dragon"),
    Set("Excadrill", "Choice Scarf", "Mold Breaker", "Jolly", "252 Atk / 4 SpD / 252 Spe",
        ["Earthquake", "Iron Head", "Rock Slide", "Rapid Spin"], "Ground"),
    Set("Glimmora", "Focus Sash", "Toxic Debris", "Timid", "252 SpA / 4 SpD / 252 Spe",
        ["Power Gem", "Sludge Wave", "Earth Power", "Mortal Spin"], "Ghost"),
    Set("Volcarona", "Heavy-Duty Boots", "Flame Body", "Timid", "252 SpA / 4 SpD / 252 Spe",
        ["Fiery Dance", "Bug Buzz", "Giga Drain", "Quiver Dance"], "Grass"),
    Set("Clefable", "Leftovers", "Magic Guard", "Bold", "252 HP / 252 Def / 4 SpD",
        ["Moonblast", "Flamethrower", "Moonlight", "Calm Mind"], "Steel"),
    Set("Iron Moth", "Heavy-Duty Boots", "Quark Drive", "Timid", "124 Def / 132 SpA / 252 Spe",
        ["Fiery Dance", "Sludge Wave", "Energy Ball", "Substitute"], "Grass"),
    Set("Ogerpon-Wellspring", "Wellspring Mask", "Water Absorb", "Jolly", "252 Atk / 4 SpD / 252 Spe",
        ["Ivy Cudgel", "Horn Leech", "Knock Off", "Swords Dance"], "Water"),
    Set("Kyurem", "Heavy-Duty Boots", "Pressure", "Timid", "252 SpA / 4 SpD / 252 Spe",
        ["Freeze-Dry", "Earth Power", "Ice Beam", "Draco Meteor"], "Ground"),
    Set("Cinderace", "Heavy-Duty Boots", "Blaze", "Jolly", "252 Atk / 4 SpD / 252 Spe",
        ["Pyro Ball", "U-turn", "Court Change", "Sucker Punch"], "Fire"),
    Set("Magnezone", "Leftovers", "Sturdy", "Modest", "252 HP / 252 SpA / 4 SpD",
        ["Thunderbolt", "Flash Cannon", "Volt Switch", "Body Press"], "Flying"),
    Set("Forretress", "Rocky Helmet", "Sturdy", "Relaxed", "252 HP / 252 Def / 4 SpD",
        ["Body Press", "Volt Switch", "Spikes", "Rapid Spin"], "Water"),
    Set("Donphan", "Leftovers", "Sturdy", "Impish", "252 HP / 252 Def / 4 SpD",
        ["Earthquake", "Knock Off", "Ice Spinner", "Rapid Spin"], "Ghost"),
    Set("Arcanine-Hisui", "Choice Band", "Rock Head", "Jolly", "252 Atk / 4 Def / 252 Spe",
        ["Head Smash", "Flare Blitz", "Extreme Speed", "Close Combat"], "Rock"),
    Set("Weezing-Galar", "Black Sludge", "Levitate", "Bold", "252 HP / 252 Def / 4 SpD",
        ["Strange Steam", "Will-O-Wisp", "Toxic Spikes", "Pain Split"], "Steel"),
    Set("Typhlosion-Hisui", "Choice Specs", "Frisk", "Timid", "252 SpA / 4 SpD / 252 Spe",
        ["Shadow Ball", "Fire Blast", "Focus Blast", "Flamethrower"], "Fire"),
    Set("Iron Bundle", "Choice Specs", "Quark Drive", "Timid", "252 SpA / 4 SpD / 252 Spe",
        ["Hydro Pump", "Freeze-Dry", "Ice Beam", "Flip Turn"], "Ice"),
    Set("Landorus-Therian", "Choice Scarf", "Intimidate", "Jolly", "252 Atk / 4 SpD / 252 Spe",
        ["Earthquake", "U-turn", "Stone Edge", "Stealth Rock"], "Flying"),
    Set("Meowscarada", "Choice Band", "Overgrow", "Jolly", "252 Atk / 4 SpD / 252 Spe",
        ["Knock Off", "Leaf Blade", "U-turn", "Play Rough"], "Grass"),
    Set("Roaring Moon", "Heavy-Duty Boots", "Protosynthesis", "Jolly", "252 Atk / 4 SpD / 252 Spe",
        ["Knock Off", "Earthquake", "Dragon Dance", "Roost"], "Flying"),
    Set("Darkrai", "Life Orb", "Bad Dreams", "Timid", "252 SpA / 4 SpD / 252 Spe",
        ["Dark Pulse", "Sludge Bomb", "Focus Blast", "Nasty Plot"], "Poison"),
    Set("Zamazenta", "Leftovers", "Dauntless Shield", "Jolly", "252 HP / 88 Def / 168 Spe",
        ["Body Press", "Iron Defense", "Heavy Slam", "Crunch"], "Fire"),
    Set("Ninetales-Alola", "Light Clay", "Snow Warning", "Timid", "252 SpA / 4 SpD / 252 Spe",
        ["Blizzard", "Moonblast", "Aurora Veil", "Freeze-Dry"], "Water"),
    Set("Pelipper", "Damp Rock", "Drizzle", "Bold", "252 HP / 252 Def / 4 SpD",
        ["Surf", "Hurricane", "U-turn", "Roost"], "Ground"),
    Set("Primarina", "Leftovers", "Torrent", "Calm", "252 HP / 4 SpA / 252 SpD",
        ["Moonblast", "Surf", "Calm Mind", "Draining Kiss"], "Poison"),
    Set("Iron Treads", "Leftovers", "Quark Drive", "Jolly", "252 HP / 4 Atk / 252 Spe",
        ["Earthquake", "Iron Head", "Knock Off", "Rapid Spin"], "Ground"),
    Set("Hatterene", "Leftovers", "Magic Bounce", "Bold", "252 HP / 252 Def / 4 SpA",
        ["Draining Kiss", "Psyshock", "Calm Mind", "Mystical Fire"], "Water"),
    Set("Raging Bolt", "Leftovers", "Protosynthesis", "Modest", "252 HP / 252 SpA / 4 SpD",
        ["Thunderclap", "Draco Meteor", "Thunderbolt", "Calm Mind"], "Fairy"),
    Set("Breloom", "Focus Sash", "Technician", "Jolly", "252 Atk / 4 SpD / 252 Spe",
        ["Mach Punch", "Seed Bomb", "Rock Tomb", "Spore"], "Fighting"),
]}
# Defenders allowed in damage items (no ambiguous items or abilities)
CALC_SAFE = [s for s in SETS.values() if s.ability not in AMBIG_ABILITIES and s.item not in AMBIG_ITEMS]

# Opponent speed spreads stated in the question: (species, nature, Spe EVs)
OPP_SPEEDS = [
    ("Dragapult", "Timid", 252), ("Great Tusk", "Jolly", 252), ("Iron Valiant", "Timid", 252),
    ("Gholdengo", "Timid", 252), ("Kingambit", "Adamant", 0), ("Garchomp", "Jolly", 252),
    ("Cinderace", "Jolly", 252), ("Meowscarada", "Jolly", 252), ("Roaring Moon", "Jolly", 252),
    ("Iron Bundle", "Timid", 252), ("Volcarona", "Timid", 252), ("Iron Moth", "Timid", 252),
    ("Excadrill", "Jolly", 252), ("Weavile", "Jolly", 252), ("Dragonite", "Adamant", 252),
    ("Landorus-Therian", "Jolly", 252), ("Heatran", "Timid", 252), ("Kyurem", "Timid", 252),
    ("Zamazenta", "Jolly", 252), ("Darkrai", "Timid", 252), ("Rotom-Wash", "Bold", 44),
    ("Corviknight", "Impish", 0), ("Iron Treads", "Jolly", 252), ("Ogerpon-Wellspring", "Jolly", 252),
    ("Raging Bolt", "Modest", 0), ("Primarina", "Modest", 0), ("Hatterene", "Bold", 0),
    ("Skarmory", "Impish", 0), ("Toxapex", "Bold", 0), ("Clefable", "Bold", 0), ("Slowking-Galar", "Sassy", 0),
    ("Glimmora", "Timid", 252), ("Moltres-Galar", "Timid", 252), ("Samurott-Hisui", "Jolly", 252),
    ("Iron Crown", "Timid", 252), ("Latios", "Timid", 252), ("Zapdos", "Timid", 252),
    ("Tornadus-Therian", "Timid", 252), ("Hydreigon", "Timid", 252), ("Enamorus", "Timid", 252),
    ("Hoopa-Unbound", "Hasty", 252), ("Rillaboom", "Adamant", 252), ("Ninetales-Alola", "Timid", 252),
    ("Sinistcha", "Bold", 0), ("Garganacl", "Careful", 0), ("Ting-Lu", "Careful", 0), ("Tinkaton", "Jolly", 252),
]


def opp_speed(name, nature, ev):
    return all_stats(DEX_SV, name, nature, {"spe": ev}, 100)["spe"]


def spe_phrase(name, nature, ev):
    return f"{nature} nature with {ev} Spe EVs"


def speed_items(rng):
    out = []
    users = list(SETS.values())
    nonscarf = [s for s in users if s.item != "Choice Scarf"]
    scarf_users = [s.with_(item="Choice Scarf") if s.item != "Choice Scarf" else s for s in users
                   if s.stats()["spe"] >= 200]

    def pick(pool_users, n, keep, make, tag_list, seen):
        made, counts, used_users = 0, {"yes": 0, "no": 0}, {}
        pairs = [(u, o) for u in pool_users for o in OPP_SPEEDS if o[0] != u.name]
        rng.shuffle(pairs)
        for u, o in pairs:
            if made >= n:
                break
            if (u.name, o[0]) in seen or used_users.get(u.name, 0) >= 2:
                continue
            r = keep(u, o)
            if r is None:
                continue
            truth, meta = r
            if counts[truth] >= (n + 1) // 2 + 1:
                continue
            seen.add((u.name, o[0]))
            used_users[u.name] = used_users.get(u.name, 0) + 1
            counts[truth] += 1
            made += 1
            out.append(make(u, o, truth, meta))

    seen = set()

    # user holds Choice Scarf (in the paste); only pairs where the Scarf decides or confirms the race
    def keep_scarf_user(u, o):
        us, os_ = u.stats()["spe"], opp_speed(*o)
        eff = scarf(us)
        if eff == os_ or us == os_:
            DROPS["speed_tie"] += 1
        if eff == os_ or abs(eff - os_) > 60 or us == os_:
            return None
        truth = "yes" if eff > os_ else "no"
        flips = (us > os_) != (eff > os_)
        if not flips and rng.random() < 0.7:
            return None
        return truth, {"user_speed": us, "user_speed_scarf": eff, "opp_speed": os_, "scarf_flips": flips}

    def make_scarf_user(u, o, truth, meta):
        text = (f"In Gen 9 OU, does my {u.name} outspeed {o[0]} if {o[0]} runs {spe_phrase(*o)} and no speed item? "
                f"Count my held item. All IVs are 31; no stat boosts, abilities or field effects.")
        return question("gen9ou", "speed", "hard", ["scarf_user"], u.paste(), text, "speed", {"value": truth}, meta)

    pick(scarf_users, 8, keep_scarf_user, make_scarf_user, None, seen)

    # opponent holds Choice Scarf (stated)
    def keep_scarf_opp(u, o):
        us, os_ = u.stats()["spe"], opp_speed(*o)
        eff = scarf(os_)
        if eff == us or us == os_:
            DROPS["speed_tie"] += 1
        if eff == us or abs(eff - us) > 60 or us == os_:
            return None
        truth = "yes" if us > eff else "no"
        flips = (us > os_) != (us > eff)
        if not flips and (us < os_ or rng.random() < 0.5):
            return None
        return truth, {"user_speed": us, "opp_speed": os_, "opp_speed_scarf": eff, "scarf_flips": flips}

    def make_scarf_opp(u, o, truth, meta):
        text = (f"In Gen 9 OU, does my {u.name} outspeed a Choice Scarf {o[0]} running {spe_phrase(*o)}? "
                f"My own item does not change my Speed. All IVs are 31; no stat boosts, abilities or field effects.")
        return question("gen9ou", "speed", "hard", ["scarf_opp"], u.paste(), text, "speed", {"value": truth}, meta)

    pick(nonscarf, 6, keep_scarf_opp, make_scarf_opp, None, seen)

    # opponent phrased as the subject; yes means the opponent is faster. Opponent spread differs from the user's.
    def keep_opp_subject(u, o):
        us, os_ = u.stats()["spe"], opp_speed(*o)
        if u.item == "Choice Scarf":
            us = scarf(us)
        if us == os_:
            DROPS["speed_tie"] += 1
        if us == os_ or abs(us - os_) > 50:
            return None
        if o[1] == u.nature and o[2] == u.evs["spe"]:
            return None
        truth = "yes" if os_ > us else "no"
        return truth, {"user_speed_effective": us, "opp_speed": os_}

    def make_opp_subject(u, o, truth, meta):
        held = "Count held items (my set is pasted above)" if u.item == "Choice Scarf" else "My item does not change my Speed"
        text = (f"In Gen 9 OU, does {o[0]} outspeed my {u.name} if {o[0]} runs {spe_phrase(*o)} and no speed item? "
                f"{held}. All IVs are 31; no stat boosts, abilities or field effects.")
        tags = ["opp_subject"] + (["scarf_user"] if u.item == "Choice Scarf" else [])
        return question("gen9ou", "speed", "hard", tags, u.paste(), text, "speed", {"value": truth}, meta)

    pick(users, 10, keep_opp_subject, make_opp_subject, None, seen)
    return out


def best_move_verdict(results, hp, guard=False):
    """
    The strongest listed move is the one with the highest minimum roll; it must also have the highest maximum
    roll (otherwise 'strongest' is ambiguous and the item is dropped). Returns (verdict, move, lo, hi).
    guard=True means Sturdy or Focus Sash at full HP blocks any single hit OHKO.
    """
    usable = [(m, r) for m, r in results if r["ok"] and r["range"][1] > 0]
    if not usable:
        return None
    by_min = max(usable, key=lambda x: x[1]["range"][0])
    by_max = max(usable, key=lambda x: x[1]["range"][1])
    if by_min[0] != by_max[0]:
        # Fine only if every move lands on the same clean side
        verdicts = {classify_ko(*r["range"], hp) for _, r in usable}
        if len(verdicts) != 1 or None in verdicts:
            DROPS["strongest_move_ambiguous"] += 1
            return None
    m, r = by_max
    v = classify_ko(*r["range"], hp)
    if v is None:
        DROPS["no_move_straddles"] += 1
        return None
    return v, m, r["range"][0], r["range"][1]


def calc_items(rng):
    out = []
    safe = CALC_SAFE
    # ---- no move named: the opponent attacks (5) and the user attacks (5); survive (8)
    pairs = [(a, d) for a in safe for d in safe if a.name != d.name and a.attacks()]
    rng.shuffle(pairs)
    pairs = pairs[:220]
    reqs, index = [], []
    for a, d in pairs:
        for m in a.attacks():
            reqs.append({"game": "sv", "attacker": a.spec(), "defender": d.spec(), "move": m})
            index.append((a.name, d.name, m))
    res = run_calc(reqs)
    by_pair = {}
    for (an, dn, m), r in zip(index, res):
        by_pair.setdefault((an, dn), []).append((m, r))
        if r["ok"]:
            check_stats(r, SETS[an], SETS[dn])
    quotas = {"opp_attacks": 5, "user_attacks": 5, "survive": 8}
    counts = {k: {"yes": 0, "no": 0} for k in quotas}
    used = set()
    for a, d in pairs:
        key = (a.name, d.name)
        results = by_pair.get(key, [])
        if not results or key in used:
            continue
        hp = results[0][1].get("maxHP") if results[0][1]["ok"] else None
        bv = best_move_verdict(results, hp) if hp else None
        if not bv:
            continue
        verdict, move, lo, hi = bv
        meta = {"best_move": move, "range_hp": [lo, hi], "max_hp": hp,
                "all_moves": {m: r["range"] for m, r in results if r["ok"]}}
        kinds = [k for k in quotas if sum(counts[k].values()) < quotas[k]]
        rng.shuffle(kinds)
        for k in kinds:
            truth = verdict if k != "survive" else ("no" if verdict == "yes" else "yes")
            cap = quotas[k] // 2 + 1
            if counts[k][truth] >= cap:
                continue
            counts[k][truth] += 1
            used.add(key)
            if k == "opp_attacks":
                text = (f"In Gen 9 OU, does {art(a.text())} OHKO my {d.name} from full health? Assume it uses its strongest "
                        f"listed move against my {d.name}, with no boosts, no crits, no Tera and no field effects.")
                out.append(question("gen9ou", "ko", "hard", ["no_move", "opp_attacker"], d.paste(), text, "ko",
                                    {"value": truth}, meta))
            elif k == "user_attacks":
                text = (f"In Gen 9 OU, does my {a.name} OHKO a full health {d.text(moves=False)}? Assume it uses its "
                        f"strongest move against it, with no boosts, no crits, no Tera and no field effects.")
                out.append(question("gen9ou", "ko", "hard", ["no_move"], a.paste(), text, "ko", {"value": truth}, meta))
            else:
                text = (f"In Gen 9 OU, can my {d.name} survive one hit from {art(a.text())} at full health? Assume it uses "
                        f"its strongest listed move against my {d.name}, with no boosts, no crits, no Tera and no field "
                        f"effects.")
                out.append(question("gen9ou", "survive", "hard", ["no_move", "opp_attacker", "survive"], d.paste(),
                                    text, "yesno", {"value": truth}, meta))
            break
        if all(sum(counts[k].values()) >= quotas[k] for k in quotas):
            break

    # ---- Sturdy and Focus Sash at full HP (8): the raw roll OHKOs but the guard holds, plus Mold Breaker cases
    guards = [s for s in SETS.values() if s.ability == "Sturdy" or s.item == "Focus Sash"]
    attackers = [s for s in SETS.values() if s.ability not in AMBIG_ABILITIES and s.item not in AMBIG_ITEMS
                 and s.attacks()] + [SETS["Excadrill"]]
    reqs, index = [], []
    for a in attackers:
        for d in guards:
            if a.name == d.name:
                continue
            for m in a.attacks():
                d_spec = d.spec()
                reqs.append({"game": "sv", "attacker": a.spec(), "defender": d_spec, "move": m})
                index.append((a, d, m))
    res = run_calc(reqs)
    cands = []
    for (a, d, m), r in zip(index, res):
        if not r["ok"] or r["range"][1] <= 0 or (r.get("hits") or 1) > 1:
            continue
        hp = r["maxHP"]
        raw = classify_ko(*r["range"], hp)
        if raw != "yes":
            continue
        broken = d.ability == "Sturdy" and d.item != "Focus Sash" and a.ability in MOLD_BREAKERS
        truth = "yes" if broken else "no"
        cands.append((a, d, m, truth, r))
    rng.shuffle(cands)
    made, seen, yes_made = 0, set(), 0
    for a, d, m, truth, r in sorted(cands, key=lambda c: c[3] != "yes"):
        if made >= 8 or (a.name, d.name) in seen or sum(x[1] == d.name for x in seen) >= 2:
            continue
        if truth == "yes" and yes_made >= 2:
            continue
        seen.add((a.name, d.name))
        made += 1
        yes_made += truth == "yes"
        guard = "Focus Sash" if d.item == "Focus Sash" else "Sturdy"
        text = (f"In Gen 9 OU, does my {a.name}'s {m} OHKO a full health {d.text(moves=False)}? Assume no boosts, no "
                f"crits, no Tera, no entry hazards and no field effects.")
        tags = ["sturdy_sash", guard.lower().replace(" ", "_")] + (["mold_breaker"] if truth == "yes" else [])
        out.append(question("gen9ou", "ko", "hard", tags, a.paste(), text, "ko", {"value": truth},
                            {"range_hp": r["range"], "max_hp": r["maxHP"], "guard": guard}))

    # ---- weather, terrain and screens stated in the question (8): the field must flip the no field verdict
    fields = [
        ("rain", {"weather": "Rain"}, "with rain active"),
        ("sun", {"weather": "Sun"}, "with harsh sunlight active"),
        ("electric_terrain", {"terrain": "Electric"}, "on Electric Terrain"),
        ("grassy_terrain", {"terrain": "Grassy"}, "on Grassy Terrain"),
        ("psychic_terrain", {"terrain": "Psychic"}, "on Psychic Terrain"),
        ("reflect", {"defenderSide": {"isReflect": True}}, "with Reflect up on the opposing side"),
        ("light_screen", {"defenderSide": {"isLightScreen": True}}, "with Light Screen up on the opposing side"),
    ]
    trip = [(a, d, m) for a in safe for d in safe if a.name != d.name for m in a.attacks()
            if DEX_SV.move(m)["priority"] <= 0]
    rng.shuffle(trip)
    trip = trip[:500]
    base = run_calc([{"game": "sv", "attacker": a.spec(), "defender": d.spec(), "move": m} for a, d, m in trip])
    reqs, index = [], []
    for (a, d, m), r0 in zip(trip, base):
        if not r0["ok"] or r0["range"][1] <= 0:
            continue
        v0 = classify_ko(*r0["range"], r0["maxHP"])
        if v0 is None:
            DROPS["field_base_straddles"] += 1
            continue
        for fname, fobj, phrase in fields:
            reqs.append({"game": "sv", "attacker": a.spec(), "defender": d.spec(), "move": m, "field": fobj})
            index.append((a, d, m, v0, fname, phrase))
    res = run_calc(reqs)
    flips = []
    for (a, d, m, v0, fname, phrase), r in zip(index, res):
        if not r["ok"]:
            continue
        v = classify_ko(*r["range"], r["maxHP"])
        if v is None:
            DROPS["field_ko_straddles"] += 1
        if v and v != v0:
            flips.append((a, d, m, v, v0, fname, phrase, r))
    rng.shuffle(flips)
    made, used_f, used_p, used_v = 0, {}, set(), {"yes": 0, "no": 0}
    for a, d, m, v, v0, fname, phrase, r in flips:
        if made >= 8 or used_f.get(fname, 0) >= 3 or (a.name, d.name) in used_p or used_v[v] >= 5:
            continue
        used_f[fname] = used_f.get(fname, 0) + 1
        used_v[v] += 1
        used_p.add((a.name, d.name))
        made += 1
        text = (f"In Gen 9 OU, {phrase}, does my {a.name}'s {m} OHKO a full health {d.text(moves=False)}? Assume no "
                f"boosts, no crits and no Tera; that is the only field effect.")
        out.append(question("gen9ou", "ko", "hard", ["field", fname], a.paste(), text, "ko", {"value": v},
                            {"range_hp": r["range"], "max_hp": r["maxHP"], "no_field_verdict": v0}))
    return out


REGIONAL_NAMES = {
    "Ninetales-Alola": ["Alolan Ninetales", "Ninetales-A"], "Slowking-Galar": ["Galarian Slowking", "G-Slowking"],
    "Moltres-Galar": ["Galarian Moltres", "Moltres-G"], "Samurott-Hisui": ["Hisuian Samurott", "H-Samurott"],
    "Arcanine-Hisui": ["Hisuian Arcanine"], "Typhlosion-Hisui": ["Hisuian Typhlosion"],
    "Zoroark-Hisui": ["Hisuian Zoroark"], "Goodra-Hisui": ["Hisuian Goodra"], "Weezing-Galar": ["Galarian Weezing"],
    "Decidueye-Hisui": ["Hisuian Decidueye"], "Sandslash-Alola": ["Alolan Sandslash"], "Muk-Alola": ["Alolan Muk"],
    "Zapdos-Galar": ["Galarian Zapdos"], "Slowbro-Galar": ["Galarian Slowbro"],
    "Rotom-Wash": ["Wash Rotom", "Rotom-W"], "Rotom-Heat": ["Heat Rotom", "Rotom-H"], "Rotom-Mow": ["Mow Rotom"],
    "Rotom-Frost": ["Frost Rotom"], "Rotom-Fan": ["Fan Rotom"],
}
REGIONAL_ABILITY = {
    "Ninetales-Alola": "Snow Cloak", "Slowking-Galar": "Regenerator", "Moltres-Galar": "Berserk",
    "Samurott-Hisui": "Sharpness", "Arcanine-Hisui": "Intimidate", "Typhlosion-Hisui": "Frisk",
    "Zoroark-Hisui": "Illusion", "Goodra-Hisui": "Sap Sipper", "Weezing-Galar": "Levitate",
    "Decidueye-Hisui": "Scrappy", "Sandslash-Alola": "Slush Rush", "Muk-Alola": "Poison Touch",
    "Zapdos-Galar": "Defiant", "Slowbro-Galar": "Regenerator", "Rotom-Wash": "Levitate", "Rotom-Heat": "Levitate",
    "Rotom-Mow": "Levitate", "Rotom-Frost": "Levitate", "Rotom-Fan": "Levitate",
}


def forme_items(rng):
    out = []
    types = list(DEX_SV.chart)
    team_pool = [SETS[n] for n in ("Great Tusk", "Kingambit", "Garchomp", "Dragapult", "Corviknight", "Heatran")]

    # regional and Rotom forme typing (6): the answer must differ from the base species' answer
    cands = []
    for forme, aliases in REGIONAL_NAMES.items():
        sp = DEX_SV.species(forme)
        base = DEX_SV.species(sp["baseSpecies"])
        ab = REGIONAL_ABILITY[forme]
        for t in types:
            v = type_verdict(DEX_SV, t, sp["types"], ab)
            vb = type_verdict(DEX_SV, t, base["types"], ab if ab in base["abilities"] else None)
            if v and vb and v != vb:
                cands.append((forme, t, v, vb))
    rng.shuffle(cands)
    made, seen = 0, set()
    for forme, t, v, vb in cands:
        if made >= 6 or forme in seen:
            continue
        seen.add(forme)
        made += 1
        alias = rng.choice(REGIONAL_NAMES[forme])
        team = rng.choice(team_pool)
        text = (f"In Gen 9 OU, is an opposing {alias} (Ability: {REGIONAL_ABILITY[forme]}) immune to, resistant to, "
                f"neutral to or weak to {t} type attacks? Ignore Tera and items.")
        out.append(question("gen9ou", "type", "hard", ["regional_forme"] + (["rotom"] if "Rotom" in forme else []),
                            team.paste(), text, "type", {"value": v},
                            {"forme": forme, "alias": alias, "types": DEX_SV.species(forme)["types"],
                             "base_species_answer": vb}))

    # regional and Rotom forme speed (4): the verdict must flip if the base species were used
    cands = []
    for forme in REGIONAL_NAMES:
        sp = DEX_SV.species(forme)
        for nature, ev in (("Timid", 252), ("Jolly", 252), ("Bold", 0), ("Modest", 252)):
            fs = opp_speed(forme, nature, ev)
            bs = opp_speed(sp["baseSpecies"], nature, ev)
            for u in SETS.values():
                if u.item == "Choice Scarf" or u.name == forme:
                    continue
                us = u.stats()["spe"]
                if us in (fs, bs):
                    continue
                if (us > fs) != (us > bs):
                    cands.append((forme, nature, ev, u, us, fs, bs))
    rng.shuffle(cands)
    made, seen = 0, set()
    for forme, nature, ev, u, us, fs, bs in cands:
        if made >= 4 or forme in seen:
            continue
        seen.add(forme)
        made += 1
        alias = rng.choice(REGIONAL_NAMES[forme])
        truth = "yes" if us > fs else "no"
        text = (f"In Gen 9 OU, does my {u.name} outspeed an opposing {alias} running {nature} nature with {ev} Spe EVs? "
                f"My item does not change my Speed. All IVs are 31; no stat boosts, abilities or field effects.")
        out.append(question("gen9ou", "speed", "hard", ["regional_forme"] + (["rotom"] if "Rotom" in forme else []),
                            u.paste(), text, "speed", {"value": truth},
                            {"forme": forme, "alias": alias, "user_speed": us, "opp_speed": fs,
                             "base_species_speed": bs}))

    # defensive Tera (8): 5 about my Pokemon, 3 about an opponent; must differ from the pre Tera answer
    cands = []
    for s in SETS.values():
        if s.name.startswith("Ogerpon"):
            continue  # Ogerpon can only Terastallize into its mask's type
        sp = DEX_SV.species(s.name)
        for tera in types:
            if [tera] == sp["types"]:
                continue
            for t in types:
                v = type_verdict(DEX_SV, t, [tera], s.ability)
                v0 = type_verdict(DEX_SV, t, sp["types"], s.ability)
                if v and v0 and v != v0:
                    cands.append((s, tera, t, v, v0))
    rng.shuffle(cands)
    made, seen = 0, set()
    for s, tera, t, v, v0 in cands:
        if made >= 8 or s.name in seen:
            continue
        seen.add(s.name)
        mine = made < 5
        made += 1
        if mine:
            paste_set = s.with_(tera=tera)
            text = (f"In Gen 9 OU, if my {s.name} Terastallizes into {tera}, is it immune to, resistant to, neutral to or "
                    f"weak to {t} type attacks? Its ability is {s.ability}; ignore items.")
            team = paste_set.paste()
        else:
            text = (f"In Gen 9 OU, an opposing {s.name} (Ability: {s.ability}) has Terastallized into {tera}. Is it "
                    f"immune to, resistant to, neutral to or weak to {t} type attacks now? Ignore items.")
            team = rng.choice([x for x in team_pool if x.name != s.name]).paste()
        out.append(question("gen9ou", "type", "hard", ["tera_defense"] + ([] if mine else ["opp_tera"]), team, text,
                            "type", {"value": v}, {"tera": tera, "original_types": DEX_SV.species(s.name)["types"],
                                                   "pre_tera_answer": v0}))
    return out


NICKS = {"Great Tusk": "Tusky", "Dragapult": "Pult Fiction", "Kingambit": "The General", "Garchomp": "Chompers",
         "Iron Valiant": "Sir Lance", "Gholdengo": "Goldie", "Weavile": "Snips", "Cinderace": "Bunbun"}


def nickname_items(rng):
    out = []
    names = list(NICKS)
    rng.shuffle(names)
    # 3 speed items, 3 KO items; each team has two nicknamed Pokemon so the reference has to be resolved
    made_speed, made_ko, used = 0, 0, set()
    opps = OPP_SPEEDS[:]
    rng.shuffle(opps)
    for i, n in enumerate(names):
        if made_speed >= 3:
            break
        u = SETS[n].with_(nick=NICKS[n])
        mate = SETS[names[(i + 1) % len(names)]].with_(nick=NICKS[names[(i + 1) % len(names)]])
        us = u.stats()["spe"] if u.item != "Choice Scarf" else scarf(u.stats()["spe"])
        for o in opps:
            os_ = opp_speed(*o)
            if o[0] in (u.name, mate.name) or os_ == us or abs(os_ - us) > 50 or os_ == mate.stats()["spe"]:
                continue
            # the teammate must give the other answer, so a wrong resolution is caught
            ms = mate.stats()["spe"] if mate.item != "Choice Scarf" else scarf(mate.stats()["spe"])
            if (ms > os_) == (us > os_):
                continue
            truth = "yes" if us > os_ else "no"
            text = (f"In Gen 9 OU, does {u.nick} outspeed {o[0]} if {o[0]} runs {spe_phrase(*o)} and no speed item? "
                    f"Count held items. All IVs are 31; no stat boosts, abilities or field effects.")
            out.append(question("gen9ou", "speed", "hard", ["nickname"], u.paste() + "\n\n" + mate.paste(), text,
                                "speed", {"value": truth}, {"nick": u.nick, "species": u.name, "user_speed": us,
                                                            "opp_speed": os_, "teammate_speed": ms}))
            used.add(n)
            made_speed += 1
            break
    rest = [n for n in names if n not in used and SETS[n].attacks()]
    reqs, index = [], []
    for i, n in enumerate(rest):
        u = SETS[n].with_(nick=NICKS[n])
        mate_name = rest[(i + 1) % len(rest)]
        for d in CALC_SAFE:
            if d.name in (n, mate_name):
                continue
            for m in u.attacks():
                reqs.append({"game": "sv", "attacker": u.spec(), "defender": d.spec(), "move": m})
                index.append((u, mate_name, d, m))
    res = run_calc(reqs)
    cand = [(u, mn, d, m, r) for (u, mn, d, m), r in zip(index, res) if r["ok"] and r["range"][1] > 0]
    rng.shuffle(cand)
    counts, seen = {"yes": 0, "no": 0}, set()
    for u, mn, d, m, r in cand:
        if made_ko >= 3 or u.name in seen:
            continue
        v = classify_ko(*r["range"], r["maxHP"])
        if not v or counts[v] >= 2:
            continue
        seen.add(u.name)
        counts[v] += 1
        made_ko += 1
        mate = SETS[mn].with_(nick=NICKS[mn])
        possessive = f"{u.nick}'" if u.nick.endswith("s") else f"{u.nick}'s"
        text = (f"In Gen 9 OU, does {possessive} {m} OHKO a full health {d.text(moves=False)}? Assume no boosts, no "
                f"crits, no Tera and no field effects.")
        out.append(question("gen9ou", "ko", "hard", ["nickname", "possessive"], mate.paste() + "\n\n" + u.paste(),
                            text, "ko", {"value": v}, {"nick": u.nick, "species": u.name, "range_hp": r["range"],
                                                       "max_hp": r["maxHP"]}))
    return out


# ---------------------------------------------------------------- assembly

# Verification pass 2026 11 05: an independent recompute agreed with every key; these items read two ways,
# so the text is pinned down (answers unchanged, applied after ids are assigned so the seeded draw is untouched)
WORDING_FIXES = {
    # Flame Orb plus Guts: a reader could assume the burn is already active
    "f019": ("Assume no boosts, no Tera and no field effects.",
             "Assume my Ursaluna is not burned (Guts inactive), with no boosts, no Tera and no field effects."),
    # Champions lists Mega Greninja separately and it is used more than the base forme
    "f047": ("outspeed Greninja if Greninja runs", "outspeed Greninja (not Mega Greninja) if Greninja runs"),
    "f075": ("held item on Greninja according", "held item on Greninja (the base forme, not Mega Greninja) according"),
}


def build():
    rng = random.Random(SEED)
    qs = gen_part1(rng)
    qs += speed_items(rng)
    qs += calc_items(rng)
    qs += forme_items(rng)
    qs += nickname_items(rng)
    if STAT_MISMATCHES:
        sys.exit(f"Own stat formula disagrees with the calc: {STAT_MISMATCHES[:5]}")
    hand = [json.loads(line) for line in HANDWRITTEN.read_text(encoding="utf-8").splitlines() if line.strip()]
    for h in hand:
        h["split"] = "handwritten"
    qs += hand
    texts = set()
    for i, q in enumerate(qs, 1):
        q["id"] = f"f{i:03d}"
        if q["id"] in WORDING_FIXES:
            old, new = WORDING_FIXES[q["id"]]
            if q["question"].count(old) != 1:
                sys.exit(f"Wording fix for {q['id']} no longer applies")
            q["question"] = q["question"].replace(old, new)
        if q["question"] in texts:
            sys.exit(f"Duplicate question text at {q['id']}")
        texts.add(q["question"])
    return qs


def serialise(qs):
    return "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in qs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="rebuild and compare with the frozen file")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    verify_snapshot()
    text = serialise(build())
    if args.check:
        frozen = OUT.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
        sys.exit(0 if frozen == text else "Rebuild differs from the frozen questions_fresh.jsonl")
    Path(args.out).write_bytes(text.encode("utf-8"))
    summary = {}
    for q in json.loads("[" + ",".join(text.splitlines()) + "]"):
        key = (q["split"], q["format"], q["category"])
        summary[key] = summary.get(key, 0) + 1
    for k, v in sorted(summary.items()):
        print(*k, v)
    print(sum(summary.values()), "questions ->", args.out)
    print("rejected candidates:", dict(DROPS), file=sys.stderr)


if __name__ == "__main__":
    main()

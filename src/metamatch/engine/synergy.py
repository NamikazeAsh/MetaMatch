"""
Team engines: the cores a team is built around (sun, rain, sand, snow, the four terrains, Trick Room, Tailwind and
screens), found by rule and measured with the damage calc.

The rules restate Pokemon Showdown's own mechanics text (data/text/abilities.ts and moves.ts, MIT licensed), curated
by hand because keyword mining misses entries worded differently. Numbers appear only where the calc models the
effect (Speed and damage); turn mechanics like Solar Beam's charge or Thunder's accuracy are stated as rules.

A core needs a setter and at least one real user. Incidental setters stay quiet: Chilly Reception is a pivot first,
so it only counts as a snow setter when the team actually has something that wants snow.
"""
from dataclasses import dataclass, field

from metamatch import config
from metamatch.engine import calc, mechanics
from metamatch.engine.constraints import SETUP_MOVES
from metamatch.engine.dex import dex_for_format

N_THREATS = 12
N_SPEED = 25
LIFT_FLOOR = 1.5


@dataclass(frozen=True)
class Rule:
    """One way a Pokemon uses a condition. kind: speed (Speed doubled or boosted), damage (hits harder),
    utility (accuracy, priority, no charge, healing, defense), defense (takes less)."""
    kind: str
    text: str
    major: bool = True    # a major user can carry a core; minor ones (a Fire move in sun) are listed but don't make one
    generic: bool = False  # only counts when the condition is set: Weather Ball works with any weather, and
                           # Protosynthesis or Quark Drive users rarely depend on it


# Conditions: label, icon type, calc field, setters, users (by ability, move, move type, member type) and drawbacks
CONDITIONS = {
    "sun": {
        "label": "Sun", "icon": "Fire", "field": {"weather": "Sun"},
        "ability_setters": {"Drought": "Drought on entry", "Orichalcum Pulse": "Orichalcum Pulse on entry"},
        "move_setters": {"Sunny Day": "Sunny Day"},
        "extender": ("Heat Rock", "Heat Rock makes it last 8 turns"),
        "abilities": {
            "Chlorophyll": Rule("speed", "Chlorophyll doubles its Speed"),
            "Solar Power": Rule("damage", "Solar Power raises its Special Attack by 50%"),
            "Protosynthesis": Rule("speed", "Protosynthesis boosts its best stat", generic=True),
            "Mega Sol": Rule("damage", "Mega Sol makes its own moves work as if sun were up"),
            "Orichalcum Pulse": Rule("damage", "Orichalcum Pulse raises its Attack by a third"),
            "Flower Gift": Rule("damage", "Flower Gift raises its Attack and Special Defense"),
            "Harvest": Rule("utility", "Harvest restores its Berry every turn", major=False),
            "Leaf Guard": Rule("utility", "Leaf Guard blocks status", major=False),
        },
        "moves": {
            "Weather Ball": Rule("damage", "Weather Ball becomes a 100 power Fire move", generic=True),
            "Solar Beam": Rule("utility", "Solar Beam fires without charging"),
            "Solar Blade": Rule("utility", "Solar Blade fires without charging"),
            "Growth": Rule("utility", "Growth raises Attack and Special Attack by 2", major=False),
            "Hydro Steam": Rule("damage", "Hydro Steam hits 50% harder instead of being halved", generic=True),
            "Synthesis": Rule("utility", "Synthesis heals two thirds", major=False),
            "Morning Sun": Rule("utility", "Morning Sun heals two thirds", major=False),
            "Moonlight": Rule("utility", "Moonlight heals two thirds", major=False),
        },
        "move_types": {"Fire": Rule("damage", "50% harder in sun", major=False)},
        "weak_cover": ("Water", "Sun halves the Water hits {names} are weak to"),
        "drawback_types": {"Water": "{move} is halved in sun"},
        "drawback_moves": {"Thunder": "Thunder drops to 50% accuracy in sun", "Hurricane": "Hurricane drops to 50% accuracy in sun"},
        "drawback_abilities": {"Dry Skin": "Dry Skin makes it lose HP every turn in sun"},
    },
    "rain": {
        "label": "Rain", "icon": "Water", "field": {"weather": "Rain"},
        "ability_setters": {"Drizzle": "Drizzle on entry"},
        "move_setters": {"Rain Dance": "Rain Dance"},
        "extender": ("Damp Rock", "Damp Rock makes it last 8 turns"),
        "abilities": {
            "Swift Swim": Rule("speed", "Swift Swim doubles its Speed"),
            "Rain Dish": Rule("utility", "Rain Dish heals it every turn", major=False),
            "Hydration": Rule("utility", "Hydration cures its status every turn", major=False),
            "Dry Skin": Rule("utility", "Dry Skin heals it every turn", major=False),
        },
        "moves": {
            "Weather Ball": Rule("damage", "Weather Ball becomes a 100 power Water move", generic=True),
            "Thunder": Rule("utility", "Thunder can't miss", major=False),
            "Hurricane": Rule("utility", "Hurricane can't miss", major=False),
            "Bleakwind Storm": Rule("utility", "Bleakwind Storm can't miss", major=False),
            "Wildbolt Storm": Rule("utility", "Wildbolt Storm can't miss", major=False),
            "Sandsear Storm": Rule("utility", "Sandsear Storm can't miss", major=False),
            "Electro Shot": Rule("utility", "Electro Shot fires without charging"),
        },
        "move_types": {"Water": Rule("damage", "50% harder in rain", major=False)},
        "weak_cover": ("Fire", "Rain halves the Fire hits {names} are weak to"),
        "drawback_types": {"Fire": "{move} is halved in rain"},
        "drawback_moves": {"Solar Beam": "Solar Beam is halved and still charges in rain",
                           "Solar Blade": "Solar Blade is halved and still charges in rain",
                           "Synthesis": "Synthesis only heals a quarter in rain", "Morning Sun": "Morning Sun only heals a quarter in rain",
                           "Moonlight": "Moonlight only heals a quarter in rain"},
        "drawback_abilities": {},
    },
    "sand": {
        "label": "Sand", "icon": "Rock", "field": {"weather": "Sand"},
        "ability_setters": {"Sand Stream": "Sand Stream on entry"},
        "move_setters": {"Sandstorm": "Sandstorm"},
        "extender": ("Smooth Rock", "Smooth Rock makes it last 8 turns"),
        "abilities": {
            "Sand Rush": Rule("speed", "Sand Rush doubles its Speed"),
            "Sand Force": Rule("damage", "Sand Force powers its Rock, Ground and Steel moves by 30%"),
            "Sand Veil": Rule("utility", "Sand Veil makes it harder to hit", major=False),
        },
        "moves": {
            "Weather Ball": Rule("damage", "Weather Ball becomes a 100 power Rock move", generic=True),
            "Shore Up": Rule("utility", "Shore Up heals two thirds", major=False),
        },
        "move_types": {},
        "member_types": {"Rock": Rule("defense", "sand raises its Special Defense by 50%", major=False)},
        "drawback_types": {}, "drawback_moves": {}, "drawback_abilities": {},
        "chip": True,
    },
    "snow": {
        "label": "Snow", "icon": "Ice", "field": {"weather": "Snow"},
        "ability_setters": {"Snow Warning": "Snow Warning on entry"},
        "move_setters": {"Snowscape": "Snowscape"},
        "incidental_setters": {"Chilly Reception": "Chilly Reception as it pivots out"},
        "extender": ("Icy Rock", "Icy Rock makes it last 8 turns"),
        "abilities": {
            "Slush Rush": Rule("speed", "Slush Rush doubles its Speed"),
            "Ice Body": Rule("utility", "Ice Body heals it every turn", major=False),
            "Snow Cloak": Rule("utility", "Snow Cloak makes it harder to hit", major=False),
            "Ice Face": Rule("utility", "Ice Face restores itself in snow", major=False),
        },
        "moves": {
            "Weather Ball": Rule("damage", "Weather Ball becomes a 100 power Ice move", generic=True),
            "Blizzard": Rule("utility", "Blizzard can't miss", major=False),
            "Aurora Veil": Rule("utility", "Aurora Veil only works in snow"),
        },
        "move_types": {},
        "member_types": {"Ice": Rule("defense", "snow raises its Defense by 50%", major=False)},
        "drawback_types": {}, "drawback_moves": {}, "drawback_abilities": {},
    },
    "electric": {
        "label": "Electric Terrain", "icon": "Electric", "field": {"terrain": "Electric"},
        "ability_setters": {"Electric Surge": "Electric Surge on entry", "Hadron Engine": "Hadron Engine on entry"},
        "move_setters": {"Electric Terrain": "Electric Terrain"},
        "extender": ("Terrain Extender", "Terrain Extender makes it last 8 turns"),
        "abilities": {
            "Quark Drive": Rule("speed", "Quark Drive boosts its best stat", generic=True),
            "Surge Surfer": Rule("speed", "Surge Surfer doubles its Speed"),
            "Hadron Engine": Rule("damage", "Hadron Engine raises its Special Attack by a third"),
        },
        "moves": {
            "Rising Voltage": Rule("damage", "Rising Voltage doubles in power against grounded targets"),
            "Psyblade": Rule("damage", "Psyblade hits 50% harder", major=False),
            "Terrain Pulse": Rule("damage", "Terrain Pulse becomes a 100 power Electric move", generic=True),
        },
        "move_types": {"Electric": Rule("damage", "30% harder in Electric Terrain", major=False)},
        "grounded_types": True,
        "drawback_types": {}, "drawback_moves": {}, "drawback_abilities": {},
    },
    "grassy": {
        "label": "Grassy Terrain", "icon": "Grass", "field": {"terrain": "Grassy"},
        "ability_setters": {"Grassy Surge": "Grassy Surge on entry"},
        "move_setters": {"Grassy Terrain": "Grassy Terrain"},
        "extender": ("Terrain Extender", "Terrain Extender makes it last 8 turns"),
        "abilities": {"Grass Pelt": Rule("defense", "Grass Pelt raises its Defense by 50%")},
        "moves": {
            "Grassy Glide": Rule("utility", "Grassy Glide gets +1 priority"),
            "Terrain Pulse": Rule("damage", "Terrain Pulse becomes a 100 power Grass move", generic=True),
        },
        "move_types": {"Grass": Rule("damage", "30% harder in Grassy Terrain", major=False)},
        "grounded_types": True,
        "drawback_types": {},
        "drawback_moves": {"Earthquake": "Earthquake is halved against grounded targets in Grassy Terrain",
                           "Bulldoze": "Bulldoze is halved against grounded targets in Grassy Terrain"},
        "drawback_abilities": {},
    },
    "psychic": {
        "label": "Psychic Terrain", "icon": "Psychic", "field": {"terrain": "Psychic"},
        "ability_setters": {"Psychic Surge": "Psychic Surge on entry"},
        "move_setters": {"Psychic Terrain": "Psychic Terrain"},
        "extender": ("Terrain Extender", "Terrain Extender makes it last 8 turns"),
        "abilities": {},
        "moves": {
            "Expanding Force": Rule("damage", "Expanding Force hits 50% harder"),
            "Terrain Pulse": Rule("damage", "Terrain Pulse becomes a 100 power Psychic move", generic=True),
        },
        "move_types": {"Psychic": Rule("damage", "30% harder in Psychic Terrain", major=False)},
        "grounded_types": True,
        "drawback_types": {}, "drawback_moves": {}, "drawback_abilities": {},
    },
    "misty": {
        "label": "Misty Terrain", "icon": "Fairy", "field": {"terrain": "Misty"},
        "ability_setters": {"Misty Surge": "Misty Surge on entry"},
        "move_setters": {"Misty Terrain": "Misty Terrain"},
        "extender": ("Terrain Extender", "Terrain Extender makes it last 8 turns"),
        "abilities": {},
        "moves": {
            "Misty Explosion": Rule("damage", "Misty Explosion hits 50% harder", generic=True),
            "Terrain Pulse": Rule("damage", "Terrain Pulse becomes a 100 power Fairy move", generic=True),
        },
        "move_types": {},
        "drawback_types": {}, "drawback_moves": {}, "drawback_abilities": {},
    },
}
WEATHER = {"sun", "rain", "sand", "snow"}
TERRAIN = {"electric", "grassy", "psychic", "misty"}
SCREENS = ("Reflect", "Light Screen", "Aurora Veil")


@dataclass
class User:
    name: str
    points: list                  # plain sentences, most important first
    major: bool = False
    speed: tuple | None = None    # (Speed without, with, share outspeeded without, with)
    damage: tuple | None = None   # (move, 2HKOs without, with, threats counted)
    peak: int = 0                 # most of the top threats it 2HKOs with the core up (after Growth when it runs it)


@dataclass
class Engine:
    key: str
    label: str
    icon: str
    setters: list = field(default_factory=list)     # [{"name", "how"}]
    users: list = field(default_factory=list)       # [User]
    drawbacks: list = field(default_factory=list)
    defense: list = field(default_factory=list)
    ladder: str = ""
    partners: list = field(default_factory=list)    # half built: setters ladder players pair the users with
    always_on: bool = False                          # set by an ability on entry

    @property
    def complete(self):
        return bool(self.setters) and any(u.major for u in self.users)


def _poss(name):
    """'Torkoal's', but 'Ninetales'' for names ending in s."""
    return name + ("'" if name.endswith("s") else "'s")


def _and(names):
    names = list(dict.fromkeys(names))
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""


def _abilities(p):
    return {a for a in (p.get("Ability"), p.get("Mega Ability")) if a}


def _moves(p):
    return [m for m in p.get("Moves", []) if m.get("name")]


def _grounded(p):
    return "Flying" not in (p.get("Type") or []) and "Levitate" not in _abilities(p) and p.get("Item") != "Air Balloon"


def _setters(team, cond, users_present):
    out = []
    for p in team.values():
        abil = _abilities(p) & set(cond["ability_setters"])
        if "Mega Sol" in _abilities(p) and cond["label"] == "Sun":
            out.append({"name": p["Pokemon"], "how": ["Mega Sol, for its own moves only"], "ability": False})
            continue
        moves = [m["name"] for m in _moves(p) if m["name"] in cond["move_setters"]]
        inc = [m["name"] for m in _moves(p) if m["name"] in cond.get("incidental_setters", {})] if users_present else []
        how = [cond["ability_setters"][a] for a in sorted(abil)] + [cond["move_setters"][m] for m in moves] + \
              [cond["incidental_setters"][m] for m in inc]
        if how:
            ext = cond.get("extender")
            if ext and p.get("Item") == ext[0]:
                how.append(ext[1])
            out.append({"name": p["Pokemon"], "how": how, "ability": bool(abil)})
    return out


def _uses(p, key, cond):
    """[Rule] this member gets from the condition, strongest first."""
    rules = []
    for a in _abilities(p):
        r = cond["abilities"].get(a)
        # Protosynthesis or Quark Drive holding Booster Energy already has its boost; the condition only saves the item
        if r and not (a in ("Protosynthesis", "Quark Drive") and p.get("Item") == "Booster Energy"):
            rules.append(r)
    for m in _moves(p):
        r = cond["moves"].get(m["name"])
        if r:
            rules.append(r)
    if not cond.get("grounded_types") or _grounded(p):
        for t, r in cond.get("move_types", {}).items():
            hits = [m["name"] for m in _moves(p) if m.get("type") == t and m.get("category") != "Status"
                    and m["name"] not in cond["moves"]]
            if hits:
                rules.append(Rule(r.kind, f"{_and(hits)} {'hits' if len(hits) == 1 else 'hit'} {r.text}", r.major))
    for t, r in cond.get("member_types", {}).items():
        if t in (p.get("Type") or []):
            rules.append(r)
    rules.sort(key=lambda r: (not r.major, r.kind != "speed", r.kind != "damage"))
    return rules


def _drawbacks(team, key, cond):
    out = []
    for p in team.values():
        for m in _moves(p):
            t = cond["drawback_types"].get(m.get("type"))
            if t and m.get("category") != "Status" and m["name"] not in cond["moves"]:
                out.append(f"{_poss(p['Pokemon'])} " + t.format(move=m["name"]))
            d = cond["drawback_moves"].get(m["name"])
            if d and not (key == "grassy" and not _grounded(p)):
                out.append(f"{_poss(p['Pokemon'])} {d}")
        for a in _abilities(p):
            d = cond["drawback_abilities"].get(a)
            if d:
                out.append(f"{_poss(p['Pokemon'])} {d}")
    if cond.get("chip"):
        hurt = [p["Pokemon"] for p in team.values()
                if not ({"Rock", "Ground", "Steel"} & set(p.get("Type") or []))
                and not (_abilities(p) & {"Overcoat", "Magic Guard", "Sand Veil", "Sand Rush", "Sand Force"})
                and p.get("Item") != "Safety Goggles"]
        if hurt:
            out.append(f"Sand chips {_and(hurt)} every turn")
    return list(dict.fromkeys(out))


def _defense(team, cond):
    cover = cond.get("weak_cover")
    if not cover:
        return []
    t, text = cover
    names = [p["Pokemon"] for p in team.values() if (p.get("Damage From") or {}).get(t.lower(), 1.0) >= 2]
    if not names:
        return []
    return [text.format(names=_and(names)).replace(" are weak", " is weak" if len(names) == 1 else " are weak")]


# --- Numbers from the calc ---------------------------------------------------------------------

def _threat_specs(team, format_id):
    from metamatch.engine.sets import calc_spec, likely_set
    from metamatch.engine.threat_board import top_threats
    names = [p["Pokemon"] for p in team.values()] + [p.get("Forme") for p in team.values() if p.get("Forme")]
    out = []
    for name, _ in top_threats(format_id, exclude=names, n=N_THREATS):
        s = likely_set(name, format_id)
        if s:
            out.append((s["name"], calc_spec(s)))
    return out


def _meta(team, format_id):
    from metamatch.engine import speed_board
    return speed_board.meta_speeds(format_id, n=N_SPEED, exclude=[p["Pokemon"] for p in team.values()])


def _share(speed, meta):
    from metamatch.engine import speed_board
    return sum(speed_board.outspeed_share(speed, m) for m in meta) / len(meta) if meta else 0.0


def _any_move(p, dex):
    for m in _moves(p):
        if dex.move_name(m["name"]):
            return dex.move_name(m["name"])
    return next(iter(dex.move_data))


def _speed(p, spec, game, dex, fld, meta):
    move = _any_move(p, dex)
    before = mechanics.final_speed(spec, game, move)
    after = mechanics.final_speed(spec, game, move, fld)
    if not before or not after or after <= before:
        return None
    return before, after, _share(before, meta), _share(after, meta)


def _damage(p, spec, game, fld, threats, boosts=None):
    """(best move, 2HKOs without the condition, with it, threats) over the member's damaging moves."""
    moves = [m["name"] for m in _moves(p) if m.get("category") != "Status"]
    if not moves or not threats:
        return None
    reqs, keys = [], []
    for mv in moves:
        for _, dspec in threats:
            for on in (False, True):
                att = dict(spec, boosts=boosts) if (boosts and on) else spec
                req = {"game": game, "attacker": att, "defender": dspec, "move": mv}
                if on:
                    req["field"] = fld
                reqs.append(req)
                keys.append((mv, on))
    results = calc.calculate_many(reqs)
    count = {}
    i = 0
    for mv in moves:
        for _, dspec in threats:
            for on in (False, True):
                r = results[i]
                att = reqs[i]["attacker"]
                i += 1
                n = mechanics.hits_to_ko(r, att, dspec, mv) if r else None
                count.setdefault(mv, [0, 0])[int(on)] += int(n is not None and n <= 2)
    best = max(count, key=lambda mv: (count[mv][1] - count[mv][0], count[mv][1]))
    off, on = count[best]
    return (best, off, on, len(threats)) if on > off else None


def _pct(x):
    """Rounded down, so 99.8% never reads as 100%."""
    return f"{int(x * 100)}%"


def _measure(user, p, key, cond, team_ctx):
    """Adds calc numbers to a user's points: Speed for Speed users, extra 2HKOs for damage users."""
    game, dex, threats, meta = team_ctx["game"], team_ctx["dex"], team_ctx["threats"], team_ctx["meta"]
    from metamatch.engine.solvers import user_spec
    spec = user_spec(p, game)
    fld = cond["field"]
    kinds = {r.kind for r in _uses(p, key, cond)}
    lines = []
    if "speed" in kinds and fld:
        sp = _speed(p, spec, game, dex, fld, meta)
        if sp:
            user.speed = sp
            lines.append(f"{sp[0]} to {sp[1]} Speed in {cond['label'].lower()}: outspeeds {_pct(sp[3])} of the top "
                         f"{N_SPEED}'s ladder sets, up from {_pct(sp[2])}")
    if ("damage" in kinds or "speed" in kinds) and fld:
        dm = _damage(p, spec, game, fld, threats)
        if dm:
            user.damage = dm
            user.peak = dm[2]
            lines.append(f"{dm[0]} 2HKOs {dm[2]} of the {dm[3]} most used Pokémon in {cond['label'].lower()}, {dm[1]} without it")
        if key == "sun" and any(m["name"] == "Growth" for m in _moves(p)):
            grown = _damage(p, spec, game, fld, threats, boosts={"atk": 2, "spa": 2})
            if grown and grown[2] > (dm[2] if dm else 0):
                lines.append(f"After one Growth in sun, {grown[0]} 2HKOs {grown[2]} of the {grown[3]} most used Pokémon")
                user.peak = max(user.peak, grown[2])
    user.points = lines + user.points


# --- Detection ---------------------------------------------------------------------------------

def _ladder(format_id, setters, users):
    """'Ladder players pair Venusaur with Torkoal 12x more often than chance' for the strongest setter and user pair."""
    from metamatch.auditor import load_chaos_data
    from metamatch.engine.completer import lift
    data = load_chaos_data(format_id) or {}
    best = None
    for s in setters:
        for u in users:
            if u.name == s["name"]:
                continue
            value = lift(data, u.name, s["name"])
            if value and (best is None or value > best[0]):
                best = (value, u.name, s["name"])
    if best and best[0] >= LIFT_FLOOR:
        return f"Ladder players pair {best[1]} with {best[2]} {best[0]:.0f}x more often than chance"
    return ""


def _partners(format_id, users, key, cond, team_names):
    """Setters ladder players run with these users (by teammate lift), for a half built core."""
    from metamatch.auditor import load_chaos_data
    from metamatch.engine.completer import lift
    from metamatch.engine.sets import likely_set
    data = load_chaos_data(format_id) or {}
    scores = {}
    for u in users:
        mates = (data.get(u.name) or {}).get("Teammates", {})
        for mate in sorted(mates, key=mates.get, reverse=True)[:40]:
            if mate in team_names:
                continue
            s = likely_set(mate, format_id)
            if not s:
                continue
            sets_it = s.get("ability") in cond["ability_setters"] or any(m in cond["move_setters"] for m, _ in s.get("moves", []))
            if sets_it:
                scores[mate] = max(scores.get(mate, 0), lift(data, u.name, mate) or 0)
    return [n for n, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]]


def _field_engine(team, key, cond, format_id, ctx, measure):
    users = []
    set_here = bool(_setters(team, cond, users_present=True))
    for p in team.values():
        rules = [r for r in _uses(p, key, cond) if set_here or not r.generic]
        if rules:
            users.append((p, User(p["Pokemon"], [r.text[0].upper() + r.text[1:] for r in rules], any(r.major for r in rules))))
    major = [u for _, u in users if u.major]
    setters = _setters(team, cond, users_present=bool(major))
    always_on = any(s["ability"] for s in setters)
    # A move setter with no real user is just a move; an ability setter always shapes the game
    if not major and not always_on:
        return None
    if not setters and not major:
        return None
    eng = Engine(key, cond["label"], cond["icon"], setters=setters, always_on=always_on)
    for p, u in users:
        if measure and setters:
            _measure(u, p, key, cond, ctx)
        eng.users.append(u)
    eng.users.sort(key=lambda u: (not u.major, u.name))
    if setters:
        eng.drawbacks = _drawbacks(team, key, cond)
        eng.defense = _defense(team, cond)
        eng.ladder = _ladder(format_id, setters, eng.users)
    else:
        eng.partners = _partners(format_id, [u for u in eng.users if u.major], key, cond, {p["Pokemon"] for p in team.values()})
    return eng


def _trick_room(team, ctx):
    setters = [p["Pokemon"] for p in team.values() if any(m["name"] == "Trick Room" for m in _moves(p))]
    if not setters:
        return None
    from metamatch.engine.solvers import user_spec
    eng = Engine("trick_room", "Trick Room", "Psychic", setters=[{"name": n, "how": ["Trick Room"], "ability": False} for n in setters])
    for p in team.values():
        sp = mechanics.final_speed(user_spec(p, ctx["game"]), ctx["game"], _any_move(p, ctx["dex"]))
        if not sp:
            continue
        normal = _share(sp, ctx["meta"])
        # Under Trick Room it moves first against everything it is normally slower than
        first = 1 - normal - _tie(sp, ctx["meta"])
        if first >= 0.6:
            u = User(p["Pokemon"], [f"At {sp} Speed it moves first against {_pct(first)} of the top {N_SPEED}'s ladder sets "
                                    f"under Trick Room, {_pct(normal)} normally"], True, (sp, sp, normal, first))
            eng.users.append(u)
    return eng if eng.users else None


def _tie(speed, meta):
    from metamatch.engine import speed_board
    return sum(speed_board.tie_share(speed, m) for m in meta) / len(meta) if meta else 0.0


def _tailwind(team, ctx):
    setters = [p["Pokemon"] for p in team.values() if any(m["name"] == "Tailwind" for m in _moves(p))]
    if not setters:
        return None
    eng = Engine("tailwind", "Tailwind", "Flying", setters=[{"name": n, "how": ["Tailwind for four turns"], "ability": False} for n in setters])
    from metamatch.engine.solvers import user_spec
    gains = []
    for p in team.values():
        spec = user_spec(p, ctx["game"])
        move = _any_move(p, ctx["dex"])
        before = mechanics.final_speed(spec, ctx["game"], move)
        after = mechanics.final_speed(spec, ctx["game"], move, {"attackerSide": {"isTailwind": True}})
        if before and after:
            b, a = _share(before, ctx["meta"]), _share(after, ctx["meta"])
            gains.append((a - b, p["Pokemon"], before, after, b, a))
    for gain, name, before, after, b, a in sorted(gains, reverse=True)[:3]:
        if gain >= 0.2:
            eng.users.append(User(name, [f"{before} to {after} Speed: outspeeds {_pct(a)} of the top {N_SPEED}'s ladder sets, "
                                         f"up from {_pct(b)}"], True, (before, after, b, a)))
    return eng if eng.users else None


def _screens(team, has_snow):
    setters = []
    for p in team.values():
        how = [m["name"] for m in _moves(p) if m["name"] in SCREENS]
        if how:
            if p.get("Item") == "Light Clay":
                how.append("Light Clay makes them last 8 turns")
            setters.append({"name": p["Pokemon"], "how": how, "ability": False})
    if not setters:
        return None
    eng = Engine("screens", "Screens", "Psychic", setters=setters)
    for p in team.values():
        setup = [m["name"] for m in _moves(p) if m["name"] in SETUP_MOVES]
        if setup:
            eng.users.append(User(p["Pokemon"], [f"Sets up with {_and(setup)} while screens halve the damage it takes"], True))
    if any("Aurora Veil" in s["how"] for s in setters) and not has_snow:
        eng.drawbacks.append("Aurora Veil only works in snow, and nothing on the team sets snow")
    return eng if eng.users or eng.drawbacks else None


def _settle_weather_ball(team, engines):
    """Weather Ball works in every weather, so a member whose only use of a weather is Weather Ball counts there only
    when nothing else it runs points at another weather (Walking Wake's Hydro Steam makes its Weather Ball a sun move,
    so a sand team doesn't count it; Kingdra's Swift Swim makes its Weather Ball a rain move)."""
    members = {p["Pokemon"]: p for p in team.values()}

    def signals(p, key):
        return [r for r in _uses(p, key, CONDITIONS[key]) if not r.text.startswith("Weather Ball")]

    for e in engines:
        if e.key not in WEATHER or not e.setters:
            continue
        keep = []
        for u in e.users:
            p = members.get(u.name)
            if p is not None and not signals(p, e.key) and any(signals(p, other) for other in WEATHER - {e.key}):
                continue
            keep.append(u)
        e.users = keep


def team_engines(team, format_id=None, measure=True):
    """[Engine]: every core the team runs (complete first), plus half built ones (users with no setter)."""
    format_id = format_id or config.team_format(team)
    dex = dex_for_format(format_id)
    if not dex:
        return []
    game = config.format_game(format_id)
    ctx = {"game": game, "dex": dex, "threats": [], "meta": []}
    if measure and calc.available():
        ctx["threats"] = _threat_specs(team, format_id)
        ctx["meta"] = _meta(team, format_id)
    engines = []
    for key, cond in CONDITIONS.items():
        eng = _field_engine(team, key, cond, format_id, ctx, measure and calc.available())
        if eng:
            engines.append(eng)
    if measure and calc.available():
        for build in (_trick_room, _tailwind):
            eng = build(team, ctx)
            if eng:
                engines.append(eng)
    has_snow = any(e.key == "snow" and e.setters for e in engines) or any(
        m["name"] in ("Snowscape", "Chilly Reception") or "Snow Warning" in _abilities(p) for p in team.values() for m in _moves(p))
    eng = _screens(team, has_snow)
    if eng:
        engines.append(eng)
    _settle_weather_ball(team, engines)
    # Complete cores first, then cores an ability sets, then half built ones
    engines.sort(key=lambda e: (not e.complete, not e.always_on, not e.setters))
    return engines


def _label(engine):
    """'sun' and 'rain' read lowercase in a sentence; Electric Terrain, Trick Room and the rest keep their capitals."""
    return engine.label.lower() if engine.key in WEATHER | {"screens"} else engine.label


def describe(engine):
    """One plain sentence for the engine, for the guide's text and the coach's prompt."""
    setter_names = [s["name"] for s in engine.setters]
    if engine.setters and engine.users:
        major = [u.name for u in engine.users if u.major] or [u.name for u in engine.users]
        others = [n for n in major if n not in setter_names]
        verb = "sets" if len(setter_names) == 1 else "set"
        if not others:
            return f"{_and(setter_names)} {verb} {_label(engine)} for {'itself' if len(setter_names) == 1 else 'themselves'}"
        return f"{_and(setter_names)} {verb} {_label(engine)} for {_and(others)}"
    if engine.users and not engine.setters:
        names = [u.name for u in engine.users if u.major] or [u.name for u in engine.users]
        return f"{_and(names)} {'wants' if len(names) == 1 else 'want'} {_label(engine)}, but nothing on the team sets it"
    return f"{_and(setter_names)} {'sets' if len(setter_names) == 1 else 'set'} {_label(engine)}"


def headline(engine, user):
    """The one line the guide's win condition quotes: what the core does for this member, with its number."""
    others = [s["name"] for s in engine.setters if s["name"] != user.name]
    lead = (f"With {_poss(_and(others))} {_label(engine)} up" if others else f"With its own {_label(engine)}")
    if engine.key == "trick_room" and user.speed:
        return f"Under Trick Room it moves first against {_pct(user.speed[3])} of the top {N_SPEED}'s ladder sets"
    if user.speed:
        return f"{lead}, it reaches {user.speed[1]} Speed and outspeeds {_pct(user.speed[3])} of the top {N_SPEED}'s ladder sets"
    if user.damage:
        move, off, on, n = user.damage
        return f"{lead}, {move} 2HKOs {on} of the {n} most used Pokémon ({off} without it)"
    point = user.points[0] if user.points else ""
    return f"{lead}: {point[:1].lower()}{point[1:]}"

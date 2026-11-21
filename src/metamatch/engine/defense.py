"""
Your walls: what each of the team's defenders can stay in on, take a hit from or must avoid among the format's most
used Pokemon, which side (physical or special) it takes hits from, and what its burn or poison does to the threats
it faces. Built from the Threat Board's numbers (every hit of each threat's most common set, from full HP) and the
damage calc, plus the game's fixed rules: what each recovery move heals (engine/moves.py), Regenerator's third,
Leftovers' sixteenth, Assault Vest and Eviolite's 1.5x, and who can't be burned or poisoned.
"""
from metamatch import config
from metamatch.engine import threat_board as tb
from metamatch.engine.moves import RECOVERY, STATUS_MOVES, category

DEFENDER_ROLES = {"Wall", "Tank", "Special Tank"}
REGENERATOR = 1 / 3
LEFTOVERS = 1 / 16
LEAN = 1.2            # one side's bulk this much bigger than the other's reads as leaning that way
SHOWN = 4             # sprites per row on a card
BURN_SHOWN = 2
# Status chances worth a line: a 10% Flamethrower burn is luck, not a plan; poison "wears down" only when it's reliable
MIN_BURN, MIN_POISON = 30, 50

# Who a status can't touch, and who it helps instead (the game's rules)
NO_BURN_TYPES, NO_POISON_TYPES = {"Fire"}, {"Steel", "Poison"}
NO_BURN = {"Water Veil", "Water Bubble", "Thermal Exchange", "Purifying Salt", "Comatose"}
NO_POISON = {"Immunity", "Pastel Veil", "Purifying Salt", "Comatose"}
HELPED_BY = {"brn": {"Guts", "Flare Boost", "Magic Guard"},
             "psn": {"Guts", "Toxic Boost", "Poison Heal", "Magic Guard"}}


def _abilities(p):
    return [a for a in (p.get("Ability"), p.get("Mega Ability")) if a]


def is_defender(p):
    """Built to take hits: a Wall, Tank or Special Tank (team.detectRole), Regenerator, or Eviolite."""
    return bool(DEFENDER_ROLES & set(p.get("Roles") or [])) or "Regenerator" in _abilities(p) or p.get("Item") == "Eviolite"


def recovery(p):
    """{move, heal, regenerator, passive, lines}: the member's best recovery move and its heal (0 to 1, None when it
    varies), Regenerator, and Leftovers or Black Sludge, with one plain line each."""
    moves = [m["name"] for m in p.get("Moves", []) if m.get("name") in RECOVERY]
    move = max(moves, key=lambda m: RECOVERY[m] or 0, default=None)
    heal = RECOVERY.get(move) if move else None
    lines = []
    if move == "Rest":
        lines.append("Rest heals it fully, but it falls asleep")
    elif move == "Wish":
        lines.append("Wish heals 50% the turn after")
    elif move and heal:
        lines.append(f"{move} heals {heal * 100:.0f}%")
    elif move:
        lines.append(f"{move} heals by the foe's Attack")
    regen = "Regenerator" in _abilities(p)
    if regen:
        lines.append("Regenerator heals 33% when it switches out")
    item = p.get("Item")
    passive = item == "Leftovers" or (item == "Black Sludge" and "Poison" in (p.get("Type") or []))
    if passive:
        lines.append(f"{item} heals 6% a turn")
    # Rest and Wish don't heal on the turn the hit lands, so they don't let it stay in and heal through a hit
    wall_heal = heal if move not in ("Rest", "Wish") else None
    return {"move": move, "heal": wall_heal, "regenerator": regen, "passive": passive, "lines": lines}


def classify(n, rec):
    """'walls', 'pivots', 'breaks' or None for one threat's numbers against a defender (threat_board.cell_numbers).
    walls: its strongest hit is less than one recovery move heals (it stays in and heals through), or, without one,
    less than Regenerator heals on the way out. pivots: it takes a hit safely (the one switch in rule). breaks: two
    hits or fewer knock it out from full HP."""
    if not n:
        return None
    hi = n["taken_hi"]
    if n.get("to_be_koed") and n["to_be_koed"] <= 2:
        return "breaks"
    if rec["heal"] and hi < rec["heal"] * 100:
        return "walls"
    if rec["regenerator"] and not rec["heal"] and hi < REGENERATOR * 100:
        return "walls"
    if tb.safe_switch(n):
        return "pivots"
    return None


def _tip(threat, n, kind, rec):
    hit = (f"{n['taken_move']} up to {n['taken_hi']:.0f}%" if n.get("taken_move") and n["taken_hi"] < 100
           else f"{n['taken_move']} knocks it out" if n.get("taken_move") else "its usual attacks do nothing")
    if kind == "walls":
        healer = rec["move"] if rec["heal"] else "Regenerator"
        back = "" if n.get("to_ko") else ", though it can't hurt it back"
        return f"{threat}: {hit}, less than {healer} heals{back}"
    if kind == "breaks":
        if n["taken_hi"] >= 100:
            return f"{threat}: {hit} in one hit"
        return f"{threat}: {hit}, " + ("a one hit knockout" if n["to_be_koed"] == 1 else "two hits knock it out")
    return f"{threat}: {hit}" + (", but it survives a second hit" if n["taken_hi"] >= 50 else "")


def bulk(p, game):
    """{physical, special, lean}: HP x Def and HP x SpD from the calc's final stats, with Assault Vest (1.5x SpD) and
    Eviolite (1.5x both) applied, and which side it leans ('physical', 'special' or None). None without the calc."""
    from metamatch.engine.solvers import _stats, user_spec
    moves = [m["name"] for m in p.get("Moves", []) if m.get("name")]
    try:
        stats = _stats(game, user_spec(p, game), moves[0] if moves else "Tackle")
    except Exception:
        stats = None
    if not stats:
        return None
    d, s = stats["def"], stats["spd"]
    if p.get("Item") == "Assault Vest":
        s *= 1.5
    if p.get("Item") == "Eviolite":
        d, s = d * 1.5, s * 1.5
    phys, spec = stats["hp"] * d, stats["hp"] * s
    lean = "physical" if phys >= LEAN * spec else "special" if spec >= LEAN * phys else None
    return {"physical": phys, "special": spec, "lean": lean}


def _worst(name, rows):
    """{'Physical': (threat, move, high %), 'Special': ...}: the strongest hit of each kind it takes from the top threats."""
    out = {}
    for r in rows:
        n = ((r.get("cells") or {}).get(name) or {}).get("n") or {}
        for move, _, hi, cat in n.get("hits") or []:
            if cat in ("Physical", "Special") and hi > out.get(cat, ("", "", -1))[2]:
                out[cat] = (r["name"], move, hi)
    return out


def _threat_info(name, format_id):
    """(types, ability) of a threat's most common set."""
    from metamatch.engine.dex import dex_for_format
    from metamatch.engine.sets import likely_set
    dex = dex_for_format(format_id)
    s = likely_set(name, format_id) or {}
    return list(((dex.species(name) if dex else None) or {}).get("types") or []), s.get("ability"), s


def _immune(status, types, ability):
    if status == "brn":
        return bool(NO_BURN_TYPES & set(types)) or ability in NO_BURN
    return bool(NO_POISON_TYPES & set(types)) or ability in NO_POISON


def status_lines(p, rows, kinds, format_id):
    """Plain lines on what the defender's burn and poison moves do to the top threats it faces: the burned damage of
    the most used physical threats it doesn't already wall (recalculated), who poison wears down while it stalls,
    and who can't be burned or poisoned, or is helped by it."""
    from metamatch.engine.dex import dex_for_format
    from metamatch.logic_engine import best_hits
    mine = [m["name"] for m in p.get("Moves", []) if m.get("name")]
    burns = [(m, STATUS_MOVES[m][1]) for m in mine if STATUS_MOVES.get(m, ("",))[0] == "brn"
             and STATUS_MOVES[m][1] >= MIN_BURN]
    poisons = [(m, STATUS_MOVES[m][1]) for m in mine if STATUS_MOVES.get(m, ("",))[0] in ("psn", "tox")
               and STATUS_MOVES[m][1] >= MIN_POISON]
    lines = []
    name, game, dex = p["Pokemon"], config.format_game(format_id), dex_for_format(format_id)
    if burns:
        move, chance = max(burns, key=lambda mc: mc[1])
        how = f"After {move}" if chance >= 100 else f"If {move} burns it ({chance}%)"
        shown, immune, helped = 0, [], []
        for r in rows:
            n = ((r.get("cells") or {}).get(name) or {}).get("n") or {}
            hits = n.get("hits") or []
            if not hits or hits[0][3] != "Physical" or kinds.get(r["name"]) == "walls":
                continue
            types, ability, s = _threat_info(r["name"], format_id)
            if _immune("brn", types, ability):
                immune.append(r["name"])
                continue
            if ability in HELPED_BY["brn"]:
                helped.append(f"{r['name']} ({ability})")
                continue
            if shown >= BURN_SHOWN or not s or not dex:
                continue
            burned = best_hits(p, dict(s, status="brn"), game, dex, n=4)
            if not burned or not burned[1]:
                continue
            bmove, res = burned[1][0]
            lines.append(f"{how}, {r['name']}'s {bmove} does up to {res['percent'][1]:.0f}% "
                         f"instead of {hits[0][2]:.0f}%")
            shown += 1
        if immune:
            lines.append(f"{_and(immune)} can't be burned")
        if helped:
            lines.append(f"A burn helps {_and(helped)}")
    if poisons:
        move = max(poisons, key=lambda mc: mc[1])[0]
        worn, immune, helped = [], [], []
        for r in rows:
            if kinds.get(r["name"]) not in ("walls", "pivots"):
                continue
            types, ability, _ = _threat_info(r["name"], format_id)
            if _immune("psn", types, ability):
                immune.append(r["name"])
            elif ability in HELPED_BY["psn"]:
                helped.append(f"{r['name']} ({ability})")
            else:
                worn.append(r["name"])
        if worn:
            lines.append(f"{move} wears down {_and(worn[:3])} while {name} takes their hits")
        if immune:
            lines.append(f"{_and(immune[:3])} can't be poisoned")
        if helped:
            lines.append(f"Poison helps {_and(helped[:2])}")
    return lines


def _and(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def card(p, rows, format_id):
    """One defender's card."""
    name = p["Pokemon"]
    rec = recovery(p)
    groups, kinds = {"walls": [], "pivots": [], "breaks": []}, {}
    for r in rows:
        n = ((r.get("cells") or {}).get(name) or {}).get("n")
        kind = classify(n, rec)
        if kind:
            kinds[r["name"]] = kind
            groups[kind].append({"name": r["name"], "tip": _tip(r["name"], n, kind, rec)})
    try:
        status = status_lines(p, rows, kinds, format_id)
    except Exception as e:   # a bonus line: never let it break the card
        print(f"Status lines failed for {name}: {e}")
        status = []
    return {"name": name, "item": p.get("Item"), "ability": p.get("Mega Ability") or p.get("Ability"),
            "types": list(p.get("Type") or []), "recovery": rec["lines"],
            "bulk": bulk(p, config.format_game(format_id)), "worst": _worst(name, rows),
            "walls": groups["walls"][:SHOWN], "pivots": groups["pivots"][:SHOWN], "breaks": groups["breaks"][:SHOWN],
            "kinds": kinds, "status": status}


def _summary(team, rows, cards):
    """One line naming the side (physical or special) nothing on the team takes safely, or None."""
    open_sides, held = {"Physical": [], "Special": []}, {"Physical": set(), "Special": set()}
    for r in rows:
        cells = {m: c.get("n") for m, c in (r.get("cells") or {}).items() if c.get("n")}
        if not cells:
            continue
        # The threat's side: the kind of its strongest hit on the team
        _, top = max(cells.items(), key=lambda mn: mn[1]["taken_hi"])
        side = next((h[3] for h in top.get("hits") or [] if h[3] in open_sides), None)
        if not side:
            continue
        takers = [m for m, n in cells.items() if tb.safe_switch(n)]
        if takers:
            held[side].update(takers)
        else:
            open_sides[side].append(r["name"])
    names = {c["name"] for c in cards}
    words = {"Physical": "physical", "Special": "special"}
    gaps = [s for s, threats in open_sides.items() if len(threats) >= 2]
    if not gaps:
        return None
    if len(gaps) == 2:
        return ("Nothing on your team safely takes a hit from " + _and(open_sides["Physical"][:2] + open_sides["Special"][:2]) +
                ", physical or special.")
    gap = gaps[0]
    other = "Special" if gap == "Physical" else "Physical"
    who = [m for m in held[other] if m in names][:2]
    threats = _and(open_sides[gap][:3])
    if who:
        return (f"{_and(who)} {'takes' if len(who) == 1 else 'take'} the {words[other]} hits, but nothing on your team "
                f"safely takes {words[gap]} ones from {threats}.")
    return f"Nothing on your team safely takes {words[gap]} hits from {threats}."


def defense_plan(team, format_id, rows):
    """{cards, summary}: a card per defender (most used threats first in each row) and the team's gap, or None
    when there are no defenders and no gap."""
    cards = [card(p, rows, format_id) for p in team.values() if is_defender(p)]
    summary = _summary(team, rows, cards)
    if not cards and not summary:
        return None
    return {"cards": cards, "summary": summary}

"""
Hazard plan: what entry hazards cost each member every time it switches in, what the team does about them, and
which of the format's most used Pokemon bring them. Rules only, from the game's fixed numbers: Stealth Rock takes
12.5% times the Rock weakness, Spikes 12.5% at one layer and 25% at three, grounded Pokemon only. Heavy-Duty Boots
and Magic Guard take nothing; Magic Bounce sends hazard moves back.
"""
from metamatch.engine.guide import _and
from metamatch.engine.moves import HAZARDS, REMOVAL
from metamatch.engine.sets import chaos_entry
from metamatch.engine.synergy import _abilities, _grounded
from metamatch.engine.threat_board import top_threats

ROCKS_BASE = 12.5
SPIKES = {1: 12.5, 3: 25.0}
SETTER_SHARE = 0.3     # a top Pokemon counts as bringing a hazard when this share of its sets runs it
N_META = 12
WORDS = {50.0: "half", 25.0: "a quarter"}


def _protected(p):
    """'Heavy-Duty Boots' or 'Magic Guard' when the member takes no hazard damage, else None."""
    if p.get("Item") == "Heavy-Duty Boots":
        return "Heavy-Duty Boots"
    if "Magic Guard" in _abilities(p):
        return "Magic Guard"
    return None


def member_hazards(p):
    """{name, rocks, spikes1, spikes3, grounded, protected}: % of max HP lost on each switch in."""
    guard = _protected(p)
    mult = (p.get("Damage From") or {}).get("rock", 1.0)
    grounded = _grounded(p)
    rocks = 0.0 if guard else ROCKS_BASE * mult
    return {"name": p["Pokemon"], "rocks": rocks, "grounded": grounded, "protected": guard,
            "mega": "-Mega" in (p.get("Forme") or ""),   # holds its stone, so it can't wear Boots
            "spikes1": 0.0 if guard or not grounded else SPIKES[1], "spikes3": 0.0 if guard or not grounded else SPIKES[3]}


def meta_setters(format_id, exclude=(), n=N_META):
    """The most used Pokemon that bring Stealth Rock or Spikes: [{name, usage, rocks, spikes}] with shares 0 to 1."""
    out = []
    for name, usage in top_threats(format_id, exclude=exclude, n=n):
        _, entry = chaos_entry(name, format_id)
        if not entry:
            continue
        total = sum((entry.get("Abilities") or {}).values()) or 1
        moves = entry.get("Moves") or {}
        rocks, spikes = moves.get("stealthrock", 0) / total, moves.get("spikes", 0) / total
        if max(rocks, spikes) >= SETTER_SHARE:
            out.append({"name": name, "usage": usage, "rocks": min(rocks, 1.0), "spikes": min(spikes, 1.0)})
    return out


def hazard_plan(team, format_id):
    """The team's hazard plan: members, its own setters and removers, Magic Bounce, Boots, the meta's setters and
    one plain verdict."""
    members = [member_hazards(p) for p in team.values()]
    moves = {p["Pokemon"]: {m["name"] for m in p.get("Moves", []) if m.get("name")} for p in team.values()}
    setters = [{"name": n, "moves": [h for h in HAZARDS if h in ms]} for n, ms in moves.items() if ms & set(HAZARDS)]
    removers = [{"name": n, "moves": [r for r in REMOVAL if r in ms]} for n, ms in moves.items() if ms & set(REMOVAL)]
    bounce = [p["Pokemon"] for p in team.values() if "Magic Bounce" in _abilities(p)]
    boots = [p["Pokemon"] for p in team.values() if p.get("Item") == "Heavy-Duty Boots"]
    meta = meta_setters(format_id, exclude=[p["Pokemon"] for p in team.values()] + [p.get("Forme") for p in team.values()])
    return {"members": members, "setters": setters, "removers": removers, "bounce": bounce, "boots": boots,
            "meta": meta, "verdict": _verdict(members, removers, bounce)}


def _verdict(members, removers, bounce):
    """One sentence on what hazards mean for this team, or None when they barely matter."""
    weak = sorted((m for m in members if m["rocks"] >= 25), key=lambda m: -m["rocks"])
    clear = _and([r["name"] for r in removers]) if removers else ""
    if weak:
        groups = {}
        for m in weak:
            groups.setdefault(m["rocks"], []).append(m["name"])
        # "Stealth Rock takes half of Charizard's HP and a quarter of Weavile's every time they come in"
        parts = [f"{WORDS.get(pct, f'{pct:g}%')} of {_and([n + chr(39) + 's' for n in names])}" + (" HP" if i == 0 else "")
                 for i, (pct, names) in enumerate(groups.items())]
        line = f"Stealth Rock takes {_and(parts)} every time {'it comes' if len(weak) == 1 else 'they come'} in"
        if removers:
            return f"{line}. Keep {clear} healthy so {'it' if len(removers) == 1 else 'they'} can clear the rocks."
        if bounce:
            return f"{line}. {_and(bounce)} can bounce Stealth Rock back, but nothing on your team clears it once it's up."
        wear = next((m["name"] for m in weak if not m["mega"]), None)
        fix = f"Heavy-Duty Boots on {wear}, or a Defog or Rapid Spin user, fixes that." if wear else             "A Defog or Rapid Spin user fixes that."
        return f"{line}, and nothing on your team clears it. {fix}"
    exposed = [m for m in members if m["spikes1"] > 0]
    if not removers and len(exposed) >= 4:
        return (f"Nothing on your team clears hazards, and {len(exposed)} of your six take Spikes damage, "
                "so long games against Spikes teams wear you down.")
    return None

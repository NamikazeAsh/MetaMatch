"""
Engine answers for Brock's building questions: comparing options on a Pokemon ("Specs or Band on Dragapult"),
teammate and replacement picks from the Team Completer, and which of the trainer's members fills a role.
Each returns a Verdict with a plain answer sentence and typed facts (engine/packet.py), so Brock only voices it.
"""
from metamatch import config
from metamatch.engine.dex import to_id
from metamatch.engine.packet import Fact, join, mon
from metamatch.engine.sets import chaos_entry, likely_set
from metamatch.engine.solvers import ORDINALS, Verdict, _user_name

FIELDS = {"item": "Items", "move": "Moves", "ability": "Abilities"}
SPECIAL_ITEMS = {"choicespecs": "special", "choiceband": "physical", "wiseglasses": "special", "muscleband": "physical"}


def _share(entry, kind, name, dex):
    """(share of sets, rank) of one option on a species' ladder sets, or (0, None)."""
    total = sum(entry.get("Abilities", {}).values()) or 1
    table = entry.get(FIELDS[kind], {})
    ranked = sorted(((k, v / total) for k, v in table.items() if k and k != "nothing" and v > 0), key=lambda x: -x[1])
    want = to_id(name)
    for i, (k, v) in enumerate(ranked):
        if to_id(k) == want:
            return v, i + 1
    return 0.0, None


def _place(rank, kind):
    noun = {"item": "item", "move": "move", "ability": "ability"}[kind]
    return f"the {ORDINALS[rank]} {noun}" if rank and rank < len(ORDINALS) else (f"number {rank} among its {noun}s" if rank else f"not a listed {noun}")


def _attack_split(moves, dex):
    phys = [m for m in moves if (dex.move(m) or {}).get("category") == "Physical"]
    spec = [m for m in moves if (dex.move(m) or {}).get("category") == "Special"]
    return phys, spec


def solve_compare(plan, dex, game):
    """'Specs or Band on Dragapult', 'should my Corviknight run Rocky Helmet instead': each option's ladder share and
    rank on that Pokemon, what the trainer's member holds now, and for attack boosting items how many of its attacks
    each one powers up."""
    from metamatch.engine import rules
    options = plan.options[:2]
    if not options:
        return None
    member = plan.user if plan.user is not None and plan.user_named else None
    target = (member.get("Forme") or member["Pokemon"]) if member else plan.opponent
    if not target:
        return None
    key, entry = chaos_entry(target, plan.format_id)
    if not entry:
        return None
    label = config.format_info(plan.format_id)["label"]
    lad = f"ladder {key}"
    typed, parts = [], []
    shares = {}
    for kind, name in options:
        share, rank = _share(entry, kind, name, dex)
        shares[name] = share
        parts.append(f"{name} on {round(share * 100)}%")
        typed.append(Fact("usage", f"{name} is on {round(share * 100)}% of {lad} sets, {_place(rank, kind)}.",
                          {"option": name, "kind": kind, "share": round(share, 3), "rank": rank}, role="why"))
    said = f"On the {label} ladder, {key} runs " + join(parts) + " of its sets."
    if len(options) == 2:
        (a, b) = [n for _, n in options]
        hi, lo = (a, b) if shares[a] >= shares[b] else (b, a)
        if shares[hi] >= 0.1 and shares[hi] >= 3 * max(shares[lo], 0.005):
            said += f" Ladder players clearly prefer {hi}."
    moves = [m["name"] for m in member.get("Moves", [])] if member else [m for m, _ in (likely_set(target, plan.format_id) or {}).get("moves", [])]
    phys, spec = _attack_split(moves, dex)
    whose = mon(_user_name(member), True) if member else lad
    if any(to_id(n) in SPECIAL_ITEMS for kind, n in options if kind == "item"):
        typed.append(Fact("set", f"{whose[:1].upper() + whose[1:]} has {len(spec)} special and {len(phys)} physical "
                                 "attacks" + (f": {join(spec + phys)}." if spec or phys else "."),
                          {"special": spec, "physical": phys}, role="why"))
    if member:
        held = member.get("Item") or "no item"
        typed.append(Fact("set", f"{whose[:1].upper() + whose[1:]} holds {held} now.", {"item": held}))
        if any(kind == "item" and to_id(n) == to_id(held) for kind, n in options):
            said += f" Your {_user_name(member)} already holds {held}."
    for kind, name in options:
        line = rules.text_line(kind, name)
        if line:
            typed.append(Fact("rule", line, {"source": "Showdown"}))
    statement = said
    facts = [f.text for f in typed]
    return Verdict("compare", options[0][1] if shares.get(options[0][1], 0) >= max(shares.values()) else options[-1][1],
                   statement, facts, persona="builder", plain=said, typed=typed)


def solve_teammate(plan, dex, game):
    """'Suggest a teammate', 'what should I replace Corviknight with': Team Completer picks (they beat threats the team
    struggles with, fill missing roles, and pair well on the ladder), never a Pokemon already on the team."""
    from metamatch.engine.completer import complete
    team = plan.team or {}
    replacing = plan.user if plan.user is not None and plan.user_named and plan.replace else None
    rest = {k: v for k, v in team.items() if v is not replacing} if replacing else team
    picks, _, _ = complete(rest, plan.format_id, top_n=4)
    names = {p["Pokemon"] for p in team.values()}
    picks = [c for c in picks if c.name not in names][:3]
    if not picks:
        return None
    typed = []
    for i, c in enumerate(picks):
        why = []
        if c.covers:
            why.append(f"beats {join(mon(t, False) for t in c.covers[:3])} one on one, which your team struggles with")
        if c.roles:
            why.append(f"adds a role your team lacks: {join(r.lower() for r in c.roles)}")
        if c.best_pair and c.best_pair[1] and c.best_pair[1] > 1.2:
            why.append(f"is often paired with {c.best_pair[0]} on the ladder")
        text = f"{c.name}, used on {c.usage:g}% of ladder teams" + (", " + "; ".join(why) if why else "") + "."
        typed.append(Fact("role", text, {"pick": c.name, "covers": c.covers, "roles": c.roles}, role="why" if i < 2 else "context"))
    slot = f" for the slot your {_user_name(replacing)} would leave" if replacing else ""
    said = f"The best new teammates{slot} are {join(c.name for c in picks)}."
    return Verdict("teammate", picks[0].name, said, [f.text for f in typed], persona="builder", plain=said, typed=typed)


ROLE_WORDS = {"wallbreaker": ("Wallbreaker", "Physical Breaker", "Special Breaker"), "breaker": ("Wallbreaker", "Physical Breaker", "Special Breaker"),
              "pivot": ("Pivot",), "hazard setter": ("Hazard Setter",), "hazard remover": ("Hazard Remover",),
              "hazard removal": ("Hazard Remover",), "sweeper": ("Setup Sweeper", "Physical Sweeper", "Special Sweeper", "Fast Sweeper"),
              "wall": ("Wall", "Tank"), "tank": ("Tank", "Wall"), "speed control": ("Speed Control",),
              "priority": ("Priority User",), "revenge killer": ("Revenge Killer",), "spinblocker": ("Spin Blocker",),
              "spin blocker": ("Spin Blocker",)}


def solve_roles(plan, dex, game):
    """'Which of my mons is my best wallbreaker': the members the role detector gives that role."""
    team = plan.team or {}
    word = plan.role
    wanted = ROLE_WORDS.get(word, ())
    holders = [p["Pokemon"] for p in team.values() if set(p.get("Roles", [])) & set(wanted)]
    typed = [Fact("role", f"Your {p['Pokemon']}'s roles: {', '.join(p.get('Roles', [])) or 'none detected'}.",
                  {"member": p["Pokemon"]}, role="why" if p["Pokemon"] in holders[:2] else "context") for p in team.values()]
    if holders:
        said = f"{join(mon(h, True) for h in holders)} {'fills' if len(holders) == 1 else 'fill'} the {word} role on your team."
        said = said[0].upper() + said[1:]
    else:
        said = f"Nobody on your team is detected as a {word}."
    return Verdict("roles", ", ".join(holders) or "none", said, [f.text for f in typed], persona="builder", plain=said, typed=typed)


SOLVERS = {"compare": solve_compare, "teammate": solve_teammate, "roles": solve_roles}

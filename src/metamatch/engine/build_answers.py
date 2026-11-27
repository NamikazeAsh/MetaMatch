"""
Engine answers for Brock's building questions: comparing options on a Pokemon ("Specs or Band on Dragapult"),
teammate and replacement picks from the Team Completer, and which of the trainer's members fills a role.
Each returns a Verdict with a plain answer sentence and typed facts (engine/packet.py), so Brock only voices it.
"""
import copy
import json
from dataclasses import replace
from functools import lru_cache

from metamatch import config
from metamatch.engine.dex import to_id
from metamatch.engine.guide import _mult
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


N_JUDGE = 12   # the most used Pokemon a compare judges each option against, as on the Threat Board


@lru_cache(maxsize=8)
def _members_for(team_json, format_id):
    from metamatch.engine.guide import board_rows, member_facts
    team = json.loads(team_json)
    return {m.name: m for m in member_facts(team, format_id, board_rows(team, format_id))}


def _members(plan):
    team = plan.team or {}
    return _members_for(json.dumps(team, sort_keys=True, default=str), plan.format_id)


def _pick(scores, unit):
    """The sentence that names the option the numbers favor, or says they're too close: scores {option: number}."""
    (a, sa), (b, sb) = sorted(scores.items(), key=lambda kv: -kv[1])[:2]
    if sa - sb <= 1:
        return None, f"On these numbers it's too close to call between {a} and {b}."
    return a, f"On these numbers, {a}: {unit(a, sa)}, against {sb} with {b}."


def _with_option(member, kind, name, dex, others):
    """A copy of a team member running `name` in place of the other options compared."""
    p = copy.deepcopy(member)
    if kind == "item":
        p["Item"] = name
    elif kind == "ability":
        p["Ability"] = name
        p.pop("Mega Ability", None)
    elif kind == "move":
        mv = dex.move(name) or {}
        kept = [m for m in p.get("Moves", []) if to_id(m["name"]) not in {to_id(o) for o in others}]
        new = {"name": name, "type": mv.get("type"), "power": mv.get("basePower") or None, "accuracy": None,
               "category": mv.get("category")}
        p["Moves"] = (kept + [new])[-4:] if len(kept) >= 4 else kept + [new]
    return p


def _judge_set(plan, member, options, dex, game):
    """Each option on the member against the format's most used Pokemon, one on one: (facts, pick, sentence)."""
    from metamatch.engine.briefing import _verdict, exchange
    from metamatch.engine.threat_board import member_names, top_threats
    names = [n for _, n in options]
    threats = top_threats(plan.format_id, exclude=member_names(plan.team or {}), n=N_JUDGE)
    beats = {}
    for kind, name in options:
        p = _with_option(member, kind, name, dex, names)
        won = []
        for threat, _ in threats:
            s = likely_set(threat, plan.format_id)
            x = exchange(p, s, game, dex) if s else None
            if x is None and s:
                return [], None, None   # the calculator is down: no numbers to judge by
            if x and _verdict(x) == "win":
                won.append(s["name"])
        beats[name] = won
    who = _user_name(member)
    facts = [Fact("matchup", f"With {n}, your {who} beats {len(w)} of the {len(threats)} most used Pokemon one on one"
                             + (f", including {join(w[:4])}." if w else "."),
                  {"option": n, "beats": w}, role="why") for n, w in beats.items()]
    a, b = names
    only = {n: [t for t in beats[n] if t not in beats[o]] for n, o in ((a, b), (b, a))}
    for n, extra in only.items():
        if extra:
            facts.append(Fact("matchup", f"Only {n} beats {join(extra)}.", {"option": n, "only": extra}, role="why"))
    pick, said = _pick({n: len(w) for n, w in beats.items()},
                       lambda n, k: f"your {who} beats {k} of the {len(threats)} most used Pokemon with it")
    if any(to_id(n) == "heavydutyboots" for n in names):
        rock = _mult("Rock", member.get("Type") or [])
        facts.append(Fact("set", f"Without Heavy-Duty Boots, Stealth Rock takes {round(12.5 * rock)}% of its HP each "
                                 "time it switches in.", {"rock": rock}))
    return facts, pick, said


def _judge_tera(plan, member, types):
    """Each Tera type's weaknesses removed and added and what it does for the member's attacks (typing only)."""
    from metamatch.engine.guide import _tera
    m = _members(plan).get(member["Pokemon"])
    if not m:
        return [], None, None
    rows = {t: _tera([replace(m, tera=t)])[0] for t in types}
    facts = []
    for t, r in rows.items():
        parts = [f"removes its {join(r['removed'])} weakness" + ("es" if len(r["removed"]) > 1 else "")
                 if r["removed"] else "removes none of its weaknesses"]
        if r["added"]:
            parts.append(f"adds {join(r['added'])}")
        note = r["note"]
        note = note[:1].lower() + note[1:] if note.split(" ")[0] in ("Purely", "Stellar") else note
        facts.append(Fact("tera", f"Tera {t} " + ", ".join(parts) + f"; {note}.",
                          {"tera": t, "removed": r["removed"], "added": r["added"]}, role="why"))
    facts.append(Fact("note", "This weighs typing and same type bonus only: the one on one calcs don't model Tera.", {}))
    (a, ra), (b, rb) = sorted(rows.items(), key=lambda kv: -kv[1]["score"])

    def counts(r):
        return f"removes {len(r['removed'])} weakness{'es' if len(r['removed']) != 1 else ''} and adds {len(r['added'])}"
    detail = f"Tera {a} {counts(ra)}, Tera {b} {counts(rb)}."
    if ra["score"] == rb["score"]:
        return facts, None, f"On typing alone, Tera {a} and Tera {b} come out even: {detail}"
    return facts, f"Tera {a}", f"On typing, Tera {a} does more for your {_user_name(member)}: {detail}"


def _judge_pokemon(plan, names):
    """Two Pokemon for a slot or a Mega: members' one on ones against the top threats, or how each covers the
    threats the rest of the team struggles with (the Team Completer)."""
    team = plan.team or {}
    on_team = {p["Pokemon"]: p for p in team.values()}
    if all(n in on_team for n in names):
        members = _members(plan)
        beats = {n: (members[n].beats if n in members else []) for n in names}
        facts = [Fact("matchup", f"Your {n} beats {len(b)} of the most used Pokemon one on one"
                                 + (f", including {join(b[:4])}." if b else "."), {"pokemon": n, "beats": b}, role="why")
                 for n, b in beats.items()]
        pick, said = _pick({n: len(b) for n, b in beats.items()},
                           lambda n, k: f"it beats {k} of the most used Pokemon one on one")
        return facts, pick, said
    from metamatch.auditor import load_chaos_data
    from metamatch.engine.completer import complete
    from metamatch.recommender import base_species
    data = load_chaos_data(plan.format_id) or {}
    absent = [n for n in names if n not in data and n not in on_team]
    if absent:
        label = config.format_info(plan.format_id)["label"]
        said = (f"{join(absent)} {'isn' if len(absent) == 1 else 'aren'}'t on the {label} ladder this month (no usage "
                f"data), so I can't weigh {'it' if len(absent) == 1 else 'them'} against your team here.")
        return [], None, said
    rest = {k: p for k, p in team.items() if base_species(p["Pokemon"]) not in {base_species(n) for n in names}}
    ranked, _, board = complete(rest, plan.format_id, top_n=200, extra=list(names))
    found = {c.name: c for c in ranked if c.name in names}
    if len(found) < 2:
        return [], None, None
    facts = [Fact("teammate", f"{n} beats {len(c.covers)} of the threats the rest of your team struggles with"
                              + (f": {join(c.covers[:4])}" if c.covers else "") + "."
                              + (f" It adds {join(c.roles)}." if c.roles else ""),
                  {"pokemon": n, "covers": c.covers, "roles": c.roles}, role="why") for n, c in found.items()]
    pick, said = _pick({n: len(c.covers) for n, c in found.items()},
                       lambda n, k: f"it beats {k} of the threats the rest of your team struggles with")
    return facts, pick, said


def solve_compare(plan, dex, game):
    """'Specs or Band on Dragapult', 'tera fairy or tera steel for my gholdengo', 'mega lop or mega zard': the engine's
    judgement first (one on ones against the most used Pokemon with each option, or Tera typing, or how each Pokemon
    covers the team's holes), naming the option the numbers favor; then each option's ladder share and rank, what the
    trainer's member holds now, and for attack boosting items how many of its attacks each one powers up."""
    from metamatch.engine import rules
    options = plan.options[:2]
    if not options:
        return None
    member = plan.user if plan.user is not None and plan.user_named else None
    kinds = {k for k, _ in options}
    judged, pick, verdict_said = [], None, None
    if kinds == {"pokemon"} and len(options) == 2:
        judged, pick, said = _judge_pokemon(plan, [n for _, n in options])
        if not said:
            return None
        return Verdict("compare", pick or "close", said, [f.text for f in judged], persona="builder", plain=said,
                       typed=judged)
    if member and kinds == {"tera"} and len(options) == 2:
        judged, pick, verdict_said = _judge_tera(plan, member, [n for _, n in options])
    elif member and len(options) == 2 and len(kinds) == 1 and kinds <= {"item", "ability", "move"}:
        judged, pick, verdict_said = _judge_set(plan, member, options, dex, game)
    if kinds == {"tera"}:
        if not verdict_said:
            return None
        return Verdict("compare", pick or "close", verdict_said, [f.text for f in judged], persona="builder",
                       plain=verdict_said, typed=judged)
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
    answer = options[0][1] if shares.get(options[0][1], 0) >= max(shares.values()) else options[-1][1]
    if verdict_said:
        # The engine's judgement leads; the ladder shares follow as context
        said, typed, answer = f"{verdict_said} {said}", judged + typed, pick or "close"
    facts = [f.text for f in typed]
    return Verdict("compare", answer, said, facts, persona="builder", plain=said, typed=typed)


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

"""
Brock, the building agent: sets, items, moves, Tera, spreads and teammates, answered from ladder usage.

The model gets a short list of labelled facts and nothing else: whose Pokemon each line is about, the member's own set,
what ladder players run with percentages, and Team Completer picks marked as not on the team. In the 2026 11 14
ablations this took Brock from 1 of 15 correct drafts to 14 of 15; the old prompt (usage tables for all six members,
rule text, a retrieved passage, "guide the trainer on what's effective in the meta") invited him to name Pokemon, moves
and items nobody had given him. Every Pokemon, move, item and ability he names, and every number, must appear in the
facts; one retry, then the facts are shown on their own.
"""
import re

from .client import chat, ollama_available
from .grounded import FACTS_MARK, FREE_NUMBERS, _numbers
from metamatch import auditor, config
from metamatch.engine import rules
from metamatch.engine.dex import dex_for_format
from metamatch.engine.names import find_pokemon
from metamatch.engine.sets import chaos_entry, spread_label

TEAMMATE_RE = re.compile(r"\b(?:teammates?|partners?|add|addition|slot|wallbreaker|breaker|sweeper|pivot|core|synergy|"
                         r"replace\w*|swap\w*|instead of|fill|missing|need|recommend\w* (?:a|an|another|some)\b|"
                         r"suggest\w* (?:a|an|another|some)\b|who (?:should|could|can) i)", re.I)
REPLACE_RE = re.compile(r"\b(?:replace\w*|swap\w*|instead of|drop|cut)\b", re.I)
SYSTEM = ("You are Brock, a calm, friendly Pokemon breeder who knows what ladder players really run.\n"
          "Answer in 2 to 4 sentences of plain prose, no lists.\n"
          "Use only the facts you are given. Percentages are the share of ladder sets that use that option.\n"
          "Suggest only options that appear in the facts. Never add a move, item, ability, type, number, stat or Pokemon "
          "the facts do not state. If the facts do not settle the question, say what they do show.")
OFFLINE = "_Brock is offline (Ollama isn't running), so here is the ladder data on its own._"
UNCHECKED = "_Brock's answer didn't pass the fact check this time, so here is the ladder data on its own._"


def _pct(x):
    return f"{100 * x:.0f}%"


def _ranked(table, total, name=lambda k: k, n=5, min_share=0.02):
    rows = sorted(((k, v / total) for k, v in (table or {}).items() if k and k != "nothing"), key=lambda kv: kv[1], reverse=True)
    return ", ".join(f"{name(k)} {_pct(v)}" for k, v in rows[:n] if v >= min_share)


def _types(name, dex):
    s = dex.species(name) if dex else None
    return "/".join(s["types"]) if s else ""


def _ladder_lines(name, format_id, dex, owner):
    """What ladder players run on `name`: items, abilities, moves, Tera and spreads with their shares."""
    key, entry = chaos_entry(name, format_id)
    if not entry:
        return [f"There is no ladder data for {name} in this format."]
    total = sum(entry.get("Abilities", {}).values()) or 1
    label = f"Ladder sets of {key} ({owner})"
    lines = [f"{label}, items: " + _ranked(entry.get("Items"), total, lambda k: dex.item_name(k) or k) + ".",
             f"{label}, moves (share of sets): " + _ranked(entry.get("Moves"), total, lambda k: dex.move_name(k) or k, n=8) + "."]
    abilities = _ranked(entry.get("Abilities"), total, lambda k: dex.ability_name(k) or k, n=3)
    if abilities.count("%") > 1:
        lines.append(f"{label}, abilities: {abilities}.")
    if config.format_game(format_id) != "champions" and entry.get("Tera Types"):
        lines.append(f"{label}, Tera types: " + _ranked(entry.get("Tera Types"), total, str.capitalize) + ".")
    spreads = _ranked(entry.get("Spreads"), total, lambda k: spread_label(k, format_id), n=3, min_share=0.03)
    if spreads:
        lines.append(f"{label}, most common spreads: {spreads}.")
    return lines


def _own_set(p, format_id):
    game = config.format_game(format_id)
    spread = p.get("SP") if game == "champions" else p.get("EVs")
    if isinstance(spread, dict):
        spread = " / ".join(f"{v} {k}" for k, v in spread.items() if v) or "no investment"
    tera = "" if game == "champions" else f", Tera {p.get('Tera Type')}"
    return (f"Your {p['Pokemon']} ({'/'.join(p.get('Type', []))}) runs {p.get('Item') or 'no item'}, {p.get('Ability')}{tera}, "
            f"{p.get('Nature', '?')} {spread}, moves {', '.join(m['name'] for m in p.get('Moves', []))}.")


def _member(name, team):
    """The team entry `name` refers to, the planner's way: 'samurott' finds a team's Samurott-Hisui."""
    from metamatch.engine.planner import _team_member
    return _team_member(name, team, dex_for_format(config.team_format(team)))


# "which of my mons is my best wallbreaker": a question about the team's own members, not a new teammate
OWN_ROLE_RE = re.compile(r"\b(?:which|who) (?:of|on|in) (?:my|our)\b|\bmy (?:best|main|only|current)\b|"
                         r"\b(?:which|what) (?:mon|pokemon|member|one) (?:is|on my)\b", re.I)


def _role_lines(team):
    out = []
    for p in team.values():
        roles = [r for r in p.get("Roles", []) if r]
        if roles:
            out.append(f"Your {p['Pokemon']}'s roles: {', '.join(roles)}.")
    return out or ["No roles were detected for your team's members."]


def _teammate_lines(team, format_id, dex, replacing=None):
    """Team Completer picks for the next slot (or for the slot `replacing` leaves), marked as not on the team."""
    from metamatch.engine.completer import complete
    rest = {k: v for k, v in team.items() if v is not replacing} if replacing else team
    picks, _, _ = complete(rest, format_id, top_n=3)
    names = {p["Pokemon"] for p in team.values()}
    lines = []
    for c in [c for c in picks if c.name not in names][:3]:
        why = []
        if c.covers:
            why.append(f"it beats {', '.join(c.covers[:3])} one on one, which your team struggles with")
        if c.roles:
            why.append(f"it adds a role your team lacks: {', '.join(r.lower() for r in c.roles)}")
        if c.best_pair and c.best_pair[1] and c.best_pair[1] > 1.2:
            why.append(f"ladder players often pair it with {c.best_pair[0]}")
        lines.append(f"Suggested new teammate (not on your team): {c.name} ({_types(c.name, dex)}), used on {c.usage:g}% of teams"
                     + (f"; {'; '.join(why)}" if why else "") + ".")
    if replacing:
        lines.insert(0, f"These picks are for the slot your {replacing['Pokemon']} would leave.")
    return lines or ["The Team Completer found no new teammate that beats a threat your team struggles with."]


def _warning_lines(team):
    """Set choices few ladder players make, from the usage audit."""
    out = []
    for w in auditor.audit_team(team).get("warnings", []):
        common = f"; the most common is {w['suggestion']}" if w.get("suggestion") else ""
        out.append(f"Your {w['pokemon']} runs {w['current']} ({w['category'].lower()}), which only {w['usage']:.1f}% of "
                   f"ladder {w['pokemon']} sets use{common}.")
    return out


def facts_for(query, team, plan=None):
    """The labelled facts Brock answers from, most specific first."""
    format_id = config.team_format(team)
    dex = dex_for_format(format_id)
    names = [p["Pokemon"] for p in team.values()]
    facts = [f"The trainer's own team (\"your\") is exactly these {len(names)}: {', '.join(names)}. "
             "Never suggest one of them as a new teammate."]
    opponents = set(plan.opponents) if plan else set()
    asked = [n for n in find_pokemon(query) if n not in opponents]
    members = list(dict.fromkeys(n for n in asked if _member(n, team)))
    others = [n for n in find_pokemon(query) if n not in members]
    for name in members:
        p = _member(name, team)
        facts.append(_own_set(p, format_id))
        facts += _ladder_lines(p.get("Forme") or p["Pokemon"], format_id, dex, "yours is above")
    for name in others[:2]:
        facts += _ladder_lines(name, format_id, dex, "not on your team")
    if TEAMMATE_RE.search(query) and OWN_ROLE_RE.search(query) and not REPLACE_RE.search(query):
        facts += _role_lines(team)
    elif TEAMMATE_RE.search(query):
        replacing = _member(members[0], team) if members and REPLACE_RE.search(query) else None
        facts += _teammate_lines(team, format_id, dex, replacing)
    elif not members and not others:
        facts += _warning_lines(team) or ["Every item, ability and move on your team is one ladder players commonly run."]
    return facts


def verify(text, facts):
    """Why Brock's answer can't be shown, or None. Every number, Pokemon, move, item and ability must be in the facts."""
    known = " ".join(facts)
    unknown = _numbers(text) - _numbers(known) - FREE_NUMBERS
    if unknown:
        return f"numbers not in the facts: {', '.join(sorted(unknown))}"
    low = known.lower()
    invented = [n for n in find_pokemon(text) if n.lower() not in low]
    if invented:
        return f"Pokemon that are not in the facts: {', '.join(invented)}"
    named = [name for kind, name in rules.find_named(text) if kind in ("move", "item", "ability") and name.lower() not in low]
    if named:
        return f"moves, items or abilities that are not in the facts: {', '.join(named)}"
    return share_clash(text, facts) or comparison_clash(text, facts)


# Numbers bound to options. The bag of numbers check above let "50% run Choice Specs, the same share as Heavy-Duty
# Boots" through (Boots is 24%): every number was somewhere in the facts, just not next to the option it was given to.
SHARE = re.compile(r"([A-Z][\w'\- ]*?[a-z0-9]) (\d+(?:\.\d+)?)%")
PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
MORE = re.compile(r"\b(?:more|higher|ahead of|over|greater|bigger|beats|above|outnumbers)\b", re.I)
LESS = re.compile(r"\b(?:less|fewer|lower|behind|below|smaller|trails|rarer)\b", re.I)
SAME = re.compile(r"\b(?:same|equal\w*|identical|matches|as (?:many|common|popular|often) as|just as)\b", re.I)


def _shares(facts):
    """{option lowercased: {shares}} from fact lines like 'items: Choice Specs 50%, Heavy-Duty Boots 24%'."""
    out = {}
    for line in facts:
        for name, pct in SHARE.findall(line.split(":", 1)[-1]):
            out.setdefault(name.strip().lower(), set()).add(float(pct))
    return out


def share_clash(text, facts):
    """A percentage given to the wrong option: in a sentence naming options from the facts, every percentage must be
    the share of one of them."""
    table = _shares(facts)
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        low = sentence.lower()
        named = {name: shares for name, shares in table.items() if name in low}
        if not named:
            continue
        for pct in PCT.findall(sentence):
            if not any(abs(float(pct) - v) < 0.6 for shares in named.values() for v in shares):
                return f"{pct}% given to {', '.join(named)}, which the facts give other shares"
    return None


def comparison_clash(text, facts):
    """Two options ranked against each other the wrong way round, or unequal shares called the same."""
    table = {name: next(iter(v)) for name, v in _shares(facts).items() if len(v) == 1}
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        low = sentence.lower()
        found = sorted((low.find(name), name) for name in table if low.find(name) >= 0)
        if len(found) < 2:
            continue
        (pa, a), (pb, b) = found[0], found[1]
        between = sentence[pa:pb + len(b)]
        if SAME.search(sentence) and abs(table[a] - table[b]) >= 2:
            return f"a claim that {a} and {b} are equally common ({table[a]:g}% and {table[b]:g}%)"
        if MORE.search(between) and table[a] < table[b]:
            return f"a claim that {a} is more common than {b} ({table[a]:g}% vs {table[b]:g}%)"
        if LESS.search(between) and table[a] > table[b]:
            return f"a claim that {a} is less common than {b} ({table[a]:g}% vs {table[b]:g}%)"
    return None


class AuditorAgent:
    def __init__(self, model_name=None):
        self.model = model_name

    def run(self, query: str, team_context: dict, plan=None, state=None, meta=None):
        """Yields the answer for a building question the engine has no single answer for: Brock's labelled ladder
        facts become a numbered packet, Brock picks the ones that answer it and adds an opener, and the facts are shown
        word for word. METAMATCH_VOICE=legacy keeps the old checked free text until the final measurement."""
        from .grounded import voice_mode
        if voice_mode() == "legacy":
            yield from self._legacy_run(query, team_context, plan)
            return
        from metamatch.engine.packet import Fact, Packet
        from .voice import pick
        lines = facts_for(query, team_context, plan)[1:]   # the first line only told the model whose team it is
        packet = Packet(query, "open", category="building", persona="builder")
        for line in lines[:12]:
            packet.add(Fact("usage", line, {}))
        block = "\n".join(f"* {f}" for f in lines)
        if not packet.facts:
            yield "I don't have ladder numbers that answer that, so I won't guess."
            return
        opener, ids, report = pick(packet, getattr(state, "recent_openers", ()), getattr(state, "recent_moods", ()))
        if meta is not None:
            meta.update(report, opener=opener)
        shown = "\n".join(f"* {packet.fact(i).text}" for i in ids if packet.fact(i))
        yield f"*{opener}*\n\n{shown}" + FACTS_MARK + block

    def _legacy_run(self, query: str, team_context: dict, plan=None):
        """The pre restructure path: Brock's checked free text (kept switchable until the final measurement)."""
        facts = facts_for(query, team_context, plan)
        block = "\n".join(f"* {f}" for f in facts)
        if not ollama_available():
            yield OFFLINE + "\n\n" + block
            return
        user = "Facts:\n" + "\n".join(f"- {f}" for f in facts) + f"\n\nQuestion: {query}"
        feedback = None
        for _ in range(2):
            system = SYSTEM + (f"\nYour previous answer was rejected because it had {feedback}. Fix that." if feedback else "")
            try:
                text = chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                            temperature=0.2, max_tokens=250, model=self.model)
            except Exception as e:
                print(f"Brock failed: {e}")
                break
            feedback = verify(text, facts)
            if feedback is None:
                yield text + FACTS_MARK + block
                return
        yield UNCHECKED + "\n\n" + block

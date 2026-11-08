"""Matchup Matrices tab: how hard each attacking type hits each member, and the best hit each member has on each type."""
from html import escape

import streamlit as st

from metamatch.sprites import get_sprite
from metamatch.type_chart import get_multiplier
from metamatch.ui import section_header

ALL_TYPES = ["Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison",
             "Ground", "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy"]
N = len(ALL_TYPES)

# Hovering a cell lights up its whole column (one :has rule per column) and its row
_COLUMN_HL = "\n".join(f'.mt:has([data-c="{i}"]:hover) [data-c="{i}"] {{ box-shadow: inset 0 0 0 1px rgba(0,212,255,.55); }}'
                       for i in range(N))
STYLE = """
<style>
.mt-cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 4px 0 12px; }
.mt-card { background: rgba(255,255,255,.03); padding: 15px; border-radius: 12px; border: 1px solid rgba(255,255,255,.05);
  box-shadow: 0 4px 15px rgba(0,0,0,.2); min-width: 0; }
.mt-card .k { color: #888; text-transform: uppercase; letter-spacing: 1px; font-size: .75rem; }
.mt-card .v { font-weight: 800; color: #fff; font-size: clamp(1.4rem, 2.2vw, 2.1rem); line-height: 1.2; margin-top: 2px; }
.mt-card .v.bad { color: #f87171; }
.mt-card .s { color: #8fa1bf; font-size: .82rem; margin-top: 2px; }
.mt-legend { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: .8rem; color: #9fb0cc; margin-bottom: 8px; }
.mt-legend .sw { display: inline-flex; align-items: center; gap: 7px; padding: 3px 10px 3px 4px; border-radius: 999px;
  background: rgba(255,255,255,.025); border: 1px solid rgba(255,255,255,.07); }
.mt-legend .sw b { font-size: .85rem; min-width: 28px; text-align: center; padding: 1px 6px; border-radius: 999px; }
.mt { border-collapse: separate !important; border-spacing: 3px; width: 100%; table-layout: fixed; border: none !important;
  font-variant-numeric: tabular-nums; margin-bottom: 18px; }
.mt th, .mt td { border: none !important; }
.mt col.who { width: 168px; }
.mt thead th { padding: 6px 0 4px; vertical-align: bottom; text-align: center; }
.mt .tp { display: inline-flex; flex-direction: column; align-items: center; gap: 4px; font-size: .7rem; font-weight: 600; color: #9fb0cc; }
.mt .tp i { display: block; width: 24px; height: 5px; border-radius: 3px; }
.mt .tp.flag { color: #f87171; font-weight: 700; }
.mt .tp.flag i { box-shadow: 0 0 0 2px #0f1219, 0 0 0 3px #f87171; }
.mt th.who { text-align: left; padding: 2px 8px 2px 2px; white-space: nowrap; overflow: hidden; }
.mt .who-in { display: flex; align-items: center; gap: 8px; }
.mt .who img { width: 34px; height: 34px; object-fit: contain; flex-shrink: 0; }
.mt .who .nm { display: block; font-weight: 600; font-size: .9rem; overflow: hidden; text-overflow: ellipsis; }
.mt .who .ty { display: block; font-size: .7rem; color: #8fa1bf; font-weight: 400; }
.mt tbody tr:hover .who .nm { color: #00d4ff; }
.mt td.c { position: relative; height: 42px; text-align: center; border-radius: 7px; font-weight: 700; font-size: 1rem;
  background: rgba(255,255,255,.025); transition: box-shadow .12s; }
.mt td.c:hover { box-shadow: 0 0 0 1px currentColor !important; z-index: 5; }
.mt td.x4 { background: rgba(248,113,113,.32); color: #fecaca; }
.mt td.x2, .mt td.res { background: rgba(248,113,113,.15); color: #f87171; }
.mt td.h, .mt td.se { background: rgba(52,211,153,.13); color: #34d399; }
.mt td.q { background: rgba(52,211,153,.27); color: #a7f3d0; }
.mt td.z { background: rgba(34,211,238,.14); color: #22d3ee; }
.mt td.none { background: rgba(248,113,113,.32); color: #fecaca; }
.mt tfoot th.who { color: #9fb0cc; font-size: .8rem; font-weight: 600; }
.mt tfoot td.c { height: auto; padding: 6px 1px; background: transparent; font-size: .7rem; font-weight: 600; line-height: 1.35; color: #9fb0cc; }
.mt tfoot td.c span { display: block; }
.mt tfoot .w { color: #f87171; } .mt tfoot .r { color: #34d399; }
.mt tfoot td.flag { background: rgba(248,113,113,.07); box-shadow: inset 0 0 0 1px rgba(248,113,113,.35); }
.mt tfoot td.flag .w { font-weight: 800; }
.mt .tip { visibility: hidden; opacity: 0; position: absolute; left: 50%; transform: translateX(-50%); top: calc(100% + 8px);
  width: 250px; z-index: 20; text-align: left; padding: 10px 12px; border-radius: 10px; background: #0f1729;
  border: 1px solid rgba(255,255,255,.12); box-shadow: 0 14px 30px rgba(0,0,0,.45); color: #dbe4f3;
  font-size: .82rem; font-weight: 400; line-height: 1.45; transition: opacity .12s; pointer-events: none; }
.mt .tip b { color: #fff; }
.mt td.c:hover .tip { visibility: visible; opacity: 1; }
.mt tr.up .tip, .mt tfoot .tip { top: auto; bottom: calc(100% + 8px); }
.mt td.c.l .tip { left: 0; transform: none; }
.mt td.c.r .tip { left: auto; right: 0; transform: none; }
@media (max-width: 1100px) { .mt col.who { width: 120px; } .mt .who img { display: none; } .mt td.c { font-size: .85rem; }
  .mt .tp { font-size: .6rem; } .mt-cards { grid-template-columns: 1fr; } }
""" + _COLUMN_HL + """
</style>
"""

def _and(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _def_cell(v):
    """(css class, symbol) for damage taken at multiplier v."""
    if v == 0:
        return "z", "0"
    if v >= 4:
        return "x4", "4×"
    if v >= 2:
        return "x2", "2×"
    if v <= 0.25:
        return "q", "¼"
    if v <= 0.5:
        return "h", "½"
    return "", ""


def defense(team):
    """[(member, {type: multiplier taken})] from each member's Damage From table."""
    return [(p, {t: p["Damage From"].get(t.lower(), 1.0) for t in ALL_TYPES}) for p in team.values()]


def offense(team):
    """[(member, {type: (best multiplier, [moves that reach it])})]; None when the member has no attacking move."""
    out = []
    for p in team.values():
        attacks = [m for m in p.get("Moves", []) if m.get("category") != "Status" and m.get("type")]
        row = {}
        for t in ALL_TYPES:
            if not attacks:
                row[t] = (None, [])
                continue
            hits = [(get_multiplier(m["type"], t), m["name"]) for m in attacks]
            best = max(x for x, _ in hits)
            row[t] = (best, [n for x, n in hits if x == best])
        out.append((p, row))
    return out


def defense_summary(rows):
    """{type: (weak, resist, immune, flagged)}: flagged when two or more are weak and they outnumber those who take it well."""
    out = {}
    for t in ALL_TYPES:
        weak = [p["Pokemon"] for p, d in rows if d[t] >= 2]
        res = [p["Pokemon"] for p, d in rows if 0 < d[t] < 1]
        imm = [p["Pokemon"] for p, d in rows if d[t] == 0]
        out[t] = (weak, res, imm, len(weak) >= 2 and len(weak) > len(res) + len(imm))
    return out


def offense_summary(rows):
    """{type: [members with a super effective hit on it]}."""
    return {t: [p["Pokemon"] for p, o in rows if (o[t][0] or 0) >= 2] for t in ALL_TYPES}


def _edge(i):
    return " l" if i < 3 else " r" if i >= N - 3 else ""


def _head(flags, type_map):
    cells = "".join(
        f'<th><span class="tp{" flag" if flags[t] else ""}"><i style="background:{type_map.get(t, {}).get("color", "#888")}"></i>'
        f'{t}</span></th>' for t in ALL_TYPES)
    return f'<colgroup><col class="who">{"<col>" * N}</colgroup><thead><tr><th class="who"></th>{cells}</tr></thead>'


def _who(p):
    sprite = escape(get_sprite(p["Pokemon"]) or "")
    types = escape(" / ".join(p.get("Type") or []))
    return (f'<th class="who"><div class="who-in"><img src="{sprite}" alt=""><span><span class="nm">{escape(p["Pokemon"])}</span>'
            f'<span class="ty">{types}</span></span></div></th>')


def _cell(i, cls, text, tip):
    return f'<td class="c {cls}{_edge(i)}" data-c="{i}">{text}<span class="tip">{tip}</span></td>'


def _def_tip(t, name, v):
    n = f"<b>{escape(name)}</b>"
    if v == 0:
        return f"{t} attacks can't touch {n}. Immune."
    if v >= 4:
        return f"{t} hits {n} for <b>4×</b> damage. Its biggest weakness."
    if v >= 2:
        return f"{t} hits {n} for <b>2×</b> damage. Weak."
    if v <= 0.25:
        return f"{t} does only <b>¼</b> damage to {n}."
    if v <= 0.5:
        return f"{t} does <b>½</b> damage to {n}. Resists."
    return f"{t} hits {n} for normal damage."


def _off_tip(t, name, v, moves):
    n, mv = f"<b>{escape(name)}</b>", escape(_and(moves)) if moves else ""
    if v is None:
        return f"{n} runs no attacking moves."
    if v >= 2:
        return f"{n} hits {t} types for <b>2×</b> with {mv}."
    if v == 0:
        return f"Nothing {n} runs can hit {t} types."
    if v <= 0.5:
        return f"{t} types resist everything {n} runs. Its best is {mv} at <b>½</b>."
    return f"{n} hits {t} types for normal damage at best ({mv})."


def _cards(cards):
    return '<div class="mt-cards">' + "".join(
        f'<div class="mt-card"><div class="k">{escape(k)}</div><div class="v{" bad" if bad else ""}">{escape(str(v))}</div>'
        f'<div class="s">{escape(s)}</div></div>' for k, v, s, bad in cards) + "</div>"


def _legend(items, note):
    colors = {"x4": ("rgba(248,113,113,.32)", "#fecaca"), "x2": ("rgba(248,113,113,.15)", "#f87171"),
              "h": ("rgba(52,211,153,.13)", "#34d399"), "q": ("rgba(52,211,153,.27)", "#a7f3d0"),
              "z": ("rgba(34,211,238,.14)", "#22d3ee")}
    chips = "".join(f'<span class="sw"><b style="background:{colors[c][0]};color:{colors[c][1]}">{sym}</b>{label}</span>'
                    for sym, c, label in items)
    return f'<div class="mt-legend">{chips}<span>{note}</span></div>'


def _up(r, n_rows):
    return ' class="up"' if r >= max(2, n_rows - 3) else ""


def render_defense(team, type_map):
    rows = defense(team)
    summary = defense_summary(rows)
    spots = [t for t in ALL_TYPES if summary[t][3]]
    immunities = sum(1 for _, d in rows for t in ALL_TYPES if d[t] == 0)
    imm_types = [t for t in ALL_TYPES if summary[t][2]]
    walled = [t for t in ALL_TYPES if len(summary[t][1]) + len(summary[t][2]) == len(rows)]
    section_header("Matchup Matrices", "Defense")
    st.caption("How hard each attacking type hits each member. Read down a column to see how the whole team takes that type.")
    cards = _cards([
        ("Weak spots", len(spots), _and(spots) if spots else "No type hits more of you than you can take", bool(spots)),
        ("Immunities", immunities, f"Across {len(imm_types)} types: {_and(imm_types)}" if imm_types else "No immunities", False),
        ("Fully walled", _and(walled) if walled else "None",
         "Every member resists it or is immune" if walled else "No type is resisted by all six", False),
    ])
    legend = _legend([("4×", "x4", "very weak"), ("2×", "x2", "weak"), ("½", "h", "resists"), ("¼", "q", "strongly resists"),
                      ("0", "z", "immune")], "Blank cells take normal damage.")
    body = "".join(
        f"<tr{_up(r, len(rows))}>" + _who(p) + "".join(
            _cell(i, *_def_cell(d[t]), _def_tip(t, p["Pokemon"], d[t])) for i, t in enumerate(ALL_TYPES)) + "</tr>"
        for r, (p, d) in enumerate(rows))
    foot = ""
    for i, t in enumerate(ALL_TYPES):
        weak, res, imm, flag = summary[t]
        lines = ([f'<span class="w">{len(weak)} weak</span>'] if weak else []) + \
                ([f'<span class="r">{len(res)} {"resists" if len(res) == 1 else "resist"}</span>'] if res else []) + \
                ([f'<span class="r">{len(imm)} immune</span>'] if imm else [])
        said = [f"weak: {_and(weak)}" if weak else "", f"resist: {_and(res)}" if res else "", f"immune: {_and(imm)}" if imm else ""]
        tip = f"<b>{t}</b>: " + (escape(". ".join(s for s in said if s)) + "." if weak or res or imm
                                 else "everyone takes normal damage.")
        if flag:
            tip += " More of your team is weak to it than can take it."
        foot += _cell(i, "flag" if flag else "", "".join(lines) or "<span>all neutral</span>", tip)
    table = (f'<table class="mt">{_head({t: summary[t][3] for t in ALL_TYPES}, type_map)}<tbody>{body}</tbody>'
             f'<tfoot><tr><th class="who">Your team</th>{foot}</tr></tfoot></table>')
    st.markdown(STYLE + cards + legend + table, unsafe_allow_html=True)


def render_offense(team, type_map):
    rows = offense(team)
    summary = offense_summary(rows)
    gaps = [t for t in ALL_TYPES if not summary[t]]
    widest = max(rows, key=lambda r: sum((r[1][t][0] or 0) >= 2 for t in ALL_TYPES), default=None)
    section_header("Matchup Matrices", "Offense")
    st.caption("The best hit each member has on each type, from the attacking moves it runs.")
    cards = _cards([
        ("Types you hit for 2×", f"{N - len(gaps)} of {N}", "Something on the team hits each of these super effectively", False),
        ("No 2× hit", _and(gaps) if gaps else "None",
         "Nothing on the team hits these super effectively" if gaps else "Every type is covered", bool(gaps)),
        ("Widest coverage", widest[0]["Pokemon"] if widest else "None",
         f"Hits {sum((widest[1][t][0] or 0) >= 2 for t in ALL_TYPES)} types for 2×" if widest else "", False),
    ])
    legend = _legend([("2×", "h", "super effective"), ("½", "x2", "resisted"), ("0", "x4", "no effect")],
                     "Blank cells hit for normal damage.")

    def cell(v):
        if v is None:
            return "", ""
        return ("se", "2×") if v >= 2 else ("none", "0") if v == 0 else ("res", "½") if v <= 0.5 else ("", "")

    body = "".join(
        f"<tr{_up(r, len(rows))}>" + _who(p) + "".join(
            _cell(i, *cell(o[t][0]), _off_tip(t, p["Pokemon"], *o[t])) for i, t in enumerate(ALL_TYPES)) + "</tr>"
        for r, (p, o) in enumerate(rows))
    foot = "".join(
        _cell(i, "" if summary[t] else "flag",
              f'<span class="r">{len(summary[t])} of {len(rows)}</span>' if summary[t] else f'<span class="w">0 of {len(rows)}</span>',
              f"<b>{t}</b>: hit for 2× by {escape(_and(summary[t]))}." if summary[t]
              else f"<b>{t}</b>: nothing on the team hits it super effectively.")
        for i, t in enumerate(ALL_TYPES))
    table = (f'<table class="mt">{_head({t: not summary[t] for t in ALL_TYPES}, type_map)}<tbody>{body}</tbody>'
             f'<tfoot><tr><th class="who">Your team<span class="ty">members with a 2× hit</span></th>{foot}</tr></tfoot></table>')
    st.markdown(STYLE + cards + legend + table, unsafe_allow_html=True)


def render(team_data: dict, type_map: dict | None = None):
    type_map = type_map or {}
    render_defense(team_data, type_map)
    st.markdown("---")
    render_offense(team_data, type_map)

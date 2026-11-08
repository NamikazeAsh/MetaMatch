"""Team Overview tab: which types the team hits hard, and which types hit several members, with who can take them."""
from html import escape

import streamlit as st

from metamatch.sprites import get_sprite, get_type_icon
from metamatch.type_chart import get_multiplier
from metamatch.ui import section_header

TYPES = ["Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison", "Ground",
         "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy"]

STYLE = """
<style>
.ov-cloud { display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 4px; }
.ov-cloud:has(.ov-pill:hover), .ov-cloud:has(.ov-pill:focus-visible) { margin-bottom:250px; }
.ov-pill { position:relative; display:inline-flex; align-items:center; gap:7px; padding:4px 12px 4px 4px; border-radius:999px; outline:none; cursor:default;
  font-size:0.8rem; font-weight:700; color:#e6eaf2; background:color-mix(in srgb, var(--c) 14%, rgba(255,255,255,0.02));
  border:1px solid color-mix(in srgb, var(--c) 40%, transparent); transition:transform .12s ease, box-shadow .12s ease; }
.ov-pill:hover, .ov-pill:focus-visible { box-shadow:0 0 0 1px var(--c), 0 6px 16px rgba(0,0,0,0.35); }
.ov-pill.miss { background:transparent; border:1px dashed rgba(255,123,123,0.6); color:#ffb0b0; }
.ov-pill.miss .ov-ico { filter:grayscale(1) brightness(0.65); }
.ov-pill .ov-ico { width:24px; height:24px; } .ov-pill .ov-ico i { width:13px; height:13px; }
.ov-ico { width:38px; height:38px; border-radius:50%; display:grid; place-items:center; flex-shrink:0;
  background:radial-gradient(circle at 35% 30%, color-mix(in srgb, var(--c) 75%, #fff), var(--c) 60%);
  box-shadow:0 0 14px -3px var(--c), inset 0 -3px 5px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.3); }
.ov-ico i { display:block; width:20px; height:20px; background-size:contain; background-repeat:no-repeat; background-position:center;
  filter:drop-shadow(0 1px 1px rgba(0,0,0,0.35)); }
/* The pills stay static so each detail panel anchors to the cloud: it always opens under the row, never off screen */
.ov-cloud { position:relative; }
.ov-pill { position:static; }
.ov-tip { position:absolute; left:0; top:calc(100% + 10px); width:min(560px, 100%); z-index:30; text-align:left; white-space:normal;
  padding:14px 16px; border-radius:16px; background:linear-gradient(160deg, color-mix(in srgb, var(--c) 14%, #141a26), #121722 65%);
  border:1px solid color-mix(in srgb, var(--c) 50%, transparent); box-shadow:0 16px 36px rgba(0,0,0,0.6);
  font-size:0.8rem; font-weight:500; color:#d6dbe6; line-height:1.45;
  opacity:0; visibility:hidden; transform:translateY(4px); transition:opacity .12s ease, transform .12s ease, visibility .12s; pointer-events:none; }
.ov-pill:hover .ov-tip, .ov-pill:focus-visible .ov-tip { opacity:1; visibility:visible; transform:translateY(0); }
.ov-tip b { color:#fff; }
.ov-tip-head { display:flex; align-items:center; gap:10px; margin-bottom:10px; }
.ov-tip-head .ov-ico { width:34px; height:34px; } .ov-tip-head .ov-ico i { width:18px; height:18px; }
.ov-tip-head b { font-size:1.05rem; } .ov-tip-head span { color:#aab3c5; font-size:0.8rem; }
.ov-tip-k { font-size:0.6rem; font-weight:800; letter-spacing:0.1em; text-transform:uppercase; color:#8a93a6; margin:8px 0 5px; }
.ov-hits { display:flex; flex-direction:column; gap:5px; }
.ov-hitrow { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.ov-hitrow img { width:26px; height:26px; object-fit:contain; }
.ov-mvchip { font-size:0.72rem; color:#e6eaf2; padding:2px 8px; border-radius:7px; background:rgba(255,255,255,0.05);
  border:1px solid rgba(255,255,255,0.07); border-left:3px solid var(--mc); }
.ov-faces { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:5px 12px; }
.ov-face { display:flex; align-items:center; gap:7px; min-width:0; }
.ov-face img { width:26px; height:26px; object-fit:contain; flex-shrink:0; }
.ov-face .nm { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; color:#e6eaf2; font-weight:700; }
.ov-face small { color:#8a93a6; white-space:nowrap; }
.ov-face .ok { color:#5fd38d; font-size:0.72rem; white-space:nowrap; } .ov-face .bad { color:#ff9b9b; font-size:0.72rem; white-space:nowrap; }
.ov-tip-none { color:#ffb0b0; }
.ov-sum { display:flex; align-items:baseline; gap:10px; margin:2px 2px 6px; }
.ov-sum b { font-size:1.6rem; font-weight:900; color:#fff; } .ov-sum b small { font-size:0.9rem; color:#8a93a6; }
.ov-sum span { font-size:0.88rem; color:#aab3c5; }
.ov-weak { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:14px; margin:4px 0 6px; }
.ov-card { display:grid; grid-template-columns:64px minmax(0, 1fr); gap:14px; align-items:center; padding:14px 16px; border-radius:16px; min-width:0;
  background:radial-gradient(circle at 8% 50%, color-mix(in srgb, var(--c) 22%, transparent), transparent 40%), linear-gradient(145deg, #1c2232, #141924);
  border:1px solid rgba(255,255,255,0.06);
  box-shadow:10px 10px 24px rgba(0,0,0,0.45), -6px -6px 16px rgba(255,255,255,0.025), inset 1px 1px 0 rgba(255,255,255,0.05); }
.ov-card.spot { border-color:rgba(255,123,123,0.4); }
.ov-card .ov-ico { width:56px; height:56px; } .ov-card .ov-ico i { width:30px; height:30px; }
.ov-card-t { display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; }
.ov-card-t b { font-size:1.05rem; color:#fff; font-weight:800; }
.ov-card-t span { font-size:0.8rem; color:#aab3c5; }
.ov-flag { font-size:0.62rem; font-weight:800; letter-spacing:0.08em; text-transform:uppercase; padding:2px 8px; border-radius:999px;
  color:#ffb0b0; background:rgba(255,123,123,0.12); border:1px solid rgba(255,123,123,0.3); }
.ov-rows { display:flex; flex-direction:column; gap:6px; margin-top:8px; }
.ov-row { display:flex; align-items:center; gap:8px; min-width:0; }
.ov-row-k { font-size:0.62rem; font-weight:800; letter-spacing:0.08em; text-transform:uppercase; width:74px; flex-shrink:0; }
.ov-row-k.bad { color:#ff9b9b; } .ov-row-k.ok { color:#5fd38d; }
.ov-mons { display:flex; flex-wrap:wrap; gap:4px; }
.ov-mon { position:relative; width:38px; height:38px; border-radius:50%; display:grid; place-items:center; outline:none; cursor:help;
  background:rgba(0,0,0,0.28); border:1px solid rgba(255,255,255,0.08); }
.ov-mon img { width:34px; height:34px; object-fit:contain; }
.ov-mon.x4 { border-color:#ff7b7b; box-shadow:0 0 10px -2px #ff7b7b; }
.ov-mon.imm { border-color:#22d3ee; }
.ov-mon .ov-mt { position:absolute; bottom:calc(100% + 6px); left:50%; transform:translateX(-50%); white-space:nowrap; font-size:0.68rem; font-weight:700;
  color:#fff; background:#0b0f17; border:1px solid rgba(255,255,255,0.14); padding:3px 8px; border-radius:7px; opacity:0; visibility:hidden;
  transition:opacity .12s ease, visibility .12s; pointer-events:none; z-index:40; }
.ov-mon:hover .ov-mt, .ov-mon:focus .ov-mt { opacity:1; visibility:visible; }
.ov-none { font-size:0.78rem; color:#8a93a6; }
.ov-quiet { font-size:0.88rem; color:#8a93a6; padding:6px 2px; }
@media (max-width: 1100px) { .ov-weak { grid-template-columns:minmax(0, 1fr); } }
@media (prefers-reduced-motion: reduce) { .ov-pill { transition:none; } }
</style>
"""


def _icon(t, type_map):
    glyph = get_type_icon(t)
    inner = f'<i style="background-image:url({glyph})"></i>' if glyph else ""
    return f'<span class="ov-ico" style="--c:{type_map.get(t, {}).get("color", "#777")}">{inner}</span>'


def _hits(team):
    """{type: [(member, move, move type)]} for every damaging move that hits the type for 2x or more."""
    out = {t: [] for t in TYPES}
    for p in team.values():
        for m in p.get("Moves", []):
            if m.get("category") == "Status" or not m.get("type"):
                continue
            for t in TYPES:
                if get_multiplier(m["type"], t) >= 2:
                    out[t].append((p["Pokemon"], m["name"], m["type"]))
    return out


def _faced(team):
    """{type: [(name, rank, usage %, answers or None)]}: the format's 30 most used Pokemon of each type, with the
    team members that beat each one when it is on the Threat Board (None when it isn't)."""
    import json
    from metamatch import config, meta_pulse
    from metamatch.engine.dex import dex_for_format
    from metamatch.tabs.tab_threats import _board, _stats_month
    format_id = config.team_format(team)
    dex = dex_for_format(format_id)
    table = meta_pulse._table(meta_pulse.load_history(), format_id, meta_pulse.current_month())
    try:
        board = {r["name"]: r["answers"] for r in _board(json.dumps(team, sort_keys=True, default=str), format_id, _stats_month())}
    except Exception:
        board = {}
    out = {t: [] for t in TYPES}
    for name, (rank, usage) in sorted(table.items(), key=lambda x: x[1][0])[:30]:
        for t in ((dex.species(name) or {}).get("types", []) if dex else []):
            if t in out:
                out[t].append((name, rank, usage, board.get(name)))
    return out, config.format_info(format_id)["label"]


def _tip(t, by, faced, label, type_map):
    """The detail panel for one type: your 2x hits, then that type's most used Pokemon and whether you beat them."""
    members = list(dict.fromkeys(n for n, _, _ in by))
    head = (f'<div class="ov-tip-head">{_icon(t, type_map)}<b>{escape(t)}</b>'
            f'<span>{"hit for 2x by " + str(len(members)) + (" member" if len(members) == 1 else " members") if members else "no 2x hit on your team"}</span></div>')
    if members:
        rows = "".join(
            f'<div class="ov-hitrow"><img src="{escape(get_sprite(n) or "")}" alt=""><b>{escape(n)}</b>'
            + "".join(f'<span class="ov-mvchip" style="--mc:{type_map.get(mt, {}).get("color", "#5a6375")}">{escape(mv)}</span>'
                      for who, mv, mt in by if who == n) + "</div>" for n in members)
        hits = f'<div class="ov-tip-k">Your 2x hits</div><div class="ov-hits">{rows}</div>'
    else:
        hits = f'<div class="ov-tip-none">Nothing on the team hits {escape(t)} types super effectively.</div>'
    if faced:
        def verdict(answers):
            if answers is None:
                return ""
            return (f'<span class="ok">beaten by {escape(answers[0])}</span>' if answers
                    else '<span class="bad">no answer</span>')
        rows = "".join(
            f'<div class="ov-face"><img src="{escape(get_sprite(n) or "")}" alt=""><span style="min-width:0">'
            f'<span class="nm">{escape(n)}</span> <small>#{rank} · {usage:.0f}%</small><br>{verdict(ans)}</span></div>'
            for n, rank, usage, ans in faced[:6])
        meta = f'<div class="ov-tip-k">{escape(t)} types you will face ({escape(label)} top 30)</div><div class="ov-faces">{rows}</div>'
    else:
        meta = f'<div class="ov-tip-k">{escape(t)} types you will face</div><div>None in the {escape(label)} top 30 this month.</div>'
    return f'<span class="ov-tip">{head}{hits}{meta}</span>'


def _coverage(team, type_map):
    """A cloud of type pills: covered types tinted, missing ones dashed, each opening a detail panel on hover."""
    hits = _hits(team)
    faced, label = _faced(team)
    pills = []
    for t in TYPES:
        color = type_map.get(t, {}).get("color", "#777")
        miss = "" if hits[t] else " miss"
        pills.append(f'<span class="ov-pill{miss}" tabindex="0" style="--c:{color}">{_icon(t, type_map)}{escape(t)}'
                     f'{_tip(t, hits[t], faced[t], label, type_map)}</span>')
    covered = sum(1 for t in TYPES if hits[t])
    missing = [t for t in TYPES if not hits[t]]
    note = f"Missing: {', '.join(missing)}" if missing else "Every type covered"
    summary = f'<div class="ov-sum"><b>{covered}<small>/18</small></b><span>types hit super effectively · {escape(note)}</span></div>'
    return summary + f'<div class="ov-cloud">{"".join(pills)}</div>', covered


def _mons(entries):
    if not entries:
        return '<span class="ov-none">nobody</span>'
    return '<div class="ov-mons">' + "".join(
        f'<span class="ov-mon {cls}" tabindex="0"><img src="{escape(get_sprite(n) or "")}" alt="">'
        f'<span class="ov-mt">{escape(n)} · {escape(label)}</span></span>' for n, cls, label in entries) + "</div>"


def _weaknesses(team, type_map):
    cards = []
    for t in TYPES:
        taken = [(p["Pokemon"], (p.get("Damage From") or {}).get(t.lower(), 1.0)) for p in team.values()]
        weak = [(n, "x4" if x >= 4 else "", "takes 4x" if x >= 4 else "takes 2x") for n, x in taken if x >= 2]
        if len(weak) < 2:
            continue
        safe = [(n, "imm" if x == 0 else "", "immune" if x == 0 else ("takes 1/4" if x <= 0.25 else "resists"))
                for n, x in taken if x < 1]
        spot = len(weak) > len(safe)
        flag = '<span class="ov-flag">Weak spot</span>' if spot else ""
        cards.append((len(weak) - len(safe), f'<div class="ov-card{" spot" if spot else ""}" style="--c:{type_map.get(t, {}).get("color", "#777")}">'
                     f'{_icon(t, type_map)}<div style="min-width:0"><div class="ov-card-t"><b>{escape(t)}</b>'
                     f'<span>{len(weak)} weak, {len(safe)} can switch in</span>{flag}</div>'
                     f'<div class="ov-rows"><div class="ov-row"><span class="ov-row-k bad">Weak</span>{_mons(weak)}</div>'
                     f'<div class="ov-row"><span class="ov-row-k ok">Switch in</span>{_mons(safe)}</div></div></div></div>'))
    cards.sort(key=lambda c: c[0], reverse=True)
    return "".join(html for _, html in cards)


def render(coverage: dict, weakness: dict, team_data: dict, type_map: dict):
    grid, covered = _coverage(team_data, type_map)
    section_header("Offense", "Coverage", "Hover a type for your 2x hits on it and the most used Pokémon of that type.")
    st.html(STYLE + grid)
    st.markdown("---")
    section_header("Defense", "Shared weaknesses",
                   "Every type that hits two or more of your Pokémon hard, and who can switch in on it. "
                   "Hover a sprite for its name; a red ring means it takes 4x.")
    cards = _weaknesses(team_data, type_map)
    st.html(STYLE + (f'<div class="ov-weak">{cards}</div>' if cards
                     else '<div class="ov-quiet">No type hits more than one of your Pokémon hard.</div>'))

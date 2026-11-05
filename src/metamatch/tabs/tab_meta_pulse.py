"""
MetaFlash section for the start screen (meta_pulse.py picks the cards), laid out like a magazine page: a featured story with a
6 month chart, a top 10 leaderboard beside it, and a grid of story cards underneath (a swipe strip
on phones). Pure HTML and CSS through st.html, so it renders in the page without an iframe.
st.html sanitizes inline <svg>, so charts ride in as data URI background images like the sprites.
"""
import base64
from html import escape

import streamlit as st

from metamatch import config, meta_pulse

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

CSS = """
<style>
.mp-head { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; margin:28px 2px 16px 2px;
  padding-bottom:14px; position:relative; }
.mp-head::after { content:""; position:absolute; left:0; right:0; bottom:0; height:1px;
  background:linear-gradient(90deg, rgba(0,212,255,0.7), rgba(0,255,204,0.25) 40%, transparent); }
.mp-kicker { font-size:0.7rem; font-weight:800; letter-spacing:2.4px; text-transform:uppercase; color:#00d4ff; }
.mp-title { font-weight:900; font-size:2.4rem; line-height:1.05; letter-spacing:-0.5px; white-space:nowrap; margin-top:2px;
  background:linear-gradient(90deg, #ffffff 0%, #9cf1ff 55%, #00ffcc 100%); -webkit-background-clip:text; background-clip:text;
  color:transparent; filter:drop-shadow(0 0 18px rgba(0,212,255,0.25)); }
.mp-tag { font-size:1rem; color:#aab3c5; margin-top:4px; }
.mp-sub { font-size:0.78rem; color:#8a93a6; text-align:right; line-height:1.5; }
.mp-sub b { color:#d6dbe6; font-weight:700; }
.mp-live { display:inline-block; width:7px; height:7px; border-radius:50%; background:#5fd38d; margin-right:6px;
  box-shadow:0 0 8px #5fd38d; vertical-align:middle; }

.mp-mag { display:grid; grid-template-columns:minmax(0, 1.65fr) minmax(0, 1fr); gap:14px; margin-bottom:14px; }
.mp-panel { position:relative; border-radius:16px; padding:16px 18px; overflow:hidden;
  background:linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.015));
  border:1px solid rgba(255,255,255,0.07); }

/* Featured story */
.mp-feature { border-color:var(--tc55); box-shadow:0 0 30px -14px var(--tc), inset 0 0 40px -30px var(--tc); }
.mp-feature::before { content:""; position:absolute; inset:0; pointer-events:none;
  background:radial-gradient(circle at 12% 30%, var(--tc33) 0%, transparent 45%); }
.mp-f-top { position:relative; display:flex; gap:18px; align-items:center; }
.mp-f-sprite { width:128px; height:128px; flex-shrink:0; background-size:contain, contain; background-repeat:no-repeat;
  background-position:center; filter:drop-shadow(0 0 16px var(--tc88)); }
.mp-f-kicker { font-size:0.72rem; font-weight:700; letter-spacing:1.2px; text-transform:uppercase; color:#8a93a6; }
.mp-f-name { font-weight:900; font-size:2rem; line-height:1.1; color:#fff; margin-top:4px; }
.mp-f-headline { font-size:1.02rem; color:#d6dbe6; margin-top:4px; }
.mp-pills { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
.mp-pill { padding:5px 10px; border-radius:10px; background:rgba(0,0,0,0.25); border:1px solid rgba(255,255,255,0.07);
  font-size:0.78rem; color:#aab3c5; }
.mp-pill b { color:#fff; font-size:0.95rem; margin-right:4px; }
.mp-f-body { position:relative; display:grid; grid-template-columns:minmax(0, 1fr) 320px; gap:18px; margin-top:16px; align-items:end; }
.mp-f-set { font-size:0.85rem; color:#d6dbe6; min-width:0; }
.mp-f-set .mp-set { white-space:normal; font-size:0.85rem; }
.mp-f-set .mp-moves { flex-wrap:wrap; margin-top:8px; }
.mp-f-set .mp-move { font-size:0.75rem; padding:3px 8px; }
.mp-f-mates { display:flex; flex-wrap:wrap; gap:6px 12px; margin-top:12px; font-size:0.75rem; color:#8a93a6; align-items:center; }
.mp-f-mate { display:flex; align-items:center; gap:5px; color:#cfd6e4; }
.mp-chart { width:320px; height:118px; background-repeat:no-repeat; background-size:contain; }

/* Leaderboard */
.mp-board-title { font-weight:800; font-size:0.95rem; color:#fff; margin-bottom:8px; display:flex; justify-content:space-between; }
.mp-board-title span { font-weight:500; font-size:0.72rem; color:#8a93a6; }
.mp-row { display:grid; grid-template-columns:22px 30px minmax(0, 1fr) 44px 40px; align-items:center; gap:8px;
  padding:5px 4px; border-radius:8px; }
.mp-row:hover { background:rgba(255,255,255,0.04); }
.mp-row-rank { font-size:0.78rem; font-weight:800; color:#8a93a6; text-align:right; }
.mp-row:nth-child(2) .mp-row-rank { color:#ffd866; }
.mp-row-sprite { width:30px; height:30px; background-size:contain, contain; background-repeat:no-repeat; background-position:center; }
.mp-row-name { font-size:0.84rem; color:#e6eaf2; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.mp-bar { height:4px; border-radius:4px; margin-top:4px; background:var(--tc); box-shadow:0 0 8px -2px var(--tc); opacity:0.85; }
.mp-row-usage { font-size:0.8rem; color:#fff; font-weight:700; text-align:right; }
.mp-row-move { font-size:0.72rem; font-weight:700; text-align:right; }

/* Story cards */
.mp-stories { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:12px; }
.mp-card { position:relative; border-radius:14px; padding:10px 12px; min-width:0;
  background:linear-gradient(160deg, var(--tc1a), rgba(255,255,255,0.015) 55%);
  border:1px solid var(--tc44); box-shadow:0 0 18px -10px var(--tc), inset 0 0 24px -20px var(--tc);
  transition:transform .15s ease, box-shadow .15s ease; }
.mp-card:hover { transform:translateY(-3px); box-shadow:0 0 24px -6px var(--tc), inset 0 0 24px -16px var(--tc); }
.mp-top { display:flex; gap:12px; align-items:center; }
.mp-sprite { width:52px; height:52px; flex-shrink:0; background-size:contain, contain; background-repeat:no-repeat;
  background-position:center; filter:drop-shadow(0 0 8px var(--tc88)); }
.mp-mid { flex-grow:1; min-width:0; }
.mp-badge { display:inline-block; font-size:0.66rem; font-weight:700; letter-spacing:0.6px; text-transform:uppercase;
  padding:2px 8px; border-radius:999px; background:rgba(0,212,255,0.12); color:#7fe6ff; border:1px solid rgba(0,212,255,0.25); }
.mp-badge.riser { background:rgba(255,120,60,0.14); color:#ffb38a; border-color:rgba(255,120,60,0.3); }
.mp-badge.faller { background:rgba(150,160,180,0.12); color:#b8c0cf; border-color:rgba(150,160,180,0.25); }
.mp-badge.top { background:rgba(255,204,51,0.14); color:#ffd866; border-color:rgba(255,204,51,0.3); }
.mp-badge.newcomer { background:rgba(119,204,85,0.14); color:#a6e68a; border-color:rgba(119,204,85,0.3); }
.mp-badge.fastest { background:rgba(170,120,255,0.14); color:#cbb0ff; border-color:rgba(170,120,255,0.3); }
.mp-name { font-weight:800; font-size:1rem; color:#fff; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.mp-headline { font-size:0.78rem; color:#aab3c5; margin-top:1px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.mp-stat { text-align:right; flex-shrink:0; }
.mp-usage { font-weight:800; font-size:1.15rem; color:#fff; }
.mp-rank { font-size:0.72rem; color:#8a93a6; white-space:nowrap; }
.mp-delta { font-size:0.75rem; font-weight:700; }
.mp-up { color:#5fd38d; } .mp-down { color:#ff7b7b; } .mp-flat { color:#8a93a6; }
.mp-set { font-size:0.76rem; color:#d6dbe6; margin-top:7px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.mp-set span + span::before { content:'·'; margin:0 6px; color:#5a6375; }
.mp-moves { display:flex; flex-wrap:nowrap; gap:4px; margin-top:6px; overflow:hidden; }
.mp-move { white-space:nowrap; font-size:0.68rem; padding:2px 6px; border-radius:6px; background:rgba(255,255,255,0.06);
  border:1px solid rgba(255,255,255,0.08); color:#cfd6e4; }
.mp-foot { display:flex; justify-content:space-between; align-items:center; margin-top:6px; gap:8px; }
.mp-mates { display:flex; align-items:center; gap:4px; font-size:0.68rem; color:#8a93a6; min-width:0; }
.mp-mate { width:26px; height:26px; flex-shrink:0; border-radius:50%; background-color:rgba(255,255,255,0.06);
  border:1px solid rgba(255,255,255,0.08); background-size:contain, contain; background-repeat:no-repeat; background-position:center; }
.mp-spark { flex-shrink:0; background-repeat:no-repeat; }

/* Partner hover cards: open on hover or keyboard focus, anchored left so a panel edge never clips them */
.mp-mate-wrap { position:relative; display:inline-flex; align-items:center; gap:5px; outline:none; cursor:default; }
.mp-mate-wrap .mp-mate { transition:transform .15s ease, box-shadow .15s ease, border-color .15s ease; }
.mp-mate-wrap:hover .mp-mate, .mp-mate-wrap:focus-visible .mp-mate { transform:scale(1.15);
  border-color:var(--pc); box-shadow:0 0 10px -2px var(--pc); }
.mp-tip { position:absolute; left:-6px; bottom:calc(100% + 10px); z-index:40; display:flex; gap:10px; align-items:center;
  width:max-content; min-width:180px; max-width:240px; padding:10px 12px; border-radius:12px;
  background:linear-gradient(160deg, color-mix(in srgb, var(--pc) 18%, #141a26), #141a26 60%);
  border:1px solid color-mix(in srgb, var(--pc) 55%, transparent);
  box-shadow:0 10px 28px rgba(0,0,0,0.55), 0 0 18px -6px var(--pc);
  opacity:0; visibility:hidden; transform:translateY(4px); pointer-events:none;
  transition:opacity .14s ease, transform .14s ease, visibility .14s; }
.mp-tip::after { content:""; position:absolute; left:14px; top:100%; border:6px solid transparent;
  border-top-color:color-mix(in srgb, var(--pc) 55%, transparent); }
.mp-mate-wrap:hover .mp-tip, .mp-mate-wrap:focus-visible .mp-tip { opacity:1; visibility:visible; transform:translateY(0); }
/* Cards in the last grid column open their hover cards leftward so they never run off the section's edge */
.mp-stories .mp-card:nth-child(3n) .mp-tip { left:auto; right:-6px; }
.mp-stories .mp-card:nth-child(3n) .mp-tip::after { left:auto; right:14px; }
@media (max-width: 1050px) {
  .mp-stories .mp-card:nth-child(3n) .mp-tip { left:-6px; right:auto; }
  .mp-stories .mp-card:nth-child(3n) .mp-tip::after { left:14px; right:auto; }
  .mp-stories .mp-card:nth-child(2n) .mp-tip { left:auto; right:-6px; }
  .mp-stories .mp-card:nth-child(2n) .mp-tip::after { left:auto; right:14px; }
}
.mp-tip-sprite { width:48px; height:48px; flex-shrink:0; background-size:contain, contain; background-repeat:no-repeat;
  background-position:center; filter:drop-shadow(0 0 8px color-mix(in srgb, var(--pc) 60%, transparent)); }
.mp-tip-body { display:flex; flex-direction:column; gap:3px; min-width:0; }
.mp-tip-name { font-weight:800; font-size:0.88rem; color:#fff; white-space:nowrap; }
.mp-tip-types { display:flex; gap:4px; }
.mp-tip-type { font-size:0.6rem; font-weight:700; letter-spacing:0.4px; text-transform:uppercase; color:#fff;
  padding:1px 6px; border-radius:4px; text-shadow:0 1px 2px rgba(0,0,0,0.35); }
.mp-tip-line { font-size:0.72rem; color:#aab3c5; white-space:nowrap; }
.mp-tip-line b { color:#fff; }
@media (prefers-reduced-motion: reduce) { .mp-tip, .mp-mate-wrap .mp-mate { transition:none; } }

@media (max-width: 1050px) { .mp-stories { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
@media (max-width: 900px) {
  .mp-mag { grid-template-columns:minmax(0, 1fr); }
  .mp-f-body { grid-template-columns:minmax(0, 1fr); }
  .mp-chart { width:100%; background-position:left center; }
}
@media (max-width: 640px) {
  .mp-head { flex-direction:column; align-items:flex-start; }
  .mp-sub { text-align:left; }
  .mp-title { font-size:1.9rem; }
  .mp-f-top { flex-direction:column; align-items:flex-start; gap:8px; }
  .mp-f-sprite { width:88px; height:88px; }
  .mp-f-name { font-size:1.5rem; }
  .mp-stories { display:flex; overflow-x:auto; scroll-snap-type:x mandatory; padding-bottom:8px; }
  .mp-stories .mp-card { flex-shrink:0; width:82%; scroll-snap-align:start; }
}
@media (prefers-reduced-motion: reduce) { .mp-card { transition:none; } .mp-card:hover { transform:none; } }
</style>
"""


def _svg_bg(svg, cls, w, h, label):
    data = base64.b64encode(svg.encode()).decode()
    return (f'<div class="{cls}" role="img" aria-label="{escape(label)}" '
            f'style="width:{w}px;height:{h}px;background-image:url(data:image/svg+xml;base64,{data});"></div>')


def _points(series, w, h, pad_x, pad_top, pad_bottom, zero_based=False):
    """Chart coordinates. zero_based keeps dips to scale, so a 7 point drop from 28% doesn't look like a crash to zero."""
    pts = [(i, u) for i, (_, u) in enumerate(series) if u is not None]
    if len(pts) < 2:
        return []
    lo, hi = (0.0 if zero_based else min(u for _, u in pts)), max(u for _, u in pts)
    span = (hi - lo) or 1.0
    n = max(len(series) - 1, 1)
    return [(pad_x + i * (w - 2 * pad_x) / n, pad_top + (1 - (u - lo) / span) * (h - pad_top - pad_bottom), u)
            for i, u in pts]


def _sparkline(series, color, w=92, h=28):
    """Small trend line for a story card; months without data are skipped."""
    coords = _points(series, w, h, 2, 3, 3, zero_based=True)
    if not coords:
        return ""
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in coords)
    lx, ly, _ = coords[-1]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
           f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" '
           f'stroke-linecap="round" opacity="0.9"/><circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6" fill="{color}"/></svg>')
    return _svg_bg(svg, "mp-spark", w, h, f"usage over the last {len(series)} months")


def _chart(series, color, w=320, h=118):
    """Featured story chart: area under the usage line, month labels and the latest value."""
    coords = _points(series, w, h, 14, 22, 20, zero_based=True)
    if not coords:
        return ""
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in coords)
    base_y = h - 20
    area = f"{coords[0][0]:.1f},{base_y} {line} {coords[-1][0]:.1f},{base_y}"
    n = max(len(series) - 1, 1)
    labels = "".join(
        f'<text x="{14 + i * (w - 28) / n:.1f}" y="{h - 5}" text-anchor="middle" font-size="10" '
        f'font-family="Inter, Segoe UI, sans-serif" fill="#8a93a6">{MONTHS[int(m[5:7]) - 1]}</text>'
        for i, (m, _) in enumerate(series))
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.4" fill="{color}" opacity="0.7"/>' for x, y, _ in coords[:-1])
    lx, ly, lu = coords[-1]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
           f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{color}" stop-opacity="0.35"/>'
           f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
           f'<polygon points="{area}" fill="url(#g)"/>'
           f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>'
           f'{dots}<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" fill="{color}"/>'
           f'<text x="{min(lx, w - 22):.1f}" y="{max(ly - 9, 11):.1f}" text-anchor="middle" font-size="11" font-weight="700" '
           f'font-family="Inter, Segoe UI, sans-serif" fill="#ffffff">{lu:.1f}%</text>{labels}</svg>')
    return _svg_bg(svg, "mp-chart", w, h, f"usage over the last {len(series)} months")


def _color(types, type_map):
    return type_map.get((types or ["Normal"])[0], {}).get("color", "#00d4ff")


def _vars(color):
    return f"--tc:{color}; --tc1a:{color}1a; --tc33:{color}33; --tc44:{color}44; --tc55:{color}55; --tc88:{color}88;"


def _sprite_bg(name):
    forme, base = meta_pulse.sprite_urls(name)
    return f"background-image:url({forme}), url({base});"


def _partner(p, type_map, label, show_name=False):
    """A partner sprite that opens a small card on hover or focus: types, ladder rank, usage and usual item."""
    if isinstance(p, str):
        p = {"name": p, "types": []}
    color = _color(p.get("types"), type_map)
    chips = "".join(f'<span class="mp-tip-type" style="background:{type_map.get(t, {}).get("color", "#555")}">{escape(t)}</span>'
                    for t in p.get("types") or [])
    lines = []
    if p.get("rank"):
        lines.append(f'<span class="mp-tip-line"><b>#{p["rank"]}</b> in {escape(label)} · <b>{p["usage"]:.1f}%</b> usage</span>')
    held = " · ".join(escape(x) for x in (p.get("item"), p.get("ability")) if x)
    if held:
        lines.append(f'<span class="mp-tip-line">{held}</span>')
    name = escape(p["name"])
    return (f'<span class="mp-mate-wrap" tabindex="0" style="--pc:{color}">'
            f'<span class="mp-mate" style="{_sprite_bg(p["name"])}" role="img" aria-label="{name}"></span>'
            f'{f"<span>{name}</span>" if show_name else ""}'
            f'<span class="mp-tip" role="tooltip"><span class="mp-tip-sprite" style="{_sprite_bg(p["name"])}"></span>'
            f'<span class="mp-tip-body"><span class="mp-tip-name">{name}</span>'
            f'<span class="mp-tip-types">{chips}</span>{"".join(lines)}</span></span></span>')


def _delta(card):
    d = card.get("delta")
    if d is None:
        return '<div class="mp-delta mp-up">NEW</div>' if card["kind"] == "newcomer" else ""
    if abs(d) < 0.05:
        return '<div class="mp-delta mp-flat">±0.0</div>'
    cls, arrow = ("mp-up", "▲") if d > 0 else ("mp-down", "▼")
    return f'<div class="mp-delta {cls}">{arrow} {abs(d):.1f}</div>'


def _set_bits(card):
    bits = [b for b in (card.get("item"), card.get("ability")) if b]
    if card.get("tera"):
        bits.append(f"Tera {card['tera']}")
    return "".join(f"<span>{escape(str(b))}</span>" for b in bits)


def _moves(card):
    return "".join(f'<span class="mp-move">{escape(m)}</span>' for m in card.get("moves", []))


def _feature(card, type_map, label_fmt=""):
    color = _color(card.get("types"), type_map)
    icon, label = card["badge"]
    pills = [f'<span class="mp-pill"><b>{card["usage"]:.1f}%</b>usage</span>']
    rank = f"#{card['rank']}" + (f" (from #{card['prev_rank']})" if card.get("prev_rank") and card["prev_rank"] != card["rank"] else "")
    pills.append(f'<span class="mp-pill"><b>{escape(rank)}</b>rank</span>')
    if card.get("delta") is not None:
        arrow = "▲" if card["delta"] > 0 else "▼"
        pills.append(f'<span class="mp-pill"><b>{arrow} {abs(card["delta"]):.1f}</b>points this month</span>')
    if card.get("speed"):
        pills.append(f'<span class="mp-pill"><b>{card["speed"]}</b>Speed</span>')
    mates = "".join(f'<span class="mp-f-mate">{_partner(p, type_map, label_fmt, show_name=True)}</span>'
                    for p in card.get("partners") or card.get("teammates") or [])
    mates_html = f'<div class="mp-f-mates"><span>Pairs with</span>{mates}</div>' if mates else ""
    return f"""
<div class="mp-panel mp-feature" style="{_vars(color)}">
  <div class="mp-f-top">
    <div class="mp-f-sprite" style="{_sprite_bg(card['name'])}" role="img" aria-label="{escape(card['name'])}"></div>
    <div>
      <div class="mp-f-kicker">{icon} Story of the month · {escape(label)}</div>
      <div class="mp-f-name">{escape(card['name'])}</div>
      <div class="mp-f-headline">{escape(card['headline'])}</div>
      <div class="mp-pills">{''.join(pills)}</div>
    </div>
  </div>
  <div class="mp-f-body">
    <div class="mp-f-set"><div class="mp-set">{_set_bits(card)}</div><div class="mp-moves">{_moves(card)}</div>{mates_html}</div>
    {_chart(card['series'], color)}
  </div>
</div>"""


def _board(rows, type_map):
    if not rows:
        return ""
    top = rows[0]["usage"] or 1
    items = []
    for r in rows:
        color = _color(r["types"], type_map)
        if not r["has_prev"]:
            move = ""
        elif r["prev_rank"] is None:
            move = '<span class="mp-up">NEW</span>'
        elif r["prev_rank"] > r["rank"]:
            move = f'<span class="mp-up">▲{r["prev_rank"] - r["rank"]}</span>'
        elif r["prev_rank"] < r["rank"]:
            move = f'<span class="mp-down">▼{r["rank"] - r["prev_rank"]}</span>'
        else:
            move = '<span class="mp-flat">–</span>'
        items.append(
            f'<div class="mp-row" style="{_vars(color)}"><span class="mp-row-rank">{r["rank"]}</span>'
            f'<span class="mp-row-sprite" style="{_sprite_bg(r["name"])}"></span>'
            f'<div style="min-width:0"><div class="mp-row-name">{escape(r["name"])}</div>'
            f'<div class="mp-bar" style="width:{max(r["usage"] / top * 100, 4):.0f}%"></div></div>'
            f'<span class="mp-row-usage">{r["usage"]:.1f}%</span><span class="mp-row-move">{move}</span></div>')
    return (f'<div class="mp-panel"><div class="mp-board-title">Top {len(rows)} by usage<span>rank change vs last month</span></div>'
            f'<div>{"".join(items)}</div></div>')


def _card(card, type_map, label_fmt=""):
    color = _color(card.get("types"), type_map)
    icon, label = card["badge"]
    mates = card.get("partners") or card.get("teammates") or []
    # Partner sprites open a small card on hover: three names never fit the card width as text
    mate_icons = "".join(_partner(p, type_map, label_fmt) for p in mates)
    mates_html = f'<span>Pairs with</span>{mate_icons}' if mates else ""
    speed = f" · {card['speed']} Spe" if card.get("speed") else ""
    return f"""
<div class="mp-card" style="{_vars(color)}">
  <div class="mp-top">
    <div class="mp-sprite" style="{_sprite_bg(card['name'])}" role="img" aria-label="{escape(card['name'])}"></div>
    <div class="mp-mid">
      <span class="mp-badge {card['kind']}">{icon} {escape(label)}</span>
      <div class="mp-name">{escape(card['name'])}</div>
      <div class="mp-headline">{escape(card['headline'])}</div>
    </div>
    <div class="mp-stat">
      <div class="mp-usage">{card['usage']:.1f}%</div>
      <div class="mp-rank">#{card['rank']}{speed}</div>
      {_delta(card)}
    </div>
  </div>
  <div class="mp-set">{_set_bits(card)}</div>
  <div class="mp-moves">{_moves(card)}</div>
  <div class="mp-foot"><div class="mp-mates">{mates_html}</div>{_sparkline(card['series'], color)}</div>
</div>"""


@st.cache_data(show_spinner=False)
def _section(format_id, month):
    """(cards, leaderboard) for a format and month, cached since both read the chaos file."""
    return meta_pulse.pulse(format_id, n=7, month=month), meta_pulse.leaderboard(format_id, month=month)


def render(format_id, type_map):
    month = meta_pulse.current_month()
    cards, rows = _section(format_id, month)
    if not cards:
        return
    fmt = config.format_info(format_id)
    rating = fmt["stats"].rsplit("-", 1)[-1]
    lead = meta_pulse.featured_index(cards)
    stories = [c for i, c in enumerate(cards) if i != lead][:6]
    head = (f'<div class="mp-head"><div><div class="mp-kicker">This month on the ladder</div>'
            f'<div class="mp-title">MetaFlash</div>'
            '<div class="mp-tag">The ladder&#39;s biggest moves, the month they happen.</div></div>'
            f'<div class="mp-sub"><span class="mp-live"></span><b>{escape(meta_pulse.month_label(month))}</b><br>'
            f'{escape(fmt["label"])} ladder {rating}+ · Smogon usage stats</div></div>')
    label = fmt["label"]
    mag = f'<div class="mp-mag">{_feature(cards[lead], type_map, label)}{_board(rows, type_map)}</div>'
    grid = f'<div class="mp-stories">{"".join(_card(c, type_map, label) for c in stories)}</div>'
    st.html(CSS + head + mag + grid)

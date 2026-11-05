"""
Meta Pulse strip for the start screen: a snapping, horizontally scrolling row of cards
(swipe on phones, scroll or shift+wheel on desktop). Pure HTML and CSS through st.html, so it
renders in the page without an iframe and costs no reruns to scroll.
"""
import base64
from html import escape

import streamlit as st

from metamatch import config, meta_pulse

CSS = """
<style>
.mp-head { display:flex; align-items:baseline; justify-content:space-between; gap:10px; margin: 2px 2px 10px 2px; }
.mp-title { font-weight:800; font-size:1.15rem; color:#fff; letter-spacing:0.3px; white-space:nowrap; }
.mp-sub { font-size:0.75rem; color:#8a93a6; text-align:right; }
.mp-feed { display:flex; flex-direction:row; gap:12px; overflow-x:auto; overflow-y:hidden;
  scroll-snap-type:x mandatory; padding:2px 2px 10px 2px; -webkit-mask-image:linear-gradient(to right, #000 93%, transparent); mask-image:linear-gradient(to right, #000 93%, transparent); scrollbar-width:thin; scrollbar-color:#2b3445 transparent; }
.mp-card { scroll-snap-align:start; flex-shrink:0; width:345px; position:relative; border-radius:14px; padding:10px 12px;
  background:linear-gradient(135deg, rgba(255,255,255,0.045), rgba(255,255,255,0.015));
  border:1px solid var(--tc44); box-shadow:0 0 18px -10px var(--tc), inset 0 0 24px -20px var(--tc);
  transition:transform .15s ease, box-shadow .15s ease; }
.mp-card:hover { transform:translateY(-2px); box-shadow:0 0 22px -6px var(--tc), inset 0 0 24px -16px var(--tc); }
.mp-top { display:flex; gap:12px; align-items:center; }
.mp-sprite { width:52px; height:52px; flex-shrink:0; background-size:contain, contain; background-repeat:no-repeat;
  background-position:center; filter:drop-shadow(0 0 8px var(--tc88)); }
.mp-mid { flex-grow:1; min-width:0; }
.mp-badge { display:inline-block; font-size:0.68rem; font-weight:700; letter-spacing:0.6px; text-transform:uppercase;
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
.mp-rank { font-size:0.72rem; color:#8a93a6; }
.mp-delta { font-size:0.75rem; font-weight:700; }
.mp-up { color:#5fd38d; } .mp-down { color:#ff7b7b; } .mp-flat { color:#8a93a6; }
.mp-set { font-size:0.76rem; color:#d6dbe6; margin-top:7px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.mp-set span + span::before { content:'·'; margin:0 6px; color:#5a6375; }
.mp-moves { display:flex; flex-wrap:nowrap; gap:4px; margin-top:6px; overflow:hidden; }
.mp-move { white-space:nowrap; font-size:0.68rem; padding:2px 6px; border-radius:6px; background:rgba(255,255,255,0.06);
  border:1px solid rgba(255,255,255,0.08); color:#cfd6e4; }
.mp-foot { display:flex; justify-content:space-between; align-items:center; margin-top:6px; gap:8px; }
.mp-mates { display:flex; align-items:center; gap:4px; font-size:0.68rem; color:#8a93a6; min-width:0; }
.mp-mate { width:26px; height:26px; border-radius:50%; background-color:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.08);
  background-size:contain, contain; background-repeat:no-repeat; background-position:center; }
.mp-spark { flex-shrink:0; background-repeat:no-repeat; }
@media (max-width: 640px) { .mp-card { width:82%; } }
</style>
"""


def _sparkline(series, color, w=92, h=28):
    """Inline SVG line of monthly usage; months without data are skipped."""
    pts = [(i, u) for i, (_, u) in enumerate(series) if u is not None]
    if len(pts) < 2:
        return ""
    lo, hi = min(u for _, u in pts), max(u for _, u in pts)
    span = (hi - lo) or 1.0
    n = max(len(series) - 1, 1)
    coords = [(2 + i * (w - 4) / n, h - 3 - (u - lo) / span * (h - 6)) for i, u in pts]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    lx, ly = coords[-1]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
           f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" '
           f'stroke-linecap="round" opacity="0.9"/><circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6" fill="{color}"/></svg>')
    # st.html sanitizes inline <svg> away, so the chart rides in as a data URI background like the sprites
    data = base64.b64encode(svg.encode()).decode()
    return (f'<div class="mp-spark" role="img" aria-label="usage over the last {len(series)} months" '
            f'style="width:{w}px;height:{h}px;background-image:url(data:image/svg+xml;base64,{data});"></div>')


def _delta(card):
    d = card.get("delta")
    if d is None:
        return '<div class="mp-delta mp-up">NEW</div>' if card["kind"] == "newcomer" else ""
    if abs(d) < 0.05:
        return '<div class="mp-delta mp-flat">±0.0</div>'
    cls, arrow = ("mp-up", "▲") if d > 0 else ("mp-down", "▼")
    return f'<div class="mp-delta {cls}">{arrow} {abs(d):.1f}</div>'


def _card(card, type_map):
    color = type_map.get((card.get("types") or ["Normal"])[0], {}).get("color", "#00d4ff")
    forme, base = meta_pulse.sprite_urls(card["name"])
    icon, label = card["badge"]
    set_bits = [b for b in (card.get("item"), card.get("ability")) if b]
    if card.get("tera"):
        set_bits.append(f"Tera {card['tera']}")
    set_html = "".join(f"<span>{escape(str(b))}</span>" for b in set_bits)
    moves = "".join(f'<span class="mp-move">{escape(m)}</span>' for m in card.get("moves", []))
    mates = card.get("teammates") or []
    # Partner sprites with names on hover: three names never fit the card width as text
    mate_icons = "".join(
        f'<span class="mp-mate" title="{escape(m)}" role="img" aria-label="{escape(m)}" '
        f'style="background-image:url({a}), url({b});"></span>'
        for m in mates for a, b in [meta_pulse.sprite_urls(m)])
    mates_html = f'<span>Pairs with</span>{mate_icons}' if mates else ""
    style = f"--tc:{color}; --tc44:{color}44; --tc88:{color}88;"
    return f"""
<div class="mp-card" style="{style}">
  <div class="mp-top">
    <div class="mp-sprite" style="background-image:url('{forme}'), url('{base}');" role="img" aria-label="{escape(card['name'])}"></div>
    <div class="mp-mid">
      <span class="mp-badge {card['kind']}">{icon} {escape(label)}</span>
      <div class="mp-name">{escape(card['name'])}</div>
      <div class="mp-headline">{escape(card['headline'])}</div>
    </div>
    <div class="mp-stat">
      <div class="mp-usage">{card['usage']:.1f}%</div>
      <div class="mp-rank">#{card['rank']}{f" · {card['speed']} Spe" if card.get("speed") else ""}</div>
      {_delta(card)}
    </div>
  </div>
  <div class="mp-set">{set_html}</div>
  <div class="mp-moves">{moves}</div>
  <div class="mp-foot"><div class="mp-mates">{mates_html}</div>{_sparkline(card['series'], color)}</div>
</div>"""


@st.cache_data(show_spinner=False)
def _cards(format_id, month):
    return meta_pulse.pulse(format_id, month=month)


def render(format_id, type_map):
    month = meta_pulse.current_month()
    cards = _cards(format_id, month)
    if not cards:
        return
    fmt = config.format_info(format_id)
    rating = fmt["stats"].rsplit("-", 1)[-1]
    head = (f'<div class="mp-head"><span class="mp-title">📡 Meta Pulse</span>'
            f'<span class="mp-sub">{escape(meta_pulse.month_label(month))} · {escape(fmt["label"])} ladder {rating}+</span></div>')
    body = "".join(_card(c, type_map) for c in cards)
    st.html(CSS + head + f'<div class="mp-feed">{body}</div>')

"""
MetaFlash section for the start screen (meta_pulse.py picks the cards), laid out like a magazine page: a featured story with a
6 month chart, a top 10 leaderboard beside it, and a grid of story cards underneath (a swipe strip
on phones). Pure HTML and CSS through st.html, so it renders in the page without an iframe.
st.html sanitizes inline <svg>, so charts ride in as data URI background images like the sprites.
"""
import base64
from html import escape

import streamlit as st

from metamatch import config, meta_pulse, meta_trends

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

/* Section headings below the magazine */
.mp-sec { display:flex; align-items:flex-end; justify-content:space-between; gap:12px; margin:30px 2px 12px; }
.mp-sec-kicker { font-size:0.66rem; font-weight:800; letter-spacing:2px; text-transform:uppercase; color:#00d4ff; }
.mp-sec-title { font-weight:900; font-size:1.4rem; color:#fff; letter-spacing:-0.3px; margin-top:2px; }
.mp-sec-note { font-size:0.76rem; color:#8a93a6; text-align:right; max-width:46%; line-height:1.45; }
.mp-duo { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:14px; }
.mp-solo .mp-panel > div:last-child { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); column-gap:28px; }

/* Leads and top players' picks */
.mp-legend { display:flex; gap:12px; font-size:0.7rem; color:#8a93a6; font-weight:500; }
.mp-legend i { display:inline-block; width:10px; height:4px; border-radius:3px; margin-right:5px; vertical-align:middle; }
.mp-fav { display:grid; grid-template-columns:30px minmax(0, 1fr) 54px; align-items:center; gap:10px; padding:4px 4px; border-radius:8px; }
.mp-fav:hover { background:rgba(255,255,255,0.04); }
.mp-fav-bars { display:flex; flex-direction:column; gap:2px; margin-top:3px; }
.mp-fav-bar { display:flex; align-items:center; gap:6px; font-size:0.68rem; color:#8a93a6; }
.mp-fav-bar span:first-child { height:5px; border-radius:4px; flex-shrink:0; }
.mp-fav-top span:first-child { background:var(--tc); box-shadow:0 0 8px -2px var(--tc); }
.mp-fav-wide span:first-child { background:rgba(170,180,200,0.35); }
.mp-fav-top { color:#e6eaf2; font-weight:700; }
.mp-gap { justify-self:end; font-size:0.8rem; font-weight:800; color:#5fd38d; padding:2px 8px; border-radius:999px;
  background:rgba(95,211,141,0.12); border:1px solid rgba(95,211,141,0.25); }

/* Set trends and rising cores */
.mp-grid3 { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:12px; }
.mp-grid4 { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:12px; }
.mp-trend { position:relative; border-radius:14px; padding:12px 14px; min-width:0;
  background:linear-gradient(160deg, var(--tc1a), rgba(255,255,255,0.015) 55%); border:1px solid var(--tc44);
  box-shadow:0 0 18px -12px var(--tc); transition:transform .15s ease, box-shadow .15s ease; }
.mp-trend:hover { transform:translateY(-3px); box-shadow:0 0 24px -8px var(--tc); }
.mp-trend-top { display:flex; gap:10px; align-items:center; }
.mp-trend .mp-sprite { width:46px; height:46px; }
.mp-cat { display:inline-block; font-size:0.62rem; font-weight:800; letter-spacing:0.8px; text-transform:uppercase;
  padding:2px 8px; border-radius:999px; border:1px solid; }
.mp-cat.items { color:#ffd866; background:rgba(255,204,51,0.12); border-color:rgba(255,204,51,0.28); }
.mp-cat.tera { color:#7fe6ff; background:rgba(0,212,255,0.12); border-color:rgba(0,212,255,0.28); }
.mp-cat.moves { color:#cbb0ff; background:rgba(170,120,255,0.12); border-color:rgba(170,120,255,0.28); }
.mp-cat.abilities { color:#a6e68a; background:rgba(119,204,85,0.12); border-color:rgba(119,204,85,0.28); }
.mp-option { display:flex; align-items:baseline; justify-content:space-between; gap:8px; margin-top:10px; }
.mp-option-name { font-weight:800; font-size:1.05rem; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.mp-option-share { font-weight:900; font-size:1.3rem; color:#fff; flex-shrink:0; }
.mp-trend-foot { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-top:6px; }
.mp-trend-text { font-size:0.74rem; color:#aab3c5; min-width:0; }
.mp-duo-sprites { position:relative; width:84px; height:52px; flex-shrink:0; }
.mp-duo-sprites .mp-sprite { position:absolute; top:0; width:52px; height:52px; }
.mp-duo-sprites .mp-sprite + .mp-sprite { left:32px; }
.mp-core-names { font-weight:800; font-size:0.92rem; color:#fff; line-height:1.3; min-width:0; margin-top:8px; }
.mp-core-names div { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.mp-core-names span { color:#7fe6ff; margin-right:5px; }
.mp-core-stat { display:flex; align-items:baseline; gap:8px; margin-top:8px; }
.mp-core-stat b { font-weight:900; font-size:1.25rem; color:#fff; }
.mp-core-stat small { font-size:0.72rem; color:#8a93a6; }

/* Your teams this month */
.mp-teams { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:12px; }
.mp-team { border-radius:14px; padding:14px; min-width:0; background:linear-gradient(160deg, rgba(0,212,255,0.07), rgba(255,255,255,0.015) 60%);
  border:1px solid rgba(0,212,255,0.22); }
.mp-team-top { display:flex; align-items:center; gap:12px; }
.mp-ring { --p:0; width:58px; height:58px; border-radius:50%; flex-shrink:0; display:grid; place-items:center;
  background:conic-gradient(#5fd38d calc(var(--p) * 1%), rgba(255,255,255,0.08) 0); }
.mp-ring span { width:46px; height:46px; border-radius:50%; background:#141a26; display:grid; place-items:center;
  font-weight:900; font-size:0.86rem; color:#fff; }
.mp-team-name { font-weight:800; color:#fff; font-size:0.98rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.mp-team-sub { font-size:0.74rem; color:#8a93a6; }
.mp-strip { display:flex; gap:2px; margin-top:4px; }
.mp-strip .mp-mate { width:26px; height:26px; }
.mp-team-lines { display:flex; flex-direction:column; gap:6px; margin-top:12px; }
.mp-team-k { font-size:0.64rem; font-weight:800; letter-spacing:1px; text-transform:uppercase; color:#8a93a6; }
.mp-threat { display:grid; grid-template-columns:28px minmax(0, 1fr); align-items:center; gap:8px; font-size:0.78rem; color:#d6dbe6; }
.mp-threat .mp-mate { width:28px; height:28px; }
.mp-threat small { color:#8a93a6; margin-left:4px; }
.mp-threat .ok { color:#5fd38d; } .mp-threat .bad { color:#ff7b7b; }
.mp-team-open { display:inline-block; margin-top:12px; font-size:0.78rem; font-weight:700; color:#7fe6ff; text-decoration:none; }
.mp-team-open:hover { text-decoration:underline; }
.mp-quiet { font-size:0.8rem; color:#8a93a6; padding:6px 2px; }

@media (max-width: 1050px) { .mp-grid3, .mp-teams { grid-template-columns:repeat(2, minmax(0, 1fr)); }
  .mp-grid4 { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
@media (max-width: 900px) { .mp-duo, .mp-solo .mp-panel > div:last-child { grid-template-columns:minmax(0, 1fr); } }
@media (max-width: 640px) { .mp-grid3, .mp-grid4, .mp-teams { grid-template-columns:minmax(0, 1fr); }
  .mp-sec { flex-direction:column; align-items:flex-start; } .mp-sec-note { text-align:left; max-width:none; } }
@media (prefers-reduced-motion: reduce) { .mp-trend { transition:none; } .mp-trend:hover { transform:none; } }
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
    step = 2 if len(series) > 8 else 1
    labels = "".join(
        f'<text x="{14 + i * (w - 28) / n:.1f}" y="{h - 5}" text-anchor="middle" font-size="10" '
        f'font-family="Inter, Segoe UI, sans-serif" fill="#8a93a6">{MONTHS[int(m[5:7]) - 1]}</text>'
        for i, (m, _) in enumerate(series) if (len(series) - 1 - i) % step == 0)
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
    # The all time peak, when it was a better rank than now
    if card.get("peak") and card["peak"][0] < card["rank"]:
        best, when = card["peak"]
        pills.append(f'<span class="mp-pill"><b>#{best}</b>peak, {escape(meta_pulse.month_label(when))}</span>')
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
    {_chart(card.get('long_series') or card['series'], color)}
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


@st.cache_data(show_spinner=False)
def _trends(format_id, month):
    """Leads, top players' picks, set trends and rising cores for a format and month, with each name's types."""
    from metamatch.engine.dex import dex_for_format
    out = {"leads": meta_trends.leads(format_id, month, n=10), "favorites": meta_trends.ladder_favorites(format_id, month),
           "sets": meta_trends.set_trends(format_id, month), "cores": meta_trends.rising_cores(format_id, month)}
    dex = dex_for_format(format_id)
    names = {r["name"] for k in ("leads", "favorites", "sets") for r in out[k]} | {n for c in out["cores"] for n in c["pair"]}
    out["types"] = {n: ((dex.species(n) or {}).get("types", []) if dex else []) for n in names}
    for t in out["sets"]:
        t["text"] = (f"from {t['prev']:.0f}% last month" if not t["new"] else f"from under {max(t['prev'], 1):.0f}% last month")
    return out


def _sec(kicker, title, note=""):
    note_html = f'<div class="mp-sec-note">{note}</div>' if note else ""
    return (f'<div class="mp-sec"><div><div class="mp-sec-kicker">{escape(kicker)}</div>'
            f'<div class="mp-sec-title">{escape(title)}</div></div>{note_html}</div>')


def _move_chip(rank, prev_rank, has_prev):
    if not has_prev:
        return ""
    if prev_rank is None:
        return '<span class="mp-up">NEW</span>'
    if prev_rank > rank:
        return f'<span class="mp-up">▲{prev_rank - rank}</span>'
    if prev_rank < rank:
        return f'<span class="mp-down">▼{rank - prev_rank}</span>'
    return '<span class="mp-flat">·</span>'


def _leads_panel(rows, types, type_map):
    if not rows:
        return ""
    top = rows[0]["share"] or 1
    items = "".join(
        f'<div class="mp-row" style="{_vars(_color(types.get(r["name"]), type_map))}"><span class="mp-row-rank">{r["rank"]}</span>'
        f'<span class="mp-row-sprite" style="{_sprite_bg(r["name"])}"></span>'
        f'<div style="min-width:0"><div class="mp-row-name">{escape(r["name"])}</div>'
        f'<div class="mp-bar" style="width:{max(r["share"] / top * 100, 4):.0f}%"></div></div>'
        f'<span class="mp-row-usage">{r["share"]:.1f}%</span>'
        f'<span class="mp-row-move">{_move_chip(r["rank"], r["prev_rank"], r["has_prev"])}</span></div>'
        for r in rows)
    return (f'<div class="mp-panel"><div class="mp-board-title">Leads to expect<span>share of games it leads</span></div>'
            f'<div>{items}</div></div>')


def _favorites_panel(rows, types, type_map, rating):
    if not rows:
        return ""
    scale = max(r["top"] for r in rows) or 1
    items = "".join(
        f'<div class="mp-fav" style="{_vars(_color(types.get(r["name"]), type_map))}">'
        f'<span class="mp-row-sprite" style="{_sprite_bg(r["name"])}"></span>'
        f'<div style="min-width:0"><div class="mp-row-name">{escape(r["name"])}</div><div class="mp-fav-bars">'
        f'<div class="mp-fav-bar mp-fav-top"><span style="width:{max(r["top"] / scale * 100, 3) * 0.7:.0f}%"></span>{r["top"]:.1f}%</div>'
        f'<div class="mp-fav-bar mp-fav-wide"><span style="width:{max(r["wide"] / scale * 100, 3) * 0.7:.0f}%"></span>{r["wide"]:.1f}%</div>'
        f'</div></div><span class="mp-gap">+{r["gap"]:.1f}</span></div>'
        for r in rows)
    legend = (f'<span class="mp-legend"><span><i style="background:#00d4ff"></i>{rating}+</span>'
              f'<span><i style="background:rgba(170,180,200,0.5)"></i>1500+</span></span>')
    return (f'<div class="mp-panel"><div class="mp-board-title">Top players&#39; picks{legend}</div>'
            f'<div>{items}</div></div>')


CAT_LABEL = {"items": "Item", "tera": "Tera", "moves": "Move", "abilities": "Ability"}


def _trend_card(t, types, type_map):
    color = _color(types.get(t["name"]), type_map)
    option = f"Tera {t['option']}" if t["category"] == "tera" else t["option"]
    share = f"&lt;{max(t['share'], 1):.0f}%" if t.get("gone") else f"{t['share']:.0f}%"
    up = t["delta"] > 0
    delta = f'<span class="mp-delta {"mp-up" if up else "mp-down"}">{"▲" if up else "▼"} {abs(t["delta"]):.0f}</span>'
    spark = _sparkline([(m, v) for m, v in t["series"]], color, w=84, h=26)
    return (f'<div class="mp-trend" style="{_vars(color)}"><div class="mp-trend-top">'
            f'<div class="mp-sprite" style="{_sprite_bg(t["name"])}"></div><div style="min-width:0">'
            f'<span class="mp-cat {t["category"]}">{CAT_LABEL[t["category"]]}</span>'
            f'<div class="mp-name">{escape(t["name"])}</div></div></div>'
            f'<div class="mp-option"><span class="mp-option-name">{escape(option)}</span>'
            f'<span class="mp-option-share">{share} {delta}</span></div>'
            f'<div class="mp-trend-foot"><span class="mp-trend-text">{escape(t["text"])}</span>{spark}</div></div>')


def _core_card(c, types, type_map):
    a, b = c["pair"]
    ca, cb = _color(types.get(a), type_map), _color(types.get(b), type_map)
    spark = _sparkline(c["series"], ca, w=84, h=26)
    since = "new pairing" if c["new"] else f"from {c['prev']:.1f}%"
    return (f'<div class="mp-trend" style="{_vars(ca)}"><div class="mp-trend-top">'
            f'<div class="mp-duo-sprites"><div class="mp-sprite" style="{_sprite_bg(a)};filter:drop-shadow(0 0 8px {ca}88)"></div>'
            f'<div class="mp-sprite" style="{_sprite_bg(b)};filter:drop-shadow(0 0 8px {cb}88)"></div></div>'
            f'</div><div class="mp-core-names"><div>{escape(a)}</div><div><span>+</span>{escape(b)}</div></div>'
            f'<div class="mp-core-stat"><b>{c["share"]:.1f}%</b><small>of teams</small>'
            f'<span class="mp-delta mp-up">▲ {c["delta"]:.1f}</span></div>'
            f'<div class="mp-trend-foot"><span class="mp-trend-text">{escape(since)}</span>{spark}</div></div>')


def _trend_sections(trends, format_id, month, type_map):
    fmt = config.format_info(format_id)
    rating = fmt["stats"].rsplit("-", 1)[-1]
    types = trends["types"]
    html = ""
    leads, favs = _leads_panel(trends["leads"], types, type_map), _favorites_panel(trends["favorites"], types, type_map, rating)
    if leads and favs:
        html += _sec("Team preview", "Leads and the top of the ladder",
                     f"Which Pokémon open games, and what {rating}+ players run more than the ladder at 1500+")
        html += f'<div class="mp-duo">{leads}{favs}</div>'
    elif leads:
        html += _sec("Team preview", "Leads to expect", "Which Pokémon opened games that month")
        html += f'<div class="mp-solo">{leads}</div>'
    if trends["sets"]:
        html += _sec("Sets", "How sets changed this month", "The biggest shift in item, Tera, moves or ability among the top 25")
        html += f'<div class="mp-grid3">{"".join(_trend_card(t, types, type_map) for t in trends["sets"])}</div>'
    if trends["cores"]:
        html += _sec("Teams", "Rising cores", "Pairs more teams are running together than last month")
        html += f'<div class="mp-grid4">{"".join(_core_card(c, types, type_map) for c in trends["cores"])}</div>'
    if not trends["sets"] and month < (meta_pulse.current_month() or ""):
        html += '<div class="mp-quiet">Set trends, top players&#39; picks and rising cores cover the last 12 months.</div>'
    return html


@st.cache_data(show_spinner=False, max_entries=24)
def _team_report(raw_text, format_id, month):
    from metamatch.team import readTeam
    team, _ = readTeam(raw_text, format_id)
    return meta_trends.team_report(team, format_id, month)


def _threat_line(t, ok_word):
    answer = (f'<span class="ok">{escape(ok_word)} {escape(t["answers"][0])}</span>' if t["answers"]
              else '<span class="bad">nobody on the team beats it</span>')
    rank = f'#{t["rank"]}' + (f', up from #{t["prev_rank"]}' if t["prev_rank"] else ", new")
    return (f'<div class="mp-threat"><span class="mp-mate" style="{_sprite_bg(t["name"])}"></span>'
            f'<div style="min-width:0"><b>{escape(t["name"])}</b><small>{rank}</small><br>{answer}</div></div>')


def _team_card(team, report):
    pct = round(100 * report["answered"] / report["total"]) if report["total"] else 0
    names = team.get("pokemon_names") or []
    strip = "".join(f'<span class="mp-mate" style="{_sprite_bg(n)}"></span>' for n in names[:6])
    lines = []
    if report["new"]:
        lines.append('<div class="mp-team-k">New in the top 12</div>' + "".join(_threat_line(t, "beaten by") for t in report["new"][:2]))
    if report["rising"]:
        lines.append('<div class="mp-team-k">Climbing, thinly answered</div>' + "".join(_threat_line(t, "only beaten by") for t in report["rising"][:2]))
    if not lines:
        lines.append('<div class="mp-quiet">No new or climbing threats it struggles with this month.</div>')
    title = escape(team.get("name") or ", ".join(names[:3]))
    return (f'<div class="mp-team"><div class="mp-team-top"><div class="mp-ring" style="--p:{pct}"><span>{report["answered"]}/{report["total"]}</span></div>'
            f'<div style="min-width:0"><div class="mp-team-name">{title}</div>'
            f'<div class="mp-team-sub">answers {report["answered"]} of the {report["total"]} most used Pokémon</div>'
            f'<div class="mp-strip">{strip}</div></div></div>'
            f'<div class="mp-team-lines">{"".join(lines)}</div>'
            f'<a class="mp-team-open" href="team?t={escape(team["id"])}" target="_self">Open its dashboard →</a></div>')


@st.fragment
def _teams_section(format_id, month):
    """Saved teams (or recent ones) in this format against this month's top threats. The calc runs on request."""
    from metamatch import storage
    teams = [t for t in storage.list_teams_detailed() if t.get("format") == format_id][:3]
    if not teams:
        teams = [t for t in storage.recent_teams(6) if t.get("format") == format_id][:3]
    if not teams:
        return
    st.html(_sec("Your teams", "Your teams this month",
                 "Each team against this month&#39;s 12 most used Pokémon, with the threats that just arrived"))
    key = f"mf_teams_{format_id}_{month}"
    if not st.session_state.get(key):
        st.button("Check my teams against this month", icon=":material/shield:", key=f"btn_{key}",
                  on_click=lambda: st.session_state.update({key: True}))
        return
    with st.spinner("Running each team against this month's top threats..."):
        cards = [_team_card(t, _team_report(t["raw_text"], format_id, month)) for t in teams]
    st.html(f'<div class="mp-teams">{"".join(cards)}</div>')


def render(format_id, type_map):
    latest = meta_pulse.current_month()
    months = sorted(meta_pulse.load_history().get(format_id, {}), reverse=True)
    fmt = config.format_info(format_id)
    rating = fmt["stats"].rsplit("-", 1)[-1]
    head_col, pick_col = st.columns([5, 1.3], vertical_alignment="bottom")
    with pick_col:
        month = st.selectbox("Month", months or [latest], format_func=meta_pulse.month_label, key=f"mf_month_{format_id}",
                             help="Browse any month since the format started")
    cards, rows = _section(format_id, month)
    if not cards:
        return
    live = '<span class="mp-live"></span>' if month == latest else ""
    with head_col:
        st.html(CSS + f'<div class="mp-head" style="margin-bottom:0"><div><div class="mp-kicker">'
                f'{"This month on the ladder" if month == latest else "Back issue"}</div>'
                f'<div class="mp-title">MetaFlash</div>'
                '<div class="mp-tag">The ladder&#39;s biggest moves, the month they happen.</div></div>'
                f'<div class="mp-sub">{live}<b>{escape(meta_pulse.month_label(month))}</b><br>'
                f'{escape(fmt["label"])} ladder {rating}+ · Smogon usage stats</div></div>')
    lead = meta_pulse.featured_index(cards)
    stories = [c for i, c in enumerate(cards) if i != lead][:6]
    label = fmt["label"]
    mag = f'<div class="mp-mag" style="margin-top:16px">{_feature(cards[lead], type_map, label)}{_board(rows, type_map)}</div>'
    grid = f'<div class="mp-stories">{"".join(_card(c, type_map, label) for c in stories)}</div>'
    st.html(CSS + mag + grid + _trend_sections(_trends(format_id, month), format_id, month, type_map))
    if config.LOCAL_MODE and month == latest:
        _teams_section(format_id, month)

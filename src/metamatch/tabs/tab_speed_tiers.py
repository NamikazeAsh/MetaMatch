"""Speed Tiers tab: your team's real Speed against the Speed of every spread the format's top Pokemon run."""
import json
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

from metamatch import config
from metamatch.engine import speed_board as sb
from metamatch.sprites import get_sprite
from metamatch.ui import section_header

N_META = 25
MIN_SHARE = 0.03   # spreads below 3% of a Pokemon's sets are left off the chart


@st.cache_data(show_spinner=False, max_entries=16)
def _data(team_json, format_id, stats_month):
    team = json.loads(team_json)
    mine = sb.member_speeds(team, format_id)
    exclude = [p["Pokemon"] for p in team.values()]
    meta = sb.meta_speeds(format_id, n=N_META, exclude=exclude)
    return mine, [{"name": m.name, "usage": m.usage, "speeds": m.speeds, "scarf": m.scarf_share, "spreads": m.spreads}
                  for m in meta]


def _stats_month():
    try:
        return json.loads((config.STATS_DIR / "manifest.json").read_text(encoding="utf-8")).get("month", "")
    except (OSError, ValueError):
        return ""


def _meta_obj(m):
    return sb.MetaSpeed(m["name"], m["usage"], [tuple(x) for x in m["speeds"]], m["scarf"], m.get("spreads", {}))


def _spreads(m, spe):
    """The most run spreads behind one dot, one per line with its share of the Pokemon's sets."""
    return "\n".join(f"{label} ({share * 100:.0f}%)" for label, share in m.get("spreads", {}).get(spe, []))


def _chart(mine, meta, colors, test=None):
    """Dots per spread (bigger = more common, amber = Choice Scarf), your team in type colours with a speed
    line each, so everything left of a line is a spread that member outspeeds."""
    points = []
    for m in meta:
        for spe, share in m["speeds"]:
            if share >= MIN_SHARE:
                points.append({"Pokemon": m["name"], "Speed": spe, "Share": round(share * 100, 1), "Kind": "Ladder spread",
                               "Note": f"{share * 100:.0f}% of {m['name']} sets", "Usage": f"on {m['usage']:g}% of teams",
                               "Spreads": _spreads(m, spe), "Color": "#7d879b"})
        if m["scarf"] >= 0.05 and m["speeds"]:
            points.append({"Pokemon": m["name"], "Speed": int(m["speeds"][0][0] * 1.5), "Share": round(m["scarf"] * 100, 1),
                           "Kind": "With Choice Scarf", "Note": f"{m['scarf'] * 100:.0f}% hold Choice Scarf",
                           "Usage": f"on {m['usage']:g}% of teams", "Spreads": _spreads(m, m["speeds"][0][0]),
                           "Color": "#f5b13d"})
    for name, spe in mine.items():
        points.append({"Pokemon": f"{name} (yours)", "Speed": spe, "Share": 100.0, "Kind": "Your team",
                       "Note": "your Speed, with your item", "Usage": "your team", "Spreads": "the spread you pasted",
                       "Color": colors.get(name, "#22d3ee")})
    df = pd.DataFrame(points)
    order = df.groupby("Pokemon")["Speed"].max().sort_values(ascending=False).index.tolist()
    yours = "indexof(datum.label, '(yours)') >= 0"
    y = alt.Y("Pokemon:N", sort=order, axis=alt.Axis(
        title=None, labelLimit=200, labelPadding=10, labelFontSize=12,
        labelColor=alt.condition(yours, alt.value("#ffffff"), alt.value("#9aa4b6")),
        labelFontWeight=alt.condition(yours, alt.value(800), alt.value(500))))
    x = alt.X("Speed:Q", scale=alt.Scale(zero=False, nice=True),
              axis=alt.Axis(title="Speed stat", titleColor="#8a93a6", titleFontWeight=600, labelColor="#8a93a6"))
    tips = [alt.Tooltip("Pokemon:N", title="Pokémon"), alt.Tooltip("Speed:Q"), alt.Tooltip("Note:N", title="Share"),
            alt.Tooltip("Spreads:N", title="Spreads"), alt.Tooltip("Usage:N", title="Usage")]
    base = alt.Chart(df).encode(y=y, x=x, tooltip=tips)
    team = df[df.Kind == "Your team"]
    lines = alt.Chart(team).mark_rule(strokeWidth=2, opacity=0.28, strokeDash=[4, 4]).encode(
        x="Speed:Q", color=alt.Color("Color:N", scale=None))
    dots = base.transform_filter(alt.datum.Kind != "Your team").mark_circle(opacity=0.75, stroke="#0f1219", strokeWidth=1).encode(
        size=alt.Size("Share:Q", scale=alt.Scale(range=[40, 420]), legend=None), color=alt.Color("Color:N", scale=None))
    mine_dots = base.transform_filter(alt.datum.Kind == "Your team").mark_circle(size=260, opacity=1, stroke="#ffffff",
                                                                                  strokeWidth=2).encode(color=alt.Color("Color:N", scale=None))
    labels = base.transform_filter(alt.datum.Kind == "Your team").mark_text(
        align="left", dx=14, fontWeight=800, fontSize=12).encode(text="Speed:Q", color=alt.Color("Color:N", scale=None))
    layers = lines + dots + mine_dots + labels
    if test:
        layers += alt.Chart(pd.DataFrame([{"Speed": test}])).mark_rule(
            color="#ffffff", strokeWidth=2, strokeDash=[6, 3], opacity=0.85).encode(x="Speed:Q")
    return layers.properties(height=max(440, 24 * len(order))).configure(
        background="transparent", font="Inter").configure_view(strokeWidth=0).configure_axis(
        gridColor="rgba(255,255,255,0.05)", domain=False, ticks=False)


LEGEND = """
<style>.st-key-speed_chart_card { background:linear-gradient(160deg, rgba(0,212,255,0.05), rgba(255,255,255,0.015) 60%); border-radius:16px !important; border-color:rgba(255,255,255,0.08) !important; box-shadow:0 8px 24px rgba(0,0,0,0.25); }</style>
<div style="display:flex;flex-wrap:wrap;gap:16px;align-items:center;font-size:0.8rem;color:#aab3c5;margin:2px 4px 6px">
  <span><i style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#22d3ee;border:2px solid #fff;margin-right:6px;vertical-align:-2px"></i>Your team, in type colours</span>
  <span><i style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#7d879b;margin-right:6px;vertical-align:-2px"></i>Ladder spread (bigger is more common)</span>
  <span><i style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#f5b13d;margin-right:6px;vertical-align:-2px"></i>With Choice Scarf</span>
  <span><i style="display:inline-block;width:16px;border-top:2px dashed rgba(255,255,255,0.35);margin-right:6px;vertical-align:3px"></i>Your speed lines: everything left of one is slower</span>
</div>
"""
TEST_KEY = ('<div style="font-size:0.8rem;color:#aab3c5;margin:-2px 4px 6px"><i style="display:inline-block;width:16px;'
            'border-top:2px dashed #fff;margin-right:6px;vertical-align:3px"></i>The Speed you are testing below</div>')


def render(team_data, type_map=None):
    format_id = config.team_format(team_data)
    label = config.format_info(format_id)["label"]
    section_header("Speed", "Speed Tiers")
    st.caption(f"The {N_META} most used Pokémon in {label} besides your own, at the Speed of each spread players run this month. "
               "Your Speed includes your item.")
    with st.spinner("Working out Speeds..."):
        mine, meta = _data(json.dumps(team_data, sort_keys=True, default=str), format_id, _stats_month())
    if not meta:
        st.info("No usage stats for this format yet. Run `python scripts/update_meta.py` to download them.")
        return
    colors = {p["Pokemon"]: (type_map or {}).get((p.get("Type") or ["Normal"])[0], {}).get("color", "#22d3ee")
              for p in team_data.values()}
    # The What if? Speed below draws as a white line here: the widgets sit under the chart, but Streamlit has
    # already stored their new values when the rerun starts
    who = st.session_state.get("speed_who") if st.session_state.get("speed_who") in mine else next(iter(mine))
    test = st.session_state.get(f"speed_test_{who}")
    test = test if test and test != int(mine[who]) else None
    with st.container(border=True, key="speed_chart_card"):
        st.html(LEGEND + (TEST_KEY if test else ""))
        st.altair_chart(_chart(mine, meta, colors, test), width="stretch")

    st.markdown("**What if?**")
    c1, c2 = st.columns([1, 2], gap="large")
    with c1:
        who = st.selectbox("Your Pokémon", list(mine), key="speed_who")
        member = next(p for p in team_data.values() if p["Pokemon"] == who)
        curve = _curve(json.dumps(member, sort_keys=True, default=str), format_id)
        base = int(mine[who])
        lo, hi = _slider_range(curve, base)
        key = f"speed_test_{who}"
        st.session_state[key] = min(max(st.session_state.get(key, base), lo), hi)
        test = st.slider("Speed to test", lo, hi, key=key,
                         help="Drag, or pick a benchmark, to see who you would outspeed and what the Speed costs.")
        st.html(PLAN_STYLE + _cost_line(who, base, test, curve))
    with c2:
        objs = [_meta_obj(m) for m in meta]
        st.html(PLAN_STYLE + _changes(objs, base, test))
        options = [b for b in _benchmarks(objs, test) if b[1] + 1 <= hi]
        if options:
            st.pills(f"Next benchmarks above {test}", options, key=f"speed_bench_{who}", on_change=_jump, args=(who,),
                     format_func=lambda b: f"{b[0]} {b[1]} · {sb.price_text(curve, sb.price(curve, b[1] + 1), short=True)}")
    st.caption("Benchmarks are the Speeds at least 10% of a Pokémon's sets run. Costs come from the damage calculator "
               "with your item and ability. Shares mix in Choice Scarf usage, and Speed ties count as not outspeeding.")


PLAN_STYLE = """<style>
.sp-cost { margin: 2px 0 6px; padding: 10px 12px; border-radius: 12px; background: rgba(0,212,255,.06);
  border: 1px solid rgba(0,212,255,.2); font-size: .88rem; line-height: 1.45; color: #d6dbe6; }
.sp-cost b { color: #7fe6ff; }
.sp-cost.far { background: rgba(248,113,113,.06); border-color: rgba(248,113,113,.28); }
.sp-cost.far b { color: #fca5a5; }
.sp-k { font-size: .7rem; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; color: #8a93a6; margin: 2px 0 6px; }
.sp-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.sp-chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px 2px 2px; border-radius: 999px; font-size: .84rem;
  background: rgba(52,211,153,.08); border: 1px solid rgba(52,211,153,.28); color: #d1fae5; }
.sp-chip.lost { background: rgba(248,113,113,.08); border-color: rgba(248,113,113,.3); color: #fde2e2; }
.sp-chip img { width: 26px; height: 26px; object-fit: contain; }
.sp-chip small { color: #9aa3b2; margin-left: 2px; }
.sp-sum { color: #c8ccd4; font-size: .88rem; margin-bottom: 10px; }
.sp-sum b { color: #fff; }
[class*="st-key-speed_bench_"] [data-testid="stButtonGroup"] div:has(> button) { flex-wrap: wrap !important;
  overflow-x: visible !important; row-gap: 6px; }
</style>"""


@st.cache_data(show_spinner=False, max_entries=48)
def _curve(member_json, format_id):
    return sb.speed_curve(json.loads(member_json), format_id)


def _slider_range(curve, base):
    """From a little under the slowest the member can be to well past the fastest EVs and nature can make it."""
    reach = [s for _, s in (curve or {}).get("own", [])] + [s for _, s in ((curve or {}).get("fast") or (None, []))[1]]
    return max(1, min(reach + [base]) - 20), max(reach + [base]) + 60


def _cost_line(who, base, test, curve):
    if test == base:
        return f'<div class="sp-cost"><b>{escape(who)}</b> runs <b>{base}</b> Speed now. Drag the slider or pick a benchmark.</div>'
    if not curve:
        return f'<div class="sp-cost"><b>{test}</b> Speed</div>'
    cost = sb.price(curve, test)
    far = "" if cost else " far"
    return f'<div class="sp-cost{far}"><b>{test}</b> Speed: {escape(sb.price_text(curve, cost))}.</div>'


def _chip(o, before, after, lost=False):
    sprite = get_sprite(o.name) or ""
    return (f'<span class="sp-chip{" lost" if lost else ""}"><img src="{escape(sprite)}" alt="">{escape(o.name)}'
            f'<small>{before * 100:.0f}% → {after * 100:.0f}%</small></span>')


def _changes(objs, base, test, min_shift=0.10):
    """Who the test Speed outspeeds more (or fewer) of, by at least 10 points of their sets, and how many of the
    top Pokemon it outspeeds most sets of."""
    now = {o.name: sb.outspeed_share(base, o) for o in objs}
    then = {o.name: sb.outspeed_share(test, o) for o in objs}
    most = sum(v >= 0.5 for v in then.values())
    summary = (f'<div class="sp-sum">Outspeeds most sets of <b>{most}</b> of the top {len(objs)} at {test} Speed'
               + (f', {sum(v >= 0.5 for v in now.values())} now' if test != base else "") + ".</div>")
    if test == base:
        return summary
    lost = test < base
    moved = [o for o in objs if abs(then[o.name] - now[o.name]) >= min_shift]
    if not moved:
        return summary + '<div class="sp-sum">No Pokémon moves by 10 points or more at this Speed.</div>'
    head = "Outspeeds fewer of its sets" if lost else "Outspeeds more of its sets"
    chips = "".join(_chip(o, now[o.name], then[o.name], lost) for o in sorted(moved, key=lambda o: o.usual))
    return f'<div class="sp-k">{head}</div><div class="sp-chips">{chips}</div>' + summary


def _benchmarks(objs, test, n=6, min_share=0.10):
    """The next common Speeds at or above the test Speed: (name, speed), slowest first."""
    seen = sorted({(o.name, spe) for o in objs for spe, share in o.speeds if share >= min_share and spe >= test},
                  key=lambda b: (b[1], b[0]))
    return seen[:n]


def _jump(who):
    """Moves the slider just past the picked benchmark, then clears the pick so the pills never go stale."""
    picked = st.session_state.get(f"speed_bench_{who}")
    if picked:
        st.session_state[f"speed_test_{who}"] = picked[1] + 1
    st.session_state[f"speed_bench_{who}"] = None

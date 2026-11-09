"""Speed Tiers tab: your team's real Speed against the Speed of every spread the format's top Pokemon run."""
import json

import altair as alt
import pandas as pd
import streamlit as st

from metamatch import config
from metamatch.engine import speed_board as sb
from metamatch.ui import section_header

N_META = 25
MIN_SHARE = 0.03   # spreads below 3% of a Pokemon's sets are left off the chart


@st.cache_data(show_spinner=False, max_entries=16)
def _data(team_json, format_id, stats_month):
    team = json.loads(team_json)
    mine = sb.member_speeds(team, format_id)
    exclude = [p["Pokemon"] for p in team.values()]
    meta = sb.meta_speeds(format_id, n=N_META, exclude=exclude)
    return mine, [{"name": m.name, "usage": m.usage, "speeds": m.speeds, "scarf": m.scarf_share} for m in meta]


def _stats_month():
    try:
        return json.loads((config.STATS_DIR / "manifest.json").read_text(encoding="utf-8")).get("month", "")
    except (OSError, ValueError):
        return ""


def _meta_obj(m):
    return sb.MetaSpeed(m["name"], m["usage"], [tuple(x) for x in m["speeds"]], m["scarf"])


def _chart(mine, meta, colors):
    """Dots per spread (bigger = more common, amber = Choice Scarf), your team in type colours with a speed
    line each, so everything left of a line is a spread that member outspeeds."""
    points = []
    for m in meta:
        for spe, share in m["speeds"]:
            if share >= MIN_SHARE:
                points.append({"Pokemon": m["name"], "Speed": spe, "Share": round(share * 100, 1), "Kind": "Ladder spread",
                               "Note": f"{share * 100:.0f}% of {m['name']} sets", "Usage": f"on {m['usage']:g}% of teams",
                               "Color": "#7d879b"})
        if m["scarf"] >= 0.05 and m["speeds"]:
            points.append({"Pokemon": m["name"], "Speed": int(m["speeds"][0][0] * 1.5), "Share": round(m["scarf"] * 100, 1),
                           "Kind": "With Choice Scarf", "Note": f"{m['scarf'] * 100:.0f}% hold Choice Scarf",
                           "Usage": f"on {m['usage']:g}% of teams", "Color": "#f5b13d"})
    for name, spe in mine.items():
        points.append({"Pokemon": f"{name} (yours)", "Speed": spe, "Share": 100.0, "Kind": "Your team",
                       "Note": "your Speed, with your item", "Usage": "your team", "Color": colors.get(name, "#22d3ee")})
    df = pd.DataFrame(points)
    order = df.groupby("Pokemon")["Speed"].max().sort_values(ascending=False).index.tolist()
    yours = "indexof(datum.label, '(yours)') >= 0"
    y = alt.Y("Pokemon:N", sort=order, axis=alt.Axis(
        title=None, labelLimit=200, labelPadding=10, labelFontSize=12,
        labelColor=alt.condition(yours, alt.value("#ffffff"), alt.value("#9aa4b6")),
        labelFontWeight=alt.condition(yours, alt.value(800), alt.value(500))))
    x = alt.X("Speed:Q", scale=alt.Scale(zero=False, nice=True),
              axis=alt.Axis(title="Speed stat", titleColor="#8a93a6", titleFontWeight=600, labelColor="#8a93a6"))
    base = alt.Chart(df).encode(y=y, x=x, tooltip=["Pokemon", "Speed", "Note", "Usage"])
    team = df[df.Kind == "Your team"]
    lines = alt.Chart(team).mark_rule(strokeWidth=2, opacity=0.28, strokeDash=[4, 4]).encode(
        x="Speed:Q", color=alt.Color("Color:N", scale=None))
    dots = base.transform_filter(alt.datum.Kind != "Your team").mark_circle(opacity=0.75, stroke="#0f1219", strokeWidth=1).encode(
        size=alt.Size("Share:Q", scale=alt.Scale(range=[40, 420]), legend=None), color=alt.Color("Color:N", scale=None))
    mine_dots = base.transform_filter(alt.datum.Kind == "Your team").mark_circle(size=260, opacity=1, stroke="#ffffff",
                                                                                  strokeWidth=2).encode(color=alt.Color("Color:N", scale=None))
    labels = base.transform_filter(alt.datum.Kind == "Your team").mark_text(
        align="left", dx=14, fontWeight=800, fontSize=12).encode(text="Speed:Q", color=alt.Color("Color:N", scale=None))
    return (lines + dots + mine_dots + labels).properties(height=max(440, 24 * len(order))).configure(
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
    with st.container(border=True, key="speed_chart_card"):
        st.html(LEGEND)
        st.altair_chart(_chart(mine, meta, colors), width="stretch")

    st.markdown("**What if?**")
    c1, c2 = st.columns([1, 2])
    with c1:
        who = st.selectbox("Your Pokémon", list(mine), key="speed_who")
        base = int(mine[who])
        test = st.slider("Speed to test", max(1, base - 80), base + 120, base, key=f"speed_test_{who}",
                         help="Drag to see who you would outspeed with more or less Speed investment.")
    with c2:
        rows = []
        for m in meta:
            obj = _meta_obj(m)
            now, then = sb.outspeed_share(base, obj), sb.outspeed_share(test, obj)
            rows.append({"Pokémon": m["name"], "Usual Speed": obj.usual,
                         "You outspeed now": f"{now * 100:.0f}%", "At test Speed": f"{then * 100:.0f}%",
                         "_gain": then - now})
        df = pd.DataFrame(rows).sort_values(["_gain", "Usual Speed"], ascending=[False, False]).drop(columns="_gain")
        st.dataframe(df, hide_index=True, width="stretch", height=320)
    if test != base:
        gained = [r["Pokémon"] for r in rows if r["_gain"] > 0.2]
        if gained:
            st.caption(f"At {test} Speed, {who} newly outspeeds most {', '.join(gained[:6])} sets.")
    st.caption("Shares mix in each Pokémon's Choice Scarf usage. Speed ties count as not outspeeding.")

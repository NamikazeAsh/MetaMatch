"""Speed Tiers tab: your team's real Speed against the Speed of every spread the format's top Pokemon run."""
import json

import altair as alt
import pandas as pd
import streamlit as st

from metamatch import config
from metamatch.engine import speed_board as sb

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


def _chart(mine, meta):
    points = []
    for m in meta:
        for spe, share in m["speeds"]:
            if share >= MIN_SHARE:
                points.append({"Pokemon": m["name"], "Speed": spe, "Share": round(share * 100, 1), "Kind": "Ladder spread",
                               "Note": f"{share * 100:.0f}% of {m['name']} sets"})
        if m["scarf"] >= 0.05 and m["speeds"]:
            points.append({"Pokemon": m["name"], "Speed": int(m["speeds"][0][0] * 1.5), "Share": round(m["scarf"] * 100, 1),
                           "Kind": "With Choice Scarf", "Note": f"{m['scarf'] * 100:.0f}% hold Choice Scarf"})
    for name, spe in mine.items():
        points.append({"Pokemon": f"{name} (yours)", "Speed": spe, "Share": 100.0, "Kind": "Your team", "Note": "with your item"})
    df = pd.DataFrame(points)
    order = (df.groupby("Pokemon")["Speed"].max().sort_values(ascending=False).index.tolist())
    base = alt.Chart(df).encode(
        y=alt.Y("Pokemon:N", sort=order, axis=alt.Axis(title=None, labelLimit=180)),
        x=alt.X("Speed:Q", axis=alt.Axis(title="Speed stat"), scale=alt.Scale(zero=False)),
        tooltip=["Pokemon", "Speed", "Note"])
    dots = base.mark_circle(opacity=.85).encode(
        size=alt.Size("Share:Q", scale=alt.Scale(range=[40, 380]), legend=None),
        color=alt.Color("Kind:N", scale=alt.Scale(domain=["Your team", "Ladder spread", "With Choice Scarf"],
                                                  range=["#22d3ee", "#8b98b0", "#f59e0b"]),
                        legend=alt.Legend(title=None, orient="top")))
    labels = base.transform_filter(alt.datum.Kind == "Your team").mark_text(align="left", dx=12, color="#22d3ee",
                                                                             fontWeight="bold").encode(text="Speed:Q")
    return (dots + labels).properties(height=max(420, 22 * len(order)))


def render(team_data):
    format_id = config.team_format(team_data)
    label = config.format_info(format_id)["label"]
    st.subheader("Speed Tiers", help="Your team's Speed against the spreads players actually run.")
    st.caption(f"The {N_META} most used Pokémon in {label}, at the Speed of each spread players run this month. "
               "Bigger dots are more common spreads; orange dots are Choice Scarf sets. Your Speed includes your item.")
    with st.spinner("Working out Speeds..."):
        mine, meta = _data(json.dumps(team_data, sort_keys=True, default=str), format_id, _stats_month())
    if not meta:
        st.info("No usage stats for this format yet. Run `python scripts/update_meta.py` to download them.")
        return
    st.altair_chart(_chart(mine, meta), width="stretch")

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

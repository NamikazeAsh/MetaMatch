import json
import pandas as pd
import altair as alt
import streamlit as st
from metamatch import config
from metamatch.scrapers import speed_tiers_path


def render(team_data: dict):
    st.subheader("⚡ Speed Tiers", help="Compare team speed against meta threats.")
    try:
        with open(speed_tiers_path(config.format_game(config.team_format(team_data))), "r") as f:
            m_s = json.load(f)
    except:
        m_s = []
    u_s = [{'Name': p['Pokemon'], 'Speed': p.get('Speed', 0), 'Type': 'Your Team'} for p in team_data.values()]
    c_d = u_s + [{'Name': m['label'], 'Speed': m['speed'], 'Type': 'Meta'} for m in m_s[:40]]
    df_c = pd.DataFrame(c_d).sort_values(by="Speed", ascending=False)
    base = alt.Chart(df_c).encode(y=alt.Y('Name', sort='-x', axis=alt.Axis(title=None)), x=alt.X('Speed', axis=alt.Axis(title='Speed Stat')), tooltip=['Name', 'Speed', 'Type'])
    dots = base.mark_circle(size=100).encode(color=alt.Color('Type', scale=alt.Scale(domain=['Your Team', 'Meta'], range=['#3399FF', '#888888'])), opacity=alt.condition(alt.datum.Type == 'Your Team', alt.value(1.0), alt.value(0.5)))
    text = base.mark_text(align='left', dx=10, color='#3399FF', fontWeight='bold').encode(text=alt.Text('Speed'), opacity=alt.condition(alt.datum.Type == 'Your Team', alt.value(1.0), alt.value(0.0)))
    st.altair_chart((dots + text).properties(height=600), use_container_width=True)

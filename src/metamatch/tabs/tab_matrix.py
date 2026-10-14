import pandas as pd
import streamlit as st
from metamatch.type_chart import get_multiplier


ALL_TYPES = ["Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison",
             "Ground", "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy"]


def render(team_data: dict):
    st.subheader("🛡️ Defensive Matchup Matrix", help="Damage taken from each type. Red = Weak.")
    st.markdown(r'''<div style="display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap;"><span style="background-color: #7b1e1e; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">🟥 4x Weak</span><span style="background-color: #c0392b; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">🟧 2x Weak</span><span style="border: 1px solid #ccc; color: #888; padding: 4px 8px; border-radius: 4px; font-size: 12px;">⬜ 1x Neutral</span><span style="background-color: #27ae60; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">🟩 0.5x Resist</span><span style="background-color: #1e8449; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">🌲 0.25x Resist</span><span style="background-color: #2c3e50; color: #ecf0f1; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">🟦 0x Immune</span></div>''', unsafe_allow_html=True)

    rows = []
    for p in team_data.values():
        r = {"Pokemon": p['Pokemon']}
        for t in ALL_TYPES:
            r[t] = p['Damage From'].get(t.lower(), 1.0)
        rows.append(r)
    df = pd.DataFrame(rows).set_index("Pokemon")

    def c_c(v):
        if v == 0: return 'background-color: #2c3e50; color: #ecf0f1'
        if v >= 4: return 'background-color: #7b1e1e; color: white'
        if v >= 2: return 'background-color: #c0392b; color: white'
        if v <= 0.25: return 'background-color: #1e8449; color: white'
        if v <= 0.5: return 'background-color: #27ae60; color: white'
        return ''

    st.dataframe(df.style.map(c_c).format("{:.1f}"), width='stretch', height=250)

    st.markdown("---")
    st.subheader("⚔️ Offensive Coverage Matrix", help="Best damage you deal to each type. Green = Super Effective.")
    st.markdown(r'''<div style="display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap;"><span style="background-color: #27ae60; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">🟩 2x SE</span><span style="border: 1px solid #ccc; color: #888; padding: 4px 8px; border-radius: 4px; font-size: 12px;">⬜ 1x Neutral</span><span style="background-color: #c0392b; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">🟥 0.5x Resisted</span><span style="background-color: #2c3e50; color: #ecf0f1; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">🟦 0x Immune</span></div>''', unsafe_allow_html=True)

    o_rows = []
    for p in team_data.values():
        r = {"Pokemon": p['Pokemon']}
        for t_d in ALL_TYPES:
            m_m = 0.0
            for m in p['Moves']:
                if m['category'] != 'Status':
                    mult = get_multiplier(m['type'], t_d)
                    if mult > m_m:
                        m_m = mult
            if not p['Moves'] and m_m == 0.0:
                m_m = 1.0
            r[t_d] = m_m
        o_rows.append(r)
    o_df = pd.DataFrame(o_rows).set_index("Pokemon")

    def c_c_o(v):
        if v >= 2: return 'background-color: #27ae60; color: white'
        if v == 0: return 'background-color: #2c3e50; color: #ecf0f1'
        if v <= 0.5: return 'background-color: #c0392b; color: white'
        return ''

    st.dataframe(o_df.style.map(c_c_o).format("{:.1f}"), width='stretch', height=250)

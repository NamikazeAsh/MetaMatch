import streamlit as st
from metamatch.utils import get_pokemon_sprite


def render():
    if st.session_state.analysis.get('suggestions'):
        sugg = st.session_state.analysis['suggestions']

        # --- Team Analysis Section ---
        st.subheader("🛡️ Team Audit")
        if 'team_analysis' in sugg and isinstance(sugg['team_analysis'], list):
            for p in sugg['team_analysis']:
                st.markdown(f"""
                <div style="background: rgba(0, 212, 255, 0.05); border-left: 4px solid #00d4ff; padding: 12px 16px; margin-bottom: 12px; border-radius: 0 8px 8px 0;">
                    <span style="font-size: 1.1rem; margin-right: 8px;">💡</span>
                    <span style="color: #e0e0e0; font-size: 0.95rem;">{p}</span>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")

        # --- Pokemon Specific Section ---
        st.subheader("🔍 Per-Pokemon Findings")
        if 'pokemon_specific' in sugg and isinstance(sugg['pokemon_specific'], dict):
            for pk, adv in sugg['pokemon_specific'].items():
                advice_text = str(adv)
                if isinstance(adv, dict):
                    advice_text = ", ".join([str(v) for v in adv.values()])

                sprite_url = get_pokemon_sprite(pk) or ""

                st.markdown(f"""
                <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 16px; margin-bottom: 12px; display: flex; align-items: start; gap: 15px; transition: all 0.2s;">
                    <div style="flex-shrink: 0; background: rgba(255, 255, 255, 0.05); border-radius: 50%; width: 60px; height: 60px; display: flex; align-items: center; justify-content: center;">
                        <img src="{sprite_url}" width="50" style="filter: drop-shadow(0 0 3px rgba(0,0,0,0.5));">
                    </div>
                    <div>
                        <div style="font-weight: 700; font-size: 1.1rem; color: #00d4ff; margin-bottom: 4px;">{pk}</div>
                        <div style="color: #ccc; font-size: 0.9rem; line-height: 1.5;">{advice_text}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    else:
        st.info("Run analysis to see the audit.")

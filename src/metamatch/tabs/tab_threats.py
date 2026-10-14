import streamlit as st
from metamatch.utils import get_pokemon_sprite


def render():
    sugg = st.session_state.analysis.get('suggestions')
    if sugg and 'threats' in sugg:
        threats = sugg['threats']
        if threats:
            st.caption("⚠️ High-priority threats identified by AI analysis based on your team composition.")
            for threat in threats:
                name = threat.get('pokemon', 'Unknown')
                explanation = threat.get('explanation', 'No explanation provided.')
                counter = threat.get('counter_play', 'No specific counter play provided.')
                sprite_url = get_pokemon_sprite(name) or ""

                threat_html = f"""
                <div style="background: rgba(255, 50, 50, 0.05); border: 1px solid rgba(255, 75, 75, 0.2); border-radius: 12px; padding: 16px; margin-bottom: 16px; display: flex; align-items: flex-start; gap: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.2);">
                    <div style="flex-shrink: 0; text-align: center; width: 80px;">
                        <div style="background: rgba(255, 0, 0, 0.1); width: 60px; height: 60px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 8px auto;">
                            <img src="{sprite_url}" width="60" style="filter: drop-shadow(0 0 5px rgba(255,0,0,0.4));">
                        </div>
                    </div>
                    <div style="flex-grow: 1;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <span style="font-size: 1.2rem; font-weight: 700; color: #ff6b6b; letter-spacing: 0.5px;">{name}</span>
                            <span style="font-size: 0.7rem; background: rgba(255, 75, 75, 0.2); color: #ff9999; padding: 2px 8px; border-radius: 10px; border: 1px solid rgba(255, 75, 75, 0.3);">MAJOR THREAT</span>
                        </div>
                        <div style="font-size: 0.9rem; color: #e0e0e0; margin-bottom: 12px; line-height: 1.5;">
                            {explanation}
                        </div>
                        <div style="background: rgba(0, 0, 0, 0.2); border-left: 3px solid #ff6b6b; padding: 10px; border-radius: 0 6px 6px 0;">
                            <div style="font-size: 0.75rem; color: #ff6b6b; text-transform: uppercase; font-weight: bold; margin-bottom: 4px;">🛡️ Counter Strategy</div>
                            <div style="font-size: 0.85rem; color: #ccc;">{counter}</div>
                        </div>
                    </div>
                </div>
                """
                st.markdown(threat_html, unsafe_allow_html=True)
        else:
            st.success("✅ No major meta threats identified based on current context!")
    elif st.session_state.submitted:
        st.warning("⚠️ No threat data returned from analysis.")
    else:
        st.info("Run analysis to see meta threats.")

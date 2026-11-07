from html import escape

import streamlit as st
from metamatch.utils import get_pokemon_sprite


CHECK_STYLE = """
<style>
.ck { display: grid; grid-template-columns: 26px 1fr; gap: 10px; align-items: start; padding: 9px 12px; margin-bottom: 6px;
  border-radius: 10px; background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.07); }
.ck b { font-size: .95rem; }
.ck.ok b { color: #34d399; } .ck.fix b { color: #f87171; } .ck.note b { color: #facc15; }
</style>
"""
MARKS = {"ok": "✓", "fix": "✗", "note": "!"}


def render_team_check():
    """Legality in plain English, then copy, convert and download."""
    from metamatch import config
    from metamatch.engine import team_check
    team = st.session_state.analysis["team"]
    format_id = config.team_format(team)
    checks = team_check.check(team, format_id)
    st.subheader("✅ Team Check")
    st.markdown(CHECK_STYLE + "".join(
        f'<div class="ck {level}"><b>{MARKS[level]}</b><span>{escape(msg)}</span></div>' for level, msg in checks),
        unsafe_allow_html=True)
    paste = st.session_state.get("pokemon_data") or ""
    champions = config.format_game(format_id) == "champions"
    with st.expander("Export and convert"):
        st.caption("Copy the team, convert its spread for the other game, or download a report to share.")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Showdown export**")
            st.code(paste.strip(), language=None)
        with c2:
            st.markdown("**As Champions stat points**" if not champions else "**As SV EVs**")
            st.code(team_check.convert_paste(paste, to_champions=not champions).strip(), language=None)
            st.caption("1 stat point is about 8 EVs: 252 EVs becomes 32 points, and 4 EVs becomes 1."
                       + (" Tera Type lines are dropped, since Champions has no Tera." if not champions else ""))
        try:
            from metamatch.tabs.tab_threats import _board, _stats_month
            import json
            board = _board(json.dumps(team, sort_keys=True, default=str), format_id, _stats_month())
        except Exception:
            board = None
        report = team_check.report_markdown(team, format_id, paste, checks, board)
        st.download_button("Download team report (Markdown)", report, file_name="metamatch_team_report.md",
                           mime="text/markdown")
    st.markdown("---")


def render():
    if st.session_state.analysis.get('team'):
        render_team_check()
    if st.session_state.analysis.get('suggestions'):
        sugg = st.session_state.analysis['suggestions']

        # --- Team Analysis Section ---
        st.subheader("🛡️ Team Audit")
        if 'team_analysis' in sugg and isinstance(sugg['team_analysis'], list):
            for p in sugg['team_analysis']:
                st.markdown(f"""
                <div style="background: rgba(0, 212, 255, 0.05); border-left: 4px solid #00d4ff; padding: 12px 16px; margin-bottom: 12px; border-radius: 0 8px 8px 0;">
                    <span style="font-size: 1.1rem; margin-right: 8px;">💡</span>
                    <span style="color: #e0e0e0; font-size: 0.95rem;">{escape(str(p))}</span>
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
                        <div style="font-weight: 700; font-size: 1.1rem; color: #00d4ff; margin-bottom: 4px;">{escape(str(pk))}</div>
                        <div style="color: #ccc; font-size: 0.9rem; line-height: 1.5;">{escape(advice_text)}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    else:
        st.info("Run analysis to see the audit.")

import streamlit as st


def _guide_controls():
    """The guide is a slow LLM call, so it's written on request instead of during analysis."""
    from metamatch.agents.client import ollama_available
    from metamatch.suggestions import get_team_guide
    if not ollama_available():
        st.info("The pilot guide is written by the local coach model. Start Ollama to generate one; "
                "every other tab works without it.")
        return
    if st.session_state.analysis.get('guide') is False:
        st.warning("The coach couldn't write a guide for this team. Try again.")
    if st.button("Write my pilot guide", type="primary", key="coach_guide_button"):
        with st.spinner("Professor Oak is writing your guide..."):
            st.session_state.analysis['guide'] = get_team_guide(st.session_state.analysis['team']) or False
        st.rerun()


def render():
    if st.session_state.analysis.get('guide'):
        g = st.session_state.analysis['guide']
        st.subheader("🎓 Team Pilot Guide")

        st.info(f"**🏆 Win Condition:** {g.get('win_condition', 'N/A')}")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🏁 Lead Options")
            for l in g.get('lead_options', []):
                st.success(f"**{l.get('pokemon')}**: {l.get('scenario')}")

        with c2:
            # Champions guides cover Mega Evolution, SV guides cover Tera
            is_mega = 'mega_strategy' in g
            st.markdown("### 🧬 Mega Strategy" if is_mega else "### 💎 Tera Strategy")
            gimmick = g.get('mega_strategy' if is_mega else 'tera_strategy')
            if isinstance(gimmick, dict):
                st.warning(f"**{gimmick.get('pokemon')}**: {gimmick.get('when_to_use')}")
            else:
                st.write(str(gimmick))

        st.markdown("### 🤝 Key Combinations")
        for c in g.get('key_combos', []):
            with st.expander(f"🔗 {c.get('name')}", expanded=True):
                st.write(c.get('description'))
    else:
        _guide_controls()

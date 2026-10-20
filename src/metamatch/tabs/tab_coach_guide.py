import streamlit as st


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
        st.warning("Guide generation failed or is unavailable.")

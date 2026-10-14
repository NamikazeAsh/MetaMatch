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
            st.markdown("### 💎 Tera Strategy")
            tera = g.get('tera_strategy')
            if isinstance(tera, dict):
                st.warning(f"**{tera.get('pokemon')}**: {tera.get('when_to_use')}")
            else:
                st.write(str(tera))

        st.markdown("### 🤝 Key Combinations")
        for c in g.get('key_combos', []):
            with st.expander(f"🔗 {c.get('name')}", expanded=True):
                st.write(c.get('description'))
    else:
        st.warning("Guide generation failed or is unavailable.")

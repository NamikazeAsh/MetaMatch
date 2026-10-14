import streamlit as st


def render(coverage: dict, weakness: dict, team_data: dict, type_map: dict):
    covered_count = sum(1 for v in coverage.values() if v)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Offensive Coverage")
        st.metric("Type Coverage", f"{covered_count}/18 types")
        covered_html = ""
        for t, is_covered in coverage.items():
            if is_covered:
                t_i = type_map.get(t.capitalize(), {'color': '#777', 'icon': '❓'})
                covered_html += f'<span style="background-color:{t_i["color"]};color:white;padding:4px 8px;border-radius:4px;font-size:14px;margin:4px;display:inline-block">{t_i["icon"]} {t.capitalize()}</span>'
        st.markdown(covered_html, unsafe_allow_html=True)
        if [t for t, v in coverage.items() if not v]:
            st.warning("⚠️ Missing offensive coverage for several types.")

    with c2:
        st.subheader("Defensive Vulnerabilities")
        for t_n, counts in weakness.items():
            cap_t = t_n.capitalize()
            if counts['weak'] >= 2:
                t_i = type_map.get(cap_t, {'color': '#777', 'icon': '❓'})
                bg = "rgba(255, 75, 75, 0.2)" if counts['weak'] >= 3 else "rgba(255, 165, 0, 0.1)"
                bc = "#ff4b4b" if counts['weak'] >= 3 else "#ffa500"
                tag = "— ⚠️ CRITICAL" if counts['weak'] >= 3 else ""

                weak_mons = []
                for p in team_data.values():
                    if p.get('Damage From', {}).get(t_n.lower(), 1.0) > 1:
                        weak_mons.append(p['Pokemon'])

                tooltip = f"Weak: {', '.join(weak_mons)}"

                alert = f'''
                <div title="{tooltip}" style="background-color:{bg}; padding:10px; border-radius:5px; border-left: 5px solid {bc}; margin-bottom:10px; cursor: help;">
                    <span style="background-color:{t_i["color"]}; color:white; padding:2px 8px; border-radius:4px; font-size:14px; margin-right:10px;">{t_i["icon"]} {cap_t}</span>
                    <b>{counts["weak"]} Weaknesses</b> {tag}
                </div>
                '''
                st.markdown(alert, unsafe_allow_html=True)

from html import escape

import streamlit as st
from metamatch import config, strategy_data
from metamatch.sprites import get_sprite


def _options(value):
    """Strategy Dex fields can be one value or a list of alternatives: 'Sitrus Berry / Heavy-Duty Boots'."""
    if isinstance(value, (list, tuple)):
        return escape(" / ".join(str(v) for v in value))
    return escape(str(value).strip("[]").replace("'", "").replace(", ", " / "))


def render(get_strat_data_fn, get_usage_data_fn):
    # The format picker above the tabs drives this tab too
    label = config.format_info(st.session_state.get("format_id"))["label"]
    is_champions = config.format_game(st.session_state.get("format_id")) == "champions"
    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption(f"Find {label} sets that run a combination of moves.")
        include_loose = st.toggle("Include loose matches", value=False, help="Search usage stats for 'homemade' combos not yet in the Strategy Dex.")

    master_strat_data = get_strat_data_fn()
    usage_data = get_usage_data_fn()

    if 'all_moves' not in st.session_state:
        with st.spinner("Loading move list..."):
            st.session_state.all_moves = strategy_data.get_all_known_moves(master_strat_data, usage_data)

    move_selection = st.multiselect(
        "Select Moves:",
        options=st.session_state.all_moves,
        placeholder="Type moves to search (e.g. 'Scald', 'Thunder Wave')...",
        key="move_search_select",
        label_visibility="collapsed"
    )

    col_btn, col_info = st.columns([1, 4])
    with col_btn:
        search_clicked = st.button("🚀 Find Sets", key="find_sets_btn", width="stretch")
    with col_info:
        if not search_clicked and not move_selection:
            st.caption("👈 Select moves to start searching.")

    st.markdown("---")

    if search_clicked:
        if move_selection:
            strat_results = [r for r in strategy_data.find_sets_with_moves(move_selection, data=master_strat_data)
                             if label in r.get('formats', [])]
            for r in strat_results:
                r['formats'] = [label]

            usage_results = []
            # Smogon has no Champions analyses yet, so ladder usage is the only source there
            if include_loose or is_champions:
                usage_results = [r for r in strategy_data.find_usage_matches(move_selection, usage_data=usage_data)
                                 if r['format'] == label]

            exact_mons = {r['pokemon'] for r in strat_results}
            filtered_usage = [r for r in usage_results if r['pokemon'] not in exact_mons]

            total_found = len(strat_results) + len(filtered_usage)

            if total_found > 0:
                st.markdown(f"""
                <div style="display:flex; gap:15px; margin-bottom: 20px; align-items: center;">
                    <span style="font-size: 1.2rem; font-weight: bold; color: #fff;">Found {total_found} Matches</span>
                    <span style="background: rgba(0, 212, 255, 0.1); color: #00d4ff; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(0, 212, 255, 0.2); font-size: 0.8rem;">{len(strat_results)} Verified</span>
                    {'<span style="background: rgba(255, 170, 0, 0.1); color: #ffaa00; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(255, 170, 0, 0.2); font-size: 0.8rem;">' + str(len(filtered_usage)) + ' Experimental</span>' if filtered_usage else ''}
                </div>
                """, unsafe_allow_html=True)

                if strat_results:
                    st.markdown("#### 📘 Verified Strategy Sets")
                    for res in strat_results:
                        poke_name = res['pokemon']
                        sprite_url = get_sprite(poke_name) or ""

                        fmt_badges = ""
                        for fmt in res.get('formats', []):
                            color = "#888"
                            if "Champions" in fmt: color = "#f1c40f"
                            elif "OU" in fmt: color = "#e74c3c"
                            elif "UU" in fmt: color = "#3498db"
                            elif "NatDex" in fmt: color = "#9b59b6"
                            fmt_badges += f'<span style="background:{color}; color:white; padding: 1px 6px; border-radius: 3px; font-size: 0.6rem; margin-right: 4px;">{fmt}</span>'

                        moves_html = ""
                        for m in dict.fromkeys(res['moves']):  # dedupe, keep order
                            m_norm = m.lower().replace("-", "").replace(" ", "")
                            sel_norms = [s.lower().replace("-", "").replace(" ", "") for s in move_selection]

                            if m_norm in sel_norms:
                                moves_html += f'<div style="background: rgba(0, 255, 136, 0.15); border: 1px solid rgba(0, 255, 136, 0.4); color: #00ff88; padding: 4px 8px; border-radius: 4px; font-weight: 600;">✅ {m}</div>'
                            else:
                                moves_html += f'<div style="background: rgba(255, 255, 255, 0.05); color: #aaa; padding: 4px 8px; border-radius: 4px;">{m}</div>'

                        st.markdown(f"""
<div class="pokemon-card" style="border: 1px solid rgba(0, 212, 255, 0.15); background: linear-gradient(145deg, rgba(255,255,255,0.03) 0%, rgba(0,0,0,0.2) 100%); margin-bottom: 15px; padding: 0; overflow: hidden;">
<div style="display: flex;">
<div style="width: 120px; background: rgba(0,0,0,0.2); display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 15px; border-right: 1px solid rgba(255,255,255,0.05);">
<img src="{sprite_url}" width="80" style="filter: drop-shadow(0 0 8px rgba(0,0,0,0.6));">
<div style="font-weight: 700; margin-top: 10px; color: #fff; text-align: center; line-height: 1.2;">{poke_name}</div>
<div style="margin-top: 8px;">{fmt_badges}</div>
</div>
<div style="flex-grow: 1; padding: 15px;">
<div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
<div>
<div style="font-size: 0.7rem; color: #00d4ff; text-transform: uppercase; letter-spacing: 1px; font-weight: bold;">Strategy Name</div>
<div style="font-size: 1.1rem; font-weight: 600; color: #e0e0e0;">{res['set_name'].split('(')[0]}</div>
</div>
<div style="text-align: right; font-size: 0.8rem; color: #aaa;">
<div>✨ {_options(res['ability'])}</div>
<div>🎒 {_options(res['item'])}</div>
<div>🧬 {_options(res['nature'])}</div>
</div>
</div>
<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; font-size: 0.85rem;">
{moves_html}
</div>
</div>
</div>
</div>
""", unsafe_allow_html=True)

                if filtered_usage:
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown("""
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                        <h4 style="margin:0; padding:0;">🧪 Experimental Matches</h4>
                        <span style="background: rgba(255, 170, 0, 0.15); border: 1px solid rgba(255, 170, 0, 0.3); color: #ffaa00; font-size: 0.7rem; padding: 2px 6px; border-radius: 4px;">USAGE > 1%</span>
                    </div>
                    """, unsafe_allow_html=True)
                    st.caption("These Pokémon use all selected moves in the meta, but not necessarily on the same set.")

                    cols = st.columns(2)
                    for i, res in enumerate(filtered_usage):
                        with cols[i % 2]:
                            poke_name = res['pokemon']
                            sprite_url = get_sprite(poke_name) or ""
                            fmt = res['format']

                            color = "#444"
                            if "Champions" in fmt: color = "#f1c40f"
                            elif "OU" in fmt: color = "#e74c3c"
                            elif "UU" in fmt: color = "#3498db"
                            elif "NatDex" in fmt: color = "#9b59b6"

                            moves_html = ""
                            for m_name, usage in res['moves'].items():
                                bar_width = min(usage, 100)
                                usage_color = "#00ff88" if usage > 50 else "#ffcc00" if usage > 10 else "#888"

                                moves_html += f"""
<div style="margin-bottom: 8px;">
<div style="display:flex; justify-content:space-between; font-size: 0.85rem; color: #ddd; margin-bottom: 2px;">
<span style="font-weight: 500;">{m_name}</span>
<span style="color:{usage_color}; font-family:monospace; font-weight: bold;">{usage:.1f}%</span>
</div>
<div style="width: 100%; height: 5px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden;">
<div style="width: {bar_width}%; height: 100%; background: {usage_color}; box-shadow: 0 0 5px {usage_color};"></div>
</div>
</div>"""

                            st.markdown(f"""
<div style="background: linear-gradient(180deg, rgba(30,30,30,0.9) 0%, rgba(20,20,20,0.9) 100%); border: 1px solid rgba(255, 170, 0, 0.25); border-left: 4px solid {color}; border-radius: 8px; padding: 16px; display: flex; gap: 16px; transition: transform 0.2s; margin-bottom: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.2);">
<div style="text-align: center; width: 70px; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; padding-top: 5px;">
<img src="{sprite_url}" width="60" style="opacity: 1.0; filter: drop-shadow(0 0 4px rgba(0,0,0,0.5));">
<div style="background:{color}; color:white; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; margin-top: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.3);">{fmt}</div>
</div>
<div style="flex-grow: 1;">
<div style="font-weight: 800; color: #fff; font-size: 1.1rem; margin-bottom: 12px; text-shadow: 0 0 10px rgba(255, 170, 0, 0.2);">{poke_name}</div>
{moves_html}
</div>
</div>
""", unsafe_allow_html=True)
            else:
                st.warning(f"No {label} matches found. Try turning on 'Include loose matches', or pick another format above.")
        else:
            st.error("Please select at least one move.")

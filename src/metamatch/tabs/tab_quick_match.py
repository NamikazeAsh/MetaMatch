import json
import streamlit as st
from metamatch import recommender, config
from metamatch.utils import get_pokemon_sprite


def render(get_strat_data_fn):
    st.markdown("### 🤝 Quick Match")
    st.caption("Don't have a full team? Pick 1-5 Pokémon to find their best partners.")

    tgt_format = st.pills(
        "Competitive Format",
        options=["OU", "UU", "NatDex"],
        default=["OU"],
        selection_mode="multi",
        label_visibility="collapsed"
    )
    fmt_map = {"OU": "gen9ou", "UU": "gen9uu", "NatDex": "gen9natdex"}

    try:
        with open(config.JSON_DIR / "topPoke.json", "r") as f:
            meta_pokes = list(json.load(f).keys())
    except:
        meta_pokes = []

    qm_selection = st.multiselect(
        "Select your core (Max 5):",
        options=meta_pokes,
        max_selections=5,
        placeholder="Search for a Pokémon...",
        key="quick_match_select"
    )

    if qm_selection:
        selected_fmts = [fmt_map.get(f) for f in tgt_format] if tgt_format else ["gen9ou"]
        recs = recommender.get_recommendations(qm_selection, top_n=16, format_id=selected_fmts)

        strat_data = get_strat_data_fn()
        selected_format_labels = tgt_format if tgt_format else ["OU"]

        if recs:
            st.markdown(f"**Top recommended partners for your squad:**")
            max_score = recs[0][1]

            for i in range(0, len(recs), 4):
                cols = st.columns(4)
                batch = recs[i:i+4]
                for j, (name, score, reason) in enumerate(batch):
                    match_pct = int((score / max_score) * 100) if max_score > 0 else 0
                    glow_color = "#00ff88" if match_pct > 80 else "#00d4ff"

                    pokemon_sets = []
                    if name in strat_data:
                        all_sets = strat_data[name].get("sets", {})
                        for set_name, set_info in all_sets.items():
                            for fmt_label in selected_format_labels:
                                if f"({fmt_label})" in set_name:
                                    pokemon_sets.append((set_name, set_info))
                                    break

                    with cols[j]:
                        sprite_url = get_pokemon_sprite(name) or ""

                        sets_html = ""
                        if pokemon_sets:
                            sets_html = '<div style="margin-top: 8px; text-align: left;">'
                            for set_name, set_info in pokemon_sets[:3]:
                                item = set_info.get("item", "")
                                if isinstance(item, list):
                                    item = item[0] if item else ""
                                ability = set_info.get("ability", "")
                                if isinstance(ability, list):
                                    ability = ability[0] if ability else ""

                                if not ability or ability == "None":
                                    ability = ""

                                display_name = set_name.rsplit(" (", 1)[0]

                                if ability:
                                    info_line = f"{item} · {ability}"
                                else:
                                    info_line = item

                                sets_html += f'''
                                <div style="background: rgba(0,0,0,0.25); border-radius: 6px; padding: 6px 10px; margin-top: 6px; border-left: 3px solid {glow_color};">
                                    <div style="font-size: 0.8rem; font-weight: 600; color: #fff;">{display_name}</div>
                                    <div style="font-size: 0.7rem; color: #aaa; margin-top: 3px;">{info_line}</div>
                                </div>'''
                            sets_html += '</div>'
                        else:
                            sets_html = '<div class="qm-sets-container" style="font-size: 0.65rem; color: #666; margin-top: 8px;">No verified sets</div>'

                        sets_wrapper = f'<div class="qm-sets-container">{sets_html}</div>' if pokemon_sets else sets_html

                        st.markdown(f"""
                        <style>
                            .qm-card .qm-sets-container {{
                                max-height: 0;
                                overflow: hidden;
                                opacity: 0;
                                transition: max-height 0.3s ease, opacity 0.3s ease;
                            }}
                            .qm-card:hover .qm-sets-container {{
                                max-height: 300px;
                                opacity: 1;
                            }}
                        </style>
                        <div class="qm-card" style="background: rgba(255, 255, 255, 0.03); border: 1px solid {glow_color}44; border-radius: 12px; padding: 10px; text-align: center; transition: transform 0.2s; margin-bottom: 15px; cursor: pointer;">
                            <img src="{sprite_url}" width="70" style="filter: drop-shadow(0 0 5px rgba(0,0,0,0.5));">
                            <div style="font-weight: 700; font-size: 0.9rem; margin-top: 5px; color: #fff;">{name}</div>
                            <div title="Based on high-ladder weighted usage statistics from Smogon." style="cursor: help; margin-top: 5px; background: rgba(0,0,0,0.3); padding: 2px 8px; border-radius: 15px; display: inline-block; border: 1px solid {glow_color}66;">
                                <span style="color: {glow_color}; font-weight: bold; font-size: 0.8rem;">{match_pct}% Synergy</span>
                            </div>
                            {sets_wrapper}
                        </div>
                        """, unsafe_allow_html=True)
        else:
            st.caption("No specific recommendations found for this combination.")

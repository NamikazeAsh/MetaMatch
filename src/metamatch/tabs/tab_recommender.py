import streamlit as st
from metamatch import recommender, config
from metamatch.utils import get_pokemon_sprite


def render(team_data: dict, pokemon_names: list):
    st.subheader("🤖 Statistical Teammate Recommendations")
    st.caption("Based on real Smogon usage data and teammate correlation matrices.")

    team_fmt = config.team_format(team_data)
    tgt_format_rec = st.pills(
        "Target Format",
        options=[f["label"] for f in config.FORMATS.values()],
        default=[config.FORMATS[team_fmt]["label"]],
        selection_mode="multi",
        key="rec_format_pills"
    )

    selected_fmts_rec = [config.format_by_label(f) for f in tgt_format_rec] if tgt_format_rec else [team_fmt]
    team_roles_rec = [p.get("Roles", []) for p in team_data.values()]
    recs = recommender.get_recommendations(
        pokemon_names,
        format_id=selected_fmts_rec,
        team_roles=team_roles_rec
    )

    if recs:
        rec_cols = st.columns(3)
        max_score = recs[0][1]

        for i, (name, score, reason) in enumerate(recs):
            col = rec_cols[i % 3]
            match_pct = int((score / max_score) * 100)

            glow_color = "#00d4ff"
            if match_pct > 80: glow_color = "#00ff88"
            elif match_pct < 50: glow_color = "#ffaa00"

            with col:
                reason_html = (
                    f'<div style="margin-top: 8px; font-size: 0.7rem; color: #ffd700; '
                    f'background: rgba(255,215,0,0.1); border: 1px solid #ffd70044; '
                    f'border-radius: 10px; padding: 3px 8px; display: inline-block;">'
                    f'{reason}</div>'
                ) if reason else '<div style="height:0;"></div>'
                rec_html = f"""
                <div class="pokemon-card" style="border: 1px solid {glow_color}44; box-shadow: 0 0 15px -5px {glow_color}, inset 0 0 20px -15px {glow_color}; min-height: 180px;">
                    <div style="text-align: center;">
                        <div style="position: relative; display: inline-block;">
                            <div style="position: absolute; width: 60px; height: 60px; background: {glow_color}; filter: blur(30px); opacity: 0.4; z-index: 0; top: 10px; left: 10px;"></div>
                            <img src="{get_pokemon_sprite(name) or ''}" width="100" style="position: relative; z-index: 1; filter: drop-shadow(0 0 5px rgba(0,0,0,0.5)); transition: transform 0.3s;">
                        </div>
                        <div class="poke-name" style="font-size: 1.2rem; margin-top: 10px;">{name}</div>
                        <div style="margin-top: 10px; background: rgba(0,0,0,0.3); padding: 5px 10px; border-radius: 20px; display: inline-block; border: 1px solid {glow_color}66;">
                            <span style="color: {glow_color}; font-weight: 800; font-size: 1.1rem;">{match_pct}%</span> <span style="font-size: 0.8rem; opacity: 0.8;">Synergy</span>
                        </div>
                        {reason_html}
                    </div>
                </div>
                """
                st.markdown(rec_html, unsafe_allow_html=True)
    else:
        st.info("No recommendations available. Try analyzing a different team or update meta data.")

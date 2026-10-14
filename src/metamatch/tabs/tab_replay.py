import pandas as pd
import streamlit as st
from metamatch import replay


def render():
    st.markdown("### 📼 Replay Auditor")
    st.caption("Paste a Pokémon Showdown replay link to receive a tactical breakdown of your battle.")

    replay_url = st.text_input(
        "Replay Link:",
        placeholder="https://replay.pokemonshowdown.com/gen9ou-...",
        key="replay_url_input",
        label_visibility="collapsed"
    )

    col_player, col_analyze = st.columns([2, 1])
    with col_player:
        user_perspective = st.radio(
            "Which player are you?",
            options=["Player 1 (left side)", "Player 2 (right side)"],
            horizontal=True,
            key="replay_perspective"
        )
    with col_analyze:
        analyze_btn = st.button("🔍 Analyze Replay", use_container_width=True, type="primary")

    st.markdown("---")

    if analyze_btn and replay_url:
        user_player = 'p1' if 'Player 1' in user_perspective else 'p2'

        with st.spinner("Fetching and analyzing replay..."):
            replay_data = replay.fetch_replay(replay_url)

            if replay_data:
                summary = replay.generate_summary(replay_data, user_player)

                if 'error' not in summary:
                    st.session_state.replay_summary = summary
                else:
                    st.error(summary['error'])
            else:
                st.error("Could not fetch replay. Check the URL and try again.")

    if 'replay_summary' in st.session_state:
        summary = st.session_state.replay_summary
        user_player = summary['user_player']
        opponent = 'p2' if user_player == 'p1' else 'p1'

        p1_name = summary['players']['p1']
        p2_name = summary['players']['p2']
        user_name = p1_name if user_player == 'p1' else p2_name
        opp_name = p2_name if user_player == 'p1' else p1_name

        winner = summary.get('winner')
        result_text = "WIN" if winner == user_player else "LOSS" if winner else "TIE"
        result_color = "#00ff88" if winner == user_player else "#ff4444" if winner else "#ffaa00"

        st.markdown(f"""
        <div style="background: linear-gradient(135deg, rgba(0,0,0,0.3) 0%, rgba({result_color[1:3]},{result_color[3:5]},{result_color[5:7]},0.1) 100%);
                    border: 1px solid {result_color}44; border-radius: 12px; padding: 20px; margin-bottom: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div style="font-size: 0.8rem; color: #888; text-transform: uppercase; letter-spacing: 1px;">{summary['format']}</div>
                    <div style="font-size: 1.4rem; font-weight: 700; color: #fff; margin-top: 5px;">
                        {user_name} <span style="color: #666;">vs</span> {opp_name}
                    </div>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 2rem; font-weight: 800; color: {result_color}; text-shadow: 0 0 20px {result_color};">{result_text}</div>
                    <div style="font-size: 0.9rem; color: #aaa;">{summary['total_turns']} turns</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        user_alive = summary['final_score'][user_player]
        opp_alive = summary['final_score'][opponent]

        sc1, sc2 = st.columns(2)
        with sc1:
            st.metric("Your Pokémon Remaining", f"{user_alive}/6")
        with sc2:
            st.metric("Opponent's Remaining", f"{opp_alive}/6")

        momentum_data = summary.get('momentum', [])
        if momentum_data and len(momentum_data) > 2:
            st.markdown("---")

            st.markdown("""
            <style>
                [data-testid="column"]:last-child {
                    display: flex;
                    justify-content: flex-end;
                }
            </style>
            """, unsafe_allow_html=True)

            mom_header = st.columns([8, 1])
            with mom_header[0]:
                st.markdown("### 📈 Battle Momentum")
            with mom_header[1]:
                with st.popover("ℹ️"):
                    st.markdown("""
                    **How momentum is calculated:**
                    - **+20** when you KO an opponent
                    - **-10** when you lose a Pokémon
                    - **+1** per 10% damage dealt

                    Higher = winning. Watch for swings where lines cross!
                    """)

            df = pd.DataFrame(momentum_data)
            df = df[df['turn'] > 0]
            if not df.empty:
                df = df.rename(columns={'p1': f"🔵 {user_name}", 'p2': f"🔴 {opp_name}"})
                df = df.set_index('turn')
                st.line_chart(df, use_container_width=True, color=["#00d4ff", "#ff6b6b"])

        hazard_dmg = summary.get('hazard_damage', {}).get(user_player, {})
        if hazard_dmg:
            total_hazard_dmg = sum(hazard_dmg.values())
            st.markdown("---")
            st.markdown("### 🪨 Hazard Damage Taken")

            haz_cols = st.columns(min(len(hazard_dmg), 4))
            for i, (poke, dmg) in enumerate(sorted(hazard_dmg.items(), key=lambda x: -x[1])):
                with haz_cols[i % len(haz_cols)]:
                    dmg_color = "#ff4444" if dmg >= 25 else "#ffaa00" if dmg >= 12 else "#00d4ff"
                    st.markdown(f"""
                    <div style="background: rgba(0,0,0,0.2); border-radius: 8px; padding: 12px; text-align: center; margin-bottom: 8px;">
                        <div style="font-weight: 600; color: #fff; font-size: 0.9rem;">{poke}</div>
                        <div style="font-size: 1.5rem; font-weight: 800; color: {dmg_color}; margin-top: 4px;">{dmg}%</div>
                        <div style="font-size: 0.7rem; color: #888;">hazard chip</div>
                    </div>
                    """, unsafe_allow_html=True)

            st.caption(f"Total hazard damage: **{total_hazard_dmg}%** — Consider Heavy-Duty Boots or prioritizing hazard removal.")

        st.markdown("---")

        blunders = summary.get('blunders', [])
        if blunders:
            st.markdown("### ⚠️ Potential Misplays Detected")

            for blunder in blunders:
                severity_colors = {
                    'critical': '#ff4444',
                    'moderate': '#ffaa00',
                    'minor': '#00d4ff'
                }
                sev_color = severity_colors.get(blunder.severity, '#888')

                st.markdown(f"""
                <div style="background: rgba(0,0,0,0.2); border-left: 4px solid {sev_color};
                            padding: 15px; margin-bottom: 12px; border-radius: 0 8px 8px 0;">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div>
                            <span style="background: {sev_color}22; color: {sev_color}; padding: 2px 8px;
                                         border-radius: 4px; font-size: 0.7rem; font-weight: bold; text-transform: uppercase;">
                                Turn {blunder.turn} • {blunder.severity}
                            </span>
                            <div style="font-size: 1rem; color: #fff; margin-top: 8px; font-weight: 600;">
                                {blunder.description}
                            </div>
                        </div>
                    </div>
                    <div style="margin-top: 10px; padding: 10px; background: rgba(0,255,136,0.05);
                                border: 1px solid rgba(0,255,136,0.2); border-radius: 6px;">
                        <span style="color: #00ff88; font-weight: 600;">💡 Suggestion:</span>
                        <span style="color: #ccc;"> {blunder.suggestion}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✅ No obvious misplays detected! Well played.")

        st.markdown("---")

        st.markdown("### 📊 Final Team States")

        tcol1, tcol2 = st.columns(2)

        with tcol1:
            st.markdown(f"**Your Team ({user_name})**")
            user_team = summary['teams'][user_player]
            for species, data in user_team.items():
                hp = data['hp']
                fainted = data['fainted']
                status = data.get('status', '')

                hp_color = "#00ff88" if hp > 50 else "#ffaa00" if hp > 0 else "#ff4444"
                status_badge = f" <span style='color:#ffaa00;'>({status})</span>" if status else ""
                faint_style = "opacity: 0.4; text-decoration: line-through;" if fainted else ""

                st.markdown(f"""
                <div style="display: flex; align-items: center; gap: 10px; padding: 8px 0; {faint_style}">
                    <span style="font-weight: 600; color: #fff; min-width: 120px;">{species}</span>
                    <div style="flex-grow: 1; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden;">
                        <div style="width: {hp}%; height: 100%; background: {hp_color};"></div>
                    </div>
                    <span style="color: {hp_color}; font-family: monospace; min-width: 40px;">{hp}%</span>
                    {status_badge}
                </div>
                """, unsafe_allow_html=True)

        with tcol2:
            st.markdown(f"**Opponent's Team ({opp_name})**")
            opp_team = summary['teams'][opponent]
            for species, data in opp_team.items():
                hp = data['hp']
                fainted = data['fainted']
                status = data.get('status', '')

                hp_color = "#00ff88" if hp > 50 else "#ffaa00" if hp > 0 else "#ff4444"
                status_badge = f" <span style='color:#ffaa00;'>({status})</span>" if status else ""
                faint_style = "opacity: 0.4; text-decoration: line-through;" if fainted else ""

                st.markdown(f"""
                <div style="display: flex; align-items: center; gap: 10px; padding: 8px 0; {faint_style}">
                    <span style="font-weight: 600; color: #fff; min-width: 120px;">{species}</span>
                    <div style="flex-grow: 1; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden;">
                        <div style="width: {hp}%; height: 100%; background: {hp_color};"></div>
                    </div>
                    <span style="color: {hp_color}; font-family: monospace; min-width: 40px;">{hp}%</span>
                    {status_badge}
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("### Faint Timeline")

        all_faints = []
        for f in summary['faints'].get(user_player, []):
            all_faints.append({
                'turn': f['turn'],
                'species': f['species'],
                'side': 'you',
                'killed_by': f.get('killed_by'),
                'move': f.get('move'),
                'damage': f.get('damage', 0),
                'self_ko': f.get('self_ko', False)
            })
        for f in summary['faints'].get(opponent, []):
            all_faints.append({
                'turn': f['turn'],
                'species': f['species'],
                'side': 'opponent',
                'killed_by': f.get('killed_by'),
                'move': f.get('move'),
                'damage': f.get('damage', 0),
                'self_ko': f.get('self_ko', False)
            })

        all_faints.sort(key=lambda x: x['turn'])

        if all_faints:
            num_cols = min(len(all_faints), 4)
            for i in range(0, len(all_faints), num_cols):
                batch = all_faints[i:i+num_cols]
                cols = st.columns(num_cols)
                for j, f in enumerate(batch):
                    with cols[j]:
                        side_color = "#ff4444" if f['side'] == 'you' else "#00ff88"
                        side_label = "Your" if f['side'] == 'you' else "Opp"

                        killer_info = ""
                        if f.get('self_ko') and f.get('move'):
                            killer_info = f"<div style='font-size: 0.7rem; color: #ffaa00; margin-top: 6px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 6px;'><span style='font-style: italic;'>{f['move']}</span><br/><span style='color: #ffaa00;'>(self-KO)</span></div>"
                        elif f.get('killed_by') and f.get('move'):
                            damage_text = f" ({f['damage']}%)" if f.get('damage') else ""
                            killer_info = f"<div style='font-size: 0.7rem; color: #aaa; margin-top: 6px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 6px;'>by <span style='color: #fff;'>{f['killed_by']}</span><br/><span style='font-style: italic;'>{f['move']}</span><span style='color: #ff6b6b;'>{damage_text}</span></div>"
                        elif f.get('killed_by'):
                            killer_info = f"<div style='font-size: 0.7rem; color: #aaa; margin-top: 6px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 6px;'>by <span style='color: #fff;'>{f['killed_by']}</span></div>"

                        st.markdown(f"""
                        <div style="background: rgba(0,0,0,0.3); border: 1px solid {side_color};
                                    padding: 10px; border-radius: 8px; text-align: center; margin-bottom: 8px;">
                            <div style="font-size: 0.75rem; color: #888; margin-bottom: 4px;">Turn {f['turn']}</div>
                            <div style="font-weight: 600; color: {side_color}; font-size: 0.9rem;">{side_label} {f['species']}</div>
                            {killer_info}
                        </div>
                        """, unsafe_allow_html=True)
        else:
            st.info("No Pokémon fainted during this battle.")

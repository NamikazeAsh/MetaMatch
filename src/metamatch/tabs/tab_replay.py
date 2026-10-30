from html import escape

import pandas as pd
import streamlit as st
from metamatch import replay
from metamatch.replay.protocol import STATUS_DAMAGE


def _faint_cause(battle, f):
    """Short description of what made a Pokémon faint."""
    by = battle.name(f["by"]) if f.get("by") else None
    source, cause = f.get("source"), f["cause"]
    if cause == "move":
        return f"{by}'s {source}" + (f" ({f['damage']}%)" if f.get("damage") else "")
    if cause == "hazard":
        return source
    if cause == "status":
        return STATUS_DAMAGE.get(source, source) + (f" from {by}" if by else "")
    if cause == "weather":
        return source
    if cause == "indirect":
        return f"{by}'s {source}"
    if cause == "self":
        return f"{source} (self inflicted)"
    if cause == "residual":
        return source + (f" from {by}" if by else "")
    if cause == "destiny_bond":
        return f"Destiny Bond from {by}"
    if cause == "perish":
        return "Perish Song"
    if cause == "self_ko":
        return f"{source} (self KO)"
    return "unknown"


def _hp_row(name, hp, status, fainted, note=""):
    hp_color = "#00ff88" if hp > 50 else "#ffaa00" if hp > 0 else "#ff4444"
    status_badge = f" <span style='color:#ffaa00;'>({escape(status)})</span>" if status else ""
    faint_style = "opacity: 0.4; text-decoration: line-through;" if fainted else ""
    hp_text = note or f"{hp}%"
    return f"""
    <div style="display: flex; align-items: center; gap: 10px; padding: 8px 0; {faint_style}">
        <span style="font-weight: 600; color: #fff; min-width: 120px;">{escape(name)}</span>
        <div style="flex-grow: 1; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden;">
            <div style="width: {hp}%; height: 100%; background: {hp_color};"></div>
        </div>
        <span style="color: {hp_color}; font-family: monospace; min-width: 40px;">{hp_text}</span>
        {status_badge}
    </div>
    """


def _team_states(battle, side):
    rows = [_hp_row(m.species, m.hp, m.status, m.fainted) for m in battle.mons[side].values()]
    rows += [_hp_row(species, 100, None, False, "not seen") for species in battle.unrevealed(side)]
    return "".join(rows)


def render():
    st.markdown("### 📼 Replay Auditor")
    st.caption("Paste a Pokémon Showdown replay link to receive a tactical breakdown of your battle.")

    col_link, col_analyze = st.columns([3, 1])
    with col_link:
        replay_url = st.text_input(
            "Replay Link:",
            placeholder="https://replay.pokemonshowdown.com/gen9ou-...",
            key="replay_url_input",
            label_visibility="collapsed"
        )
    with col_analyze:
        analyze_btn = st.button("🔍 Analyze Replay", width="stretch", type="primary")

    if analyze_btn and replay_url:
        with st.spinner("Fetching and analyzing replay..."):
            try:
                _, link_side = replay.parse_replay_link(replay_url)
                st.session_state.replay_analysis = replay.analyze(replay.fetch_replay(replay_url))
                st.session_state.replay_perspective = link_side or "p1"
            except replay.ReplayError as e:
                st.error(str(e))
            except Exception as e:  # a log this parser has never seen; never show a traceback
                print(f"Replay analysis failed: {e}")
                st.error("Something in this replay couldn't be analysed. Try another replay.")

    analysis = st.session_state.get("replay_analysis")
    if not analysis:
        return
    battle = analysis.battle

    # Pick yourself by username; changing it reuses the analysis instead of refetching
    sides = ["p1", "p2"]
    if st.session_state.get("replay_perspective") not in sides:
        st.session_state.replay_perspective = "p1"
    me = st.radio(
        "Which player are you?",
        options=sides,
        format_func=lambda s: battle.players[s],
        horizontal=True,
        key="replay_perspective",
    )
    them = "p2" if me == "p1" else "p1"
    user_name, opp_name = escape(battle.players[me]), escape(battle.players[them])
    st.markdown("---")

    winner = battle.winner
    if winner in (None, "tie"):
        result_text, result_color = ("TIE" if winner == "tie" else "UNFINISHED"), "#ffaa00"
    else:
        result_text, result_color = ("WIN", "#00ff88") if winner == me else ("LOSS", "#ff4444")

    st.markdown(f"""
    <div style="background: linear-gradient(135deg, rgba(0,0,0,0.3) 0%, rgba({int(result_color[1:3], 16)},{int(result_color[3:5], 16)},{int(result_color[5:7], 16)},0.1) 100%);
                border: 1px solid {result_color}44; border-radius: 12px; padding: 20px; margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <div style="font-size: 0.8rem; color: #888; text-transform: uppercase; letter-spacing: 1px;">{escape(battle.format_name)}</div>
                <div style="font-size: 1.4rem; font-weight: 700; color: #fff; margin-top: 5px;">
                    {user_name} <span style="color: #666;">vs</span> {opp_name}
                </div>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 2rem; font-weight: 800; color: {result_color}; text-shadow: 0 0 20px {result_color};">{result_text}</div>
                <div style="font-size: 0.9rem; color: #aaa;">{len(battle.turns)} turns</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    sc1, sc2 = st.columns(2)
    with sc1:
        st.metric("Your Pokémon Remaining", f"{battle.remaining(me)}/{battle.teamsize[me]}")
    with sc2:
        st.metric("Opponent's Remaining", f"{battle.remaining(them)}/{battle.teamsize[them]}")

    if len(battle.health) > 2:
        st.markdown("---")
        head = st.columns([8, 1])
        with head[0]:
            st.markdown("### 📈 Team Health")
        with head[1]:
            with st.popover("ℹ️"):
                st.markdown("Each line is a team's total HP at the end of every turn, as a share of its "
                            "full team. Pokémon that haven't appeared yet count as full health.")
        df = pd.DataFrame(battle.health).set_index("turn")[[me, them]]
        df.columns = [f"🔵 {battle.players[me]}", f"🔴 {battle.players[them]}"]
        st.line_chart(df, width="stretch", color=["#00d4ff", "#ff6b6b"], y_label="Team HP %")

    st.markdown("---")
    flags = analysis.flags[me]
    if flags:
        st.markdown("### ⚠️ Mistakes and Notes")
        st.caption("Mistakes are clear from the log. Notes are worth knowing but not necessarily wrong.")
        for flag in flags:
            color = "#ff4444" if flag.kind == "mistake" else "#00d4ff"
            when = "Lead" if flag.turn == 0 else f"Turn {flag.turn}"
            st.markdown(f"""
            <div style="background: rgba(0,0,0,0.2); border-left: 4px solid {color};
                        padding: 15px; margin-bottom: 12px; border-radius: 0 8px 8px 0;">
                <span style="background: {color}22; color: {color}; padding: 2px 8px;
                             border-radius: 4px; font-size: 0.7rem; font-weight: bold; text-transform: uppercase;">
                    {when} • {flag.kind}
                </span>
                <div style="font-size: 1rem; color: #fff; margin-top: 8px; font-weight: 600;">{escape(flag.title)}</div>
                <div style="color: #ccc; margin-top: 6px;">{escape(flag.detail)}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.success("✅ No clear mistakes found in the log.")

    hazard = {m.species: m.hazard_damage for m in battle.mons[me].values() if m.hazard_damage}
    if hazard:
        st.markdown("---")
        st.markdown("### 🪨 Hazard Damage Taken")
        haz_cols = st.columns(min(len(hazard), 4))
        for i, (poke, dmg) in enumerate(sorted(hazard.items(), key=lambda x: -x[1])):
            with haz_cols[i % len(haz_cols)]:
                dmg_color = "#ff4444" if dmg >= 25 else "#ffaa00" if dmg >= 12 else "#00d4ff"
                st.markdown(f"""
                <div style="background: rgba(0,0,0,0.2); border-radius: 8px; padding: 12px; text-align: center; margin-bottom: 8px;">
                    <div style="font-weight: 600; color: #fff; font-size: 0.9rem;">{escape(poke)}</div>
                    <div style="font-size: 1.5rem; font-weight: 800; color: {dmg_color}; margin-top: 4px;">{dmg}%</div>
                    <div style="font-size: 0.7rem; color: #888;">hazard chip</div>
                </div>
                """, unsafe_allow_html=True)
        st.caption(f"Total hazard damage: **{sum(hazard.values())}%**")

    st.markdown("---")
    st.markdown("### 🔍 Opponent's Revealed Sets")
    rows = []
    for m in battle.mons[them].values():
        rows.append({
            "Pokémon": m.species,
            "Item": m.item or "",
            "Ability": m.ability or "",
            "Tera": m.tera or "",
            "Moves seen": ", ".join(m.moves),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.markdown("---")
    st.markdown("### 📊 Final Team States")
    tcol1, tcol2 = st.columns(2)
    with tcol1:
        st.markdown(f"**Your Team ({user_name})**")
        st.markdown(_team_states(battle, me), unsafe_allow_html=True)
    with tcol2:
        st.markdown(f"**Opponent's Team ({opp_name})**")
        st.markdown(_team_states(battle, them), unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### Faint Timeline")
    if not battle.faints:
        st.info("No Pokémon fainted during this battle.")
        return
    num_cols = min(len(battle.faints), 4)
    for i in range(0, len(battle.faints), num_cols):
        cols = st.columns(num_cols)
        for j, f in enumerate(battle.faints[i:i + num_cols]):
            with cols[j]:
                mine = f["side"] == me
                side_color = "#ff4444" if mine else "#00ff88"
                st.markdown(f"""
                <div style="background: rgba(0,0,0,0.3); border: 1px solid {side_color};
                            padding: 10px; border-radius: 8px; text-align: center; margin-bottom: 8px;">
                    <div style="font-size: 0.75rem; color: #888; margin-bottom: 4px;">Turn {f['turn']}</div>
                    <div style="font-weight: 600; color: {side_color}; font-size: 0.9rem;">{'Your' if mine else 'Opp'} {escape(f['species'])}</div>
                    <div style="font-size: 0.7rem; color: #aaa; margin-top: 6px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 6px;">
                        {escape(_faint_cause(battle, f))}
                    </div>
                </div>
                """, unsafe_allow_html=True)

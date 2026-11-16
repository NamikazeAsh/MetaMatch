import streamlit as st
from metamatch import config, storage
from metamatch.ui import section_header

AVATARS = {"🧪": "🧪", "📜": "📜", "🍳": "🍳"}


def _persist(role, content, name=None, avatar=None):
    """Keeps the conversation with its team, so a refresh or reopening the team brings it back."""
    tid = st.session_state.get("team_id")
    if config.LOCAL_MODE and tid:
        storage.add_chat_message(tid, role, content, name=name, avatar=avatar)


def _ask(question):
    """A suggestion chip was clicked: the next run asks it as if typed."""
    st.session_state.chat_prefill = question


def _chips(questions, key):
    """Clickable follow up questions the engine answers exactly."""
    with st.container(horizontal=True, gap="small"):
        for i, q in enumerate(questions):
            st.button(q, key=f"chip_{key}_{i}", on_click=_ask, args=(q,), icon=":material/subdirectory_arrow_right:")


def _show(content, placeholder=None, chips_key=None):
    """An answer: the voiced part as text, any suggested questions as chips (only when chips_key is given, so only
    the latest answer offers them), and the exact engine result in a collapsed dropdown under it."""
    from metamatch.agents.grounded import FACTS_MARK
    from metamatch.agents.suggest import split
    target = placeholder.container() if placeholder is not None else st.container()
    spoken, _, facts = content.partition(FACTS_MARK)
    spoken, questions = split(spoken)
    with target:
        st.markdown(spoken)
        if questions and chips_key is not None:
            _chips(questions, chips_key)
        if facts.strip():
            with st.expander("Engine facts and sources", expanded=False):
                st.markdown(facts)


def _dialogue_state(manager):
    """This team's conversation state, rebuilt from the stored turns when the chat was reopened in a new session."""
    tid = st.session_state.get("team_id")
    held = st.session_state.get("chat_state")
    if not held or held.get("team") != tid:
        held = {"team": tid, "state": manager.replay(st.session_state.chat_messages, st.session_state.analysis['team'])}
        st.session_state.chat_state = held
    return held


def help_cards(team):
    """[(coach, focus, icon, [example questions])] for the help panel. Member questions use this team's own
    Pokemon, so every example routes to an engine answer (tests/test_packet.py checks this)."""
    names = [p["Pokemon"] for p in (team or {}).values()] or ["Kingambit"]
    first, last = names[0], names[-1]
    return [
        ("Professor Oak", "Matchups and game plan", ":material/menu_book:",
         ["How do I beat Kingambit?", "Who can switch into Raging Bolt?", "How do I play against rain?",
          "What should I lead?", "What's my win condition?", "Is my team good?"]),
        ("Clemont", "Speed and mechanics", ":material/bolt:",
         [f"What is my {first} weak to?", "What am I weak to?", "Walk me through my speed tiers",
          "Does Mold Breaker ignore Levitate?", "How do I use weather on my team?"]),
        ("Brock", "Sets and building", ":material/construction:",
         ["What does Raging Bolt usually run?", "Specs or Band on Dragapult?", f"What should I replace {last} with?",
          "What did the audit flag?"]),
    ]


def _help(team):
    """Three coach cards with example questions that ask themselves when clicked."""
    st.caption("Every answer is worked out by the engine (the damage calculator, the type chart and this month's "
               "ladder data); the coaches only say it. Exact numbers and sources sit in the dropdown under each answer. "
               "Follow ups work too: \"what about Gholdengo?\", \"what if it's Scarf?\", \"why?\".")
    for col, (coach, focus, icon, questions) in zip(st.columns(3), help_cards(team)):
        with col, st.container(border=True, height="stretch"):
            st.markdown(f"{icon} **{coach}**  \n:gray[{focus}]")
            for i, q in enumerate(questions):
                st.button(q, key=f"help_{coach}_{i}", on_click=_ask, args=(q,), type="tertiary")


def _clear():
    tid = st.session_state.get("team_id")
    if config.LOCAL_MODE and tid:
        storage.clear_chat(tid)
    st.session_state.chat_messages = []
    st.session_state.chat_state = None


def render():
    section_header("Ask anything", "Ask the Coach")
    st.caption("Ask about counters, speed, damage or strategy. Answers use this month's ladder data and the real damage calculator.")
    try:
        from metamatch.rag import store
        if store.index_stale():
            st.caption(f"The strategy references were built for {store.index_info().get('stats_month') or 'older'} stats. "
                       "Run `python scripts/update_meta.py --rebuild-index` to refresh them.")
    except Exception:  # the RAG stack is optional; the chat works without it
        pass

    chat_container = st.container()

    with chat_container:
        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = []

        last = len(st.session_state.chat_messages) - 1
        for i, msg in enumerate(st.session_state.chat_messages):
            display_name = msg.get("name", msg["role"])
            with st.chat_message(display_name, avatar=msg.get("avatar")):
                if msg["role"] == "assistant" and "name" in msg:
                    st.markdown(f"**{msg['name']}**")
                _show(msg["content"], chips_key=i if i == last else None)

    team = st.session_state.analysis['team']
    if st.session_state.chat_messages:
        left, right = st.columns([5, 1], vertical_alignment="center")
        with left:
            with st.expander("What you can ask", expanded=False):
                _help(team)
        with right:
            st.button("Clear chat", on_click=_clear, width="stretch", icon=":material/delete_sweep:")
    help_slot = st.empty()
    if not st.session_state.chat_messages:
        with help_slot.container():
            _help(team)

    typed = st.chat_input("How do I beat Kingambit?")
    if prompt := (typed or st.session_state.pop("chat_prefill", None)):
        help_slot.empty()   # the first question replaces the empty state's cards
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)

        with chat_container:
            from metamatch.agents import AgentManager
            from metamatch.agents.grounded import FACTS_MARK
            from metamatch.agents.suggest import split
            manager = AgentManager()
            held = _dialogue_state(manager)
            agent_name, avatar, full_response, turn = "MetaMatch", "🤖", "", None
            try:
                turn = manager.prepare(prompt, team, held["state"])
                agent_name = turn.persona
                avatar = next((a for mark, a in AVATARS.items() if mark in agent_name), "🤖")
            except Exception as e:
                print(f"Chat planning failed: {e}")

            with st.chat_message(agent_name, avatar=avatar):
                st.markdown(f"**{agent_name}**")
                if turn is not None and turn.rewritten:
                    st.caption(f"Reading this as: {turn.text}")
                response_placeholder = st.empty()
                # Answers are checked before they show, so say something is happening meanwhile
                response_placeholder.caption(f"{agent_name.rsplit(' ', 1)[0]} is thinking...")
                try:
                    if turn is None:
                        raise RuntimeError("the question couldn't be planned")
                    for content in manager.respond(turn, team, st.session_state.analysis['weakness'], held["state"]):
                        full_response += content
                        response_placeholder.markdown(split(full_response.partition(FACTS_MARK)[0])[0] + "▌")
                except Exception as e:
                    print(f"Chat answer failed: {e}")
                    response_placeholder.error(f"Something went wrong answering that ({e}). Nothing was saved; try again.")
                    return
                _show(full_response, response_placeholder, chips_key=len(st.session_state.chat_messages) + 1)

        # Only a completed exchange is kept, so a failure never leaves a question without its answer
        held["state"] = manager.remember(turn, held["state"])
        st.session_state.chat_messages += [{"role": "user", "content": prompt},
                                           {"role": "assistant", "name": agent_name, "avatar": avatar, "content": full_response}]
        _persist("user", prompt)
        _persist("assistant", full_response, name=agent_name, avatar=avatar)

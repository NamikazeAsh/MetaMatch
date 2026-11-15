import streamlit as st
from metamatch import config, storage
from metamatch.ui import section_header

AVATARS = {"🧪": "🧪", "📜": "📜", "🍳": "🍳"}


def _persist(role, content, name=None, avatar=None):
    """Keeps the conversation with its team, so a refresh or reopening the team brings it back."""
    tid = st.session_state.get("team_id")
    if config.LOCAL_MODE and tid:
        storage.add_chat_message(tid, role, content, name=name, avatar=avatar)


def _show(content, placeholder=None):
    """An answer: the voiced part as text, the exact engine result in a collapsed dropdown under it."""
    from metamatch.agents.grounded import FACTS_MARK
    target = placeholder.container() if placeholder is not None else st.container()
    spoken, _, facts = content.partition(FACTS_MARK)
    with target:
        st.markdown(spoken)
        if facts.strip():
            with st.expander("Engine facts", expanded=False):
                st.markdown(facts)


def _dialogue_state(manager):
    """This team's conversation state, rebuilt from the stored turns when the chat was reopened in a new session."""
    tid = st.session_state.get("team_id")
    held = st.session_state.get("chat_state")
    if not held or held.get("team") != tid:
        held = {"team": tid, "state": manager.replay(st.session_state.chat_messages, st.session_state.analysis['team'])}
        st.session_state.chat_state = held
    return held


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

        for msg in st.session_state.chat_messages:
            display_name = msg.get("name", msg["role"])
            with st.chat_message(display_name, avatar=msg.get("avatar")):
                if msg["role"] == "assistant" and "name" in msg:
                    st.markdown(f"**{msg['name']}**")
                _show(msg["content"])

    left, right = st.columns([5, 1])
    with left:
        with st.expander("💡 How to use the AI Coach efficiently", expanded=False):
            st.markdown("""
            **Meet your Coaching Staff:**

            🧪 **Clemont** (Mechanics Engine)
            *Ask him about math, specific interactions, and speed tiers.*
            *   "Is Rotom-Wash weak to Ground?"
            *   "Who is faster: Dragapult or Zamazenta?"

            📜 **Professor Oak** (Strategy Mentor)
            *Ask him about win conditions, game plans, and high-level concepts.*
            *   "How do I beat Stall teams?"
            *   "What is the best lead for this team?"

            🍳 **Brock** (Team Builder)
            *Ask him about sets, items, and meta usage stats.*
            *   "What is the most popular item for Great Tusk?"
            *   "Is this moveset good?"

            Follow ups work too: "what about Gholdengo?", "what if it's Scarf?", "why?".
            """)
    with right:
        if st.session_state.chat_messages:
            st.button("Clear chat", on_click=_clear, use_container_width=True)

    if prompt := st.chat_input("How do I beat Kingambit?"):
        team = st.session_state.analysis['team']
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)

        with chat_container:
            from metamatch.agents import AgentManager
            from metamatch.agents.grounded import FACTS_MARK
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
                    for content in manager.respond(turn, team, st.session_state.analysis['weakness']):
                        full_response += content
                        response_placeholder.markdown(full_response.partition(FACTS_MARK)[0] + "▌")
                except Exception as e:
                    print(f"Chat answer failed: {e}")
                    response_placeholder.error(f"Something went wrong answering that ({e}). Nothing was saved; try again.")
                    return
                _show(full_response, response_placeholder)

        # Only a completed exchange is kept, so a failure never leaves a question without its answer
        held["state"] = manager.remember(turn, held["state"])
        st.session_state.chat_messages += [{"role": "user", "content": prompt},
                                           {"role": "assistant", "name": agent_name, "avatar": avatar, "content": full_response}]
        _persist("user", prompt)
        _persist("assistant", full_response, name=agent_name, avatar=avatar)

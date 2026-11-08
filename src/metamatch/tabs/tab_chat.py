import streamlit as st
from metamatch import config, storage
from metamatch.suggestions import get_chat_response
from metamatch.ui import section_header


def _persist(role, content, name=None, avatar=None):
    """Keeps the conversation with its team, so a refresh or reopening the team brings it back."""
    tid = st.session_state.get("team_id")
    if config.LOCAL_MODE and tid:
        storage.add_chat_message(tid, role, content, name=name, avatar=avatar)


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
                st.markdown(msg["content"])

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
        """)

    if prompt := st.chat_input("How do I beat Kingambit?"):
        history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.chat_messages]
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        _persist("user", prompt)
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)

        with chat_container:
            from metamatch.agents import AgentManager
            manager = AgentManager()
            agent_name = manager.get_active_agent_name(prompt, st.session_state.analysis['team'])

            avatar = "🤖"
            if "🧪" in agent_name: avatar = "🧪"
            elif "📜" in agent_name: avatar = "📜"
            elif "🍳" in agent_name: avatar = "🍳"

            with st.chat_message(agent_name, avatar=avatar):
                st.markdown(f"**{agent_name}**")
                response_placeholder = st.empty()
                full_response = ""

                try:
                    stream = get_chat_response(
                        prompt,
                        st.session_state.analysis['team'],
                        st.session_state.analysis['weakness'],
                        history
                    )

                    for content in stream:
                        full_response += content
                        response_placeholder.markdown(full_response + "▌")
                except Exception as e:
                    full_response += f"\n\n⚠️ LLM request failed: {e}"

                response_placeholder.markdown(full_response)

        st.session_state.chat_messages.append({
            "role": "assistant",
            "name": agent_name,
            "avatar": avatar,
            "content": full_response
        })
        _persist("assistant", full_response, name=agent_name, avatar=avatar)

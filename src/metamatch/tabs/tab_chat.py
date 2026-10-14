import streamlit as st
from metamatch.suggestions import get_chat_response


def render():
    st.subheader("💬 Ask the Coach (Powered by RAG)")
    st.caption("Ask specific questions about counters, mechanics, or strategy. The AI uses Smogon data to answer.")

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
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)

        with chat_container:
            from metamatch.agents import AgentManager
            manager = AgentManager()
            agent_name = manager.get_active_agent_name(prompt)

            avatar = "🤖"
            if "🧪" in agent_name: avatar = "🧪"
            elif "📜" in agent_name: avatar = "📜"
            elif "🍳" in agent_name: avatar = "🍳"

            with st.chat_message(agent_name, avatar=avatar):
                st.markdown(f"**{agent_name}**")
                response_placeholder = st.empty()
                full_response = ""

                stream = get_chat_response(
                    prompt,
                    st.session_state.analysis['team'],
                    st.session_state.analysis['weakness']
                )

                for chunk in stream:
                    content = chunk.choices[0].delta.content or ""
                    full_response += content
                    response_placeholder.markdown(full_response + "▌")

                response_placeholder.markdown(full_response)

        st.session_state.chat_messages.append({
            "role": "assistant",
            "name": agent_name,
            "avatar": avatar,
            "content": full_response
        })

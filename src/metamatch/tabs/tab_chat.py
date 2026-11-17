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
            _chip_row(questions, f"answer_{chips_key}")
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
    """[(coach, focus, icon, how to ask him, [example questions])] for the help panel. Member questions use this
    team's own Pokemon, so every example routes to an engine answer (tests/test_packet.py checks this)."""
    names = [p["Pokemon"] for p in (team or {}).values()] or ["Kingambit"]
    first, last = names[0], names[-1]
    foe = "Dragapult" if first == "Iron Valiant" else "Iron Valiant"
    return [
        ("Professor Oak", "Matchups and game plan", ":material/menu_book:",
         "Name an opposing Pokemon or a team style, or ask about your own plan. He checks your team one on one "
         "against their usual ladder sets.",
         ["How do I beat Kingambit?", "How do I play against rain?", "What's my win condition?"]),
        ("Clemont", "Speed, types and mechanics", ":material/bolt:",
         "Say \"my\" for your Pokemon and name the one you're facing. He works it out from real Speed stats, the type "
         "chart and Showdown's rules.",
         [f"Does my {first} outspeed {foe}?", f"What is my {first} weak to?", "Does Mold Breaker ignore Levitate?"]),
        ("Brock", "Sets and building", ":material/construction:",
         "Ask what a Pokemon usually runs, which of two options to pick, or what to change. He answers from this "
         "month's ladder usage.",
         ["What does Raging Bolt usually run?", "Specs or Band on Dragapult?", f"What should I replace {last} with?"]),
    ]


HELP_CSS = """<style>
.st-key-help_cards [data-testid="stVerticalBlockBorderWrapper"] { padding: 4px 2px; }
.st-key-help_cards .mm-coach { font-weight: 800; font-size: 1.02rem; color: #fff; display: flex; gap: 8px; align-items: center; }
.st-key-help_cards .mm-focus { font-size: 0.7rem; font-weight: 800; letter-spacing: 1.6px; text-transform: uppercase;
  color: #00d4ff; margin-top: 2px; }
.st-key-help_cards .mm-how { font-size: 0.86rem; color: #aab3c5; line-height: 1.45; margin: 8px 0 4px; }
.st-key-help_cards .mm-try { font-size: 0.68rem; font-weight: 700; letter-spacing: 1.4px; text-transform: uppercase;
  color: #6f7a90; margin-top: 6px; }
[class*="st-key-chiprow"] .stButton { max-width: 100%; }
[class*="st-key-chiprow"] .stButton > button { width: auto !important; max-width: 100% !important; transform: none !important;
  border-radius: 16px !important; height: auto !important; text-align: left !important;
  padding: 5px 14px !important; min-height: 0 !important; font-weight: 500 !important; font-size: 0.85rem !important;
  background: rgba(0, 212, 255, 0.06) !important; border: 1px solid rgba(0, 212, 255, 0.35) !important; color: #cfefff !important; }
[class*="st-key-chiprow"] .stButton > button p { white-space: normal !important; overflow-wrap: anywhere; line-height: 1.3; }
[class*="st-key-chiprow"] .stButton > button:hover { background: rgba(0, 212, 255, 0.16) !important; border-color: #00d4ff !important;
  box-shadow: 0 0 14px rgba(0, 212, 255, 0.25) !important; }
.mm-loader { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; padding: 64px 16px;
  border: 1px solid #2a3142; border-radius: 14px; background: rgba(26, 32, 48, 0.55); text-align: center; }
.mm-loader-logo { width: 72px; height: 72px; background: url("/app/static/logo_spinner.png") center / contain no-repeat;
  animation: mm-chat-spin 1.1s linear infinite; filter: drop-shadow(0 0 12px rgba(0, 212, 255, .45)); }
.mm-loader-t { font-weight: 800; font-size: 1.15rem; color: #fff; }
.mm-loader-c { font-size: 0.88rem; color: #aab3c5; max-width: 46ch; }
@keyframes mm-chat-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .mm-loader-logo { animation: mm-chat-pulse 1.6s ease-in-out infinite; } }
@keyframes mm-chat-pulse { 50% { opacity: .45; } }
</style>"""

LOADER = ('<div class="mm-loader"><div class="mm-loader-logo"></div><div class="mm-loader-t">Warming up the coaches</div>'
          '<div class="mm-loader-c">Loading the search model and the strategy library. This takes about 20 seconds '
          'the first time the app starts, then the chat opens on its own.</div></div>')


def _warm_up():
    """The first question after a restart used to wait about 25 s for torch, the embedding model and the index.
    Load them here behind a loading screen instead, then the chat appears; later visits skip straight past."""
    try:
        from metamatch.rag import store
    except Exception:   # the RAG stack is optional; the chat works without it
        return
    if store.is_warm():
        return
    slot = st.empty()
    slot.html(LOADER)
    try:
        store.warm()
        from metamatch.agents import AgentManager
        AgentManager()
    except Exception as e:
        print(f"Chat warm up failed: {e}")
    slot.empty()


def _chip_row(questions, key):
    """Questions as pill buttons that wrap across the row and ask themselves when clicked."""
    with st.container(horizontal=True, gap="small", key=f"chiprow_{key}"):
        for i, q in enumerate(questions):
            st.button(q, key=f"chip_{key}_{i}", on_click=_ask, args=(q,))


def _help(team):
    """Three coach cards: what each one answers, how to ask him, and example questions to click."""
    from html import escape
    with st.container(key="help_cards"):
        for col, (coach, focus, icon, how, questions) in zip(st.columns(3, gap="medium"), help_cards(team)):
            with col, st.container(border=True, height="stretch", gap="small"):
                st.markdown(f"{icon} **{coach}**")
                st.html(f'<div class="mm-focus">{escape(focus)}</div><div class="mm-how">{escape(how)}</div>'
                        '<div class="mm-try">Try</div>')
                _chip_row(questions, f"help_{coach.split()[-1].lower()}")
        st.caption("Follow ups work too: \"what about Gholdengo?\", \"what if it's Scarf?\", \"why?\". Every answer is "
                   "worked out by the engine and the coaches only say it; exact numbers and sources sit in the dropdown "
                   "under each answer.")


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
    st.html(HELP_CSS)
    _warm_up()

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

# Plan: 4.1 Split app.py into Tab Modules

## Context
`app.py` is ~1407 lines covering CSS, session state, sidebar, pre-analysis tools, and 8 post-analysis tabs. It's hard to navigate and adding features (e.g. new tabs, UI changes) requires scrolling through unrelated code. The goal is to extract each tab's `with tab_X:` block into `src/metamatch/tabs/{name}.py` exposing a `render(...)` function, leaving `app.py` as a thin orchestrator (~300 lines).

---

## File Structure After Refactor

```
src/metamatch/
    tabs/
        __init__.py           (empty)
        tab_chat.py           render(team_data, weakness)
        tab_overview.py       render(team_data, weakness, type_map, covered_count)
        tab_suggestions.py    render(suggestions)
        tab_threats.py        render(suggestions)
        tab_guide.py          render(guide)
        tab_rec.py            render(team_data)
        tab_matrix.py         render(team_data, type_map)
        tab_speed.py          render(team_data)
        tool_quick_match.py   render(get_master_strategy_data)
        tool_move_search.py   render(get_usage_data)
        tool_replay.py        render()
    app.py                    (orchestrator, ~300 lines)
    utils.py                  (gains get_pokemon_sprite + extract_pokemon_names)
```

---

## Helper Function Moves

**Move to `utils.py`** (already a utility module, no circular risk):
- `get_pokemon_sprite(name)` — currently line 123–134 of app.py. Used in Quick Match and Recommendations tabs. Logically a PokeAPI fetch utility.
- `extract_pokemon_names(text)` — currently line 109–121 of app.py. Used in sidebar AND tool tabs. Moving to utils.py lets both app.py and tab modules import it cleanly.

**Stay in `app.py`** (Streamlit-specific cache wrappers, used in sidebar/app logic):
- `get_cached_teams()` — sidebar only
- `get_master_strategy_data()` — passed as parameter to `tool_quick_match.render()` and `tab_rec.render()`
- `get_usage_data()` — passed as parameter to `tool_move_search.render()`

This avoids circular imports entirely: tab modules never import from app.py.

---

## Render Function Signatures

| Module | Signature | Variables read |
|---|---|---|
| `tab_chat.py` | `render(team_data, weakness)` | `st.session_state.chat_messages` |
| `tab_overview.py` | `render(team_data, weakness, type_map, covered_count)` | — |
| `tab_suggestions.py` | `render(suggestions)` | — |
| `tab_threats.py` | `render(suggestions)` | — |
| `tab_guide.py` | `render(guide)` | — |
| `tab_rec.py` | `render(team_data, get_master_strategy_data)` | `st.session_state.pokemon_names` |
| `tab_matrix.py` | `render(team_data, type_map)` | — |
| `tab_speed.py` | `render(team_data)` | — |
| `tool_quick_match.py` | `render(get_master_strategy_data)` | — |
| `tool_move_search.py` | `render(get_usage_data)` | `st.session_state.all_moves` (initialized inside render) |
| `tool_replay.py` | `render()` | `st.session_state.replay_summary` |

---

## What Stays in app.py

- All imports
- `st.set_page_config()`
- Global CSS block (lines 42–106)
- Session state initializations (lines 141–148)
- `get_cached_teams()`, `get_master_strategy_data()`, `get_usage_data()`
- Sidebar (lines 151–293) — tightly coupled with session state mutation; not a tab
- Logo section (lines 303–309)
- `type_map` dict definition (line 923 area)
- Metrics dashboard and squad section (lines 935–1043) — not tabs
- Pre-analysis tab creation + dispatch (calls tool_*.render())
- Post-analysis tab creation + dispatch (calls tab_*.render())

---

## Execution Order (least risky first)

1. Add `get_pokemon_sprite` and `extract_pokemon_names` to `utils.py`; update their call sites in `app.py` to import from utils
2. Create `src/metamatch/tabs/__init__.py`
3. Extract simple stateless tabs: `tab_speed.py`, `tab_guide.py`, `tab_threats.py`, `tab_suggestions.py`
4. Extract `tab_overview.py` (reads type_map + covered_count)
5. Extract `tab_matrix.py` (reads type_map)
6. Extract `tab_rec.py` (role weighting, format pills, sprite fetching)
7. Extract `tab_chat.py` (streaming, AgentManager, chat history — most complex)
8. Extract pre-analysis: `tool_replay.py`, `tool_move_search.py`, `tool_quick_match.py`
9. Clean up app.py — remove extracted code, verify ~300 lines remain

After each step: run `streamlit run src/metamatch/app.py` and navigate to the affected tab to verify nothing broke.

---

## Critical Files

- `src/metamatch/app.py` — source of all extractions (lines 1–1407)
- `src/metamatch/utils.py` — gains 2 helper functions
- `src/metamatch/tabs/` — new directory (11 new files)

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Circular imports | Tab modules never import from app.py; callables passed as params instead |
| `@st.cache_resource` moving modules | `get_master_strategy_data` / `get_usage_data` stay in app.py; cache identity preserved |
| Local variables leaking | Each render function is self-contained; local pills/selectors defined inside render |
| `type_map` missing in a tab | Explicitly passed as parameter to every tab that uses it (tab_overview, tab_matrix) |
| `st.session_state.all_moves` init | Moved inside `tool_move_search.render()` — initializes on first call |

---

## Verification

- Run `streamlit run src/metamatch/app.py` after each extraction step
- Submit a team → navigate all 8 analysis tabs, verify content renders
- Use Quick Match, Move Search, Replay Auditor — verify pre-analysis tools work
- Type a chat message → verify streaming response still works
- Check recommendations tab → verify format pills + role badge still render

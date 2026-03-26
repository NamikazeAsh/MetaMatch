# MetaMatch Improvement Roadmap

## Context

MetaMatch has a solid foundation — good architecture, real data grounding, and clean separation of concerns. But the AI/ML layer is underperforming relative to the data available: agents are missing critical context in their prompts, the RAG retrieval passes irrelevant chunks to the LLM, the flagship `get_suggestions()` function is essentially ungrounded LLM hallucination, and core Gen 9 mechanics (Tera type, damage numbers) are absent. The result is a system that *looks* sophisticated but produces surface-level or occasionally wrong advice.

The plan below fixes the highest-impact gaps first, then adds mechanical depth, then expands coverage, and finally addresses structural debt.

---

## Phase 1 — Core AI Quality ✅ DONE (tested 23/23)

These five changes are independent, additive, and directly fix why the LLM gives bad advice.

### 1.1 Enrich Agent Prompts with Full Set Context

**Problem:** `CoachAgent` and `AuditorAgent` build their team string with only `Pokemon @ Item | Moves`. Nature, EVs, ability, Tera Type, roles, and speed are already on the pokemon dict but never forwarded to the LLM.

**Fix:** Replace the team-string construction in both agents to include all fields:
```
{name} @ {item} | Ability: {ability} | Tera: {tera} | Nature: {nature} | EVs: {evs} | Roles: {roles} | Speed: {speed} | Moves: {moves}
```

**Files:**
- `src/metamatch/agents/coach.py` — `CoachAgent.run()`, team_str loop
- `src/metamatch/agents/auditor.py` — `AuditorAgent.run()`, audit_str loop

**Reference pattern:** `suggestions.py` lines 46–57 already serializes sets correctly — copy that approach.

---

### 1.2 Add Few-Shot Output Examples to Prompts

**Problem:** `llama3.2:3b` frequently drifts from the expected JSON structure. The 3-retry loop in `get_suggestions()` is a symptom. Agents also inconsistently produce JSON vs prose.

**Fix:**
- In `get_suggestions()` and `get_team_guide()`: insert a 1-shot example of the exact JSON shape *inside* the prompt, between the instruction block and `Team Data:`.
- In all three agents' system prompts: add `Respond in plain prose only. No JSON. Be concise: 3–5 sentences.`

**Files:**
- `src/metamatch/suggestions.py` — `get_suggestions()`, `get_team_guide()`
- `src/metamatch/agents/coach.py`, `tactician.py`, `auditor.py` — system prompts

---

### 1.3 Router Confidence Threshold

**Problem:** `SemanticRouter.route_query()` always dispatches to the max-score route, even at 0.35 confidence (barely above noise). Off-topic or vague queries silently route to the wrong agent.

**Fix:** Add a `CONFIDENCE_THRESHOLD = 0.45` guard in `route_query()`. Below threshold, return `("fallback", score)`. In `AgentManager.get_response()`, handle the `"fallback"` route by streaming a clarification prompt: *"Could you be more specific? Are you asking about mechanics, strategy, or team building?"*

**Files:**
- `src/metamatch/agents/router.py` — `route_query()` line ~68
- `src/metamatch/agents/manager.py` — `get_response()` line ~21

---

### 1.4 RAG Distance Threshold

**Problem:** `query_strategies()` always returns `n_results` chunks regardless of relevance. ChromaDB L2 distances > 1.0 indicate near-orthogonal (irrelevant) results — these currently get passed to the LLM as context.

**Fix:** Add a `max_distance=1.0` parameter to `query_strategies()`. Filter out hits beyond this threshold before returning. Agents already null-check `if rag_hits:` so no downstream changes needed.

**Files:**
- `src/metamatch/rag/store.py` — `query_strategies()` lines ~81–105

---

### 1.5 Ground `get_suggestions()` with Smogon Usage Data ✅ Extended

**Problem:** `get_suggestions()` sends team data + a 60-Pokemon meta list. The LLM has no constraints and can recommend illegal, niche, or suboptimal items/moves (e.g. Sucker Punch on Garchomp).

**Fix (3 grounding layers):**
1. `auditor.audit_team(team)` — injects top usage items/moves per Pokemon as `### USAGE CONSTRAINTS`.
2. `load_strategy_data()` — injects all verified Smogon sets per Pokemon as `### VERIFIED SMOGON SETS`.
3. `_build_grounding_context()` — builds an explicit `### ALLOWED MOVES/ITEMS` whitelist (union of verified set moves + top usage moves). Constraint changed from *"build on this data"* to *"YOU MUST NOT suggest any move or item not present in these lists"*.

**Files:**
- `src/metamatch/suggestions.py` — `_build_grounding_context()` helper + updated prompt

---

## Phase 2 — Mechanical Depth & Tera Integration (5–8 hours)

### 2.1 Tera Type Role Detection

**Problem:** `team.py` parses Tera Type (line 52) and stores it, but `detectRole()` never reads it. Tera is absent from every agent prompt despite being the defining Gen 9 mechanic.

**Fix:** In `detectRole()`, after existing role assignment:
- If Tera Type flips a weakness to resistance/immunity (check via `damageRelations([tera_type])` vs current `Damage From`) → add `"Defensive Tera"` role.
- If Tera Type matches a STAB move + high offensive EVs → add `"Offensive Tera"` role.
- If Tera Type is Ghost → add `"Ghost Tera (Normal/Fighting immunity)"`.

Tera Type will also flow automatically into agent prompts once Phase 1.1 is done.

**Files:**
- `src/metamatch/team.py` — `detectRole()` line ~136; `damageRelations()` already available in scope

---

### 2.2 Damage Estimation in Tactician

**Problem:** The Tactician only says "X is weak to Y." Users expect "X's Y move deals ~65–80% to your Z." This is the most requested mechanic in competitive analysis.

**Fix:** Add `estimate_damage(attacker, move, defender) -> (low_pct, high_pct)` to `logic_engine.py` using the Gen 9 damage formula. Scope to: base power × STAB × type effectiveness × attacker offensive stat / defender defensive stat. Assume standard EV spreads for unknown opponents (252 offensive / 252 defensive). Return a `(min_roll%, max_roll%)` range. Skip burn/weather modifiers for now (edge case, Phase 3+).

In `analyze_matchup()`, for each super-effective move found, append: `"[KO potential: ~X–Y% vs 252 HP opponent]"`.

**Files:**
- `src/metamatch/logic_engine.py` — add `estimate_damage()`, extend `analyze_matchup()`
- `src/metamatch/agents/tactician.py` — no changes needed; receives enriched output from `generate_mechanics_report()`

---

### 2.3 Multi-Format Auditor

**Problem:** `auditor.py` hardcodes `gen9ou-1825.json`. UU/NatDex players get false positives because their items/moves appear at low rates in OU data.

**Fix:** Add optional `format_id` parameter to `audit_team()`, defaulting to `"gen9ou"`. Mirror the `file_map` dict already in `recommender.py`. The format is already selectable in the UI (the `tgt_format_rec` pill); write it to `st.session_state.active_format` on team submit and pass it to both `auditor.audit_team()` call sites in `app.py`.

**Files:**
- `src/metamatch/auditor.py` — `audit_team()` signature + file loading
- `src/metamatch/app.py` — 2 call sites; add `active_format` to session state

---

## Phase 3 — Recommender Intelligence & RAG Coverage (5–6 hours)

### 3.1 Role-Weighted Recommender with Explanations ✅ DONE

**Problem:** `recommender.get_recommendations()` sums correlation scores equally, ignoring whether the team has 3 sweepers and zero hazard setters. Returned tuples `(name, score)` give users no reason to pick a recommendation.

**Fix:**
- Accept `team_roles: list[set]` parameter (current team's role sets).
- Identify missing roles: if no Pokemon has `"Hazard Setter"` in roles, boost candidates whose `strategies_combined.json` set includes Stealth Rock/Spikes by ×1.2.
- Return `(name, score, reason)` where reason = `"Fills missing: Hazard Setter, Pivot"`.
- Display `reason` on the recommendation card in `app.py` tab_rec.

**Files:**
- `src/metamatch/recommender.py` — `get_recommendations()`
- `src/metamatch/app.py` — recommendation card display

---

### 3.2 Expand RAG to UU and NatDex

**Problem:** `scraper.py` hardcodes `gen9ou.json`. UU/NatDex Pokemon get no RAG hits or get OU-centric advice.

**Fix:** Convert `fetch_smogon_strategies()` to iterate over a `FORMATS` list: `["gen9ou", "gen9uu", "gen9nationaldex"]`. Attach a `format` metadata field to each chunk. Update `build_index.py` to call the expanded scraper. Rebuild index offline (one-time ~15 min operation).

**Files:**
- `src/metamatch/rag/scraper.py` — `SMOGON_API_URL` → `FORMATS` list
- `src/metamatch/rag/build_index.py` — update `main()`

---

### 3.3 Cache TTL and Size Cap ✅ DONE

**Problem:** `api_cache.json` grows unbounded. Stale entries (e.g., from a PokeAPI update) are never evicted.

**Fix:** Wrap each cache entry as `{"data": ..., "ts": timestamp}`. On read, evict if `age > 30 days`. On write, if `len(cache) > 2000`, drop the 200 oldest entries by timestamp.

**Files:**
- `src/metamatch/utils.py` — `fetch_pokemon_data()`, `fetch_move_data()`, save/load logic

---

## Phase 4 — Architecture Cleanup (7–10 hours, lower urgency)

### 4.1 Split app.py into Tab Modules

Extract each `with tab_X:` block into `src/metamatch/tabs/{tab_name}.py` exposing a `render(...)` function. `app.py` becomes a thin orchestrator. Priority order: `tab_chat.py` first (most complex), then `tab_rec.py`, `tab_matrix.py`.

**Files:** `src/metamatch/app.py` → `src/metamatch/tabs/`

### 4.2 User-Facing Error Handling

Wrap `readTeam()` and all Ollama calls in `app.py` with `st.error()` showing actionable messages. In `agents/client.py`, add a pre-flight Ollama connection check that raises `ConnectionError` with `"Start Ollama with 'ollama run llama3.2:3b' and try again."` rather than letting `httpx` surface an opaque error.

**Files:** `src/metamatch/agents/client.py`, `src/metamatch/app.py`

### 4.3 Consolidate Hardcoded Immunity Mappings

The `ABILITY_IMMUNITIES` dict is copy-pasted across `team.py`, `logic_engine.py`, and `agents/tactician.py`. Move to a single `constants.py` and import everywhere.

**Files:** `src/metamatch/team.py`, `src/metamatch/logic_engine.py`, `src/metamatch/agents/tactician.py` → new `src/metamatch/constants.py`

---

## Execution Order

| Priority | Item | Files | ~Effort |
|---|---|---|---|
| ✅ **Done** | 1.1 Enrich prompts | `coach.py`, `auditor.py` | 30 min |
| ✅ **Done** | 1.2 Few-shot examples | `suggestions.py`, agents | 45 min |
| ✅ **Done** | 1.3 Router threshold | `router.py`, `manager.py` | 20 min |
| ✅ **Done** | 1.4 RAG distance filter | `rag/store.py` | 15 min |
| ✅ **Done** | 1.5 Ground suggestions | `suggestions.py` | 45 min |
| ✅ **Done** | 3.1 Role-weighted recommender | `recommender.py`, `app.py` | 3–4 hrs |
| ✅ **Done** | 3.3 Cache TTL | `utils.py` | 45 min |
| **Next** | 2.1 Tera role detection | `team.py` | 2–3 hrs |
| **Next** | 2.2 Damage estimation | `logic_engine.py` | 3–4 hrs |
| **Next** | 2.3 Multi-format audit | `auditor.py`, `app.py` | 1–2 hrs |
| **Later** | 3.2 RAG → UU/NatDex | `rag/scraper.py`, `build_index.py` | 2 hrs |
| **Debt** | 4.1 Split app.py | `app.py` → `tabs/` | 4–6 hrs |
| **Debt** | 4.2 Error handling | `client.py`, `app.py` | 2–3 hrs |
| **Debt** | 4.3 Consolidate mappings | `team.py`, `logic_engine.py`, `tactician.py` | 1.5 hrs |

## Verification

After Phase 1: ✅ Verified (20/20 e2e tests, live Ollama)
- ✅ `get_suggestions()` returns valid JSON grounded in Smogon usage data, first-try.
- ✅ Coach prompt includes Ability, Nature, Tera Type, EVs, Roles, Speed.
- ✅ "hi" and off-topic queries route to fallback (scores 0.21–0.25, below 0.45 threshold).
- ✅ ChromaDB returns hits with distances ~0.75, all within the 1.0 threshold.

After Phase 2:
- Submit a team with Tera Steel Hatterene → verify `"Defensive Tera"` appears in role list.
- Ask Tactician "Can Kingambit beat my Roaring Moon?" → verify response includes a damage % estimate.
- Submit a UU team → verify auditor no longer false-flags UU staples.

After Phase 3 (3.1 + 3.3 done):
- ✅ Recommendation cards show gold reason badge when a role gap is filled.
- ✅ Role boost (×1.2) fires correctly; well-rounded teams show no boost (expected).
- ✅ Cache TTL/size cap unit tested; legacy flat entries pass through transparently.
- ⏳ 3.2 (RAG → UU/NatDex) still pending.

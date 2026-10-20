# Plan: add Pokémon Champions singles formats to MetaMatch

## Context

The premise "switch from VGC to Champions" needs correcting. MetaMatch was never VGC. It is a Smogon Gen 9 **singles** tool (OU, UU and NatDex, level 100, EV based). What has changed in 2026:

* Pokémon Champions launched on 8 April 2026, and official VGC moved onto it. Worlds 2026 used Reg MB, and Reg MC runs 9 Sep to 2 Dec 2026. All of these are doubles.
* Smogon publishes Champions **singles** ladders. The September 2026 stats include `gen9championsou` and `gen9championsuu` at cutoffs 0, 1500, 1630 and 1760 (there is no 1825). They also include Champions BSS and Champions VGC Reg MB and Reg MC.
* SV OU, UU and NatDex stats are still published every month (September files exist). Dropping them would be a loss.

Decision (user): **keep the SV formats and add Champions OU and UU.** Champions VGC doubles is out of scope.

Mechanics that differ in Champions and touch our code:
* There are no EVs. Champions uses stat points: 66 total, 32 max per stat, 1 point ≈ 8 EVs. Chaos spreads look like `Adamant:32/32/0/0/2/0`.
* All IVs are fixed at 31.
* Smogon moveset data has **no Tera Types section and no Checks and Counters**.
* Mega Evolution is back. Mega Stones show up in the item data, for example Salamencite.
* pkmn.github.io has **no Champions sets file** (`gen9championsou.json` returns 404). Strategy sets are only available for SV formats.

## Approach

### 1. Central format registry (new, in `src/metamatch/config.py`)
Add a single `FORMATS` dict that all modules read. It replaces the four duplicated maps.
```python
FORMATS = {
    "gen9ou":           {"label": "OU",           "stats": "gen9ou-1825",          "sets": "gen9ou",           "game": "sv"},
    "gen9uu":           {"label": "UU",           "stats": "gen9uu-1760",          "sets": "gen9uu",           "game": "sv"},
    "gen9natdex":       {"label": "NatDex",       "stats": "gen9nationaldex-1760", "sets": "gen9nationaldex",  "game": "sv"},
    "gen9championsou":  {"label": "Champions OU", "stats": "gen9championsou-1760", "sets": None,               "game": "champions"},
    "gen9championsuu":  {"label": "Champions UU", "stats": "gen9championsuu-1760", "sets": None,               "game": "champions"},
}
```
`game` drives the mechanics branch (stat points vs EVs, Tera, level).

### 2. Point existing maps at the registry
* `scrapers.py:115` `TARGET_FORMATS`: build from `FORMATS`.
* `scripts/update_meta.py:51`: loop over `FORMATS` and fetch JSON from `chaos/`. This also fixes the existing bug where the JSON is pulled from the base URL.
* `recommender.py:53` `file_map`: use the registry.
* `suggestions.py:54` `STATS_FILE_MAP`: use the registry. This fixes the `gen9nationaldex` vs `gen9natdex` key mismatch.
* `strategy_data.py:10` `STRATEGY_SOURCES`: only formats where `sets` is set. `strategy_data.py:138` label logic: look up the registry. Today `gen9championsou` would fall through to the label "CHAMPIONSOU".
* `strategy_data.py:110` currently globs any 1760 file, so Champions files load automatically. Keep it, but key the results by registry id.
* `tab_move_search.py:71,131`: add colour badges for the two new labels.

### 3. UI
* `tab_recommender.py:10` and `tab_quick_match.py:11`: generate the pill options and `fmt_map` from `FORMATS`.
* Add one sidebar "Game" toggle (SV / Champions) in `app.py`, stored in `st.session_state`. It sets which mechanics the team analysis uses, and can be inferred from an imported team (see step 4).
* `auditor.py:8` and `compute_threats` (`suggestions.py:61`) are hardcoded to OU. Pass the selected format through.

### 4. Mechanics for the Champions game
* **Speed**: in `utils.py:196`, give `calculate_speed` parameters for `level` and `sp` (stat points). The Champions formula converts SP to EV equivalents (`ev = min(sp*8, 252)`; verify against the in-game stat shown). Callers to update: `logic_engine.py:71`, `scrapers.py:92` and `team.py:79`. Champions speed tiers go to their own file, `meta_speeds_champions.json`, so the two games do not mix.
* **Team parsing** (`team.py:53`): **before coding, verify the Showdown export format for Champions**, including what label the stat points line uses and the level. Export one Champions team from the Showdown teambuilder. Store the values under `EVs` but scale them through one helper (`sp_to_ev`), so the role thresholds at `team.py:196` to `team.py:287` keep working unchanged.
* **Validation** (`team.py:308` checks the 508 EV sum, `team.py:312` checks Tera): branch on `game`. For Champions, check that the total is at most 66 and that no stat is above 32, and skip the Tera check.
* **Megas**: `recommender.py:6` already detects Megas and enforces one per team. That check should apply to Champions too.
* **LLM prompts**: `agents/coach.py:38` and the guide in `suggestions.py:295` mention Tera. Omit the Tera field and "Tera Captain" when `game == "champions"`.

### 5. Data
* Run the updated scraper to pull September 2026 Champions OU and UU files at the 1760 cutoff into `data/stats/`.
* `topPoke.json` merges all formats. Keep it merged, since the search bar wants everything.
* RAG (`rag/scraper.py:13`): there are no Champions analyses on pkmn.github.io. Leave it as is and note the gap.

### 6. Housekeeping
* Copy this plan to `D:\CS\Python\MetaMatch\CHAMPIONS_PLAN.md` (per the saved preference).
* README: list the new formats.

## Out of scope
Champions VGC and BSS doubles. These need level 50, doubles roles, bring 4 of 6, and a rewrite of how `replay.py` tracks two active Pokémon per side.

## Open items to verify during implementation
1. What Showdown's export text for Champions stat points looks like, and what level Champions OU uses on Showdown.
2. The exact SP to stat formula, checked against the stat shown in the Showdown teambuilder.

## Verification
1. `python scripts/update_meta.py`: confirm that the September 2026 Champions OU and UU `.txt` and chaos `.json` files at the 1760 cutoff land in `data/stats/`.
2. `pytest src/metamatch/tests`: existing tests pass (SV behaviour unchanged). Add tests for:
   * `calculate_speed` with SP
   * parsing a Champions export
   * Champions validation (66 cap, no Tera)
   * recommender output for `gen9championsou`
3. Run the Streamlit app. Select Champions OU in the Recommender and Quick Match. Import a Champions team and check that the roles, speed tiers and audit have no Tera warnings and no 508 EV warning.

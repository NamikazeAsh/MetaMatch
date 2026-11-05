<p align="center">
  <img src="assets/images/dark_logo_transp.png" alt="MetaMatch logo" width="220">
</p>

<h1 align="center">MetaMatch</h1>

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Ollama](https://img.shields.io/badge/AI-Ollama-000000?logo=ollama&logoColor=white)](https://ollama.com/)
[![Node.js](https://img.shields.io/badge/Calc-%40smogon%2Fcalc-339933?logo=nodedotjs&logoColor=white)](https://github.com/smogon/damage-calc)
[![ChromaDB](https://img.shields.io/badge/RAG-ChromaDB-FF6F00)](https://www.trychroma.com/)
[![MetaBench](<https://img.shields.io/badge/MetaBench-97.5%25%20held%20out-brightgreen>)](#-metabench-the-metamatch-benchmarker)
[![Frozen Test Set](<https://img.shields.io/badge/Frozen%20test%20set-201%20questions-blueviolet>)](#frozen-fresh-test-set)
[![Tests](https://github.com/NamikazeAsh/MetaMatch/actions/workflows/tests.yml/badge.svg)](https://github.com/NamikazeAsh/MetaMatch/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**MetaMatch** is a hybrid AI system for competitive Pokémon team analysis that runs entirely on a laptop. It pairs a deterministic battle engine (the official Smogon damage calculator, monthly ladder statistics, type and role logic) with a small local LLM, on one principle:

> ### 🧠 The engine does the thinking. The LLM does the talking.

Every factual answer (damage rolls, KOs, speed, immunities, stats, usage) is computed by code before the model ever sees the question. The LLM only explains a verdict that is already correct, and a verifier throws out any explanation that contradicts it.

**The result:** a 3B model on a 4 GB laptop GPU goes from **18% to 100%** on factual battle questions, and holds **94% and 97.5%** on blind held out sets.

* ⚡ **Instant:** a full team analysis lands in about a second, with no GPU needed for anything but chat.
* 🔌 **Works offline:** every analysis tab runs on the engine alone. The LLM is an upgrade, not a dependency.
* 🔒 **Private:** your teams never leave your machine. No API keys, no cloud, no paid models.
* 🛡️ **Regression tested:** every push replays the benchmark through CI against a pinned stats snapshot.
* 📡 **Always current:** MetaFlash turns six months of Smogon ladder data into a live meta front page, refreshed every month by CI.
* 🔗 **Every team has a link:** dashboards live at their own URL, so refresh, bookmarks, Back and a second tab all just work.

![MetaMatch Dashboard](assets/images/dashboard.png)

<p align="center"><b>No install needed: <a href="showcase/">take the visual tour</a></b>, every screen of the app with real data and real coach answers.</p>

---

## 📊 MetaBench: The MetaMatch Benchmarker

MetaBench is a 120 question benchmark across speed, KO, damage, type, stat and usage questions in SV and Champions formats. Every answer key comes straight from `@smogon/calc` and raw Smogon data, so nothing is graded on vibes.

| Question set                              | 🤖 Llama 3.2 3B alone | ⚪ MetaMatch (same 3B model) |
| :---------------------------------------- | :-------------------: | :--------------------------: |
| **Development set** (120)           |    18% (12 to 25)     |        **100%**        |
| **Held out set 1** (reworded blind) |    25% (18 to 33)     |   **94%** (90 to 98)   |
| **Held out set 2** (written blind)  |    26% (18 to 34)     |  **97.5%** (94 to 100) |

Brackets are bootstrap 95% confidence intervals. On held out set 2 MetaMatch beats the bare model by **+71.7 points** (paired 95% CI +63.3 to +79.2). It ties the planner and engine running with no LLM at all (+0.8 points, CI includes 0), which is the point: the engine produces the accuracy, and the LLM only has to explain it.

**Evaluation explained**

* **Development set:** 120 questions generated from the damage calculator and Smogon data, used while building MetaMatch.
* **Reworded blind:** the same 120 questions rewritten in formal wording by an agent that never saw the code.
* **Written blind:** the same 120 questions rewritten again in casual player style (lowercase, slang, swapped name order), also by an agent that never saw the code.

* **Overfitting check:** a high held out score means MetaMatch understands the question rather than memorizing the dev wording.
* **Fair grading:** free form answers are graded by a second local model (Gemma 3 4B) that was validated at 100% agreement (100 of 100) with strict `ANSWER:` line grading before use.
* **Fully local:** no paid APIs anywhere, for answering or for grading.

### Frozen Fresh Test Set

The next round of evaluation is already locked in: **201 brand new questions** that no part of MetaMatch has ever been run on.

* **Harder than the originals:** Choice Scarf speed, opponent phrased questions (*"does Dragapult outspeed my Great Tusk?"*), KO and survive checks with no move named, Sturdy and Focus Sash, sun and screens, defensive Tera, regional and Rotom formes, nicknames, plus 40 hand written questions in real player slang.
* **New Pokémon:** drawn from usage ranks 41 to 80, so none overlap the original question pool.
* **Independent answer keys:** generated by a separate script that imports nothing from MetaMatch, then recomputed from scratch by a second independent pass. All 201 keys agreed.
* **Tamper proof:** the questions and the stats snapshot they were built from are hash locked by a test, so editing a single question fails CI.

### 🧪 Real Answers From the Benchmark

Same model, same team, same question. These are trimmed from the benchmark logs.

#### 1. The Speed Tie

**Q:** *Does my Iron Moth outspeed Ogerpon-Wellspring running its most common spread, ignoring items and abilities?*

* **Llama 3B alone:** "Your Iron Moth's base speed is 120 + 50 (from Quark Drive) = 170... it will outspeed Ogerpon-Wellspring." ❌ *(invented a stat formula)*
* **MetaMatch:** "Iron Moth (350 Speed) **speed ties** with Ogerpon-Wellspring (Jolly 252 Spe, 350 Speed). Across all Ogerpon-Wellspring sets on the ladder, Iron Moth outspeeds 26% and ties 74%." ✅

#### 2. The Kingambit Check

**Q:** *Does my Cinderace's Flamethrower OHKO a full health Kingambit running its most common set?*

* **Llama 3B alone:** "Kingambit's most common spread is the Choice Scarf... base 120 Speed becomes 240... Pyro Ball has a 10% chance to burn..." ❌ *(wrong item, wrong stats, wrong move)*
* **MetaMatch:** "Flamethrower does **34.7 to 41.6%** to Kingambit, so it does not OHKO (69.2% chance to 3HKO after Leftovers recovery)." ✅

#### 3. The Stat Check

**Q:** *What is my Cresselia's Speed stat at level 100?*

* **Llama 3B alone:** "Cresselia's base Speed is 120. With 252 EVs... 428." ❌
* **MetaMatch:** "Cresselia's Speed stat is **250**. HP 401, Attack 158, Defense 256, Special Attack 273, Special Defense 276, Speed 250." ✅

---

## ⚙️ How a Chat Answer Is Made

```mermaid
graph LR
    Q["Question"] --> P["Planner"]
    P -->|fact question| S["Solver"]
    S -->|"@smogon/calc + dex + usage"| V["Verdict"]
    V --> L["LLM explains"]
    L --> C{"Verifier"}
    C -->|consistent| A["Answer"]
    C -->|contradiction| R["Retry once, then show facts"]
    P -->|opponent unclear| Q2["Ask which Pokémon"]
    P -->|strategy question| G["Router to Oak or Brock"]
```

1. **Planner (zero LLM):** works out what the question asks (speed, KO, damage, type, stat or usage) and which Pokémon, move and set are involved. Recognizes all 1,400+ species and formes in the bundled dex, plus nicknames (*Lando*, *Pult*, *Tusk*), typos and Mega names.
2. **Solver:** computes the answer with the real damage calculator. Opponents get their most common ladder set unless the question gives one (*"Garchomp @ Choice Scarf, Jolly 252 Spe"*).
3. **Verdict:** the headline answer comes from a template, so it is always the engine's answer, never the model's guess.
4. **Verifier:** the LLM writes a short explanation. Any number not in the facts, or any claim that flips the speed, type or KO verdict, gets rejected. One retry, then MetaMatch shows the raw facts instead.
5. **Clarify:** if a matchup question names no recognizable opponent, MetaMatch asks rather than answering a different question.

### 📜 Grounded Strategy Advice

Strategy questions ("how do I play against Kingambit?", "what are my biggest threats?") follow the same principle. The engine draws the conclusions, the LLM explains them:

* **🧮 One on one verdicts:** for a named opponent, or each of the top meta threats, the calc works out hits to KO both ways plus speed for every team member, then labels who wins and who loses.
* **📋 Engine check:** those verdicts open the answer, written by code, so the key facts are always right:
  > **Vs Kingambit** answers: Corviknight, Garchomp, Torkoal; loses: Dragapult (OHKO'd by Sucker Punch), Venusaur, Alomomola
* **🔍 Advice verifier:** Professor Oak's advice is rejected if it invents numbers, mentions Pokémon that appear nowhere in the facts, calls a team member an answer to something it loses to, or gives a member a move it doesn't run. One retry, then only the engine check is shown.

---

## ✨ Features

### 📡 MetaFlash: The Meta Front Page

The home screen opens on a magazine style front page of what the ladder is doing right now, for whichever format you pick.

![MetaFlash](assets/images/metaflash.png)

* **Story of the month:** the biggest move in the top 10, with its usage, rank change, standard set, common partners and a six month chart.
* **Top 10 leaderboard:** usage bars in each Pokémon's type colour and rank changes versus last month.
* **Story cards:** the #1, the biggest risers and fallers, newcomers breaking into the top 30, and the fastest common threat, each with its standard set and a trend line.
* **Written by code, not an LLM:** every card and headline (*"Raging Bolt climbs 8 ranks to #5"*) is picked by fixed rules from the data, with usage floors so tiny tiers can't fake a headline.
* **Honest charts:** every axis starts at zero, so a dip looks as big as it really was.
* **Self updating:** the monthly stats workflow appends each new month to a compact usage history, so the page is always current with no manual step.

### 🧭 Pages, Links & Memory

* **Top navigation:** Home, Team, Quick Match, Move Search and Replay Auditor are real pages with their own URLs.
* **Shareable team links:** every analysed team opens at `/team?t=<id>`, a short hash of the paste, so refreshing, bookmarking, opening a second tab and Back / Forward all keep your dashboard.
* **Pick up where you left off:** your last teams sit in the sidebar as sprite cards, one click from reopening.
* **A coach chat per team:** each team keeps its own conversation, and it survives a refresh.
* **Always fresh analysis:** saved and recent teams store only the paste, so reopening one runs the current engine and this month's stats.
* **Crash safe storage:** teams, chats and preferences live in a local SQLite database with atomic writes, so two tabs saving at once can never lose your saved teams. Everything stays on your machine.

### 🤖 Multi Agent Chat

Three specialist agents, each with its own persona and temperature:

* **Clemont (Tactician):** mechanics and math, backed by the grounded pipeline above.
* **Professor Oak (Coach):** win conditions and game plans, grounded with engine matchup verdicts (see above) and retrieval over Smogon analyses, strategy concepts and Champions community guides (ChromaDB + `bge-small-en-v1.5`). Sees full set context: item, ability, Tera type, nature, EVs, speed and roles.
* **Brock (Builder):** audits your sets against ladder usage and cites exact percentages.
* **Semantic Router:** MiniLM embeddings pick the right agent for open questions, with a confidence gate that falls back to Oak.
* **Named opponent awareness:** mention any Pokémon and the agents get its likely set card from usage stats.

### 🧮 Real Damage Calculator

* The official **`@smogon/calc`** runs as a lightweight Node sidecar the app talks to over JSON.
* Species, moves, items, abilities and the type chart are exported from the same package, so the app and the calc **never disagree**.
* Speed answers consider the opponent's whole ladder speed distribution, not just one spread.

### 🔍 Team Audit (Fully Deterministic)

Instant, zero LLM checks on every team:

* **Item and Ability Synergy Flags:** *Drought* without *Heat Rock*, *Guts* without an Orb, *Magic Guard* without *Life Orb*, each with a plain English explanation.
* **Role Gap Detection:** flags a missing *Hazard Setter*, *Hazard Remover* or *Pivot*.
* **Type Coverage Holes:** types none of your damaging moves hit super effectively.
* **Usage Warnings:** moves and items under 5% ladder usage, with the most common alternatives.
* **Role Detection:** about 35 competitive roles (*Wall, Setup Sweeper, Stallbreaker, Forced Switcher...*) and team archetypes (*Hyper Offense, Stall, Volt Turn, Weather, Trick Room*).

### ⚠️ Meta Threats

The top 5 threats to your specific team, scored by `members_hit² × ladder_usage%` so breadth beats raw popularity. Each threat shows which of your Pokémon can hit back, which resist its STABs, and its key moves by usage.

### 🤝 Teammate Recommender & Quick Match

* **Statistical Synergy:** teammate correlation matrices from Smogon chaos data covering millions of ladder battles.
* **Role Weighted Boosting:** candidates that fill a missing role get a ×1.2 boost and a gold *"Fills missing: Hazard Setter, Pivot"* badge.
* **Quick Match:** no team yet? Pick 1 to 5 Pokémon and get the best glue for your core.

### 🌐 Multi Format

Gen 9 **OU, UU, National Dex**, plus **Pokémon Champions OU and UU** with Level 50 stats, stat points instead of EVs, and full Mega Evolution support (Mega Stone holders map to their Mega forme's stats, ability and usage data).

### 🔎 Set Finder & Move Search

* **Verified Sets:** official Smogon Strategy Dex sets with full spreads.
* **Experimental Matches:** scans ladder usage for Pokémon running your move combo (over 1%), surfacing niche tech nobody has written up yet.

### 📼 Replay Auditor

Paste a Showdown replay link (shared `?p2` links and private links work) and get a post mortem. Every analysis gets its own link (`/replay-auditor?id=<replay>`), so a breakdown can be reopened or bookmarked.

* **Protocol accurate parsing:** Pokémon are tracked by identity, so Illusion, Mega Evolution, forme changes and Bring 3 team sizes are handled. Validated against an independent parser on 450 real ladder replays: zero crashes, 445 of 445 winners and 890 of 890 faint lists matched, and every remaining disagreement (Revival Blessing, Future Sight, Illusion) traced to the reference parser being wrong. The whole pool parses in under a second.
* **Team Health Chart** turn by turn, and a **Faint Timeline** with the real cause of every KO: the move, hazards, status, recoil, Destiny Bond or Perish Song.
* **Mistakes and Notes**, built only from what the log shows and dated to their turn: losing your only hazard remover, letting a setup sweeper run through you, moves into immune targets (not counted when the target Terastallized or changed type that turn), bounced hazards, Destiny Bond and hazard chip.
* **Opponent's Revealed Sets:** every item, ability, Tera type and move they showed.

### Self Updating Data

A GitHub Action pulls new Smogon usage stats every month, rebuilds top Pokémon and speed tiers, appends the month to the MetaFlash usage history, and commits them. Downloads are all or nothing, so months never mix. The benchmark gate answers from a pinned stats snapshot, so a new month of data can never break CI or silently shift the answer keys.

---

## 🏗️ System Architecture

```mermaid
graph TD
    A["User Input"] -->|"Showdown Export"| B("Streamlit App")
    B --> C{"Analysis Pipeline"}
    B <-->|"Teams, chats, prefs"| S["SQLite (local)"]

    subgraph Engine ["Battle Engine"]
    K["@smogon/calc (Node)"]
    X["Bundled Dex"]
    Y["Likely Sets"]
    end

    subgraph AI_Core ["Chat Core"]
    B --> PL["Planner"]
    PL -->|"Fact question"| SO["Solvers"]
    SO --> GR["Grounded Answer + Verifier"]
    PL -->|"Open question"| R["Semantic Router (MiniLM)"]
    R -->|Mechanics| T["Clemont"]
    R -->|Strategy| U["Prof. Oak"]
    R -->|Builder| V["Brock"]
    end

    K --> SO
    X --> SO
    Y --> SO

    subgraph RAG_Engine ["RAG System"]
    H["Smogon Analyses, Concepts, Champions Guides"] --> I["ChromaDB (BGE Small)"]
    I --> U
    end

    subgraph Statistical_Engine ["Statistical Engine"]
    M["Smogon Chaos Data"] -->|"Weighted Usage"| N["Meta Auditor"]
    M -->|"Correlation Matrix"| O["Teammate Recommender"]
    M --> Y
    M --> V
    end

    subgraph Static_Analysis ["Static Analysis"]
    C --> D["Team Parser"]
    D --> F["Role Detection"]
    D --> G["Type Calculator"]
    end

    F --> P["Dashboard UI"]
    G --> P
    GR --> P
    T --> P
    U --> P
    V --> P
    N --> P
    O --> P
```

---

## 🚀 Setup

### Prerequisites

1. **Python 3.10+**
2. **Node.js 18+** for the damage calculator.
3. **[Ollama](https://ollama.com/)**, then pull the model:

   ```bash
   ollama pull llama3.2:3b-instruct-q4_K_M
   ```

   To try another local model, set `LLM_MODEL` in `.env` (for example `LLM_MODEL=gemma3:4b`).

### Install & Run

```bash
git clone https://github.com/NamikazeAsh/MetaMatch.git
cd MetaMatch
pip install -r requirements.txt
cd src/metamatch/engine && npm install && cd ../../..

python scripts/update_meta.py              # usage stats, top Pokémon, speed tiers
python scripts/build_strategy_cache.py     # Smogon sets for move search
python src/metamatch/rag/build_index.py    # vector index for the coach
python scripts/backfill_usage_history.py   # optional: rebuild MetaFlash's six month history (it ships in the repo)

streamlit run src/metamatch/app.py        # run from the repo root so the dark theme loads
```

Ollama and Node are both optional. Without Ollama, every analysis tab still works and chat answers with the engine's facts; the pilot guide and Oak's prose come back as soon as Ollama starts. Without Node, chat falls back to type matchups instead of real damage numbers.

---

## 🧪 Tests & Benchmark

```bash
pytest                                     # 124 tests: parsing, mechanics, planner, verifiers, strategy verdicts, replays, MetaFlash, storage, frozen set integrity

python bench/run.py --arm raw              # bare model with the team pasted in
python bench/run.py --arm metamatch        # full pipeline
python bench/run.py --arm template         # planner and solver only, no LLM
python bench/run.py --arm metamatch --questions bench/questions_paraphrase2.jsonl --name held_out_2
python bench/run.py --arm template --stats-dir bench/fixtures/stats_2026_09 --min-accuracy 1.0   # the CI gate
python bench/generate_fresh.py --check     # rebuild the frozen fresh set from its snapshot and confirm it matches
python bench/report.py                     # accuracy by arm, format and category, with 95% CIs
python bench/report.py --compare raw_paraphrase2 metamatch_paraphrase2   # paired difference
```

---

## 🛠️ Module Overview

| Path                                             | What it does                                                                                                 |
| :----------------------------------------------- | :----------------------------------------------------------------------------------------------------------- |
| `src/metamatch/app.py`, `tabs/`              | Streamlit app, one module per tab                                                                            |
| `src/metamatch/engine/`                        | Damage calc bridge, dex, likely sets, query planner, solvers, name matching                                  |
| `src/metamatch/agents/`                        | Router, manager, grounded answerer and verifier, the three agents ([details](src/metamatch/agents/README.md)) |
| `src/metamatch/rag/`                           | Smogon scraper, Champions usage cards and guides, ChromaDB store ([details](src/metamatch/rag/README.md))     |
| `src/metamatch/team.py`                        | Showdown parser, role detection, type math, Mega handling                                                    |
| `src/metamatch/suggestions.py`                 | Team audit, threat scoring, team guide                                                                       |
| `src/metamatch/recommender.py`, `auditor.py` | Teammate synergy and usage checks from chaos data                                                            |
| `src/metamatch/replay/`                        | Showdown protocol parser, team health, mistake and note rules                                                |
| `src/metamatch/meta_pulse.py`                  | MetaFlash: usage history, story selection rules, leaderboard, template headlines                             |
| `src/metamatch/storage.py`                     | SQLite store for teams, per team chats and preferences, with a one time import of the old JSON saves         |
| `scripts/update_meta.py`                       | Monthly stats pipeline (also run by GitHub Actions), including the MetaFlash usage history                   |
| `bench/`                                       | MetaBench question generators, runner, grader, report, and pinned stats snapshots in `bench/fixtures/`       |

---

## 🔮 Limitations & Future Outlook

* **Strategy is the frontier.** Facts are solved and Oak's matchup claims are verified, but open ended advice is not benchmarked yet, and the verifier can't catch every strategic mistake a 3B model makes. A rubric graded strategy benchmark is next.
* **Fresh set results.** The [201 question frozen set](#frozen-fresh-test-set) covers new Pokémon, items, field effects and opponent phrased questions. It is locked and waiting for its first run.
* **Assumed sets.** Damage numbers use the opponent's most common set unless you give one.
* **Champions data.** Smogon has no Champions analyses yet, so its retrieval uses usage cards and community guides, and verified sets are SV only.

**The bet:** you should not need a frontier model to calculate a Speed stat. Code is perfect for rules, language models are good at explaining them, and keeping everything local means your teams stay private. MetaMatch is a proof that a small model that knows how to use tools can beat a raw model at the same size by a wide margin.

---

## Acknowledgements

* **[Smogon University](https://www.smogon.com/)**: usage statistics, strategy analyses and [`@smogon/calc`](https://github.com/smogon/damage-calc).
* **[PokeAPI](https://pokeapi.co/)**: Pokémon relational data.
* **[Ollama](https://ollama.com/)**: local LLM runtime.
* **[Streamlit](https://streamlit.io/)**: dashboard framework.

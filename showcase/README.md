<p align="center">
  <img src="../assets/images/dark_logo_transp.png" alt="MetaMatch logo" width="160">
</p>

<h1 align="center">MetaMatch: The Visual Tour</h1>

<p align="center">
  Everything MetaMatch does, without installing anything.<br>
  Every screen below is the real app running locally: real ladder data, real engine verdicts and real answers from a 3B model on a laptop GPU. Nothing is mocked.
</p>

<p align="center">
  <a href="../README.md">Main README</a> ·
  <a href="#-home-and-metaflash">Home</a> ·
  <a href="#-the-team-dashboard">Dashboard</a> ·
  <a href="#-the-coaching-staff">Coach chat</a> ·
  <a href="#-tools">Tools</a> ·
  <a href="#-built-to-be-used">Everyday use</a> ·
  <a href="#-under-the-hood">Under the hood</a>
</p>

![The team dashboard for the built in sample team](images/dashboard.webp)

<p align="center"><i>One click on "Try a sample team": parsing, roles, type math, threats and audit land in about a second, no GPU needed.</i></p>

---

## 🏠 Home and MetaFlash

The home screen is a paste box and a live front page of the ladder for whichever format you pick.

![Home screen with the format picker and paste box](images/home.webp)

**MetaFlash** turns six months of Smogon usage stats into a story page that rewrites itself every month: the story of the month with a six month chart, the top 10 with rank changes, and story cards for the risers, fallers, newcomers and fastest threat.

![MetaFlash: story of the month and the top 10 leaderboard](images/metaflash.webp)

![MetaFlash story cards: the #1, risers, fallers, newcomers and the fastest threat](images/metaflash_stories.webp)

Every headline (*"Raging Bolt climbs 8 ranks to #5"*) is chosen by rules from the data, not written by a model. Hover any partner for its own card.

![A partner hover card on a story card](images/metaflash_hover.webp)

Switch the format and the whole page rebuilds for that ladder, here Pokémon Champions OU with Mega Evolution:

![MetaFlash for Champions OU](images/metaflash_champions.webp)

---

## 📊 The Team Dashboard

Paste a Showdown export or a pokepast.es link and every member is parsed, typed, statted and given competitive roles.

![Squad cards with type glow, roles, item, ability and spread](images/squad.webp)

| | |
| :-- | :-- |
| ![Team Overview: offensive coverage and defensive weaknesses](images/tab_overview.webp) | ![Audit: item and ability synergy flags and role gaps](images/tab_audit.webp) |
| **Team Overview:** which types you hit and which ones hit you, counted per member. | **Audit:** deterministic checks for item and ability synergy, missing roles and coverage holes. |
| ![Meta Threats: the five biggest threats to this team](images/tab_threats.webp) | ![Coach Guide: a pilot guide written by the local model](images/tab_guide.webp) |
| **Meta Threats:** scored by members hit squared times ladder usage, each with counterplay from your own team. | **Coach Guide:** win condition, leads, Tera plan and key combos, written on demand by the local model. |
| ![Recommendations: teammates that fill your missing roles](images/tab_recommendations.webp) | ![Matchup Matrices: offensive and defensive type charts for the team](images/tab_matrices.webp) |
| **Recommendations:** ladder teammate data with a boost for Pokémon that fill a missing role. | **Matchup Matrices:** the full type chart for your six, attack and defence. |
| ![Speed Tiers: your team against the meta's speed tiers](images/tab_speed.webp) | |
| **Speed Tiers:** your real speed stats placed among the top meta threats. | |

---

## 🧑‍🏫 The Coaching Staff

Chat questions are planned by code first. Facts (speed, damage, KOs, types, usage) are computed by the engine and stated before the model says a word; the model only explains, and a verifier rejects any explanation that contradicts the engine.

**Clemont, mechanics.** The verdict comes from the engine, the explanation from the model, checked against it:

![Clemont answering a speed question with an engine verdict](images/chat_clemont.webp)

**Professor Oak, strategy.** One on one engine verdicts open the answer, then verified advice:

![Professor Oak's engine check and advice against Raging Bolt](images/chat_oak.webp)

**Brock, building.** Usage numbers straight from this month's ladder stats:

![Brock answering a usage question with ladder numbers](images/chat_brock.webp)

**When a question is ambiguous, it asks** instead of answering a different question:

![The coach asking which Pokémon the question is about](images/chat_clarify.webp)

---

## 🧰 Tools

**Quick Match.** No team yet? Pick a core and get the partners that pair best with it on the ladder.

![Quick Match partners for Great Tusk and Kingambit](images/quick_match.webp)

**Move Search.** Find every set that runs a combination of moves, from the Smogon Strategy Dex and ladder usage.

![Move Search results for Knock Off and U-turn](images/move_search.webp)

**Replay Auditor.** Paste a Showdown replay for a post mortem: the result, team health turn by turn, the cause of every faint, mistakes and notes dated to their turn, and every set the opponent revealed.

![Replay Auditor: result and team health chart](images/replay_auditor.webp)

![Replay Auditor: mistakes and notes, and the opponent's revealed sets](images/replay_details.webp)

---

## 🧭 Built to Be Used

**It remembers.** Recent teams sit in the sidebar, one click from reopening; saved teams show every set on hover. Every team also has its own link (`/team?t=<id>`), so refresh, bookmarks, Back and a second tab all keep your dashboard.

![Sidebar with recent teams and a saved team's set cards](images/sidebar.webp)

**It works offline.** With the model server off, every analysis tab still runs and the coach answers with the engine's facts:

![The coach answering with engine facts while the model is offline](images/offline_mode.webp)

**It works on a phone.**

![MetaMatch at phone width: home, MetaFlash and the dashboard](images/phone.webp)

---

## ⚙️ Under the Hood

* **MetaBench:** a 3B model alone scores 18% on factual battle questions; MetaMatch on the same model scores 100%, and 94% and 97.5% on blind held out sets. [Results and method](../README.md#-metabench-the-metamatch-benchmarker)
* **Frozen fresh test set:** 201 new questions with independently computed answer keys, hash locked in CI. [Details](../README.md#frozen-fresh-test-set)
* **Regression tested:** every push runs the test suite and replays the benchmark against a pinned stats snapshot.
* **Fully local:** Ollama for the model, the official Smogon damage calculator as a Node sidecar, SQLite for your teams. No API keys, no cloud.

<p align="center"><a href="../README.md#-setup">Run it yourself →</a></p>

---

<sub>Captured by [`scripts/capture_showcase.py`](../scripts/capture_showcase.py), which boots the app against a throwaway store and drives every flow in a headless browser, so this tour can be regenerated whenever the UI changes. Needs Playwright, Pillow and Ollama (dev tools, not app requirements).</sub>

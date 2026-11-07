<img src="../assets/images/dark_logo_transp.png" alt="MetaMatch logo" width="120">

# MetaMatch: The Visual Tour

Everything MetaMatch does, without installing anything. Every screen is the real app running locally: real ladder data, real engine verdicts and real answers from a 3B model on a laptop GPU. Nothing is mocked.

[Main README](../README.md) · [Home](#home-and-metaflash) · [Dashboard](#the-team-dashboard) · [Coach chat](#the-coaching-staff) · [Team building](#team-building-tools) · [Tools](#tools) · [Everyday use](#built-to-be-used)

![The team dashboard for the built in sample team](images/dashboard.webp)

*One click on "Try a sample team": parsing, roles, type math, threats and audit land in about a second.*

---

## Home and MetaFlash

### Home

A paste box for a Showdown export or pokepast.es link, and a format picker that drives the whole app.

![Home screen with the format picker and paste box](images/home.webp)

### MetaFlash

Six months of Smogon usage stats turned into a front page that rewrites itself every month: the story of the month with a six month chart, and the top 10 with rank changes.

![MetaFlash: story of the month and the top 10 leaderboard](images/metaflash.webp)

### Story cards

The #1, the biggest risers and fallers, newcomers to the top 30 and the fastest common threat. Every headline is chosen by rules from the data, not written by a model.

![MetaFlash story cards: the #1, risers, fallers, newcomers and the fastest threat](images/metaflash_stories.webp)

### Partner cards

Hover any partner to see its types, ladder rank, usage and usual item.

![A partner hover card on a story card](images/metaflash_hover.webp)

### Every format

Switch the format and the page rebuilds for that ladder, here Pokémon Champions OU with Mega Evolution.

![MetaFlash for Champions OU](images/metaflash_champions.webp)

---

## The Team Dashboard

### Squad

Every member parsed, typed, statted and given competitive roles.

![Squad cards with type glow, roles, item, ability and spread](images/squad.webp)

### Team Overview

Which types you hit and which ones hit you, counted per member.

![Team Overview: offensive coverage and defensive weaknesses](images/tab_overview.webp)

### Audit and Team Check

Legality in plain English, a one click conversion between SV EVs and Champions stat points, a team report to download, and checks for item and ability synergy, missing roles and coverage holes.

![Audit: Team Check, export, and synergy and role checks](images/tab_audit.webp)

### Threat Board

Your team against the format's 12 most used Pokémon, one matchup at a time, every verdict worked out by the damage calculator.

![Threat Board: a win or lose grid of the top 12 threats against the team](images/tab_threats.webp)

Hover any cell to see how the matchup plays out: who moves first, the best hit each way and how many hits each side needs.

![A Threat Board hover card with speed, damage and hits to KO](images/threat_hover.webp)

Pick a threat to see exactly who answers it and who loses to it.

![Answers to and losses to Kyurem, with the numbers for each](images/threat_detail.webp)

### Team Completer

The next teammate, picked by which of your weak spots it beats and how often players really pair it with your team, not by popularity. Across 882 tests on real ladder teams, its first pick fixes 82% of a team's weak spots.

![Team Completer: candidates that beat the team's weak spots](images/tab_recommendations.webp)

Hover a pairing to see the ladder numbers behind it.

![A pairing hover card with how often the pick appears next to each team member](images/completer_hover.webp)

### Matchup Matrices

The full type chart for your six, on defence and on offence.

![Matchup Matrices: offensive and defensive type charts for the team](images/tab_matrices.webp)

### Speed Tiers

Your true Speed, with items and IVs, against every spread the format's top Pokémon really run, with Choice Scarf sets marked and a slider to test more Speed.

![Speed Tiers: the team against real ladder spreads](images/tab_speed.webp)


---

## The Coaching Staff

Questions are planned by code first. Facts (speed, damage, KOs, types, usage) are computed by the engine and stated before the model says a word; the model only explains, and a verifier rejects any explanation that contradicts the engine.

### Clemont, mechanics

The verdict comes from the engine, the explanation from the model, checked against it.

![Clemont answering a speed question with an engine verdict](images/chat_clemont.webp)

### Professor Oak, strategy

One on one engine verdicts open the answer, then verified advice, with the Smogon references he read listed underneath.

![Professor Oak's engine check and advice against Raging Bolt](images/chat_oak.webp)

### Brock, building

Usage numbers straight from this month's ladder stats.

![Brock answering a usage question with ladder numbers](images/chat_brock.webp)

### Asking when unsure

When a question is ambiguous, it asks instead of answering a different question.

![The coach asking which Pokémon the question is about](images/chat_clarify.webp)

---

## Team Building Tools

### Spread Lab

Pick what your Pokémon needs to do: outspeed a threat, OHKO or 2HKO a target, survive a hit. It finds the smallest spread that does all of it.

![Spread Lab: the Pokémon being tuned and its benchmarks](images/spread_lab.webp)

Every benchmark is rechecked with the damage calculator, and compared with the spreads players run most.

![Spread Lab result: the spread, stat bars, checks and the ladder comparison](images/spread_lab_result.webp)

### Matchup Preview

Paste the team you're about to face, even just the six names from team preview, and see every matchup.

![Matchup Preview: your team against theirs, with summary cards and the grid](images/matchup_preview.webp)

In Pokémon Champions it also picks the three to bring, checked against every three they could bring.

![Matchup Preview: the three to bring and the matchup cards](images/matchup_bring.webp)

---

## Tools

### Quick Match

No team yet? Pick a core and get the partners players actually build with it in your format.

![Quick Match partners for Great Tusk and Kingambit](images/quick_match.webp)

### Move Search

Every set that runs a combination of moves, from the Smogon Strategy Dex and ladder usage.

![Move Search results for Knock Off and U-turn](images/move_search.webp)

### Replay Auditor

A post mortem of any Showdown replay: the result, team health turn by turn and the cause of every faint.

![Replay Auditor: result and team health chart](images/replay_auditor.webp)

Mistakes and notes dated to their turn, and every set the opponent revealed.

![Replay Auditor: mistakes and notes, and the opponent's revealed sets](images/replay_details.webp)

---

## Built to Be Used

### It remembers

Recent teams sit in the sidebar, one click from reopening, and saved teams show every set on hover. Every team has its own link, so refresh, bookmarks, Back and a second tab all keep your dashboard.

![Sidebar with recent teams and a saved team's set cards](images/sidebar.webp)

### It works offline

With the model server off, every analysis tab still runs and the coach answers with the engine's facts.

![The coach answering with engine facts while the model is offline](images/offline_mode.webp)

### It works on a phone

![MetaMatch at phone width: home, MetaFlash and the dashboard](images/phone.webp)

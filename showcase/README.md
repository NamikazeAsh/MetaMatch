<img src="../assets/images/dark_logo_transp.png" alt="MetaMatch logo" width="120">

# MetaMatch: The Visual Tour

Everything MetaMatch does, without installing anything. Every screen is the real app running locally: real ladder data, real engine verdicts and real answers from a 3B model on a laptop GPU. Nothing is mocked.

[Main README](../README.md) · [Home](#home-and-metaflash) · [Dashboard](#the-team-dashboard) · [Coach chat](#the-coaching-staff) · [Tools](#tools) · [Everyday use](#built-to-be-used)

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

### Audit

Deterministic checks for item and ability synergy, missing roles and coverage holes.

![Audit: item and ability synergy flags and role gaps](images/tab_audit.webp)

### Meta Threats

The five biggest threats to this team, scored by members hit squared times ladder usage, each with counterplay from your own six.

![Meta Threats: the five biggest threats to this team](images/tab_threats.webp)

### Coach Guide

Win condition, leads, Tera plan and key combos, written on demand by the local model.

![Coach Guide: a pilot guide written by the local model](images/tab_guide.webp)

### Recommendations

Ladder teammate data, with a boost for Pokémon that fill a role the team is missing.

![Recommendations: teammates that fill your missing roles](images/tab_recommendations.webp)

### Matchup Matrices

The full type chart for your six, on defence and on offence.

![Matchup Matrices: offensive and defensive type charts for the team](images/tab_matrices.webp)

### Speed Tiers

Your real speed stats placed among the top meta threats.

![Speed Tiers: your team against the meta's speed tiers](images/tab_speed.webp)

---

## The Coaching Staff

Questions are planned by code first. Facts (speed, damage, KOs, types, usage) are computed by the engine and stated before the model says a word; the model only explains, and a verifier rejects any explanation that contradicts the engine.

### Clemont, mechanics

The verdict comes from the engine, the explanation from the model, checked against it.

![Clemont answering a speed question with an engine verdict](images/chat_clemont.webp)

### Professor Oak, strategy

One on one engine verdicts open the answer, then verified advice.

![Professor Oak's engine check and advice against Raging Bolt](images/chat_oak.webp)

### Brock, building

Usage numbers straight from this month's ladder stats.

![Brock answering a usage question with ladder numbers](images/chat_brock.webp)

### Asking when unsure

When a question is ambiguous, it asks instead of answering a different question.

![The coach asking which Pokémon the question is about](images/chat_clarify.webp)

---

## Tools

### Quick Match

No team yet? Pick a core and get the partners that pair best with it on the ladder.

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

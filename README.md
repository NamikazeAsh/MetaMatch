# MetaMatch <img src="https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/items/poke-ball.png" width="40" height="40">

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Ollama](https://img.shields.io/badge/AI-Ollama-000000?logo=ollama&logoColor=white)](https://ollama.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**MetaMatch** is an advanced AI-powered Pokémon team analysis tool. It combines hard-coded competitive logic with Large Language Model (LLM) insights to provide deep feedback on team synergy, weaknesses, and current meta threats.

![MetaMatch Dashboard](assets/images/dark_logo_transp.png)

## ✨ Features

### 🧠 Smart Analysis
*   **Role Detection:** Automatically identifies 30+ competitive roles (e.g., *Wall, Setup Sweeper, Cleric, Hazard Setter*) based on movesets and stats.
*   **Deep Logic:** Calculates type weaknesses while respecting **Abilities** and **Items** (e.g., ignores Ground damage for *Levitate* or *Air Balloon* users).
*   **Meta Integration:** Scrapes live Smogon usage stats to identify top-tier threats relevant to the current season.

### 🤖 AI-Powered Coaching
*   **Local LLM Integration:** Connects to **Ollama** (Llama 3.2) to act as a competitive coach.
*   **Team Synergy:** Provides high-level feedback on your team's archetype (e.g., "Hyper Offense", "Stall").
*   **Threat Hunter:** Identifies specific meta counters to your team and suggests counter-strategies.
*   **Detailed Tips:** Gives per-Pokemon advice (e.g., "Swap Leftovers for Heavy-Duty Boots on Volcarona").

### 📊 Modern Dashboard
*   **Trading Card UI:** Visualizes your team as a grid of detailed cards with Sprites, Types, and Roles.
*   **At-a-Glance Metrics:** A top-bar dashboard shows Team Archetype, Coverage, and Critical Weaknesses.
*   **Defensive & Offensive Heatmaps:** Instantly see your team's type vulnerabilities and coverage gaps in color-coded matrices.
*   **Speed Tier Chart:** A visual plot comparing your team's speed against live meta benchmarks.
*   **Debug Presets:** Instantly load "Balanced", "Rain", or "Stall" teams to test the analyzer.

---

## 💡 Why MetaMatch? (vs. Generic LLMs)

Why not just ask ChatGPT? Because generic LLMs "guess" — MetaMatch **calculates**.

| Feature | 🤖 Generic LLMs (ChatGPT/Claude) | ⚪ MetaMatch |
| :--- | :--- | :--- |
| **Accuracy** | **Hallucinations:** Can fail simple type math (e.g., ignoring *Levitate*). | **Hard Logic:** Deterministic type calculator respecting Abilities & Items. |
| **Data Freshness**| **Cutoff Dates:** Doesn't know this month's usage stats. | **Live Meta:** Scrapes Smogon stats *on demand* for real-time relevance. |
| **Hybrid Engine** | **Text Only:** Generates plausible-sounding but often mathematically flawed advice. | **Math + AI:** Uses code for 100% accurate stats/weaknesses, and AI for high-level strategy. |
| **Model Efficiency** | **Massive:** Needs massive frontier models (**GPT-5.2**) to minimize hallucinations. | **Lightweight:** Works perfectly with a tiny ~3B model (Llama 3.2) because logic is offloaded to code. |
| **Workflow** | **Slow Prompting:** "Here is my new team..." (copy-paste-repeat). | **Rapid Iteration:** Tweak one move in the sidebar -> Instant re-analysis. |

### 🧪 Real World Examples

#### 1. The "Rotom-Wash" Test
**Scenario:** You ask for the weaknesses of a standard **Rotom-Wash** (*Electric/Water* type with *Levitate* ability).
*   **Generic LLM:** "Rotom-Wash is Electric/Water. Electric is weak to Ground. Therefore, **Rotom-Wash is weak to Ground**." ❌ *(Fails to account for Ability)*
*   **MetaMatch:** `Ground: 0.0` (Immune) ✅

#### 2. The "Air Balloon Heatran" Test
**Scenario:** You have a **Heatran** (*Fire/Steel*) holding an **Air Balloon**.
*   **Generic LLM:** Often overlooks the item and flags a **4x Ground weakness**. ❌
*   **MetaMatch:** Correctly identifies the item grants **Ground Immunity** until popped. ✅

---

## 🔮 Limitations & Future Outlook

It's important to acknowledge that the AI landscape is evolving rapidly. As frontier models (like **GPT-5.2**, **Gemini 3**, and beyond) continue to scale, their ability to "simulate" game logic internally will undoubtedly improve.

However, MetaMatch represents a philosophy of **Efficiency & Transparency**:
1.  **Right Tool for the Job:** We shouldn't need a massive frontier model to calculate a Speed stat. Code is perfect for rules; AI is perfect for strategy.
2.  **Privacy:** By optimizing for smaller models (Llama 3B), MetaMatch allows you to keep your strategies local and offline.
3.  **The "Hybrid" Bet:** We believe the future of AI isn't just "bigger models," but "models that know how to use tools." MetaMatch is a proof-of-concept for that future.

---

## 🤝 Contributing

Contributions are welcome! Whether it's adding new Role definitions, improving the LLM prompt, or enhancing the UI.

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the Branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull-Review (`git push origin feature/AmazingFeature`)

---

## 🙏 Acknowledgements

MetaMatch is built upon the incredible work of the Pokémon community:

*   **[PokeAPI](https://pokeapi.co/)**: For providing the comprehensive database of Pokémon, types, and moves.
*   **[Smogon University](https://www.smogon.com/)**: For the competitive usage stats that power our meta-analysis.
*   **[Ollama](https://ollama.com/)**: For enabling local LLM execution, keeping analysis private and fast.
*   **[Streamlit](https://streamlit.io/)**: For the framework that makes building this dashboard a breeze.
# MetaMatch ⚪

**MetaMatch** is an advanced AI-powered Pokémon team analysis tool. It combines hard-coded competitive logic with Large Language Model (LLM) insights to provide deep feedback on team synergy, weaknesses, and current meta threats.

![MetaMatch Dashboard](logo/dark_logo_transp.png)

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
*   **Metrics Bar:** At-a-glance view of your **Team Archetype**, **Type Coverage**, and **Critical Weaknesses**.
*   **Interactive Tabs:** Deep dive into Type Coverage charts, Weakness Alerts, and AI suggestions.
*   **Debug Presets:** Instantly load "Balanced", "Rain", or "Stall" teams to test the analyzer.

---

## 💡 Why MetaMatch? (vs. Generic LLMs)

Why not just ask ChatGPT? Because generic LLMs "guess" — MetaMatch **calculates**.

| Feature | 🤖 Generic LLMs (ChatGPT/Claude) | ⚪ MetaMatch |
| :--- | :--- | :--- |
| **Accuracy** | **Hallucinations:** Can fail simple type math (e.g., ignoring *Levitate*). | **Hard Logic:** Deterministic type calculator respecting Abilities & Items. |
| **Data Freshness**| **Cutoff Dates:** Doesn't know this month's usage stats. | **Live Meta:** Scrapes Smogon stats *on demand* for real-time relevance. |
| **User Experience**| **Wall of Text:** Requires reading long paragraphs to find flaws. | **Visual Dashboard:** Instant heatmaps, charts, and "Trading Card" visuals. |
| **Privacy** | **Cloud Logged:** Your secret tech is sent to OpenAI/Anthropic. | **100% Local:** Runs on your machine (via Ollama). Your strategy stays yours. |

---

## 🚀 Getting Started

### Prerequisites
1.  **Python 3.10+**
2.  **Ollama** (for AI features):
    *   Install Ollama from [ollama.com](https://ollama.com/).
    *   Pull the model: `ollama pull llama3.2:3b-instruct-q4_K_M`
    *   Start the server: `ollama serve`

### Installation

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/NamikazeAsh/MetaMatch.git
    cd MetaMatch
    ```

2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the App:**
    ```bash
    streamlit run app.py
    ```

---

## 🛠️ Architecture

*   **`app.py`**: The Streamlit frontend. Handles the Sidebar input, Dashboard rendering, and state management.
*   **`team_read.py`**: The "Static Analyzer." Parses Showdown text, calculates type math, and detects roles heuristically.
*   **`suggestion_call.py`**: The "AI Brain." Formats data into a JSON-enforced prompt and queries the local LLM for qualitative advice.
*   **`smogon_scrape.py`**: The "Meta Crawler." Downloads and parses the latest usage stats from Smogon to update `jsons/topPoke.json`.
*   **`jsons/`**: Stores cached analysis data and the current meta list.

---

## 📝 Usage

1.  **Paste Team:** Copy your team export from [Pokémon Showdown](https://play.pokemonshowdown.com/teambuilder).
2.  **Input:** Paste it into the Sidebar text area.
3.  **Analyze:** Click "Analyze Team".
4.  **Review:**
    *   Check the **Dashboard** for major red flags.
    *   View **Suggestions** for specific move/item tweaks.
    *   Check **Meta Threats** to see what Pokemon you lose to.

---

## 🤝 Contributing

Contributions are welcome! Whether it's adding new Role definitions, improving the LLM prompt, or enhancing the UI.

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the Branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request
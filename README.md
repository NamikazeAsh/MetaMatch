# MetaMatch - Competitive Pokémon Team Analyzer

<div align="center">
<img width="700" height="700" alt="MetaMatch Logo" src="https://github.com/user-attachments/assets/fa82cd10-63fd-4cac-a974-0b97333a60cb" />
</div>

A comprehensive Pokemon team analyzer that bridges the gap between casual team building and competitive play. MetaMatch takes your raw team data, analyzes it against the current competitive meta, and provides detailed insights to transform your team into a tournament-ready powerhouse.

## Getting Started

This section provides instructions on how to set up and run a local copy of MetaMatch.

### Prerequisites

1.  **Python 3.8+**
2.  **Ollama:** You must have Ollama installed and running. You can download it from [ollama.com](https://ollama.com/).
3.  **LLM Model:** Pull the model used by the application by running the following command in your terminal:
    ```sh
    ollama pull llama3.2:3b-instruct-q4_K_M
    ```

### Installation & Setup

1.  **Clone the repository:**
    ```sh
    git clone <your-repo-url>
    cd MetaMatch
    ```

2.  **Install Python dependencies:**
    It is recommended to use a virtual environment.
    ```sh
    pip install -r requirements.txt
    ```

3.  **Download Latest Meta Data:**
    Before the first run, you need to populate the meta-analysis data. Run the automated script:
    ```sh
    python smogon_scrape.py
    ```
    This will download the latest Smogon usage stats and create the `jsons/topPoke.json` file.

### Running the Application

Once the setup is complete, launch the Streamlit web application:

```sh
streamlit run app.py
```

Open your web browser to the local URL provided by Streamlit to start analyzing your teams.

## Technologies Used

- **Backend:** Python
- **Web Framework:** Streamlit
- **Local AI Inference:** Ollama
- **Pokémon Data:** [PokeAPI](https://pokeapi.co/)
- **Usage Statistics:** [Smogon](https://www.smogon.com/stats/)

---

## What MetaMatch Does

MetaMatch is designed for Pokemon trainers who want to elevate their competitive game. Whether you're a newcomer trying to understand the meta or a seasoned player looking to optimize your team, MetaMatch provides the analytical depth needed to compete at the highest levels.

### Core Functionality Currently Implemented

**Team Composition Analysis**
MetaMatch dissects your team's fundamental structure, examining role distribution, type coverage, and synergy between team members.

**Meta Comparison Engine**
The tool automatically downloads and compares your team against current high-level competitive data from Smogon.

**AI-Powered Suggestions**
Leverages a local LLM (via Ollama) to provide qualitative feedback and improvement ideas for your team.

**Strategic Weakness Detection**
MetaMatch performs deep analysis to uncover strategic vulnerabilities, such as shared type weaknesses across your team.

## How the Analysis Works

**Data Processing Pipeline**
The system ingests your team data (from Pokémon Showdown format) and cross-references it against extensive databases of competitive Pokemon statistics, including usage rates and type data from PokeAPI.

**Meta Intelligence**
The `smogon_scrape.py` script maintains up-to-date information on the competitive landscape by downloading the latest usage stats for multiple competitive tiers. This ensures recommendations are relevant to the current meta.

**Improvement Algorithms**
The recommendation engine (powered by a local LLM) doesn't just identify problems—it suggests specific, actionable solutions.

## What You Get

- **Detailed team composition breakdown** showing role distribution and synergy analysis
- **Meta positioning report** explaining where your team stands in the competitive landscape
- **Specific improvement recommendations** with alternative Pokemon and moveset suggestions
- **Weakness identification** highlighting exploitable gaps in your team structure

MetaMatch transforms team building from guesswork into informed decision-making, giving you the analytical edge needed to compete with confidence in the ever-evolving world of competitive Pokemon.

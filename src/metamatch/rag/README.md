# MetaMatch RAG Pipeline

This directory contains the core components for the Retrieval-Augmented Generation (RAG) system used in MetaMatch. The pipeline scrapes competitive strategy guides from Smogon, embeds them into a vector space, and stores them for semantic retrieval by the AI coach.

## 📂 Architecture

### 1. `scraper.py` (ETL: Extract, Transform, Load)
*   **Purpose:** Fetches raw HTML strategy guides from the Smogon Strategy Dex.
*   **Process:**
    1.  Uses `BeautifulSoup` to parse HTML.
    2.  Extracts key sections: "Moves", "Checks and Counters", and "Team Options".
    3.  Cleanses text to remove whitespace artifacts and boilerplate.
*   **Target:** Focuses on Generation 9 OU (OverUsed) strategies.

### 2. `store.py` (Vector Database Interface)
*   **Tech Stack:** `ChromaDB` (Vector Store) + `Sentence-Transformers` (Embedding Model).
*   **Embedding Model:** Uses `all-MiniLM-L6-v2` (384 dimensions) for efficient, high-performance semantic similarity.
*   **Functions:**
    *   `add_documents()`: Embeds and upserts text chunks into the `smogon_strategies` collection.
    *   `query_strategies()`: Performs K-Nearest Neighbors (KNN) search to find the most relevant advice for a user's query.

### 3. `build_index.py` (Orchestration)
*   **Purpose:** The "One-Click" initialization script.
*   **Workflow:**
    1.  Calls `scraper.py` to get the latest Top 50 meta Pokemon strategies.
    2.  Chunks the data into semantically meaningful segments.
    3.  Calls `store.py` to persist these embeddings into `./data/chroma_db/`.

## 🔄 Data Flow

```
[Smogon Dex] 
    ⬇️ (scraper.py)
[Raw Text] "Gholdengo checks include..."
    ⬇️ (sentence-transformers)
[Vector Embedding] [0.12, -0.45, ...]
    ⬇️ (store.py)
[ChromaDB] ./data/chroma_db/
    ⬇️ (suggestions.py)
[RAG Context] "SOURCE: Gholdengo checks..." -> LLM Prompt
```

## 🚀 Usage

To rebuild the vector database (e.g., after a meta shift):

```bash
# From project root
python src/metamatch/rag/build_index.py
```
*Note: This will populate `data/chroma_db/` with the latest strategies.*

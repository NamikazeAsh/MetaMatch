import sys

# --- SQLite FIX FOR DEPLOYMENT ---
# Streamlit Community Cloud uses an older version of sqlite3. 
# ChromaDB requires a newer version.
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass # Locally we might not have it or need it
# ---------------------------------

import chromadb
from sentence_transformers import SentenceTransformer
import os
import shutil
from metamatch import config

# Persist DB in the data directory
DB_PATH = config.DATA_DIR / "chroma_db"
EMBEDDING_MODEL_NAME = 'BAAI/bge-small-en-v1.5'

def get_client():
    """
    Returns a persistent ChromaDB client.
    """
    # Ensure the directory exists
    DB_PATH.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(DB_PATH))

def get_collection():
    """
    Returns the strategies collection, creating it if needed.
    """
    client = get_client()
    return client.get_or_create_collection(name="pokemon_strategies")

def get_model():
    """
    Returns the embedding model.
    """
    return SentenceTransformer(EMBEDDING_MODEL_NAME)

def rebuild_index(chunks):
    """
    Wipes the existing index and rebuilds it with new chunks.
    """
    print("Initializing embedding model...")
    model = get_model()
    
    client = get_client()
    
    # Delete existing collection to start fresh
    try:
        client.delete_collection("pokemon_strategies")
    except Exception:
        pass # Collection didn't exist or other error
        
    collection = client.create_collection(name="pokemon_strategies")
    
    print(f"Embedding {len(chunks)} chunks...")
    
    # Prepare data for batch insertion
    documents = [c['text'] for c in chunks]
    ids = [f"id_{i}" for i in range(len(chunks))]
    metadatas = [c['metadata'] for c in chunks]
    
    # Compute embeddings
    embeddings = model.encode(documents).tolist()
    
    # Add to Chroma
    collection.add(
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids
    )
    print("Index successfully rebuilt.")

def query_strategies(query, n_results=3):
    """
    Queries the database for relevant strategies.
    """
    model = get_model()
    collection = get_collection()
    
    query_embedding = model.encode([query]).tolist()
    
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=n_results
    )
    
    # Flatten results
    hits = []
    if results['documents']:
        for i in range(len(results['documents'][0])):
            hits.append({
                "text": results['documents'][0][i],
                "metadata": results['metadatas'][0][i],
                "distance": results['distances'][0][i]
            })
            
    return hits

import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Tuple

class SemanticRouter:
    def __init__(self, model_name="all-MiniLM-L6-v2"):
        # Load the lightweight embedding model
        # This matches the model used in your RAG pipeline to save memory/downloads
        self.model = SentenceTransformer(model_name)
        
        # Define Anchor Phrases for each Route
        # These are the "centroids" for each intent
        self.routes = {
            "mechanics": [
                "Does Rotom-Wash resist Ground?",
                "How much damage does Earthquake do to Heatran?",
                "Is Gengar faster than Dragapult?",
                "What is the speed tie between these two?",
                "Does Mold Breaker ignore Levitate?",
                "Type matchup analysis",
                "Damage calculation facts",
                "Will I survive a Close Combat?",
                "Who outspeeds whom?",
                "is it weak to",
                "is it faster than"
            ],
            "strategy": [
                "How do I beat Stall teams?",
                "What is the best win condition for this team?",
                "How do I use Kingambit effectively?",
                "What is a good lead against Hyper Offense?",
                "Explain the Volt-Turn combo",
                "General gameplan advice",
                "How to pilot this team",
                "What is the strategy for this Pokemon?",
                "How do I counter rain teams?",
                "how to play",
                "strategic guide",
                "win condition"
            ],
            "builder": [
                "Is this moveset good?",
                "Suggest a teammate for Cinderace",
                "What item should I put on Great Tusk?",
                "Fix my EVs",
                "What is the usage rate of Heavy-Duty Boots?",
                "Recommend a wallbreaker",
                "Analyze my team synergy",
                "Is this ability common?",
                "What is the standard set for Dragapult?",
                "moveset advice",
                "item recommendation",
                "popular items",
                "usage stats"
            ]
        }
        
        # Pre-compute embeddings for anchors
        self.route_embeddings = self._precompute_embeddings()

    def _precompute_embeddings(self) -> Dict[str, np.ndarray]:
        """Encodes all anchor phrases at initialization."""
        embeddings = {}
        for route, phrases in self.routes.items():
            embeddings[route] = self.model.encode(phrases)
        return embeddings

    def route_query(self, query: str) -> Tuple[str, float]:
        """
        Classifies the query into 'mechanics', 'strategy', or 'builder'.
        Returns (route_name, confidence_score).
        """
        query_embedding = self.model.encode(query)
        
        best_route = "strategy" # Default fallback
        max_score = -1.0
        
        for route, anchors in self.route_embeddings.items():
            # Calculate Cosine Similarity with all anchors in this route
            # (Dot product of normalized vectors)
            scores = np.dot(anchors, query_embedding)
            
            # We take the max similarity found in this route's anchors
            route_score = np.max(scores)
            
            if route_score > max_score:
                max_score = route_score
                best_route = route
                
        return best_route, float(max_score)

# Singleton instance for import
_router_instance = None

def get_router():
    global _router_instance
    if _router_instance is None:
        _router_instance = SemanticRouter()
    return _router_instance

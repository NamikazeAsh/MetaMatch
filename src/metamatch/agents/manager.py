from .router import get_router
from .tactician import TacticianAgent
from .coach import CoachAgent
from .auditor import AuditorAgent

class AgentManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None or not hasattr(cls._instance, 'router'):
            instance = super(AgentManager, cls).__new__(cls)
            instance.router = get_router()
            instance.tactician = TacticianAgent()
            instance.coach = CoachAgent()
            instance.auditor = AuditorAgent()
            cls._instance = instance
        return cls._instance

    def get_response(self, query: str, team_context: dict, team_weakness: dict = None):
        """
        Main entry point. Routes the query and dispatches to the correct agent.
        Returns a generator (stream).
        """
        # 1. Route
        route, confidence = self.router.route_query(query)
        
        # 2. Dispatch (low confidence queries go to the Coach, the most general agent)
        if route == "mechanics":
            return self.tactician.run(query, team_context, team_weakness)

        elif route == "builder":
            return self.auditor.run(query, team_context)

        else: # Default to Strategy/Coach
            return self.coach.run(query, team_context)

    def get_active_agent_name(self, query: str) -> str:
        """Helper for UI to show which agent is working"""
        route, _ = self.router.route_query(query)
        
        personas = {
            "mechanics": "Clemont 🧪",
            "strategy": "Professor Oak 📜",
            "builder": "Brock 🍳",
            "fallback": "Professor Oak 📜"
        }
        return personas.get(route, "Unknown Agent")

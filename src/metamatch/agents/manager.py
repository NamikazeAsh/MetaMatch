from metamatch.engine.planner import plan_query
from metamatch.engine.solvers import solve
from metamatch.engine.sets import likely_set
from metamatch.logic_engine import describe_likely_set
from .router import get_router
from .tactician import TacticianAgent
from .coach import CoachAgent
from .auditor import AuditorAgent
from .grounded import GroundedAgent

PERSONAS = {
    "mechanics": "Clemont 🧪",
    "strategy": "Professor Oak 📜",
    "builder": "Brock 🍳",
    "fallback": "Professor Oak 📜",
}


def _texts(stream):
    """OpenAI style chunk stream -> plain text chunks."""
    for chunk in stream:
        if chunk.choices:
            yield chunk.choices[0].delta.content or ""


class AgentManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None or not hasattr(cls._instance, 'router'):
            instance = super(AgentManager, cls).__new__(cls)
            instance.router = get_router()
            instance.tactician = TacticianAgent()
            instance.coach = CoachAgent()
            instance.auditor = AuditorAgent()
            instance.grounded = GroundedAgent()
            instance._last = (None, None)
            cls._instance = instance
        return cls._instance

    def _plan(self, query, team_context):
        """(plan, verdict) for the query; verdict is None for open questions. Cached for the persona lookup."""
        key = (query, id(team_context))
        if self._last[0] != key:
            plan = plan_query(query, team_context)
            self._last = (key, (plan, solve(plan) if plan.intent != "open" else None))
        return self._last[1]

    def _named_context(self, plan):
        """Likely set cards for named Pokemon that aren't on the user's team."""
        lines = []
        for name in plan.opponents[:3]:
            s = likely_set(name, plan.format_id)
            if s:
                lines.append(describe_likely_set(s, plan.format_id))
        return ("### LIKELY SETS FOR POKEMON YOU ASKED ABOUT\n" + "\n".join(lines) + "\n") if lines else ""

    def get_response(self, query: str, team_context: dict, team_weakness: dict = None, history: list = None):
        """
        Main entry point. Questions the engine can answer get a computed verdict;
        everything else is routed to an LLM agent. Returns a generator of text chunks.
        """
        plan, verdict = self._plan(query, team_context)
        if verdict:
            return self.grounded.run(query, verdict)

        route, confidence = self.router.route_query(query)
        named = self._named_context(plan)

        # Low confidence queries go to the Coach, the most general agent
        if route == "mechanics":
            return _texts(self.tactician.run(query, team_context, team_weakness))
        elif route == "builder":
            return _texts(self.auditor.run(query, team_context, history, named))
        else:
            return _texts(self.coach.run(query, team_context, history, named))

    def get_active_agent_name(self, query: str, team_context: dict = None) -> str:
        """Helper for UI to show which agent is working"""
        if team_context is not None:
            _, verdict = self._plan(query, team_context)
            if verdict:
                return PERSONAS[verdict.persona]
        route, _ = self.router.route_query(query)
        return PERSONAS.get(route, "Unknown Agent")

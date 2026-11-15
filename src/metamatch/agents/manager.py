import re
from dataclasses import dataclass

from metamatch.engine import dialogue
from metamatch.engine.planner import plan_query
from metamatch.engine.solvers import solve
from metamatch.engine.sets import likely_set
from metamatch.engine.briefing import strategy_briefing
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


CLARIFY = ("I couldn't tell which opposing Pokemon you mean. Could you name it? "
           "Full names and common nicknames like Lando, Pex or Corv both work.")
CALC_DOWN = ("The damage calculator isn't running (it needs Node.js and `npm install` in src/metamatch/engine), "
             "so I can't work that out right now, and I won't guess at damage or Speed numbers.")
# "thanks!", "hi": a friendly line, not a strategy essay built on whatever the index returns for "thanks"
SMALLTALK_RE = re.compile(r"^\s*(?:thanks?(?: a lot| so much)?|thank you(?: so much)?|thx|ty|cheers|ok(?:ay)?|cool|nice|great|"
                          r"got it|perfect|awesome|hi|hello|hey|yo|good morning|good evening)[\s!.]*(?:oak|brock|clemont)?[\s!.]*$",
                          re.I)
GREETING_RE = re.compile(r"^\s*(?:hi|hello|hey|yo|good morning|good evening)\b", re.I)
GREETING = ("Hello there! Ask me about any matchup, your leads, your win condition, a set or a teammate, "
            "and I'll check it against the engine.")
THANKS = "Anytime! Ask away whenever something comes up, like a matchup, a lead or a set to check."
# Answers that need the calc: without it, a planned question gets this notice, never unchecked model text
CALC_INTENTS = {"speed", "speed_spread", "ko", "damage", "checks", "matchup", "win", "lead", "threats", "gameplan",
                "tera", "switchins", "member"}
# Set, item, spread and teammate questions are Brock's: he has the ladder numbers, Oak and Clemont don't. In the
# 2026 11 12 audit six of these ("Is Life Orb the best item on Venusaur", "What should I replace Alomomola with")
# reached Oak through the router's low confidence fallback
BUILDER_RE = re.compile(r"\b(?:items?|movesets?|sets?(?! up)|evs?|spreads?|natures?|investment|tera(?: type)?|abilit(?:y|ies)|"
                        r"teammates?|partners?|replace\w*|swap\w*|wallbreaker|slot|specs|band|scarf|boots|life orb|"
                        r"leftovers|sash|helmet|assault vest|eviolite|booster)\b", re.I)
STRATEGY_RE = re.compile(r"\bhow (?:do|can|should) (?:i|we) (?:beat|play|win|handle|deal|stop|counter|use|pilot)\b|"
                         r"\b(?:win ?con\w*|game ?plan|lead\w*|against|vs\.?|versus|matchups?|archetype|stall|offense|rain|sun)\b",
                         re.I)


@dataclass
class Turn:
    """One chat question, worked out once: how it reads in context, its plan, the engine's answer and the persona."""
    query: str                  # as the user typed it
    reading: dialogue.Reading   # the full question after the dialogue state
    plan: object
    verdict: object = None
    route: str = ""
    persona: str = ""

    @property
    def text(self):
        return self.reading.text

    @property
    def rewritten(self):
        return self.reading.text != self.query


class AgentManager:
    """Shared by every chat session, so it holds no per conversation state: that lives in the DialogueState the
    caller passes in."""
    _instance = None

    def __new__(cls):
        if cls._instance is None or not hasattr(cls._instance, 'router'):
            instance = super(AgentManager, cls).__new__(cls)
            instance.router = get_router()
            instance.tactician = TacticianAgent()
            instance.coach = CoachAgent()
            instance.auditor = AuditorAgent()
            instance.grounded = GroundedAgent()
            cls._instance = instance
        return cls._instance

    def _named_context(self, plan):
        """Likely set cards for named Pokemon that aren't on the user's team."""
        lines = []
        for name in plan.opponents[:3]:
            s = likely_set(name, plan.format_id)
            if s:
                lines.append(describe_likely_set(s, plan.format_id))
        return ("### LIKELY SETS FOR POKEMON YOU ASKED ABOUT\n" + "\n".join(lines) + "\n") if lines else ""

    def prepare(self, query: str, team_context: dict, state: dialogue.DialogueState = None) -> Turn:
        """Reads the question in the context of the conversation, plans it and solves it if the engine can."""
        reading = dialogue.resolve(query, state, team_context)
        plan = plan_query(reading.text, team_context)
        if reading.why_of is not None:
            return Turn(query, reading, plan, reading.why_of, persona=PERSONAS[reading.why_of.persona])
        verdict = solve(plan) if plan.intent not in ("open", "clarify") else None
        if verdict:
            return Turn(query, reading, plan, verdict, persona=PERSONAS[verdict.persona])
        if plan.intent == "clarify":
            return Turn(query, reading, plan, persona=PERSONAS["mechanics"])
        if SMALLTALK_RE.match(query):
            return Turn(query, reading, plan, route="smalltalk", persona=PERSONAS["strategy"])
        if plan.intent in CALC_INTENTS:
            from metamatch.engine import calc
            if not calc.available():
                return Turn(query, reading, plan, route="calc_down", persona=PERSONAS["mechanics"])
        route, _ = self.router.route_query(reading.text)
        if BUILDER_RE.search(reading.text) and not STRATEGY_RE.search(reading.text):
            route = "builder"
        return Turn(query, reading, plan, route=route, persona=PERSONAS.get(route, PERSONAS["fallback"]))

    def respond(self, turn: Turn, team_context: dict, team_weakness: dict = None):
        """The answer to a prepared turn, as a generator of text chunks."""
        if turn.verdict:
            return self.grounded.run(turn.text, turn.verdict, team_context)
        if turn.plan.intent == "clarify":
            return iter([CLARIFY])
        if turn.route == "calc_down":
            return iter([CALC_DOWN])
        if turn.route == "smalltalk":
            return iter([GREETING if GREETING_RE.match(turn.query) else THANKS])
        named = self._named_context(turn.plan)
        if turn.route == "mechanics":
            return self.tactician.run(turn.text, team_context, team_weakness)
        if turn.route == "builder":
            return self.auditor.run(turn.text, team_context, turn.plan)
        briefing = strategy_briefing(team_context, turn.plan.opponents)
        return self.coach.run(turn.text, team_context, named, briefing, plan=turn.plan)

    def remember(self, turn: Turn, state: dialogue.DialogueState = None) -> dialogue.DialogueState:
        """The dialogue state after answering `turn`."""
        return dialogue.update(state, turn.reading, turn.plan, turn.verdict, clarified=turn.plan.intent == "clarify")

    def replay(self, history: list, team_context: dict) -> dialogue.DialogueState:
        """Rebuilds the dialogue state from stored user turns, for a conversation reopened in a new session."""
        state = None
        for m in history or []:
            if m.get("role") == "user":
                reading = dialogue.resolve(m["content"], state, team_context)
                plan = plan_query(reading.text, team_context)
                state = dialogue.update(state, reading, plan, clarified=plan.intent == "clarify")
        return state

    def get_response(self, query: str, team_context: dict, team_weakness: dict = None, history: list = None,
                     state: dialogue.DialogueState = None):
        """One shot entry point (benchmarks, scripts): prepare and respond. `history` rebuilds the state if none
        is given."""
        if state is None and history:
            state = self.replay(history, team_context)
        return self.respond(self.prepare(query, team_context, state), team_context, team_weakness)

    def get_active_agent_name(self, query: str, team_context: dict = None) -> str:
        """The persona that answers `query` on its own (no conversation context)."""
        if team_context is not None:
            return self.prepare(query, team_context).persona
        route, _ = self.router.route_query(query)
        return PERSONAS.get(route, PERSONAS["fallback"])

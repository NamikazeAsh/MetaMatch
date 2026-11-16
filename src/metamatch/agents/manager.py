import re
from dataclasses import dataclass, field

from metamatch.engine import dialogue
from metamatch.engine.planner import plan_query
from metamatch.engine.solvers import solve
from metamatch.engine.sets import likely_set
from metamatch.engine.briefing import strategy_briefing
from metamatch.logic_engine import describe_likely_set
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
# Questions nobody can answer from data: a fixed, honest line and the nearest thing the engine can answer instead
DECLINES = [
    ("next_move", re.compile(r"\bwhat will (?:they|my opponent|the opponent|he|she)\b|\bpredict\w*\b|"
                             r"\b(?:will|is going to|gonna|would)\b[^?.!]*\b(?:they|he|she|the opponent|my opponent|opp)\b[^?.!]*"
                             r"\b(?:lead|click|use|switch|go for|do|bring|send)\b", re.I),
     "I can't know what your opponent will click. What I can show you is their usual set and how each of your Pokemon "
     "does against it: ask me how to beat the Pokemon you're worried about."),
    ("odds", re.compile(r"\bwill i win\b|\b(?:odds|chances?) (?:of|to|i) win\w*\b|\bwinnable\b|\bwin ?rate\b|"
                        r"\bam i (?:favou?red|going to win)\b", re.I),
     "I don't predict results: games come down to the player. I can show you how your team lines up against a threat, "
     "or your game plan."),
    ("luck", re.compile(r"\bhax\w*\b|\bwhy did i lose\b|\b(?:bad )?luck\w*\b|\brigged\b", re.I),
     "Luck in a past game isn't something I can measure. If you name a move or ability, I can tell you exactly how "
     "it works."),
    ("format", re.compile(r"\b(?:in|for|playing|play) doubles\b|\bdoubles (?:format|battles?|tiers?|teams?)\b|"
                          r"\b(?:vgc|random battles?|randbats|battle stadium|bss|little cup|monotype|"
                          r"gen ?[1-8]\b|ubers)\b", re.I),
     "I'm built for {label} singles with your team, so I can't judge other formats like VGC, doubles or older "
     "generations."),
    ("future", re.compile(r"\b(?:will|gonna|going to|get)\b[^?.!]*\b(?:banned|ban|suspect\w*|tier ?shift\w*|drop to|"
                          r"rise to)\b", re.I),
     "I can't predict bans or tier shifts. The Meta page shows which Pokemon are rising and falling in usage."),
]


def decline_for(query, format_id):
    """The decline line for a question nobody can answer from data, or None."""
    from metamatch import config
    label = config.format_info(format_id)["label"] if format_id else "OU"
    for kind, pattern, line in DECLINES:
        if pattern.search(query):
            # A question about the team's own format ("is this good in Ubers" on an Ubers team) is not out of scope
            if kind == "format" and re.search(rf"\b{re.escape(label)}\b", query, re.I):
                continue
            return line.format(label=label)
    return None


# Answers that need the calc: without it, a planned question gets this notice, never unchecked model text
CALC_INTENTS = {"speed", "speed_spread", "ko", "damage", "checks", "matchup", "win", "lead", "threats", "gameplan",
                "tera", "switchins", "member", "score", "archetype"}
# Set, item, spread and teammate questions are Brock's: he has the ladder numbers, Oak and Clemont don't. In the
# 2026 11 12 audit six of these ("Is Life Orb the best item on Venusaur", "What should I replace Alomomola with")
# reached Oak through the router's low confidence fallback
BUILDER_RE = re.compile(r"\b(?:items?|moves?|movesets?|sets?(?! up)|evs?|spreads?|natures?|investment|tera(?: type)?|abilit(?:y|ies)|"
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
    meta: dict = field(default_factory=dict)   # what the voice did (opener used, slots from the model)

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
        if cls._instance is None or not hasattr(cls._instance, 'grounded'):
            instance = super(AgentManager, cls).__new__(cls)
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
        declined = decline_for(reading.text, plan.format_id)
        if declined:
            return Turn(query, reading, plan, route="decline", persona=PERSONAS["strategy"], meta={"decline": declined})
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
        route = self._open_route(reading.text)
        return Turn(query, reading, plan, route=route, persona=PERSONAS.get(route, PERSONAS["fallback"]))

    def _open_route(self, text):
        """Category of an open question: building words go to Brock, everything else to Oak. The old embedding router
        (and Clemont's free text) is only loaded for the legacy voice kept for the final comparison."""
        from .grounded import voice_mode
        if voice_mode() == "legacy":
            from .router import get_router
            route, _ = get_router().route_query(text)
            return "builder" if BUILDER_RE.search(text) and not STRATEGY_RE.search(text) else route
        return "builder" if BUILDER_RE.search(text) and not STRATEGY_RE.search(text) else "strategy"

    def respond(self, turn: Turn, team_context: dict, team_weakness: dict = None, state: dialogue.DialogueState = None):
        """The answer to a prepared turn, as a generator of text chunks."""
        if turn.verdict:
            return self.grounded.run(turn.text, turn.verdict, team_context, plan=turn.plan, state=state, meta=turn.meta)
        if turn.plan.intent == "clarify":
            return iter([CLARIFY])
        if turn.route == "calc_down":
            return iter([CALC_DOWN])
        if turn.route == "smalltalk":
            return iter([GREETING if GREETING_RE.match(turn.query) else THANKS])
        if turn.route == "decline":
            return iter([turn.meta["decline"]])
        named = self._named_context(turn.plan)
        if turn.route == "mechanics":
            from .tactician import TacticianAgent   # legacy voice only
            return TacticianAgent().run(turn.text, team_context, team_weakness)
        if turn.route == "builder":
            return self.auditor.run(turn.text, team_context, turn.plan, state=state, meta=turn.meta)
        from .grounded import voice_mode
        # Only the legacy voice still reads the threat briefing; the open fallback offers questions instead
        briefing = strategy_briefing(team_context, turn.plan.opponents) if voice_mode() == "legacy" else None
        return self.coach.run(turn.text, team_context, named, briefing, plan=turn.plan, state=state, meta=turn.meta)

    def remember(self, turn: Turn, state: dialogue.DialogueState = None) -> dialogue.DialogueState:
        """The dialogue state after answering `turn`."""
        state = dialogue.update(state, turn.reading, turn.plan, turn.verdict, clarified=turn.plan.intent == "clarify")
        # Recent openers and moods keep the persona from repeating itself turn after turn
        if turn.meta.get("opener"):
            state.recent_openers = (state.recent_openers + [turn.meta["opener"]])[-5:]
        if turn.meta.get("mood"):
            state.recent_moods = (state.recent_moods + [turn.meta["mood"]])[-3:]
        return state

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
        return self.respond(self.prepare(query, team_context, state), team_context, team_weakness, state)

    def get_active_agent_name(self, query: str, team_context: dict = None) -> str:
        """The persona that answers `query` on its own (no conversation context)."""
        if team_context is not None:
            return self.prepare(query, team_context).persona
        return PERSONAS.get(self._open_route(query), PERSONAS["fallback"])

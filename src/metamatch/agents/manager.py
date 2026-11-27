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
                          r"got it|perfect|awesome|hi|hello|hey|yo|sup|wh?at'?s up|good morning|good evening)"
                          r"(?:[\s,!.]*how(?:'?s| is) it go(?:in'?|ing))?[\s!.?]*(?:oak|brock|clemont)?[\s!.?]*$",
                          re.I)
GREETING_RE = re.compile(r"^\s*(?:hi|hello|hey|yo|sup|wh?at'?s up|good morning|good evening)\b", re.I)
GREETING = ("Hello there! Ask me about any matchup, your leads, your win condition, a set or a teammate, "
            "and I'll check it against the engine.")
THANKS = "Anytime! Ask away whenever something comes up, like a matchup, a lead or a set to check."
# Questions nobody can answer from data: a fixed, honest line and the nearest thing the engine can answer instead
DECLINES = [
    ("other_game", re.compile(r"\bpok[eé]mon go\b|\b(?:great|ultra|master) league\b|\b(?:pocket|tcg|unite|nuzlocke)\b|"
                              r"\btrading card\b", re.I),
     "I only know competitive {label} singles on Showdown, so I can't help with other Pokemon games."),
    ("events", re.compile(r"\bwho (?:will|is going to|gonna) win\b|\b(?:worlds|nationals|regionals|naic|euic|ocic)\b", re.I),
     "I can't predict who wins tournaments: games come down to the players. I can show you how your team lines up "
     "against the Pokemon you'll face."),
    ("illegal", re.compile(r"\bhack(?:ed|s|ing)?\b|\billegal\b|\bcheat\w*\b", re.I),
     "I only help with legal sets. The Audit tab checks your team's legality, and I can suggest legal sets that do "
     "the job."),
    ("autopilot", re.compile(r"\bplay (?:the game |it |a game )?for me\b|\b(?:battle|ladder) for me\b|\bbot\b", re.I),
     "I can't play for you, but I can tell you how each of your Pokemon does against whatever you're facing."),
    ("hidden", re.compile(r"\bbefore team preview\b|\bopponent'?s? (?:team|set|moves?) before\b|\bsee their team\b",
                          re.I),
     "I can't see your opponent's team before team preview. Once you see it, paste it into Matchup Preview to see "
     "every matchup."),
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
    ("format", re.compile(r"\bdoubles\b|"
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


# A set word inside a question about Speed, typing, a mechanic or a moment in a game doesn't make it a set question:
# the 2026 11 26 coverage audit found "what does tera steel do for tusk defensively", "how does choice lock work if i
# tera" and "should i tera kingambit now" all answered with Brock's set listing
# "speed" alone would catch the move Extreme Speed in "Dragonite sets? tera normal extreme speed or something else"
NOT_BUILDING_RE = re.compile(r"\b(?:fast|faster|slower|outspeed\w*|speed (?:tier|stat|control)\w*|defensive\w*|resist\w*|"
                             r"weak\w*|immun\w*|"
                             r"switch(?:es)? into|how does\b[^?.!]*\bwork|how do\b[^?.!]*\bwork|does\b[^?.!]*\bwork|"
                             r"what happens|now|this turn|save it|survive\w*|tank\w*|live)\b", re.I)


def _is_building(text):
    return bool(BUILDER_RE.search(text) and not STRATEGY_RE.search(text) and not NOT_BUILDING_RE.search(text))


# The learned classifier (engine/intent.py) only declines over a rule's answer when it is this sure
SURE_OUT_OF_SCOPE = 0.9
# Below the sure threshold but at least this confident, an answerable best guess is answered with chips under it
ANSWER_FLOOR = 0.2
# Calculator and lookup questions the planner's rules answer first: they read the details exactly (MetaBench 100%)
RULE_KINDS = {"speed", "speed_spread", "ko", "damage", "type", "stat", "usage"}
# An unsure question with building words goes to Brock only when the classifier also leans to a building kind: an
# item word alone ("specs draco into assault vest raging bolt") sent damage and Speed questions to his set listing
BUILDING_KINDS = {"sets", "teammate", "compare", "how_to_use", "usage"}
OUT_OF_SCOPE = ("That's outside what I cover: I'm built for {label} singles with the team you pasted. Ask me about a "
                "matchup, a member, your threats or your game plan.")
IN_BATTLE_PREFIX = ("I can't see the battle itself, so I can't call this turn for you. Here's how your team lines up "
                    "against {opp}:")
IN_BATTLE = ("I can't see the battle itself, so I can't call this turn for you. Tell me which opposing Pokemon is in "
             "and I'll show you who beats it and who can switch into it.")
UNSURE = "I'm not quite sure what you're asking. Did you mean one of these?"
SWITCH_WORD_RE = re.compile(r"\bswitch\w*\b|\bsend in\b|\bgo(?:es)? in\b|\bbring in\b", re.I)
# Kinds that need an opposing Pokemon; without one the chat asks which, instead of answering something else
NEEDS_OPPONENT = {"speed", "ko", "damage", "checks", "switchins", "matchup"}
# A question per kind for the "did you mean" buttons, filled with the Pokemon the question names
KIND_QUESTIONS = {
    "checks": "How do I beat {opp}?", "switchins": "What switches into {opp}?",
    "matchup": "How does my {me} do against {opp}?", "speed": "Does my {me} outspeed {opp}?",
    "damage": "How much damage does my {mine} do to {opp}?", "ko": "How much damage does my {mine} do to {opp}?",
    "stat": "What are {any}'s stats?",
    "member": "What does my {me} do on my team?", "usage": "What does {any} usually run?",
    "sets": "What set should {any} run?", "how_to_use": "How do I use {any}?", "type": "What is {any} weak to?",
    "score": "Is my team good?", "threats": "What are my biggest threats?", "gameplan": "Walk me through my game plan",
    "win": "What's my win condition?", "lead": "What should I lead with?", "tera": "Who should I Tera?",
    "team_type": "What is my team weak to?", "teammate": "What teammate should I add?",
    "meta_trends": "What's rising this month?", "archetype": "How does my team do against stall?",
}


def _prefixed(prefix, chunks):
    yield prefix + "\n\n"
    yield from chunks


ALSO = "_Not what you asked? Try one of these:_"


def _with_also(chunks, questions):
    """The answer with "did you mean" chips under its spoken part, before the collapsed engine facts."""
    from .grounded import FACTS_MARK
    from .suggest import marker
    extra = f"\n\n{ALSO}" + marker(questions)
    done = False
    for chunk in chunks:
        if not done and FACTS_MARK in chunk:
            head, _, tail = chunk.partition(FACTS_MARK)
            chunk, done = head + extra + FACTS_MARK + tail, True
        yield chunk
    if not done:
        yield extra


def _classify(text, team):
    """The classifier's reading of a question, or None without a trained model or the embedding model."""
    try:
        from metamatch.engine import intent
        return intent.classify(text, team) if intent.available() else None
    except Exception as e:   # the model files can't load (offline first run): the rules alone
        print(f"Intent classifier unavailable: {e}")
        return None


def _label(format_id):
    from metamatch import config
    return config.format_info(format_id)["label"] if format_id else "OU"


def named_attack(text, team):
    """(member, move) when the question names a move exactly one of your members carries, by name or nickname."""
    from metamatch.engine.constraints import MOVE_NICKNAMES
    lowered = (text or "").lower()
    asked = {full for nick, full in MOVE_NICKNAMES.items() if re.search(rf"\b{re.escape(nick)}\b", lowered)}
    hits = []
    for member in (team or {}).values():
        for move in member.get("Moves") or []:
            name = move.get("name") if isinstance(move, dict) else move
            if name and (name in asked or re.search(rf"\b{re.escape(name.lower())}\b", lowered)):
                hits.append((member["Pokemon"], name))
    return hits[0] if len({m for m, _ in hits}) == 1 else (None, None)


def unsure_options(kinds, plan, team):
    """The "did you mean" questions for the classifier's top kinds, skipping ones that need a Pokemon it lacks."""
    me = (plan.user or next(iter((team or {}).values()), {}) or {}).get("Pokemon")
    opp = plan.opponent
    # A damage chip names only a member the question named, or the one member carrying the move it names:
    # guessing the attacker would answer something else
    mine = (plan.user or {}).get("Pokemon")
    attacker, move = named_attack(getattr(plan, "query", ""), team)
    names = {"me": me, "mine": mine or attacker, "opp": opp, "any": opp or mine}
    out = []
    for kind in kinds:
        template = KIND_QUESTIONS.get(kind)
        if kind in ("damage", "ko") and move and names["mine"] == attacker and opp:
            # Keep the opposing item the question stated: Assault Vest turns 149% into 100% on Raging Bolt
            item = (getattr(plan, "opp_overrides", None) or {}).get("item")
            template = f"How much damage does my {{mine}}'s {move} do to {item + ' ' if item else ''}{{opp}}?"
        if not template:
            continue
        needed = re.findall(r"\{(\w+)\}", template)
        if all(names.get(n) for n in needed) and template.format(**names) not in out:
            out.append(template.format(**names))
    return out


def meta_trends(format_id):
    """This month's ladder in a few lines, from MetaFlash's data (meta_pulse): who rose, fell and leads."""
    from metamatch import meta_pulse
    label = _label(format_id)
    cards = meta_pulse.pulse(format_id, n=10, with_sets=False) or []
    if not cards:
        return f"I don't have this month's {label} usage history yet, so I can't say what's moving."
    risers = [c for c in cards if c["kind"] in ("riser", "newcomer")][:3]
    fallers = [c for c in cards if c["kind"] == "faller"][:2]
    top = [r["name"] for r in meta_pulse.leaderboard(format_id, n=3)]
    lines = [f"Here's what's moving on the {label} ladder this month:"]
    lines += [f"* **{c['name']}**: {c['headline'].lower()} ({c['usage']:.1f}% of teams)." for c in risers]
    lines += [f"* **{c['name']}**: {c['headline'].lower()} ({c['usage']:.1f}%)." for c in fallers]
    if top:
        lines.append(f"\nThe most used are {', '.join(top[:-1])} and {top[-1]}. MetaFlash on Home has the full picture.")
    return "\n".join(lines)


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
        """Reads the question in the context of the conversation, plans it and solves it if the engine can.

        Who decides what was asked, measured on a sealed blind set (docs/research/intent_2026_11_27, 168 questions):
        the planner's rules keep the calculator questions (Speed, KO, damage, type, stat, usage), where they read
        every detail precisely; the learned classifier (engine/intent.py) decides the rest when it is sure; when it
        isn't, the chat asks "did you mean". That order got 62% of questions right and only 11 confidently wrong,
        against 54% and 41 for rules first (the rules misread about half of the new phrasings they did place)."""
        reading = dialogue.resolve(query, state, team_context)
        plan = plan_query(reading.text, team_context)
        if reading.why_of is not None:
            return Turn(query, reading, plan, reading.why_of, persona=PERSONAS[reading.why_of.persona])
        declined = decline_for(reading.text, plan.format_id)
        if declined:
            return Turn(query, reading, plan, route="decline", persona=PERSONAS["strategy"], meta={"decline": declined})
        guess = _classify(reading.text, team_context)
        meta = {"kind": guess["kind"], "confidence": round(guess["confidence"], 3)} if guess else {}
        if guess and guess["kind"] == "out_of_scope" and guess["confidence"] >= SURE_OUT_OF_SCOPE:
            return Turn(query, reading, plan, route="decline", persona=PERSONAS["strategy"],
                        meta={**meta, "decline": OUT_OF_SCOPE.format(label=_label(plan.format_id))})
        rules_first = guess is None or plan.intent in RULE_KINDS
        verdict = solve(plan) if plan.intent not in ("open", "clarify") and rules_first else None
        if verdict:
            return Turn(query, reading, plan, verdict, persona=PERSONAS[verdict.persona], meta=meta)
        if SMALLTALK_RE.match(query):
            return Turn(query, reading, plan, route="smalltalk", persona=PERSONAS["strategy"])
        # The classifier's turn: everything but the calculator questions the rules placed
        if guess and guess["sure"] and not (plan.intent == "clarify" and guess["kind"] in ("speed", "ko", "damage")):
            turn = self._classified(query, reading, plan, guess["kind"], team_context, meta)
            if turn:
                return turn
            verdict = solve(plan) if plan.intent not in ("open", "clarify") else None
            if verdict:
                return Turn(query, reading, plan, verdict, persona=PERSONAS[verdict.persona], meta=meta)
        elif guess and plan.intent != "clarify" and not (_is_building(reading.text) and guess["kind"] in BUILDING_KINDS):
            # Unsure, but the engine can answer its best guess: answer it, with the other readings as chips under it.
            # On the 2026 11 27 sealed set, unsure questions above the floor whose guess solved were right 18 times,
            # had the right reading among the chips 6 times, and were wrong with no way back once
            if guess["confidence"] >= ANSWER_FLOOR and guess["kind"] not in ("out_of_scope", "smalltalk"):
                turn = self._classified(query, reading, plan, guess["kind"], team_context, meta)
                if turn and turn.verdict:
                    others = [k for k, _ in guess["top"][1:]]
                    turn.meta = {**turn.meta, "also": unsure_options(others, turn.plan, team_context)}
                    return turn
            # Unsure, and the rules would only give Oak's generic fallback: offer the likely readings instead
            return Turn(query, reading, plan, route="unsure", persona=PERSONAS["strategy"],
                        meta={**meta, "options": [k for k, _ in guess["top"]]})
        if plan.intent == "clarify":
            return Turn(query, reading, plan, persona=PERSONAS["mechanics"])
        if plan.intent in CALC_INTENTS:
            from metamatch.engine import calc
            if not calc.available():
                return Turn(query, reading, plan, route="calc_down", persona=PERSONAS["mechanics"])
        route = self._open_route(reading.text)
        return Turn(query, reading, plan, route=route, persona=PERSONAS.get(route, PERSONAS["fallback"]))

    def _classified(self, query, reading, plan, kind, team, meta):
        """The turn for a kind the classifier chose, or None to fall back to the open route."""
        from metamatch.engine.planner import PLANNED_KINDS
        if kind == "smalltalk":
            return Turn(query, reading, plan, route="smalltalk", persona=PERSONAS["strategy"], meta=meta)
        if kind == "out_of_scope":
            return Turn(query, reading, plan, route="decline", persona=PERSONAS["strategy"],
                        meta={**meta, "decline": OUT_OF_SCOPE.format(label=_label(plan.format_id))})
        if kind == "meta_trends":
            return Turn(query, reading, plan, route="meta", persona=PERSONAS["builder"], meta=meta)
        if kind == "in_battle":
            # No battle state to read: the closest engine answer about the Pokemon they're facing, said as such
            if plan.opponents:
                forced = plan_query(reading.text, team, force="switchins" if SWITCH_WORD_RE.search(reading.text)
                                    else "checks")
                verdict = solve(forced)
                if verdict:
                    return Turn(query, reading, forced, verdict, persona=PERSONAS[verdict.persona],
                                meta={**meta, "prefix": IN_BATTLE_PREFIX.format(opp=forced.opponent)})
            return Turn(query, reading, plan, route="in_battle", persona=PERSONAS["strategy"], meta=meta)
        if kind in PLANNED_KINDS:
            forced = plan_query(reading.text, team, force=kind)
            verdict = solve(forced)
            if verdict:
                return Turn(query, reading, forced, verdict, persona=PERSONAS[verdict.persona], meta=meta)
            # The kind needs a Pokemon the question doesn't name: ask for it rather than answer something else
            if kind in NEEDS_OPPONENT and not forced.opponents:
                forced.intent = "clarify"
                return Turn(query, reading, forced, persona=PERSONAS["mechanics"], meta=meta)
            if kind in ("teammate", "compare"):
                return Turn(query, reading, forced, route="builder", persona=PERSONAS["builder"], meta=meta)
            return None
        if kind == "sets":
            return Turn(query, reading, plan, route="builder", persona=PERSONAS["builder"], meta=meta)
        if kind == "how_to_use":
            return Turn(query, reading, plan, route="strategy", persona=PERSONAS["strategy"], meta=meta)
        return None

    def _open_route(self, text):
        """Category of an open question: building words go to Brock, everything else to Oak. The old embedding router
        (and Clemont's free text) is only loaded for the legacy voice kept for the final comparison."""
        from .grounded import voice_mode
        if voice_mode() == "legacy":
            from .router import get_router
            route, _ = get_router().route_query(text)
            return "builder" if BUILDER_RE.search(text) and not STRATEGY_RE.search(text) else route
        return "builder" if _is_building(text) else "strategy"

    def respond(self, turn: Turn, team_context: dict, team_weakness: dict = None, state: dialogue.DialogueState = None):
        """The answer to a prepared turn, as a generator of text chunks."""
        if turn.verdict:
            answer = self.grounded.run(turn.text, turn.verdict, team_context, plan=turn.plan, state=state, meta=turn.meta)
            prefix = turn.meta.get("prefix")
            answer = _prefixed(prefix, answer) if prefix else answer
            return _with_also(answer, turn.meta["also"]) if turn.meta.get("also") else answer
        if turn.plan.intent == "clarify":
            return iter([CLARIFY])
        if turn.route == "calc_down":
            return iter([CALC_DOWN])
        if turn.route == "smalltalk":
            return iter([GREETING if GREETING_RE.match(turn.query) else THANKS])
        if turn.route == "decline":
            return iter([turn.meta["decline"]])
        if turn.route == "meta":
            return iter([meta_trends(turn.plan.format_id)])
        if turn.route == "in_battle":
            return iter([IN_BATTLE])
        if turn.route == "unsure":
            from .suggest import marker, suggestions
            options = unsure_options(turn.meta.get("options", []), turn.plan, team_context)
            options = options or suggestions(turn.text, turn.plan, team_context)
            return iter([UNSURE + marker(options)])
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

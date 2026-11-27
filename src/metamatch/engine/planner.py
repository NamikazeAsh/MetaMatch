"""
Deterministic query planner: works out what a chat question is asking (intent) and about
what (team member, opponent, move, type, stat, explicit opponent set), so questions the
engine can answer never depend on the LLM reading facts correctly.
"""
import re
from dataclasses import dataclass, field

from metamatch import config
from metamatch.engine import constraints, rules
from metamatch.engine.dex import dex_for_format, to_id
from metamatch.engine.sets import likely_set
from metamatch.engine.names import find_pokemon, find_pokemon_spans

TYPES = ["Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison", "Ground",
         "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy"]
STAT_WORDS = {"hp": "hp", "attack": "atk", "atk": "atk", "defense": "def", "def": "def",
              "special attack": "spa", "spa": "spa", "special defense": "spd", "spd": "spd",
              "speed": "spe", "spe": "spe"}

USAGE_RE = re.compile(r"\b(most common|most used|usage|popular|what rank|ranked|ranking|standard (?:set|item|spread)|what (?:item|ability|tera|nature|spread|moves?)|"
                      r"which (?:item|ability|tera)|usual(?:ly)?|typical(?:ly)?|carr(?:y|ies)|common\s+(?:\w+\s+)?sets?|"
                      r"teammates? (?:of|for)|(?:who|what) (?:pairs?|goes|runs) (?:well )?with|"
                      r"(?:common|standard|popular|normal) (?:on|for))\b|\bsets?\W*$", re.I)
# "is Loaded Dice common on Garchomp": the share of one named option, not the top option
OPTION_ASK_RE = re.compile(r"\b(?:common|standard|popular|normal|usual|used|run|ran)\s+(?:on|for|with)\b|\bhow (?:common|popular|often)\b|"
                           r"\b(?:usually|typically|normally|often|ever) (?:carry|carries|run|runs|use|uses|hold|holds|have|has)\b", re.I)
# "Does my Kingambit beat Gholdengo?": one member against one opponent, from the same one on one as the Threat Board
MATCHUP_RE = re.compile(r"\b(?:beat|beats|win|wins|handle|handles|check|checks|counter|counters|lose|loses|losing) "
                        r"(?:to |against |vs\.? )?|\bmatch ?up\b|\b(?:good|bad|fine) (?:against|vs|into)\b|"
                        r"\b(?:dying|dies|die|died|fainting|faints?) to\b|\bgets? (?:ko'?d|killed|destroyed|swept|walled|"
                        r"outsped|one ?shot) by\b|\bstruggles? (?:with|against|vs)\b|"
                        # "how does my Corviknight do against Kingambit", "how does it fare vs", "hold up against"
                        r"\b(?:do|does|doing|fare|fares|faring|hold(?:s)? up|stack(?:s)? up|perform(?:s)?) "
                        r"(?:against|vs\.?|into)\b", re.I)
# "is great tusk still top 10", "what rank is kingambit", "did gholdengo fall off": where it sits on the ladder
RANK_FIELD_RE = re.compile(r"\b(?:rank\w*|top \d+|top ten|number one|#\d+|still (?:used|popular|good|relevant|common)|"
                           r"fall(?:en|ing)? off|fell|dropp?(?:ed|ing) off|how (?:popular|used|common) is)\b", re.I)
TEAMMATE_FIELD_RE = re.compile(r"\b(?:teammates?|partners?|pairs?|goes with|runs with|alongside|paired with|"
                               r"(?:bring|brings|brought) (?:\w+ )?with)\b", re.I)
# "what EVs does X need to outspeed Y", "how much Speed to outspeed": an investment question, not a yes or no
SPREAD_ASK_RE = re.compile(r"\b(?:what|which|how many|how much)\s+(?:speed\s+)?(?:evs?|spreads?|investment|natures?|stat points|sp)\b|"
                           r"\bevs?\s+(?:to|for|needed|do i need|does it need)|\bneeds? to (?:outspeed|survive|live|tank)|"
                           r"\bhow much speed\b", re.I)
# "how do I beat Kingambit", "Kingambit keeps sweeping me": a checks question asked as advice
BEAT_RE = re.compile(r"\bhow (?:do|can|should|would|to) (?:i |we |you )?(?:beat|handle|deal with|stop|counter|check|wall|answer|"
                     r"play (?:against|around|into)|take (?:on|down|out)|get past|break)\b|"
                     r"\b(?:keeps?|kept) (?:sweeping|beating|destroying|wrecking|killing|winning|walling|getting kills)\b|"
                     r"\b(?:struggl\w*|trouble|problems?|issues?|losing) (?:with|against|to)\b|\b(?:scared|afraid) of\b|"
                     r"\bwhat (?:do|should) i do (?:about|against|vs)\b|\bhow (?:do i |to )?deal w(?:ith|/)?\b|"
                     r"\b(?:best|good) way to (?:beat|handle|deal with|stop|counter|check)\b|"
                     r"\bis (?:so |really )?(?:destroying|shredding|wrecking|killing|sweeping|annoying|a problem|an issue|"
                     r"too strong|broken|unbeatable)\b|"
                     r"\b(?:walls?|stops?|shuts? down|beats?|destroys?|wrecks?|sweeps?|counters?) (?:me|us|my (?:whole |entire )?team)\b|"
                     r"\b(?:counters?|checks?|answers?)\s*\??\s*$", re.I)
# "who can switch into Raging Bolt", "safe switch ins to Kingambit": taking the hit, not winning the one on one
SWITCH_RE = re.compile(r"\bswitch(?:es|ing)? (?:in(?:to)?|on)\b|\bswitch ?ins?\b|\b(?:tank|take|takes|absorb)s? "
                       r"(?:a hit|hits|its (?:hits|attacks)|the hit)\b|\bwho (?:can )?(?:tank|take)s?\b", re.I)
# "why is Torkoal on this team", "how do I use my Slowking-Galar", "what does my Corviknight do", "why does Garganacl run
# Protect": one member's job on the team
MEMBER_RE = re.compile(r"\bwhy (?:is|do i have|did i (?:put|add|pick|use)|are)\b|\bwhy does\b[^?.!]*\b(?:run|have|use|carry)\b|"
                       r"\bhow (?:do|should|can|would) (?:i|you|we) (?:use|play|pilot|run)\b|\bwhat does (?:my )?[\w-]+ do\b|"
                       r"\b(?:best|good|right) way to (?:use|play)\b|\b(?:role|job|purpose|point) of\b|"
                       r"\bwhat(?:'s| is) (?:my )?[\w-]+'?s? (?:job|role|purpose)\b|\bwhen (?:should|do) i (?:use|click|set ?up|"
                       r"dragon dance|swords dance|nasty plot|calm mind|tera)\b", re.I)
# Questions about the whole team's plan, answered from the Coach Guide (engine/team_answers.py) when no opponent is named
WIN_RE = re.compile(r"\bwin ?con(?:dition)?s?\b|\bhow (?:do|does|can|will) (?:i|we|my team|this team) win\b|"
                    r"\b(?:main|best|primary) (?:sweeper|win\w*|wincon)\b|\bwho (?:wins|sweeps|should sweep)\b", re.I)
LEAD_RE = re.compile(r"\b(?:what|who|which|best|good|ideal|should i|do i|to)\b[^.?!]{0,30}\blead(?:s|ing)?\b(?!\s+to\b)|"
                     r"\blead with\b|\bopen with\b|\bopener\b|\bsend (?:in|out) first\b", re.I)
THREATS_RE = re.compile(r"\b(?:biggest|main|worst|scariest|top|major|key) threats?\b|\bthreats? (?:to|for) (?:my|our|this) team\b|"
                        r"\bwhat threatens\b|\bwatch out for\b|\bwhat (?:beats|counters|walls|destroys|wrecks|checks|sweeps) "
                        r"(?:my|our|this) team\b|\bwhat (?:should|do) i (?:fear|worry about|be worried about)\b|"
                        r"\b(?:holes?|gaps?) in (?:my|our|this) team\b|\bwhat (?:am i|is my team) (?:struggling|losing) (?:with|to)\b",
                        re.I)
GAMEPLAN_RE = re.compile(r"\bgame ?plan\b|\bhow (?:do|should|would) (?:i|we|you) (?:play|pilot|use|run) (?:this|my|our) team\b|"
                         r"\bhow (?:does|do) (?:this|my|our) team (?:work|play|function)\b|\bstrategy for (?:this|my|our) team\b|"
                         r"\bwhat does (?:this|my|our) team (?:do|want)\b", re.I)
# "summarize my threat board", "walk me through my speed tiers": a dashboard tab, answered by the same functions
TABS = [(re.compile(r"\bthreat ?board\b", re.I), "threats"), (re.compile(r"\bspeed ?tiers?\b", re.I), "speed_tiers"),
        (re.compile(r"\baudit\b|\bteam check\b", re.I), "audit"), (re.compile(r"\b(?:team )?completer\b", re.I), "teammate"),
        (re.compile(r"\bcoach(?:'s)? guide\b|\bguide tab\b", re.I), "gameplan"),
        (re.compile(r"\b(?:matchup )?matri(?:x|ces)\b", re.I), "team_type"),
        (re.compile(r"\bteam overview\b|\boverview tab\b", re.I), "score")]
TAB_ASK_RE = re.compile(r"\b(?:summari[sz]e|explain|walk me through|go over|what does|what do|tell me about|break down|"
                        r"read|show|say|says|flag\w*)\b|\btab\b", re.I)
# "how do I play against rain", "stall walls my team", "is my team good against stall": an archetype question
ARCHETYPE_ASK_RE = re.compile(r"\b(?:against|vs\.?|versus|beat\w*|handle|deal\w*|play\w*|struggl\w*|counter\w*|annoying|"
                              r"wreck\w*|problem|trouble|good|weak)\b|\bteams?\b", re.I)
# "how do I use weather", "does my team run rain", "how to build a sun team": the team's own weather, not facing one
WEATHER_WORD_RE = re.compile(r"\b(weather|rain|sun|sand(?:storm)?|snow)\b", re.I)
WEATHER_USE_RE = re.compile(r"\b(?:use|using|run|running|runs|build\w*|abus\w*|pilot\w*|work|my team'?s? \w+|"
                            r"(?:do|does) (?:i|my team) (?:have|set))\b", re.I)
FACING_RE = re.compile(r"\b(?:against|vs\.?|versus|beat\w*|counter\w*|deal\w*|handle|stop|struggl\w*|threat\w*)\b", re.I)
# "is my team good", "rate my team": the broken down team score (engine/team_score.py)
SCORE_RE = re.compile(r"\b(?:is|how good is|how strong is) (?:this|my|our) team(?: (?:good|any good|viable|decent|strong|"
                      r"bad|ok|okay|fine))?\b|\b(?:rate|grade|score|judge|review) (?:this|my|our) team\b|"
                      r"\bteam (?:score|rating|grade)\b|\bhow (?:good|bad|strong|solid) is (?:this|my|our) team\b|"
                      # "how does my team do in the current meta", "how would this team fare on the ladder"
                      r"\bhow (?:does|do|will|would|is) (?:this|my|our) team (?:do|doing|fare|faring|hold up|perform|stack up|"
                      r"match up|look)\b|\bis (?:this|my|our) team (?:meta|viable|good|any good) (?:in|on|for) (?:the|this)\b",
                      re.I)
TERA_PLAN_RE = re.compile(r"\b(?:who|which (?:mon|pokemon|member|one)) (?:should|do|would|can) (?:i |we )?(?:tera|terastal\w*)\b|"
                          r"\btera (?:plan|target|user|candidate)s?\b|\bwhen (?:should|do) (?:i|we) (?:tera|terastal\w*)\b|"
                          r"\b(?:best|good) (?:tera|terastal\w*) (?:user|target|candidate)\b", re.I)
# "Specs or Band on Dragapult", "is Leftovers better than Rocky Helmet", "should my Corv run Rocky Helmet instead"
COMPARE_RE = re.compile(r"\b(?:or|vs\.?|versus|better than|worse than|instead of|over)\b|\binstead\b|"
                        r"\bshould\b[^?.!]*\b(?:run|use|hold|carry|have)\b", re.I)
# "suggest a teammate", "what should I replace Corviknight with", "who should I add"
TEAMMATE_ASK_RE = re.compile(r"\b(?:teammates?|partners?|replace\w*|swap\w*|addition|wallbreaker for (?:my|this) team)\b|"
                             r"\bwho (?:should|could|can) i (?:add|bring|use)\b|\bwhat (?:should|could) i (?:add|change)\b|"
                             r"\b(?:sixth|last|6th) (?:slot|member|mon)\b", re.I)
REPLACE_ASK_RE = re.compile(r"\b(?:replace\w*|swap\w*|instead of|drop|cut)\b", re.I)
OWN_ROLE_ASK_RE = re.compile(r"\b(?:which|who|what) (?:of|on|in) (?:my|our)\b|\bmy (?:best|main|only)\b|"
                             r"\b(?:which|what) (?:mon|pokemon|member|one) (?:is|on my)\b|\bdo i have an?\b", re.I)
ROLE_RE = re.compile(r"\b(wallbreaker|breaker|pivot|hazard setter|hazard remover|hazard removal|sweeper|wall|tank|"
                     r"speed control|priority|revenge killer|spin ?blocker)\b", re.I)
# "What should I lead against rain": a plan against an archetype is still Oak's to discuss
VERSUS_RE = re.compile(r"\b(?:against|vs\.?|versus|into|facing)\b", re.I)
# A team species right after one of these is the opponent's copy even when no team member is named yet:
# "How do I beat Kingambit?" on a team that runs Kingambit asks about an opposing one
STRONG_OPP_RE = re.compile(r"\b(opposing|enemy|their|opp|beat|handle|counter|stop|check|checks|deal with|answer|answers|"
                           r"play around|play against|played against|facing|face|scared of|afraid of|threatened by|"
                           r"switch(?:es|ing)? into|switch in(?: on| to)?|tank|take hits from)\s+"
                           r"(?:an?\s+|the\s+|that\s+)?$", re.I)
# Words right before a target: a team species named after one of these is the opponent's copy
OPP_MARK_RE = re.compile(r"\b(a|an|opposing|enemy|their|opp|vs|versus|against|into|on|to|from|than|ohko|ohkos|2hko|"
                         r"outspeeds?|kos?|beats?|hits?|resists?)\s+(?:[\w+-]+\s+){0,2}$", re.I)
MIRROR_RE = re.compile(r"\bmirror\b", re.I)
# "what checks Kyurem", "who on my team counters Zamazenta", "answers to Raging Bolt": a team wide matchup question
CHECKS_RE = re.compile(r"\b(?:what|who|which)\b[^.?!]*\b(?:checks?|counters?|answers?|handles?|beats?|walls?|stops?)\b|"
                       r"\b(?:checks?|counters?|answers?)\s+(?:to|for|against)\b", re.I)
KO_RE = re.compile(r"\b(ohko|2hko|3hko|ohkos|2hkos|one ?shot|survive|survives|live|lives|tank|tanks|withstand|"
                   r"kill|kills|ko|kos)\b", re.I)
# "can X survive / live / tank Y": the yes or no is about the defender
SURVIVE_RE = re.compile(r"\b(survive|survives|live|lives|tank|tanks|withstand)\b", re.I)
DAMAGE_RE = re.compile(r"(\bdamage\b|\bdmg\b|\bcalc\b|\bpercent(?:age)?\b|%|\bhow much\b)", re.I)
SPEED_RE = re.compile(r"\b(outspeed|outspeeds|faster|slower|speed tie|out speed|outpace|moves? first|goes? first|"
                      r"mirror speed|speed (?:check|comparison|matchup))\b", re.I)
TYPE_ASK_RE = re.compile(r"\b(immune|immunity|immunities|weak|weakness|weaknesses|resist|resists|resistant|resistances?|neutral|super effective|not very effective|"
                         r"type matchup|typing)\b", re.I)
# "which of my Pokemon resist Water", "who on my team is weak to Ground", "is my team weak to Fairy": the whole team
TEAM_WIDE_RE = re.compile(r"\b(?:my|our)\s+(?:team|squad|six|pok[eé]mon|mons|members)\b|\bwhat (?:am i|are we)\b|"
                          r"\b(?:which|who|any|anyone|anything|none|what)\s+(?:of|on|in)\s+(?:my|our)\b|"
                          r"\bwhich\s+(?:pok[eé]mon|mons|members)\b", re.I)
# Asking what to do about a weakness is a strategy question, not a type chart lookup ("how many" is still a lookup)
TEAM_ADVICE_RE = re.compile(r"\bhow\b(?!\s+many)|\b(?:fix|cover|patch|deal with|improve|beat|handle|play|replace|add|"
                            r"should|recommend|suggest|teammate|why)\b", re.I)
TEAM_ASKS = (("neutral", re.compile(r"\bneutral", re.I)), ("immune", re.compile(r"\bimmun", re.I)),
             ("weak", re.compile(r"\b(?:weak|super effective|vulnerable)", re.I)))
RESIST_RE = re.compile(r"\bresist", re.I)
# "how does Multiscale work", "does Mold Breaker ignore Levitate", "what does Booster Energy do": a rules question
RULES_CUE_RE = re.compile(r"\b(?:how does|how do(?!\s+(?:i|we|you)\b)|what does|what do|what is|what's|whats|what happens|"
                          r"explain|works?|mean|means|boosts?|ignores?|bypass\w*|reflects?|bounces?|halves?|blocks?|"
                          r"affects?|interacts?|stacks?|activates?|triggers?|weaken\w*|strengthen\w*|stronger|weaker|"
                          r"change\w*)\b", re.I)
# ... unless it asks for advice or ladder usage, which the builder and strategy agents answer
RULES_ADVICE_RE = re.compile(r"\bhow (?:do|can|should) (?:i|we)\b|\bwhat (?:do|should|can) (?:i|we) do\b|"
                             r"\b(?:against|vs\.?|versus|teams?)\b|\b(?:beat|win|play|handle|counter|lead|deal with|standard|"
                             r"common|usage|popular|usual\w*|good|best|worth|better|should|recommend|suggest|replace|instead|"
                             r"run|running|plan|strategy|approach|game ?plan|matchup)\b", re.I)
# "stat boosts" and "stat changes" are assumptions in matchup questions, not stat questions
STAT_RE = re.compile(r"\bstat\b(?!\s+(?:boost|change|stage|drop|raise))", re.I)
# "how much Speed does my X have", "what Speed does my X hit": a stat question when no opponent is named
STAT_ASK_RE = re.compile(r"\b(how much|what)\s+(speed|attack|defense|special attack|special defense|hp)\b|"
                         r"\bhow fast (?:is|are)\b", re.I)
# "who switches into a Ghost move safely", "who takes Fire hits": the team's resists to one attacking type
SWITCH_TYPE_RE = re.compile(r"\bwho(?: on (?:my|our) team)? (?:switch(?:es)? into|takes?|tanks?|eats?|handles?|walls?) "
                            r"(?:a |an )?(normal|fire|water|electric|grass|ice|fighting|poison|ground|flying|psychic|bug|"
                            r"rock|ghost|dragon|dark|steel|fairy)(?:[- ]type)? (?:moves?|attacks?|hits?)\b", re.I)


@dataclass
class Plan:
    intent: str = "open"            # speed, speed_spread, ko, damage, type, stat, usage, checks, team_type, rules, clarify, open
    kind: str = ""                  # the classifier's kind when it planned this (engine/intent.py), else ""
    format_id: str = config.DEFAULT_FORMAT
    user: dict | None = None        # team member entry from readTeam
    user_named: bool = False        # False when `user` is just the only member of a one Pokemon team
    opponents: list = field(default_factory=list)   # Pokemon names not on the team
    move: str | None = None
    attacker: str = "user"          # who uses `move`: "user" or "opponent"
    subject: str = "user"           # whose side the question is asked from: "user" or "opponent"
    speed_ask: str = "faster"       # "slower" when the question asks if the subject is slower
    ko_hits: int = 1                # 1 for OHKO, 2 for 2HKO...
    survive: bool = False           # "can X survive ..." flips the yes/no
    atk_type: str | None = None
    stat: str | None = None
    usage_field: str | None = None  # item, ability, move, tera, spread, teammates
    usage_option: str | None = None  # "is Loaded Dice common on Garchomp": the one option asked about
    asks_how: bool = False          # checks questions asked as advice ("how do I beat X"), voiced by Oak
    options: list = field(default_factory=list)     # compare questions: [(kind, name)] items, moves, abilities named
    replace: bool = False           # teammate questions: find a replacement for the named member
    role: str = ""                  # roles questions: the role asked about ("wallbreaker")
    archetype: str = ""             # archetype questions: rain, sun, sand, stall or hazards
    opp_overrides: dict = field(default_factory=dict)   # set details the question states for the opponent
    user_overrides: dict = field(default_factory=dict)  # ... and for the player's Pokemon
    conditions: dict = field(default_factory=dict)      # calc Field the question states: weather, terrain
    screens: dict = field(default_factory=dict)         # "user" | "opponent" | "defender" -> calc Side screen flags
    strongest: bool = False         # "assume it uses its strongest listed move"
    stat_target: str = "user"       # stat questions: whose stat ("opponent" for a Pokemon off the team)
    situation: list = field(default_factory=list)  # stated battle conditions the solver counts (constraints.Condition)
    counted: list = field(default_factory=list)    # ... as the question phrased them ("Tailwind", "50% HP")
    unhandled: list = field(default_factory=list)  # stated conditions this answer can't count ("Sticky Web")
    team: dict = field(default_factory=dict, repr=False)  # the whole team, for team wide answers ("what checks X")
    raw_stats: bool = False         # "ignore items/abilities": compare bare stats, no Scarf or field
    no_boosts: bool = False         # "assume no boosts": Booster Energy and other boost triggers stay off too
    team_ask: str = "resist"        # team_type questions: which group is asked for (weak, neutral, resist, immune)
    rules: list = field(default_factory=list)       # rules questions: [(kind, name)] abilities, items, moves, weather named
    query: str = ""

    @property
    def opponent(self):
        return self.opponents[0] if self.opponents else None


def _team_member(name, team, dex):
    """The team entry a query name refers to, matching base species or Mega forme."""
    target = to_id(name)
    species = dex.species(name) if dex else None
    base = to_id(species.get("baseSpecies", "")) if species else ""
    for p in team.values():
        ids = {to_id(p.get("Pokemon")), to_id(p.get("Forme"))}
        # A bare base name ("Ogerpon") also means a team member of that species ("Ogerpon-Wellspring")
        member = dex.species(p.get("Pokemon")) if dex else None
        member_base = to_id(member.get("baseSpecies", "")) if member else ""
        if target in ids or (base and base in ids) or (member_base and target == member_base):
            return p
    return None


def _blank(text, phrase):
    """Blank out a matched phrase (case insensitive) so later scans don't see it."""
    return re.sub(re.escape(phrase), " " * len(phrase), text, flags=re.I)


def _find_move(query, candidates, dex):
    """Longest move named in the query: known movesets match in any case, other dex moves only in Title Case."""
    lowered = query.lower()
    hits = [m for m in candidates if m and m.lower() in lowered]
    if hits and dex:
        # A known move inside a longer one the query names is the longer one: "trick room" is not Trick
        longer = [m for m in dex.move_data if any(h.lower() in m.lower() and len(m) > len(h) for h in hits)
                  and re.search(rf"(?<![\w]){re.escape(m.lower())}(?![\w])", lowered)]
        hits = [h for h in hits if not any(h.lower() in m.lower() for m in longer)] + longer
    if not hits and dex:
        hits = [m for m in dex.move_data if len(m) > 3 and re.search(rf"(?<![\w]){re.escape(m)}(?![\w])", query)]
    # "Psychic type attacks" names a type, not the move Psychic
    hits = [m for m in hits if not re.search(rf"\b{re.escape(m)}[\s-]*type", query, re.I)]
    return max(hits, key=len) if hits else None


def _find_type(text):
    """Attack type named in the question, preferring 'X type' / 'X attacks' phrasing."""
    for t in TYPES:
        if re.search(rf"\b{t}[\s-]*(type|attacks?|moves?)\b", text, re.I):
            return t
    for t in TYPES:
        if re.search(rf"\b{t}\b", text, re.I):
            return t
    return None


def _attack_type(text, move, dex):
    """Attack type a type question asks about: a named type, else the type of a named damaging move
    ("does Toxapex resist Moonblast"). Status moves don't count: their effect isn't a type matchup."""
    named = _find_type(text)
    if named or not (move and dex):
        return named
    data = dex.move(move) or {}
    return data.get("type") if data.get("category") != "Status" else None


def _find_stat(query):
    lowered = query.lower()
    for word in sorted(STAT_WORDS, key=len, reverse=True):
        if re.search(rf"\b{word}\b", lowered):
            return STAT_WORDS[word]
    return None


def _usage_field(query):
    """Which usage field is asked for; whole words only, so 'Terapagos' is not 'tera'."""
    if TEAMMATE_FIELD_RE.search(query):
        return "teammates"
    if RANK_FIELD_RE.search(query):
        return "rank"
    for pattern, fld in ((r"tera", "tera"), (r"abilit(?:y|ies)", "ability"), (r"items?", "item"),
                         (r"spreads?", "spread"), (r"natures?", "spread"), (r"moves?", "move"),
                         (r"(?:move)?sets?|builds?|runs?|running|ran", "set")):
        if re.search(rf"\b{pattern}\b", query, re.I):
            return fld
    # "do Zapdos mostly have static": a named ability, item or move, in any case, says which field
    return _named_any_case(query) or "item"


def _named_any_case(query):
    """The usage field of the first ability, item or move named in `query`, ignoring case. find_named keeps short
    names case sensitive so everyday words aren't read as moves; a usage question is already about a set."""
    lowered = query.lower()
    table = rules.table()
    for fld, key in (("ability", "abilities"), ("item", "items"), ("move", "moves")):
        for name in table[key]:
            if len(name) >= 5 and re.search(rf"(?<![\w-]){re.escape(name.lower())}(?![\w-])", lowered):
                return fld
    return None


def _archetype(text, format_id):
    """'rain', 'sun', 'sand', 'stall' or 'hazards' when the question names one the engine has a roster for."""
    from metamatch.engine.archetypes import archetype_of, available
    key = archetype_of(text)
    return key if key and available(key, format_id) else None


TERA_OPTION_RE = re.compile(r"\btera(?:stal(?:ize)?)?[\s-]*(?:type\s+)?(" + "|".join(constraints.TYPES) + r")\b", re.I)


def _options(text):
    """[(kind, name)] for the items, moves, abilities and Tera types a question names, casual item names included
    ("specs"). Tera types read as ("tera", "Fairy") from "tera fairy or tera steel"."""
    found = [("tera", m.group(1).capitalize()) for m in TERA_OPTION_RE.finditer(text)]
    found += [(kind, name) for kind, name in rules.find_named(text) if kind in ("item", "move", "ability")]
    for alias, item in constraints.ITEM_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text, re.I) and ("item", item) not in found:
            found.append(("item", item))
    return list(dict.fromkeys(found))


def _species_options(text, species, format_id):
    """Options the question names among what `species` actually runs on the ladder, in any case ("zapdos static vs
    pressure"): find_named keeps short everyday words case sensitive, which a compare question about one Pokemon's
    set doesn't need."""
    from metamatch.engine.dex import to_id
    from metamatch.engine.sets import chaos_entry
    _, entry = chaos_entry(species, format_id)
    if not entry:
        return []
    table = rules.table()
    names = {}
    for kind, field, key in (("ability", "Abilities", "abilities"), ("item", "Items", "items"), ("move", "Moves", "moves")):
        ids = {to_id(k) for k in (entry.get(field) or {})}
        names.update({n.lower(): (kind, n) for n in table[key] if to_id(n) in ids})
    words = re.findall(r"[a-z][a-z'-]*", text.lower())
    found = []
    for i in range(len(words)):
        for size in (2, 1):   # two word names first: "Iron Head" before "iron"
            hit = names.get(" ".join(words[i:i + size]))
            if hit:
                if hit not in found:
                    found.append(hit)
                break
    return found


def _pokemon_options(names, team):
    """[("pokemon", name)] for two Pokemon a compare question weighs ("mega lop or mega zard"), a team member's own
    name (its Mega or forme) standing in for the species it shares."""
    from metamatch.recommender import base_species
    own = {base_species(p["Pokemon"]): p["Pokemon"] for p in (team or {}).values()}
    picked = list(dict.fromkeys(own.get(base_species(n), n) for n in names))
    return [("pokemon", n) for n in picked[:2]] if len(picked) >= 2 else []


PRONOUN_RE = re.compile(r"\b(i|we|it|you|he|she|they)\b", re.I)
TARGET_RE = re.compile(r"\b(to|against|into|on|vs)\b", re.I)


def _subject(query, spans):
    """Side of the question's grammatical subject: the last mention before the question verb
    ("outspeed", "OHKO", "survive", or "to" in damage questions) in the same sentence. A lead in
    sentence ("Raging Bolt is on its usual set, does my Skarmory outspeed it?") is skipped."""
    anchor = SPEED_RE.search(query) or KO_RE.search(query) or TARGET_RE.search(query)
    if not anchor:
        return "user"
    begin = max(query.rfind(c, 0, anchor.start()) for c in ".?!;") + 1
    before = [(b, side) for a, b, _, side in spans if begin <= a < anchor.start()]
    if not before:
        return "user"
    # "my Skarmory vs a Raging Bolt, do I outspeed it?": a pronoun after the last name is the real subject
    if PRONOUN_RE.search(query[before[-1][0]:anchor.start()]):
        return "user"
    return before[-1][1]


def _possessor(query, move, plan):
    """'user' or 'opponent' when the move is written as 'X's Move' (X may be a nickname), else None."""
    m = re.search(rf"['’]s\s+{re.escape(move)}", query, re.I)
    if not m:
        return None
    owners = find_pokemon(query[:m.start()])
    if not owners:
        return None
    if owners[-1] in plan.opponents:
        return "opponent"
    return "user" if plan.user is not None else None


def _move_boosts(plan, src, dst, boosts):
    """Moves stat boosts the question gave one side over to the other."""
    sides = {"user": plan.user_overrides, "opponent": plan.opp_overrides}
    a, b = sides[src], sides[dst]
    for stat, n in boosts.items():
        left = a.get("boosts", {}).get(stat, 0) - n
        if left > 0:
            a["boosts"][stat] = left
        else:
            a.get("boosts", {}).pop(stat, None)
        b.setdefault("boosts", {})[stat] = min(6, b.get("boosts", {}).get(stat, 0) + n)
    if "boosts" in a and not a["boosts"]:
        del a["boosts"]


# Classifier kinds that are planner intents (solved by engine/solvers.py); the rest (sets, how_to_use, meta_trends,
# in_battle, out_of_scope, smalltalk) stay "open" with plan.kind set, for the chat to route
PLANNED_KINDS = {"speed", "ko", "damage", "type", "stat", "usage", "team_type", "checks", "switchins", "matchup",
                 "member", "score", "threats", "gameplan", "win", "lead", "tera", "archetype", "weather", "teammate",
                 "compare", "rules", "learn"}


# The question is the player's own ("my", "I", "we", "this team"): team answers need it (see agents/manager)
SELF_RE = re.compile(r"\b(?:my|me|i|i'm|im|i've|ive|our|we|us|mine)\b|\b(?:this|the) team\b", re.I)
# "how is Mega Greninja in this format", "is Garganacl dead on arrival", "is blissey still good"
PERFORMANCE_RE = re.compile(r"\bhow(?:'s| is| are| has)\b[^?.!]{0,30}\b(?:doing|performing|been|in|on) (?:this|the) "
                            r"(?:format|meta|metagame|tier|ladder)\b|\bdead on arrival\b|\b(?:is|are) \w+(?:[ -]\w+)? dead\b|"
                            r"\bfallen off\b|\b(?:still|even) (?:good|viable|usable)\b", re.I)
# "can I use Charizard on my team", "would kyurem fit this team", "is zapdos good for my team"
FIT_RE = re.compile(r"\b(?:use|run|add|bring|fit|slot|put|try)\b[^?.!]{0,30}\b(?:on|in|into|onto|for|with)\s+"
                    r"(?:my|this|the)\s+(?:team|squad|comp)\b|\bfit\w*\s+(?:my|this)\s+(?:team|squad)\b|"
                    r"\b(?:good|worth it|viable|work)\s+(?:on|for|with|in)\s+(?:my|this)\s+(?:team|squad)\b", re.I)


def _fit_candidate(plan):
    """The one Pokemon a fit question names that the team doesn't already run, or None."""
    from metamatch.recommender import base_species
    own = {base_species(p["Pokemon"]) for p in (plan.team or {}).values()}
    outside = [n for n in dict.fromkeys(plan.opponents) if base_species(n) not in own]
    return outside[0] if len(outside) == 1 else None


# "run" is left out: "does gambit run sucker punch usually" asks about its set, not whether it can learn the move
LEARN_VERB_RE = re.compile(r"\b(?:learn\w*|gets?|have|has|access to|give)\s+(?:the move\s+|an?\s+)?", re.I)


def _learn_move(q, dex):
    """'can gholdengo learn shell smash', 'does tusk get knock off', 'give kingambit u-turn': the move named right after
    the verb (after the Pokemon for "give"), in any case, so "does tusk get knocked out by" names none; or None."""
    if not dex:
        return None
    for m in LEARN_VERB_RE.finditer(q):
        starts = [m.end()]
        if m.group(0).lower().startswith("give"):
            starts += [m.end() + w.end() for w in re.finditer(r"\S+\s+", q[m.end():m.end() + 40])][:3]
        for start in starts:
            tail = to_id(q[start:start + 30])
            hits = [n for n in dex.move_data if len(to_id(n)) > 3 and tail.startswith(to_id(n))]
            if hits:
                return max(hits, key=len)
    return None


def _force(plan, kind, q, scrubbed, names_only, raw_spans, dex, format_id, target, survive):
    """Fills the slots a classifier chosen kind needs, the way that kind's rule branch would, without its guards."""
    plan.kind = kind
    if kind not in PLANNED_KINDS:
        return
    plan.intent = kind
    if kind == "team_type":
        m = SWITCH_TYPE_RE.search(q)
        plan.atk_type = m.group(1).capitalize() if m else _attack_type(scrubbed, plan.move, dex)
        plan.team_ask = next((ask for ask, pattern in TEAM_ASKS if pattern.search(q)), "resist")
    elif kind == "stat":
        plan.stat_target = target or "user"
        plan.stat = _find_stat(scrubbed) or "spe"
    elif kind == "ko":
        hits = re.search(r"\b(o|\d)hko", q, re.I)
        plan.ko_hits = 1 if not hits or hits.group(1).lower() == "o" else int(hits.group(1))
        plan.survive = survive
    elif kind == "type":
        plan.atk_type = _attack_type(scrubbed, plan.move, dex)
        if not plan.atk_type:
            plan.team_ask = next((ask for ask, pattern in TEAM_ASKS if pattern.search(q)), None) or (
                "resist" if RESIST_RE.search(q) else "weak")
    elif kind == "checks":
        plan.asks_how = bool(BEAT_RE.search(q))
    elif kind in ("archetype", "weather"):
        word = WEATHER_WORD_RE.search(q)
        plan.archetype = (_archetype(q, format_id) if kind == "archetype" else
                          {"weather": None, "sandstorm": "sand"}.get(word.group(1).lower(), word.group(1).lower())
                          if word else None)
    elif kind == "compare":
        plan.options = _options(names_only)
        subject = (plan.user or {}).get("Pokemon") if plan.user is not None and plan.user_named else plan.opponent
        if len(plan.options) < 2 and subject:
            plan.options = list(dict.fromkeys(plan.options + _species_options(names_only, subject, format_id)))
        if len(plan.options) < 2:
            plan.options = _pokemon_options([n for _, _, n in raw_spans], plan.team) or plan.options
    elif kind == "teammate":
        plan.replace = bool(REPLACE_ASK_RE.search(q)) and plan.user_named
        if FIT_RE.search(q) and _fit_candidate(plan):
            plan.options = [("pokemon", _fit_candidate(plan))]
    elif kind == "rules":
        plan.rules = rules.find_named(q, [(a, b) for a, b, _ in raw_spans])
    elif kind == "usage":
        plan.usage_field = _usage_field(names_only)
        option = [(k, name) for k, name in rules.find_named(names_only) if k in ("item", "move", "ability")]
        if OPTION_ASK_RE.search(q) and option and plan.usage_field != "teammates":
            plan.usage_field, plan.usage_option = option[0]


def plan_query(query, team, force=None):
    """Builds a Plan for a chat question about `team` (readTeam output). `force`: a question kind from the learned
    classifier (engine/intent.py) to plan instead of the rule chain; the shared extraction (names, moves, stated
    details) is the same either way, and only the kind's own slots are filled."""
    team = team or {}
    format_id = config.team_format(team)
    dex = dex_for_format(format_id)
    plan = Plan(format_id=format_id, team=team, query=query)

    raw_spans = find_pokemon_spans(query)
    names = list(dict.fromkeys(d for _, _, d in raw_spans))
    spans, owned_names = [], []
    for a, b, name in raw_spans:
        member = _team_member(name, team, dex)
        before = query[max(0, a - 30):a]
        owned = bool(re.search(r"\b(my|our)\s+$", before, re.I))
        if owned and member is not None:
            owned_names.append(name)
        # A team species named as a target once the player's Pokemon is known is the opponent's copy:
        # "does my Scizor OHKO a full health Scizor", "how much does rilla wood hammer do to corv"
        if member is not None and not owned and (STRONG_OPP_RE.search(before)
                                                 or (plan.user is not None and OPP_MARK_RE.search(before))):
            member = None
        if member is not None:
            plan.user = plan.user or member
            plan.user_named = True
        elif name not in plan.opponents:
            plan.opponents.append(name)
        spans.append((a, b, name, "user" if member is not None else "opponent"))
    # "Does Kingambit OHKO my Great Tusk" on a team that also runs Kingambit: when only some of the team species named
    # are marked "my", the unmarked ones are the opponent's copies
    unmarked = [n for _, _, n, side in spans if side == "user" and n not in owned_names]
    if owned_names and unmarked and not plan.opponents:
        spans = [(a, b, n, "opponent" if n in unmarked else side) for a, b, n, side in spans]
        plan.opponents = list(dict.fromkeys(unmarked))
        plan.user = _team_member(owned_names[0], team, dex)
        plan.user_named = True
    # "gambit keeps sweeping me" on a team that runs Kingambit: a complaint about a Pokemon is about the opponent's
    if (plan.user is not None and not plan.opponents and not owned_names and len(names) == 1
            and (BEAT_RE.search(query) or CHECKS_RE.search(query))):
        plan.opponents = [names[0]]
        plan.user, plan.user_named = None, False
        spans = [(a, b, n, "opponent") for a, b, n, _ in spans]
    # "tusk mirror": the opponent is the same species as the only Pokemon named
    if plan.user is not None and not plan.opponents and MIRROR_RE.search(query):
        plan.opponents.append(plan.user["Pokemon"])
    if plan.user is None and len(team) == 1:
        plan.user = next(iter(team.values()))
    plan.subject = _subject(query, spans)

    # Set details and field conditions the question states
    stated = constraints.extract(query, spans, dex, (plan.user or {}).get("Item"), plan.subject,
                                 bool(SURVIVE_RE.search(query)))
    plan.user_overrides, plan.opp_overrides = stated.user, stated.opponent
    plan.conditions, plan.screens, plan.strongest = stated.conditions, stated.screens, stated.strongest
    found = constraints.conditions(query, stated.consumed, spans)

    # Text with Pokemon names removed, for move, type and keyword scans
    scrubbed = query
    for name in names:
        scrubbed = _blank(scrubbed, name)
    # Nicknames too ("gambit"), which the canonical name blanking above misses
    for a, b, _ in raw_spans:
        scrubbed = scrubbed[:a] + " " * (b - a) + scrubbed[b:]
    names_only = scrubbed
    # ... and the stated details, so "moves: Knock Off, Ice Shard" or "Reflect up" never reads as the asked move
    for a, b in stated.consumed:
        scrubbed = scrubbed[:a] + " " * (b - a) + scrubbed[b:]

    members = [plan.user] if plan.user else list(team.values())
    user_moves = [m["name"] for p in members for m in p.get("Moves", [])]
    opp_set = likely_set(plan.opponent, format_id) if plan.opponent else None
    opp_moves = [m for m, _ in opp_set["moves"]] if opp_set else []
    # A setup move credited to a Pokemon that doesn't run it belongs to the other side when that one does:
    # "does Kingambit OHKO Great Tusk after a Swords Dance" is Kingambit's Swords Dance
    for setup_move, owner, boosts in stated.setups:
        runs = {"user": setup_move in user_moves, "opponent": setup_move in opp_moves}
        other_side = "opponent" if owner == "user" else "user"
        if not runs[owner] and runs[other_side]:
            _move_boosts(plan, owner, other_side, boosts)
    plan.move = _find_move(scrubbed, user_moves + opp_moves, dex)
    if plan.move:
        scrubbed = _blank(scrubbed, plan.move)
        # "How much does Knock Off do to X?" is about whichever team member runs Knock Off
        if plan.user is None:
            plan.user = next((p for p in members if plan.move in [m["name"] for m in p.get("Moves", [])]), None)
            plan.user_named = plan.user is not None
            user_moves = [m["name"] for m in (plan.user or {}).get("Moves", [])]

    if dex:
        for ability in dex.ability_names:
            if len(ability) > 3:
                scrubbed = _blank(scrubbed, ability)

    # Who attacks: possessive "X's Move" wins, then a move only one side runs, then grammar:
    # the subject attacks, unless it is the one trying to survive
    survive = bool(SURVIVE_RE.search(query))
    other = "opponent" if plan.subject == "user" else "user"
    possessor = _possessor(query, plan.move, plan) if plan.move else None
    if possessor:
        plan.attacker = possessor
    elif plan.move and plan.move in user_moves and plan.move not in opp_moves:
        plan.attacker = "user"
    elif plan.move and plan.move in opp_moves and plan.move not in user_moves:
        plan.attacker = "opponent"
    else:
        plan.attacker = other if survive else plan.subject
    if re.search(r"\b(slower|outsped)\b", query, re.I):
        plan.speed_ask = "slower"

    plan.raw_stats, plan.no_boosts = stated.raw_stats, stated.no_boosts

    # Usage goes last: speed and KO questions also say "most common spread"
    q = query
    # A stat question is about the named team member, else a named Pokemon off the team
    target = ("user" if plan.user is not None and (plan.user_named or not plan.opponents)
              else "opponent" if plan.opponents else None)
    tab = next((intent for pattern, intent in TABS if pattern.search(q)), None) if team and TAB_ASK_RE.search(q) else None
    if force:
        _force(plan, force, q, scrubbed, names_only, raw_spans, dex, format_id, target, survive)
    elif tab:
        # A question about a dashboard tab gets that tab's own answer (same functions, so the numbers match)
        plan.intent = tab
    elif len(names) == 1 and _learn_move(q, dex):
        plan.intent = "learn"
        plan.move = _learn_move(q, dex)
    elif len(names) == 1 and plan.opponents and PERFORMANCE_RE.search(q) and not SELF_RE.search(q):
        # "how is Mega Greninja in this format", "is Garganacl dead on arrival": where it stands on the ladder
        plan.intent, plan.usage_field = "usage", "rank"
    elif team and plan.opponents and FIT_RE.search(q) and _fit_candidate(plan):
        # "can I use Charizard on my team": would a Pokemon the team doesn't run fit as a teammate
        plan.intent = "teammate"
        plan.options = [("pokemon", _fit_candidate(plan))]
    elif team and SWITCH_TYPE_RE.search(q):
        plan.intent = "team_type"
        plan.atk_type = SWITCH_TYPE_RE.search(q).group(1).capitalize()
        plan.team_ask = "resist"
    elif (team and TEAM_WIDE_RE.search(q) and TYPE_ASK_RE.search(q) and not TEAM_ADVICE_RE.search(q)
            and not SPEED_RE.search(q)):
        # A type chart lookup over the whole team: one type, the opponent's usual attacks, or every shared weakness
        plan.intent = "team_type"
        plan.atk_type = _attack_type(scrubbed, plan.move, dex)
        plan.team_ask = next((ask for ask, pattern in TEAM_ASKS if pattern.search(q)), "resist")
        # "who resists Gholdengo's moves" when the team also runs Gholdengo: the attacks of an opposing one
        if (not plan.atk_type and not plan.opponents and plan.user_named
                and re.search(r"['’]s\s+(?:\w+\s+)?(?:moves|attacks|coverage|stabs?)\b", q, re.I)):
            plan.opponents.append(plan.user["Pokemon"])
    elif target and not SPEED_RE.search(q) and (
            STAT_RE.search(q) or (STAT_ASK_RE.search(q) and (not plan.opponents or target == "opponent"))):
        plan.intent = "stat"
        plan.stat_target = target
        plan.stat = _find_stat(scrubbed) or "spe"
    elif SPREAD_ASK_RE.search(q) and plan.opponent and plan.user and SPEED_RE.search(q):
        # "What EVs does my Tusk need to outspeed Iron Valiant": the investment, not whether it already does
        plan.intent = "speed_spread"
    elif SPREAD_ASK_RE.search(q) and KO_RE.search(q):
        # "What spread lets Corviknight survive Thunderclap": a spread search no solver runs yet; a yes or no would
        # answer a different question, so it stays open for the builder
        pass
    elif KO_RE.search(q) and plan.opponent and (plan.user or plan.move):
        plan.intent = "ko"
        hits = re.search(r"\b(o|\d)hko", q, re.I)
        plan.ko_hits = 1 if not hits or hits.group(1).lower() == "o" else int(hits.group(1))
        plan.survive = survive
    elif TYPE_ASK_RE.search(q) and _attack_type(scrubbed, plan.move, dex) and (plan.user or plan.opponent):
        plan.intent = "type"
        plan.atk_type = _attack_type(scrubbed, plan.move, dex)
    elif (TYPE_ASK_RE.search(q) and team and plan.user is not None and plan.user_named and not plan.opponents
            and not TEAM_ADVICE_RE.search(q)):
        # "What is my Dragapult weak to": one member's whole type profile (no attacking type named), led by the
        # group asked about
        plan.intent = "type"
        plan.team_ask = next((ask for ask, pattern in TEAM_ASKS if pattern.search(q)), None) or (
            "resist" if RESIST_RE.search(q) else "weak")
    elif DAMAGE_RE.search(q) and plan.opponent and (plan.user or plan.move):
        plan.intent = "damage"
    elif SPEED_RE.search(q) and plan.opponent and plan.user:
        plan.intent = "speed"
    elif plan.opponent and team and SWITCH_RE.search(q) and plan.user_named and plan.move and plan.attacker == "opponent":
        # "Can my Kingambit switch into Great Tusk's Headlong Rush": whether that member lives that hit
        plan.intent, plan.survive, plan.ko_hits = "ko", True, 1
    elif plan.opponent and team and SWITCH_RE.search(q):
        plan.intent = "switchins"
    elif plan.user is not None and plan.user_named and plan.opponent and team and MATCHUP_RE.search(q) \
            and not TEAM_WIDE_RE.search(q):
        plan.intent = "matchup"
    elif plan.user is not None and plan.user_named and not plan.opponents and team and MEMBER_RE.search(q):
        plan.intent = "member"
    elif (CHECKS_RE.search(q) or BEAT_RE.search(q)) and plan.opponent and team:
        plan.intent = "checks"
        plan.asks_how = bool(BEAT_RE.search(q))
    elif team and not plan.opponents and not plan.user_named and TERA_PLAN_RE.search(q):
        plan.intent = "tera"
    elif (team and not plan.opponents and WEATHER_WORD_RE.search(q) and WEATHER_USE_RE.search(q)
            and not FACING_RE.search(q)):
        word = WEATHER_WORD_RE.search(q).group(1).lower()
        plan.intent, plan.archetype = "weather", {"weather": None, "sandstorm": "sand"}.get(word, word)
    elif team and not plan.opponents and ARCHETYPE_ASK_RE.search(q) and _archetype(q, format_id):
        plan.intent, plan.archetype = "archetype", _archetype(q, format_id)
    elif team and not plan.opponents and not VERSUS_RE.search(q) and SCORE_RE.search(q):
        plan.intent = "score"
    elif team and not plan.opponents and not VERSUS_RE.search(q) and GAMEPLAN_RE.search(q):
        plan.intent = "gameplan"
    elif team and not plan.opponents and not VERSUS_RE.search(q) and WIN_RE.search(q):
        plan.intent = "win"
    elif team and not plan.opponents and not VERSUS_RE.search(q) and LEAD_RE.search(q):
        plan.intent = "lead"
    elif team and not plan.opponents and THREATS_RE.search(q):
        plan.intent = "threats"
    elif (plan.user or plan.opponent) and COMPARE_RE.search(q) and _options(names_only):
        # Comparing options on one Pokemon: two named, or one named against what the member holds now
        plan.options = _options(names_only)
        if len(plan.options) >= 2 or (plan.user is not None and plan.user_named):
            plan.intent = "compare"
    elif team and OWN_ROLE_ASK_RE.search(q) and ROLE_RE.search(q) and not plan.opponents:
        plan.intent = "roles"
        plan.role = ROLE_RE.search(q).group(1).lower().replace("spinblocker", "spin blocker")
    elif team and TEAMMATE_ASK_RE.search(q) and not plan.opponents and not (USAGE_RE.search(q) and plan.user_named
                                                                              and not REPLACE_ASK_RE.search(q)):
        plan.intent = "teammate"
        plan.replace = bool(REPLACE_ASK_RE.search(q)) and plan.user_named
    elif RULES_CUE_RE.search(q) and not RULES_ADVICE_RE.search(q) and rules.find_named(q, [(a, b) for a, b, _ in raw_spans]):
        # What an ability, item, move or weather does, from Showdown's rule text
        plan.intent = "rules"
        plan.rules = rules.find_named(q, [(a, b) for a, b, _ in raw_spans])
    elif (SPEED_RE.search(q) or KO_RE.search(q) or DAMAGE_RE.search(q)) and not plan.opponents:
        # A matchup question with no recognisable opponent: ask, never answer a different question
        plan.intent = "clarify"
    elif USAGE_RE.search(q) and (plan.opponent or plan.user):
        plan.intent = "usage"
        plan.usage_field = _usage_field(names_only)
        option = [(kind, name) for kind, name in rules.find_named(names_only) if kind in ("item", "move", "ability")]
        if OPTION_ASK_RE.search(q) and option and plan.usage_field != "teammates":
            plan.usage_field, plan.usage_option = option[0]

    # Stated battle conditions: counted when they change this kind of answer, otherwise reported as not counted
    plan.situation = [c for c in found if not plan.raw_stats and constraints.counts_for(c, plan.intent)]
    plan.counted = list(dict.fromkeys(c.text for c in plan.situation))
    plan.unhandled = list(dict.fromkeys(c.text for c in found if c not in plan.situation))
    return plan

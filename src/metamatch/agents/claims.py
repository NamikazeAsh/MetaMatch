"""
Clause level claim extraction for the grounded answer verifiers.

Each explanation is split into clauses; inside a clause the speed, KO or type claim is pulled out together with
who it is about and whether it is negated, then compared with the engine's verdict. Plain keyword lists can't do
this: "Dragapult can't outspeed Tusk" agrees with a "yes, Tusk is faster" verdict.
"""
import re

# Negation cues; "n't" covers can't/won't/doesn't/isn't, "cannot" is its own token
NEG = re.compile(r"\b(?:not|never|no longer|cannot|unable to|unlikely to|prevents?(?: it)? from|keeps?(?: it)? from|fails? to|failing to|isn't|aren't|wasn't|can't|won't|"
                 r"doesn't|don't|didn't|wouldn't|couldn't|shouldn't|nor|neither|no|non|insufficient|short of)\b|n't\b|\bnon-", re.I)
# "not only X but", "not just": not a negation of the predicate
NOT_NEG = re.compile(r"\bnot (?:only|just|merely)\b|\bno doubt\b|\bnever (?:fail|miss)s?\b", re.I)
CLAUSE_SPLIT = re.compile(r"\.(?!\d)|[;!?:\n]+|,\s*(?=(?:but|while|whereas|although|though|so|and|since|because|which|meaning|however|yet)\b)|"
                          r"\b(?:but|whereas|although|though|because|since|however|which means|meaning|while|yet)\b", re.I)
WINDOW = 4  # tokens between the negation cue and the predicate
# "To determine if X OHKOs Y", "If Dragapult is Scarfed, it moves first": not an assertion
QUESTION = re.compile(r"\b(?:if|whether|unless)\b", re.I)


def asserted(clause, start):
    return not QUESTION.search(clause[:start])


def clauses(text):
    return [c.strip() for c in CLAUSE_SPLIT.split(text or "") if c and c.strip()]


def negated(clause, start):
    """A negation cue ends within WINDOW tokens before position `start`."""
    before = clause[:start]
    before = NOT_NEG.sub(" ", before)
    last = None
    for m in NEG.finditer(before):
        last = m
    if not last:
        return False
    gap = before[last.end():].split()
    # "no"/"non" only negate the word right after them ("no knockout"), not "No Guard, it is immune"
    tight = last.group(0).lower().rstrip("-") in ("no", "non")
    return len(gap) <= (0 if tight else WINDOW)


# ---------------------------------------------------------------- speed
SPEED_PREDICATES = [
    # (regex, direction for subject: +1 faster, -1 slower, 0 tie, transitive)
    (r"outsped by|outpaced by|out-sped by", -1, True),
    (r"\b(?:is|are|be|being|been|gets?|got|getting) (?:\w+ )?(?:outsped|outpaced|out-sped)\b", -1, False),
    (r"\bunder-?speeds?\b|\bslower than\b|\b(?:lower|less) speed than\b|\bbehind\b(?= \w+ in speed)", -1, True),
    (r"\b(?:moves?|moving|goes|go|going|attacks?|strikes?|acts?|hits?) (?:second|last|after)\b", -1, False),
    (r"\bis slower\b|\bare slower\b|\bslower\b", -1, False),
    (r"\bout-?speed(?:s|ing)?\b|\bout-?pac(?:e|es|ing)\b|\boutruns?\b", +1, True),
    (r"\b(?:faster|quicker|speedier) than\b|\b(?:higher|more) speed than\b|\b(?:gets?|has|have) the jump on\b|"
     r"\b(?:speed )?(?:advantage|edge) over\b|\b(?:moves?|goes|go|attacks?|strikes?|acts?) before\b", +1, True),
    (r"\b(?:moves?|moving|goes|go|going|attacks?|strikes?|acts?|hits?|gets? to move) first\b|\bis faster\b|\bfaster\b", +1, False),
    (r"\bspeed[\s-]ties?\b|\bties? with\b|\btied\b|\bsame speed\b|\bequal speed\b|\bequally fast\b", 0, False),
]
SPEED_SKIP = re.compile(r"%|\bscarf\b|\btailwind\b|\btrick room\b|\bboost|\+\d|\bpriority\b|\bdragon dance\b|\bparaly", re.I)


def _aliases(name):
    name = name.strip()
    out = {name}
    base = re.sub(r"^Mega ", "", name)
    out.add(base)
    out.add(base.split("-")[0])
    if "-Mega" in name or name.startswith("Mega "):
        out.add("Mega " + base.split("-")[0])
    words = base.split("-")[0].split()
    if len(words) > 1:
        out.add(words[-1])
    return {a.lower() for a in out if len(a) > 2}


def _entity_regex(user, other, player="user"):
    """Mentions of the verdict's subject ("user" role) and other side. `player` is the role of the player's own
    Pokemon, which "you" refers to: the subject normally, the other side when the question's subject is the opponent."""
    ua, oa = _aliases(user) if user else set(), _aliases(other) if other else set()
    shared = ua & oa
    ua, oa = ua - shared, oa - shared
    foe = "other" if player == "user" else "user"
    ents = [(a, "user") for a in ua] + [(a, "other") for a in oa]
    ents += [(w, player) for w in ("you", "your", "you're")] + [(w, foe) for w in ("the opponent", "the foe", "opposing")]
    ents += [("it", "it")]
    ents.sort(key=lambda e: -len(e[0]))
    pat = re.compile("|".join(rf"\b{re.escape(a)}\b" for a, _ in ents), re.I)
    role = {a: r for a, r in ents}
    return pat, role


def speed_claims(text, verdict):
    """Yields (clause, answers the clause allows) for each speed claim about the verdict's pair."""
    player = "user" if getattr(verdict, "subject_is_player", True) else "other"
    pat, role = _entity_regex(verdict.subject, verdict.other, player)
    last = "user"
    for clause in clauses(text):
        mentions = [(m.start(), m.end(), role[m.group(0).lower()]) for m in pat.finditer(clause)]
        skip = SPEED_SKIP.search(clause)
        taken = []
        for rx, direction, transitive in SPEED_PREDICATES:
            for m in re.finditer(rx, clause, re.I):
                if any(m.start() < e and s < m.end() for s, e in taken):
                    continue
                taken.append((m.start(), m.end()))
                if skip or not asserted(clause, m.start()):
                    continue
                subj = [r for s, e, r in mentions if e <= m.start()]
                obj = [r for s, e, r in mentions if s >= m.end()]
                subject = (last if subj[-1] == "it" else subj[-1]) if subj else None
                if obj and obj[0] == "it":  # "you don't outspeed it": it is the other side
                    obj[0] = {"user": "other", "other": "user"}.get(subject, last)
                if transitive and obj:
                    subject = "other" if obj[0] == "user" else "user" if obj[0] == "other" else subject
                if subject is None or (direction != 0 and transitive and not obj and not subj):
                    continue
                if direction == 0:
                    allows = {"yes", "no"} if negated(clause, m.start()) else {"tie"}
                else:
                    d = direction if subject == "user" else -direction
                    claim = "yes" if d > 0 else "no"
                    allows = ({"yes", "no", "tie"} - {claim}) if negated(clause, m.start()) else {claim}
                yield clause, allows
        named = [r for s, e, r in mentions if r != "it"]
        if named:  # "it" in the next clause means this clause's subject
            last = named[0]


def speed_clash(text, verdict):
    if not verdict.other:
        return None
    # Claims are read as "the subject is faster"; an "is X slower?" verdict answers the inverse
    faster = {"yes": "no", "no": "yes"}.get(verdict.answer, verdict.answer) if getattr(verdict, "ask_slower", False) \
        else verdict.answer
    for clause, allows in speed_claims(text, verdict):
        if faster not in allows:
            return f"a speed claim that contradicts the result: \"{clause}\""
    return None


# ---------------------------------------------------------------- KO
WORDNUM = {"one": 1, "o": 1, "single": 1, "two": 2, "three": 3, "four": 4, "five": 5}
KO_PRED = re.compile(
    r"\b(?P<n>o|\d|one|two|three|four)[\s-]?hko(?:s|es|ed|ing|'s)?\b"
    r"|\b(?P<n2>one|two|three|four|\d)[\s-]?hit[\s-]?(?:ko|knock ?out)s?\b"
    r"|\bone[\s-]?shot(?:s|ting)?\b"
    r"|\b(?:ko(?:s|es|ed|'s)?|knocks? (?:\w+ ){0,3}?out|knock(?:ed|ing)? out|knockout|kills?|takes? (?:\w+ )?(?:out|down)|"
    r"finish(?:es)? (?:\w+ )?off|faints?|fainting)\b", re.I)
SURVIVE_PRED = re.compile(r"\b(?:survives?|surviving|lives?|living|tanks?|withstands?|endures?|stays? (?:alive|standing))\b", re.I)
HITS_MOD = re.compile(r"\bin (?:one|a single|1|just one|a) (?:hit|shot|attack|blow)\b|\bin (?P<n>two|three|four|\d) (?:hits|shots|attacks)\b", re.I)
HEDGE = re.compile(r"%|\bchance\b|\brolls?\b|\bcan\b|\bcould\b|\bmay\b|\bmight\b|\bpossibl|\blikely\b|\bsometimes\b|"
                   r"\bunless\b|\bif\b|\bonly\b|\bpotential|\boccasional|\bhigh roll|\bnot (?:always|guaranteed)|\breliably\b|"
                   r"\bconsistently\b|\balways\b|\bguarantee", re.I)
STRONG = re.compile(r"\bguarantee[sd]?\b|\bguaranteeing\b|\balways\b|\bsurely\b|\bcomfortably\b|\bcleanly\b|\beasily\b|\bevery roll\b", re.I)


def ko_truth(verdict):
    """A function n -> 'yes'/'no'/'sometimes'/None for 'the attack KOs in n hits'."""
    asked = getattr(verdict, "hits", None) or _asked_hits(verdict.statement)
    ko_answer = {"yes": "no", "no": "yes", "sometimes": "sometimes"}[verdict.answer] if verdict.survive else verdict.answer
    calc = None
    for f in verdict.facts:
        m = re.search(r"(guaranteed|chance to) (O|\d+)HKO", f)
        if m:
            calc = (1 if m.group(2) == "O" else int(m.group(2)), m.group(1) == "guaranteed")
    pct = re.search(r"does ([\d.]+)-([\d.]+)%", verdict.statement)

    def truth(n):
        if n == asked:
            return ko_answer
        if calc:
            h, sure = calc
            return "yes" if h < n or (h == n and sure) else "sometimes" if h == n else "no"
        if n == 1 and pct:
            lo, hi = float(pct.group(1)), float(pct.group(2))
            return "yes" if lo >= 100 else "no" if hi < 100 else "sometimes"
        if ko_answer == "yes" and n > asked:
            return "yes"
        if ko_answer == "no" and n < asked:
            return "no"
        return None
    return truth, asked


def _asked_hits(statement):
    m = re.search(r"\b(O|\d)HKO", statement)
    return 1 if not m or m.group(1) == "O" else int(m.group(1))


def ko_claims(text, verdict):
    truth, asked = ko_truth(verdict)
    for clause, sentence in ((c, s) for s in re.split(r"(?<=[.!?])\s+", text or "") for c in clauses(s)):
        mod = HITS_MOD.search(clause)
        for m in list(KO_PRED.finditer(clause)) + list(SURVIVE_PRED.finditer(clause)):
            word = m.group(0).lower()
            n = m.groupdict().get("n") or m.groupdict().get("n2")
            if n:
                n = WORDNUM.get(n.lower()) or int(n)
            elif "shot" in word:
                n = 1
            elif mod:
                n = WORDNUM.get((mod.group("n") or "one").lower(), None) or int(mod.group("n"))
            else:
                n = asked
            survive = bool(SURVIVE_PRED.fullmatch(m.group(0)))
            neg = negated(clause, m.start())
            ko = (not neg) if not survive else neg
            # "not enough to OHKO" / "fails to OHKO"
            t = truth(n)
            # postposed negation: "the OHKO is not possible"
            if re.match(r"[^,]{0,12}?\b(?:is|are|was)(?: not|n't) (?:possible|happening|likely|on the table)", clause[m.end():], re.I):
                ko = not ko
            if not asserted(clause, m.start()) or re.search(r"\bwhen\b", clause[:m.start()], re.I):
                continue
            if t is None:
                continue
            hedged = bool(HEDGE.search(sentence))  # "would OHKO ..., an 87.5% chance to OHKO" is hedged
            strong = bool(STRONG.search(clause)) and not re.search(r"\bnot (?:a )?guarantee|\bno guarantee", clause, re.I)
            if ko:
                allows = {"yes"} if strong else {"yes", "sometimes"} if hedged else {"yes"}
            else:
                allows = {"no", "sometimes"} if hedged else {"no"}
            yield clause, n, allows, t


def ko_clash(text, verdict):
    for clause, n, allows, t in ko_claims(text, verdict):
        if t not in allows:
            return f"a KO claim that contradicts the result: \"{clause}\""
    return None


# ---------------------------------------------------------------- type
TYPE_WORDS = {
    "immune": re.compile(r"\bimmun\w*|\b(?:takes|deals?|does) no damage\b|\bno effect\b|\bunaffected\b", re.I),
    "resists": re.compile(r"\bresist\w*|\bnot very effective\b|\bresisted\b", re.I),
    "weak": re.compile(r"\bweak(?:ness|nesses)?\b|\bsuper[\s-]effective\b", re.I),
    "neutral": re.compile(r"\bneutral\w*\b", re.I),
}
TYPES = "normal fire water electric grass ice fighting poison ground flying psychic bug rock ghost dragon dark steel fairy".split()


def type_clash(text, verdict):
    t = re.search(r"(?:to|from) (\w+) attacks", verdict.statement)
    t = t.group(1).lower() if t else None
    # Ability names like Weak Armor must not read as matchup words
    ability = re.search(r"\([^,()]+, ([^()]+)\)", verdict.statement)
    if ability:
        text = re.sub(re.escape(ability.group(1)), "the ability", text, flags=re.I)
    for clause in clauses(text):
        named = {w for w in TYPES if re.search(rf"\b{w}\b", clause, re.I)}
        # A clause about other attacking types ("but weak to Fire") is not about this verdict
        if t and named and t not in named:
            continue
        for answer, rx in TYPE_WORDS.items():
            for m in rx.finditer(clause):
                if answer == "resists" and m.group(0).lower() == "not very effective":
                    neg = False
                elif answer == "immune" and re.match(r"no |not ", m.group(0), re.I):
                    neg = False
                else:
                    neg = negated(clause, m.start())
                if (answer != verdict.answer) == neg:
                    continue
                # positive claim of a different answer, or a denial of the right one
                return f"wording that says {'not ' if neg else ''}{answer} when the result is {verdict.answer}: \"{clause}\""
    return None

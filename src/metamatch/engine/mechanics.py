"""
Shared battle mechanics on top of calc results, used by both the chat solvers and Oak's briefing
so the two can never disagree: final Speed, KO counts that respect Sturdy, Focus Sash and
Disguise, and which side lands its KO first once priority is counted.
"""
import math
import re

from metamatch.engine import calc

ABILITY_BREAKERS = {"Mold Breaker", "Teravolt", "Turboblaze"}
ABILITY_IGNORING_MOVES = {"Sunsteel Strike", "Moongeist Beam", "Photon Geyser", "Menacing Moonraze Maelstrom",
                          "Searing Sunraze Smash", "Light That Burns the Sky"}
OPP_SPEED_ITEMS = {"Choice Scarf", "Iron Ball"}


# Speed: one rule set. The user's own item and ability always apply (that is their set). An
# opponent's item only applies when the question states it; its likely Scarf is reported as a
# share, never assumed. Field effects (Tailwind, weather) only apply when the request passes them.

def final_speed(spec, game, move, field=None, side="attacker"):
    """Speed after item, ability, boosts, status and field, from @smogon/calc's getFinalSpeed."""
    req = {"game": game, "attacker": spec, "defender": spec, "move": move}
    if field:
        req["field"] = field
    r = calc.calculate(req)
    return r.get(f"{side}_speed") if r else None


def opponent_speed_spec(spec, stated_item):
    """The opponent spec for Speed: its likely Speed item is dropped unless the question named one."""
    if stated_item or spec.get("item") not in OPP_SPEED_ITEMS:
        return spec
    return {k: v for k, v in spec.items() if k != "item"}


def scarf_adjusted_share(user_speed, speeds, scarf_share):
    """Share of opponent sets the user outspeeds, mixing in the chance it holds Choice Scarf."""
    plain = sum(share for spe, share in speeds if spe < user_speed)
    scarfed = sum(share for spe, share in speeds if int(spe * 1.5) < user_speed)
    return (1 - scarf_share) * plain + scarf_share * scarfed


# KOs

def _hits_in_move(result):
    m = re.search(r"\((\d+) hits\)", result.get("desc") or "")
    return int(m.group(1)) if m else 1


def survival_effect(result, attacker, defender, move):
    """'Sturdy', 'Focus Sash', 'Disguise' or None: what stops a full HP defender being OHKOed."""
    if _hits_in_move(result) > 1:
        return None
    breaks = attacker.get("ability") in ABILITY_BREAKERS or move in ABILITY_IGNORING_MOVES
    ability, item = defender.get("ability"), defender.get("item")
    if ability == "Disguise" and not breaks:
        return "Disguise"
    if ability == "Sturdy" and not breaks:
        return "Sturdy"
    if item == "Focus Sash":
        return "Focus Sash"
    return None


def _total(result, n, effect):
    """(min, max) damage of n uses of the move from full HP, first hit adjusted for `effect`."""
    hp = result["defender_stats"]["hp"]
    lo, hi = result["range"]
    if effect == "Disguise":
        first = (hp // 8, hp // 8)
    elif effect:
        first = (min(lo, hp - 1), min(hi, hp - 1))
    else:
        first = (lo, hi)
    return first[0] + (n - 1) * lo, first[1] + (n - 1) * hi


def _text_hits(ko_text):
    m = re.search(r"(guaranteed|chance to) (O|\d+)HKO", ko_text or "")
    if not m:
        return None, False
    return (1 if m.group(2) == "O" else int(m.group(2))), m.group(1) == "guaranteed"


def ko_answer(result, n, attacker, defender, move):
    """('yes' | 'no' | 'sometimes', effect) for 'does this move nHKO', from damage rolls."""
    effect = survival_effect(result, attacker, defender, move)
    hp = result["defender_stats"]["hp"]
    if effect != "Disguise" and result["range"][1] < hp:
        effect = None    # the hit never threatens a full HP KO, so Sturdy or Sash changes nothing
    if hp <= 0 or result["range"][1] <= 0:
        return "no", effect
    text_n, text_sure = _text_hits(result.get("ko"))
    # The calc text counts end of turn recovery (Leftovers, ...), so trust it whenever it reaches n
    # hits or more; it only stops being enough when it names fewer hits (a 'chance to OHKO' says
    # nothing about a guaranteed 2HKO), and it knows nothing about Sturdy, Sash or Disguise
    if not effect and text_n is not None and text_n >= n:
        return ("no" if text_n > n else "yes" if text_sure else "sometimes"), effect
    lo, hi = _total(result, n, effect)
    return ("yes" if lo >= hp else "sometimes" if hi >= hp else "no"), effect


def hits_to_ko(result, attacker, defender, move, cap=10):
    """Hits needed at the lowest roll from full HP, or None when the move does no damage."""
    if not result or result["range"][0] <= 0:
        return None
    effect = survival_effect(result, attacker, defender, move)
    hp = result["defender_stats"]["hp"]
    for n in range(1, cap + 1):
        if _total(result, n, effect)[0] >= hp:
            return n
    return math.ceil(hp / result["range"][0]) + (1 if effect else 0)


# Priority

def move_priority(move, dex, attacker, field=None, turn=1):
    """Priority bracket of `move` for this attacker: Grassy Glide only in Grassy Terrain, Fake Out only turn 1."""
    data = dex.move(move) or {}
    pri = data.get("priority", 0) or 0
    terrain = (field or {}).get("terrain") or ("Grassy" if attacker.get("ability") == "Grassy Surge" else None)
    if data.get("name") == "Grassy Glide" and terrain == "Grassy":
        pri = 1
    if data.get("name") == "Fake Out" and turn != 1:
        pri = 0
    return pri

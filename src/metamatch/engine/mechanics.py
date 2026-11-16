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
    """The opponent spec for Speed: its likely Speed item is dropped unless the question named one.
    Booster Energy counts as one, since it raises Speed whenever Speed is the holder's best stat."""
    if stated_item or spec.get("item") not in OPP_SPEED_ITEMS | {"Booster Energy"}:
        return spec
    return {k: v for k, v in spec.items() if k != "item"}


def scarf_adjusted_share(user_speed, speeds, scarf_share, booster_share=0.0):
    """Share of opponent sets the user outspeeds, mixing in the chance it holds Choice Scarf or a Booster Energy that
    raises its Speed (both x1.5)."""
    plain = sum(share for spe, share in speeds if spe < user_speed)
    boosted = sum(share for spe, share in speeds if int(spe * 1.5) < user_speed)
    fast = min(1.0, scarf_share + booster_share)
    return (1 - fast) * plain + fast * boosted


def scarf_adjusted_tie(user_speed, speeds, scarf_share, booster_share=0.0):
    """Share of opponent sets at exactly the user's Speed, with the same Choice Scarf and Booster mix."""
    plain = sum(share for spe, share in speeds if spe == user_speed)
    boosted = sum(share for spe, share in speeds if int(spe * 1.5) == user_speed)
    fast = min(1.0, scarf_share + booster_share)
    return (1 - fast) * plain + fast * boosted


# KOs

def _hits_in_move(result):
    m = re.search(r"\((\d+) hits\)", result.get("desc") or "")
    return int(m.group(1)) if m else 1


def survival_effect(result, attacker, defender, move, full_hp=True):
    """'Sturdy', 'Focus Sash', 'Disguise' or None: what stops a full HP defender being OHKOed.
    Sturdy and Focus Sash need full HP; Disguise breaks only on a hit, so chip doesn't remove it."""
    if _hits_in_move(result) > 1:
        return None
    breaks = attacker.get("ability") in ABILITY_BREAKERS or move in ABILITY_IGNORING_MOVES
    ability, item = defender.get("ability"), defender.get("item")
    if ability == "Disguise" and not breaks:
        return "Disguise"
    if not full_hp:
        return None
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


def ko_answer(result, n, attacker, defender, move, full_hp=True):
    """('yes' | 'no' | 'sometimes', effect) for 'does this move nHKO', from damage rolls.
    full_hp=False when the defender is chipped first (stated HP, hazards), so Sturdy and Sash can't save it."""
    effect = survival_effect(result, attacker, defender, move, full_hp)
    hp = result.get("defender_cur_hp") or result["defender_stats"]["hp"]
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


def self_drop(move, game):
    """Stages the user's attacking stat falls after each use (Draco Meteor 2, Make It Rain 1), 0 for most moves."""
    from metamatch.engine.dex import get_dex
    dex = get_dex(game) if game else None
    return ((dex.move(move) or {}).get("selfDrop", 0) if dex else 0) or 0


def hits_to_ko(result, attacker, defender, move, cap=10, game=None, field=None, roll=0):
    """Hits needed from full HP at the lowest roll (roll=0, the guaranteed count) or the highest (roll=1, the best
    case), or None when the move does no damage.
    A move that lowers its user's attacking stat (Draco Meteor, Make It Rain) hits weaker every time: with `game`
    known, the calc's own 'times used' option counts every later use at the dropped stat, with the same `field`,
    instead of repeating the first hit."""
    if not result or result["range"][0] <= 0 or result.get("half_hp"):
        # A move that takes half the target's current HP (Ruination) never knocks out on its own
        return None
    effect = survival_effect(result, attacker, defender, move)
    hp = result["defender_stats"]["hp"]
    if game and self_drop(move, game) and _total(result, 1, effect)[roll] < hp:
        uses = range(2, 6)
        reqs = [{"game": game, "attacker": attacker, "defender": defender, "move": move,
                 "moveOptions": {"timesUsed": n}, **({"field": field} if field else {})} for n in uses]
        results = calc.calculate_many(reqs)
        if any(results):
            for n, r in zip(uses, results):
                # A Sash or Sturdy first hit is held at 1 HP, so it takes one more use than the plain total
                if r and r.get("range") and r["range"][roll] >= hp:
                    return n + (1 if effect else 0)
            return uses[-1] + 1
        # Calc unavailable for the repeat: fall back to repeating the first hit
    for n in range(1, cap + 1):
        if _total(result, n, effect)[roll] >= hp:
            return n
    return math.ceil(hp / result["range"][roll]) + (1 if effect else 0)


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

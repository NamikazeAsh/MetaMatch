"""
The move lists every part of the app shares, in one place: what counts as a pivot, a hazard, a priority attack,
hazard removal and setup. Pivots, hazards and priority are read from Pokemon Showdown's own move data
(data/json/rules_text.json, built by scripts/build_rules_text.py), so a new move counts the day it's in the data.
Removal and setup are typed here because Showdown has no flag for them: each removal move is coded on its own, and
"boosts its own stats" also covers moves nobody sets up with (Growth aside, Harden, Withdraw...).
"""
import json
from functools import lru_cache

from metamatch import config
from metamatch.engine.constraints import SETUP_MOVES

RULES_TEXT = config.JSON_DIR / "rules_text.json"
# Moves the data marks but that don't do the job the list is for
NOT_PIVOTS = {"Revival Blessing"}                    # "switches" to revive a fainted teammate, never pivots out
CHIP_PRIORITY = {"Fake Out", "Feint", "Bide"}        # first turn chip or a relic: priority, but never a finisher
# Priority only under a condition the user's ability brings: move -> ability
ABILITY_PRIORITY = {"Grassy Glide": "Grassy Surge"}
HAZARD_ORDER = ("Stealth Rock", "Spikes", "Toxic Spikes", "Sticky Web")

REMOVAL = ("Rapid Spin", "Defog", "Mortal Spin", "Court Change", "Tidy Up")
# Setup moves: the constraint parser's list (with its boost amounts) plus the ones it never needs to read from a question
SETUP = frozenset(SETUP_MOVES) | {"Growth", "Coil", "Work Up", "Shift Gear", "Curse", "Tail Glow", "Geomancy",
                                  "Clangorous Soul", "No Retreat", "Fillet Away", "Rock Polish"}


@lru_cache(maxsize=1)
def _moves():
    return json.loads(RULES_TEXT.read_text(encoding="utf-8"))["moves"]


def _hazards():
    found = {n for n, m in _moves().items() if m.get("hazard")}
    return tuple(sorted(found, key=lambda n: (HAZARD_ORDER.index(n) if n in HAZARD_ORDER else len(HAZARD_ORDER), n)))


HAZARDS = _hazards()
PIVOTS = tuple(sorted(n for n, m in _moves().items() if m.get("switches") and n not in NOT_PIVOTS))
PRIORITY = frozenset(n for n, m in _moves().items()
                     if m.get("priority", 0) > 0 and m.get("category") != "Status" and n not in CHIP_PRIORITY)


def is_priority(move, abilities=()):
    """A damaging move that moves first: priority in the data, or priority through the user's own ability."""
    needs = ABILITY_PRIORITY.get(move)
    return move in PRIORITY or (needs is not None and needs in abilities)


def ids(names):
    """Showdown ids ('U-turn' -> 'uturn'), the form the usage stats key moves by."""
    return {n.lower().replace("-", "").replace(" ", "").replace("'", "") for n in names}

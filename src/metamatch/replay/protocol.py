"""
Parses a Pokémon Showdown battle log (singles) into a Battle, following sim/SIM-PROTOCOL.md.

Every Pokémon is keyed by its protocol identity ("p1: Nickname"), never by species, so team
preview wildcards, Mega Evolution and other forme changes can't create ghost entries. Each
turn keeps its start state (actives, HP, boosts, field), what each side chose to do and the
faints it caused; each Pokémon keeps what it revealed and on which turn, so later analysis can
use only what a player knew at the time.
"""
import copy
import re
from dataclasses import dataclass, field

from metamatch.engine.dex import get_dex, to_id

SIDES = ("p1", "p2")
# Entry hazards and their maximum layers; everything else on a side (screens, Tailwind) is not a hazard
HAZARD_LAYERS = {"Stealth Rock": 1, "Spikes": 3, "Toxic Spikes": 2, "Sticky Web": 1, "G-Max Steelsurge": 1}
HAZARD_DAMAGE = {"Stealth Rock", "Spikes", "G-Max Steelsurge"}
REMOVAL_MOVES = {"Rapid Spin", "Defog", "Mortal Spin", "Tidy Up", "Court Change"}
SELF_KO_MOVES = {"Explosion", "Self-Destruct", "Misty Explosion", "Final Gambit", "Healing Wish",
                 "Lunar Dance", "Memento"}
SETUP_MOVES = {"Swords Dance", "Dragon Dance", "Nasty Plot", "Calm Mind", "Quiver Dance", "Bulk Up",
               "Iron Defense", "Amnesia", "Agility", "Rock Polish", "Shell Smash", "Coil", "Shift Gear",
               "Belly Drum", "Curse", "Growth", "Work Up", "Hone Claws", "Tail Glow", "Geomancy",
               "Cotton Guard", "Cosmic Power", "Stockpile", "Victory Dance", "Clangorous Soul",
               "No Retreat", "Howl", "Tidy Up", "Fillet Away", "Acid Armor", "Barrier", "Autotomize",
               "Trailblaze", "Flame Charge"}
STATUS_DAMAGE = {"psn": "poison", "tox": "poison", "brn": "burn"}
DELAYED_MOVES = {"Future Sight", "Doom Desire"}
WEATHER_DAMAGE = {"Sandstorm", "Hail"}
# Damage a Pokémon does to itself (as written in [from] tags, prefixes stripped)
SELF_DAMAGE = {"Recoil", "recoil", "Life Orb", "confusion", "Solar Power", "Dry Skin", "Sticky Barb",
               "Black Sludge", "Mind Blown", "Steel Beam", "Chloroblast", "Struggle"}

HP_RE = re.compile(r"^(\d+)(?:/(\d+))?")
IDENT_RE = re.compile(r"^(p[1-4])[a-d]?: (.+)$")


class UnsupportedReplay(ValueError):
    """The log is not a singles battle this parser can analyse."""


def parse_hp(text):
    """
    '75/100 par' -> (75, 'par'); '0 fnt' -> (0, None); Champions '50/100y' -> (50, None).
    HP is returned as a percent (never 0 unless fainted). (None, None) when unreadable.
    """
    parts = (text or "").split()
    m = HP_RE.match(parts[0]) if parts else None
    if not m:
        return None, None
    current, maximum = int(m.group(1)), int(m.group(2) or 100)
    if current == 0 or maximum == 0:
        return 0, None
    pct = max(1, current * 100 // maximum)
    status = parts[1] if len(parts) > 1 and parts[1] != "fnt" else None
    return min(pct, 100), status


def parse_ident(text):
    """'p1a: Nick' or 'p1: Nick' -> ('p1', 'p1: Nick'); (None, None) when it isn't a Pokémon."""
    m = IDENT_RE.match((text or "").strip())
    if not m:
        return None, None
    return m.group(1), f"{m.group(1)}: {m.group(2)}"


def species_of(details):
    """'Garchomp-Mega, L50, F, shiny' -> 'Garchomp-Mega'."""
    return (details or "").split(",")[0].strip()


def _tags(args):
    """{'from': 'item: Life Orb', 'of': 'p2a: X', 'miss': True, ...} from trailing [tag] args."""
    tags = {}
    for a in args:
        if a.startswith("["):
            key, _, value = a[1:].partition("]")
            tags[key.strip()] = value.strip() or True
    return tags


def _effect(text):
    """('item', 'Life Orb') from 'item: Life Orb'; ('', 'Stealth Rock') from 'Stealth Rock'."""
    kind, sep, name = (text or "").partition(": ")
    return (kind, name) if sep and kind in ("item", "ability", "move") else ("", text or "")


@dataclass
class Mon:
    side: str
    ident: str
    species: str
    first_species: str
    first_turn: int
    hp: int = 100
    status: str | None = None
    status_by: str | None = None       # opponent identity that inflicted the status, when known
    fainted: bool = False
    boosts: dict = field(default_factory=dict)
    item: str | None = None
    item_turn: int | None = None
    item_lost: bool = False
    ability: str | None = None
    ability_turn: int | None = None
    moves: dict = field(default_factory=dict)        # move -> turn first used
    tera: str | None = None
    tera_turn: int | None = None
    hazard_damage: int = 0
    kos: list = field(default_factory=list)          # indexes into Battle.faints
    afflictions: dict = field(default_factory=dict)  # 'Salt Cure' -> opponent identity
    zero_hit: dict | None = None                     # the hit that took HP to 0, until it faints
    perish0: bool = False
    transformed: bool = False
    typechange_turn: int | None = None               # last turn its type changed (Protean, Soak...)

    @property
    def nickname(self):
        return self.ident.split(": ", 1)[1]


@dataclass
class Action:
    kind: str            # 'move', 'switch' or 'cant'
    ident: str           # who moved, or who switched in
    move: str | None = None
    target: str | None = None
    order: int = 0       # position among the turn's actions, 0 = first


@dataclass
class Turn:
    number: int
    start: dict          # side -> {'ident', 'species', 'hp', 'status', 'boosts', 'tera'} or None
    hazards: dict        # side -> {hazard: layers} at the start of the turn
    weather: str | None
    terrain: str | None
    trick_room: bool
    actions: dict = field(default_factory=dict)   # side -> Action
    faints: list = field(default_factory=list)    # indexes into Battle.faints
    health: dict = field(default_factory=dict)    # side -> team health % at the end of the turn
    log: list = field(default_factory=list)       # compact event dicts, see Battle.log


@dataclass
class Battle:
    format_id: str = ""
    format_name: str = ""
    players: dict = field(default_factory=lambda: {"p1": "Player 1", "p2": "Player 2"})
    teamsize: dict = field(default_factory=lambda: {"p1": 6, "p2": 6})
    preview: dict = field(default_factory=lambda: {"p1": [], "p2": []})
    mons: dict = field(default_factory=lambda: {"p1": {}, "p2": {}})
    turns: list = field(default_factory=list)
    faints: list = field(default_factory=list)       # {'turn', 'side', 'ident', 'species', 'cause', 'by', 'source', 'damage'}
    winner: str | None = None                       # 'p1', 'p2', 'tie' or None if unfinished
    conditions: dict = field(default_factory=lambda: {"p1": {}, "p2": {}})
    weather_history: list = field(default_factory=list)   # {'turn', 'weather', 'side', 'ident'}
    removals: list = field(default_factory=list)          # {'turn', 'side', 'hazard', 'by', 'move'}
    setups: list = field(default_factory=list)            # {'turn', 'side', 'ident', 'move'}
    bounced: list = field(default_factory=list)           # {'turn', 'side', 'ident', 'move', 'bouncer'}
    immune: list = field(default_factory=list)            # {'turn', 'side', 'ident', 'move', 'target', 'source'}
    health: list = field(default_factory=list)            # {'turn', 'p1', 'p2'} team health % per turn

    def mon(self, ident):
        side = ident[:2]
        return self.mons.get(side, {}).get(ident)

    def name(self, ident):
        m = self.mon(ident)
        return m.species if m else (ident.split(": ", 1)[1] if ident and ": " in ident else ident)

    def hazards(self, side):
        return {h: n for h, n in self.conditions[side].items() if h in HAZARD_LAYERS}

    def fainted(self, side):
        return sum(1 for m in self.mons[side].values() if m.fainted)

    def remaining(self, side):
        return max(0, self.teamsize[side] - self.fainted(side))

    def unrevealed(self, side):
        """Team preview species that never appeared (or, in Bring 3 formats, were not brought)."""
        seen = [m for m in self.mons[side].values()]
        out = []
        for species in self.preview[side]:
            match = next((m for m in seen if _same_species(species, m.first_species)), None)
            if match:
                seen.remove(match)
            else:
                out.append(species.replace("-*", ""))
        return out


def _base_species(name):
    clean = (name or "").replace("-*", "")
    for game in ("sv", "champions"):
        dex = get_dex(game)
        s = dex.species(clean) if dex else None
        if s:
            return to_id(s.get("baseSpecies") or s["name"])
    return to_id(clean.split("-")[0])


def _same_species(preview, species):
    return to_id(preview.replace("-*", "")) == to_id(species) or _base_species(preview) == _base_species(species)


class _Parser:
    def __init__(self, battle):
        self.b = battle
        self.turn_no = 0
        self.turn = None
        self.phase = "start"          # start (leads), action, end (after upkeep)
        self.active = {"p1": None, "p2": None}
        self.stint = {"p1": None, "p2": None}
        self.current = None           # (side, ident, move) of the move being resolved
        self.pending_dbond = None
        self.order = 0
        self.field = {}               # 'weather', 'terrain', 'Trick Room' -> name
        self.delayed = {}             # side about to be hit -> (user side, user ident, 'Future Sight')

    # --- helpers -------------------------------------------------------------------------

    def get(self, ident, species=None, create=False):
        side = ident[:2]
        mons = self.b.mons[side]
        if ident not in mons and create:
            mons[ident] = Mon(side=side, ident=ident, species=species or ident.split(": ", 1)[1],
                              first_species=species or ident.split(": ", 1)[1], first_turn=self.turn_no)
        return mons.get(ident)

    def resolve(self, text):
        """Mon for a protocol POKEMON argument, or None."""
        side, ident = parse_ident(text)
        return self.get(ident) if ident else None

    def reveal(self, mon, effect):
        """Records an item or ability named in an effect string on its owner."""
        kind, name = _effect(effect)
        if not mon or not name:
            return
        if kind == "item" and not mon.item:
            mon.item, mon.item_turn = name, self.turn_no
        elif kind == "ability" and not mon.ability and not mon.transformed:
            mon.ability, mon.ability_turn = name, self.turn_no

    def owner(self, target, tags):
        """The Pokémon an [from] item/ability belongs to: [of] when given, else the target."""
        of = self.resolve(tags["of"]) if isinstance(tags.get("of"), str) else None
        return of or target

    @staticmethod
    def opp(side):
        return "p2" if side == "p1" else "p1"

    @staticmethod
    def set_status(mon, status):
        """HP strings always carry the current status, so they are authoritative."""
        if status != mon.status:
            mon.status = status
            if not status:
                mon.status_by = None

    def log(self, **event):
        event["turn"] = self.turn_no
        if self.turn is not None:
            self.turn.log.append(event)

    def health(self, side):
        size = self.b.teamsize[side] or 6
        revealed = list(self.b.mons[side].values())
        hp = sum(0 if m.fainted else m.hp for m in revealed) + 100 * max(0, size - len(revealed))
        return round(hp / size)

    def snapshot(self):
        start = {}
        for side in SIDES:
            m = self.get(self.active[side]) if self.active[side] else None
            start[side] = None if not m or m.fainted else {
                "ident": m.ident, "species": m.species, "hp": m.hp, "status": m.status,
                "boosts": dict(m.boosts), "tera": m.tera}
        return start

    def close_turn(self):
        if self.turn is not None:
            self.turn.health = {s: self.health(s) for s in SIDES}
            self.b.health.append({"turn": self.turn.number, **self.turn.health})

    def act(self, side, action):
        """Records a side's chosen action for this turn (only the first one counts)."""
        if self.phase == "action" and self.turn is not None and side not in self.turn.actions:
            action.order = self.order
            self.order += 1
            self.turn.actions[side] = action

    # --- protocol messages ---------------------------------------------------------------

    def on_switch(self, args, cmd):
        side, ident = parse_ident(args[0])
        if not ident or len(args) < 2:
            return
        tags = _tags(args[2:])
        species = species_of(args[1])
        existed = ident in self.b.mons[side]
        mon = self.get(ident, species, create=True)
        if "*" in mon.species or (mon.species != species and not mon.species.startswith(species)):
            mon.species = species
        # Leaving the field clears boosts and transformation of the previous active
        prev = self.get(self.active[side]) if self.active[side] else None
        if prev:
            prev.boosts = {}
            prev.transformed = False
        self.stint[side] = {"ident": ident, "backup": copy.deepcopy(mon) if existed else None,
                            "faints": len(self.b.faints), "turn": self.turn_no}
        self.active[side] = ident
        if len(args) > 2:
            hp, status = parse_hp(args[2])
            if hp is not None:
                mon.hp = hp
                mon.status = status
        mon.zero_hit = None
        forced = cmd == "drag" or "from" in tags or self.phase != "action"
        if not forced:
            self.act(side, Action("switch", ident))
        self.log(kind="switch", side=side, ident=ident, forced=forced)

    def on_replace(self, args):
        """Illusion ends: everything the disguise 'did' this stint belongs to the real Pokémon."""
        side, real_ident = parse_ident(args[0])
        stint = self.stint.get(side) if side else None
        if not stint or len(args) < 2:
            return
        fake_ident = stint["ident"]
        if fake_ident == real_ident:
            return
        fake = self.get(fake_ident)
        species = species_of(args[1])
        real = self.get(real_ident, species, create=True)
        real.species = species
        backup = stint["backup"]
        real.hp, real.status, real.boosts = fake.hp, fake.status, fake.boosts
        real.status_by, real.zero_hit, real.afflictions = fake.status_by, fake.zero_hit, fake.afflictions
        old_moves = backup.moves if backup else {}
        for move, turn in fake.moves.items():
            if move not in old_moves:
                real.moves.setdefault(move, turn)
        new_kos = fake.kos[len(backup.kos) if backup else 0:]
        real.kos.extend(new_kos)
        real.hazard_damage += fake.hazard_damage - (backup.hazard_damage if backup else 0)
        for attr in ("item", "ability", "tera"):
            if getattr(fake, attr) and getattr(fake, attr) != (getattr(backup, attr) if backup else None):
                setattr(real, attr, getattr(fake, attr))
                setattr(real, f"{attr}_turn", getattr(fake, f"{attr}_turn"))
        # Restore the disguise to what it was before this stint
        if backup:
            self.b.mons[side][fake_ident] = backup
        else:
            del self.b.mons[side][fake_ident]
        # Relabel this stint's records
        for f in self.b.faints[stint["faints"]:]:
            if f["by"] == fake_ident:
                f["by"] = real_ident
        for turn in self.b.turns:
            if turn.number < stint["turn"]:
                continue
            for action in turn.actions.values():
                if action.ident == fake_ident:
                    action.ident = real_ident
                if action.target == fake_ident:
                    action.target = real_ident
            for e in turn.log:
                for key in ("ident", "target", "by"):
                    if e.get(key) == fake_ident:
                        e[key] = real_ident
        for record in (self.b.setups, self.b.bounced, self.b.immune):
            for r in record:
                if r["turn"] >= stint["turn"]:
                    for key in ("ident", "target", "bouncer"):
                        if r.get(key) == fake_ident:
                            r[key] = real_ident
        if self.current and self.current[1] == fake_ident:
            self.current = (side, real_ident, self.current[2])
        self.active[side] = real_ident
        stint["ident"] = real_ident
        stint["backup"] = None

    def on_move(self, args):
        side, ident = parse_ident(args[0])
        if not ident or len(args) < 2:
            return
        mon = self.get(ident)
        move = args[1]
        tags = _tags(args[2:])
        _, target = parse_ident(args[2]) if len(args) > 2 else (None, None)
        self.current = (side, ident, move)
        source = tags.get("from") if isinstance(tags.get("from"), str) else None
        if source:
            kind, name = _effect(source)
            if name == "Magic Bounce" and kind == "ability" and target:
                self.reveal(mon, source)
                self.b.bounced.append({"turn": self.turn_no, "side": target[:2], "ident": target,
                                       "move": move, "bouncer": ident})
            elif name == "Dancer":
                self.reveal(mon, source)
        voluntary = not source or source.endswith("Sleep Talk")
        if mon and voluntary and not mon.transformed and move not in ("Struggle", "Recharge"):
            mon.moves.setdefault(move, self.turn_no)
        if not source:
            self.act(side, Action("move", ident, move, target))
            if move in SETUP_MOVES:
                self.b.setups.append({"turn": self.turn_no, "side": side, "ident": ident, "move": move})
        self.log(kind="move", side=side, ident=ident, move=move, target=target,
                 miss="miss" in tags, called=bool(source))

    def on_cant(self, args):
        side, ident = parse_ident(args[0])
        if not ident:
            return
        move = args[2] if len(args) > 2 else None
        mon = self.get(ident)
        if mon and move and not mon.transformed:
            mon.moves.setdefault(move, self.turn_no)
        self.act(side, Action("cant", ident, move))
        self.log(kind="cant", side=side, ident=ident, move=move, reason=args[1] if len(args) > 1 else "")

    def on_damage(self, args):
        mon = self.resolve(args[0])
        if not mon or len(args) < 2:
            return
        hp, status = parse_hp(args[1])
        if hp is None:
            return
        tags = _tags(args[2:])
        source = tags.get("from") if isinstance(tags.get("from"), str) else ""
        amount = max(0, mon.hp - hp)
        mon.hp = hp
        self.set_status(mon, status)
        kind, name = _effect(source)
        if kind in ("item", "ability"):
            self.reveal(self.owner(mon, tags), source)
        if source in HAZARD_DAMAGE:
            mon.hazard_damage += amount
        _, of_ident = parse_ident(tags["of"]) if isinstance(tags.get("of"), str) else (None, None)
        hit = {"source": name if source else None, "of": of_ident, "amount": amount,
               "move": self.current if not source else None}
        if hp == 0:
            mon.zero_hit = hit
        self.log(kind="damage", side=mon.side, ident=mon.ident, amount=amount, hp=hp,
                 source=name if source else None, by=(self.current[1] if self.current and not source else of_ident),
                 move=(self.current[2] if self.current and not source else None))

    def on_heal(self, args, cmd):
        mon = self.resolve(args[0])
        if not mon or len(args) < 2:
            return
        hp, status = parse_hp(args[1])
        if hp is None:
            return
        tags = _tags(args[2:])
        source = tags.get("from") if isinstance(tags.get("from"), str) else ""
        kind, _ = _effect(source)
        if kind in ("item", "ability"):
            self.reveal(self.owner(mon, tags), source)
        if mon.fainted and hp > 0:      # Revival Blessing
            mon.fainted = False
        mon.hp = hp
        self.set_status(mon, status)
        if hp > 0:
            mon.zero_hit = None

    def on_faint(self, args):
        mon = self.resolve(args[0])
        if not mon:
            return
        mon.fainted, mon.hp = True, 0
        side = mon.side
        cause, by, source, damage = "unknown", None, None, None
        hit = mon.zero_hit
        if hit:
            damage = hit["amount"]
            src = hit["source"]
            if src:
                source = src
                if src in HAZARD_DAMAGE:
                    cause = "hazard"
                elif src in STATUS_DAMAGE:
                    cause, by = "status", mon.status_by
                elif src in WEATHER_DAMAGE:
                    cause = "weather"
                elif hit["of"] and hit["of"][:2] != side:
                    cause, by = "indirect", hit["of"]
                elif src in SELF_DAMAGE:
                    cause = "self"
                else:
                    cause, by = "residual", mon.afflictions.get(src)
            elif hit["move"]:
                m_side, m_ident, m_move = hit["move"]
                source = m_move
                cause, by = ("move", m_ident) if m_side != side else ("self", None)
        elif self.pending_dbond and self.pending_dbond[:2] != side:
            cause, by, source = "destiny_bond", self.pending_dbond, "Destiny Bond"
        elif mon.perish0:
            cause, source = "perish", "Perish Song"
        elif self.current and self.current[1] == mon.ident and self.current[2] in SELF_KO_MOVES:
            cause, source = "self_ko", self.current[2]
        record = {"turn": self.turn_no, "side": side, "ident": mon.ident, "species": mon.species,
                  "cause": cause, "by": by, "source": source, "damage": damage}
        self.b.faints.append(record)
        index = len(self.b.faints) - 1
        if by and by[:2] != side:
            killer = self.get(by)
            if killer:
                killer.kos.append(index)
        if self.turn is not None:
            self.turn.faints.append(index)
        mon.zero_hit = None
        self.log(kind="faint", side=side, ident=mon.ident, cause=cause, by=by, source=source)

    def on_sidecondition(self, cmd, args):
        side = args[0][:2] if args else None
        if side not in SIDES or len(args) < 2:
            return
        _, name = _effect(args[1])
        conds = self.b.conditions[side]
        if cmd == "-sidestart":
            limit = HAZARD_LAYERS.get(name, 1)
            conds[name] = min(limit, conds.get(name, 0) + 1)
        else:
            if name in conds:
                del conds[name]
            tags = _tags(args[2:])
            _, by = parse_ident(tags["of"]) if isinstance(tags.get("of"), str) else (None, None)
            src = tags.get("from") if isinstance(tags.get("from"), str) else ""
            if name in HAZARD_LAYERS:
                self.b.removals.append({"turn": self.turn_no, "side": side, "hazard": name, "by": by,
                                        "move": _effect(src)[1] if src else None})

    def on_weather(self, args):
        if not args:
            return
        weather = args[0]
        tags = _tags(args[1:])
        if tags.get("upkeep"):
            return
        if weather == "none":
            return
        setter = None
        if isinstance(tags.get("of"), str):
            setter = self.resolve(tags["of"])
            self.reveal(setter, tags.get("from") if isinstance(tags.get("from"), str) else "")
        elif self.current:
            setter = self.get(self.current[1])
        self.b.weather_history.append({"turn": self.turn_no, "weather": weather,
                                       "side": setter.side if setter else None,
                                       "ident": setter.ident if setter else None})

    def on_boost(self, cmd, args):
        mon = self.resolve(args[0]) if args else None
        if not mon:
            return
        stat = args[1] if len(args) > 1 else None
        amount = int(args[2]) if len(args) > 2 and args[2].lstrip("-").isdigit() else 0
        if cmd in ("-boost", "-unboost") and stat:
            delta = amount if cmd == "-boost" else -amount
            mon.boosts[stat] = max(-6, min(6, mon.boosts.get(stat, 0) + delta))
        elif cmd == "-setboost" and stat:
            mon.boosts[stat] = max(-6, min(6, amount))
        elif cmd == "-clearboost":
            mon.boosts = {}
        elif cmd == "-clearnegativeboost":
            mon.boosts = {k: v for k, v in mon.boosts.items() if v > 0}
        elif cmd == "-clearpositiveboost":
            mon.boosts = {k: v for k, v in mon.boosts.items() if v < 0}
        mon.boosts = {k: v for k, v in mon.boosts.items() if v}

    def on_start(self, args):
        mon = self.resolve(args[0]) if args else None
        if not mon or len(args) < 2:
            return
        effect = _effect(args[1])[1]
        if effect == "perish0":
            mon.perish0 = True
        if effect == "typechange":
            mon.typechange_turn = self.turn_no
        if effect in DELAYED_MOVES:
            # Logged on the user; the hit lands two turns later on whatever the other side has in
            self.delayed[self.opp(mon.side)] = (mon.side, mon.ident, effect)
            return
        tags = _tags(args[2:])
        _, of = parse_ident(tags["of"]) if isinstance(tags.get("of"), str) else (None, None)
        by = of or (self.current[1] if self.current and self.current[0] != mon.side else None)
        if by and by[:2] != mon.side:
            mon.afflictions[effect] = by

    # --- main loop -----------------------------------------------------------------------

    def feed(self, line):
        if not line.startswith("|"):
            return
        parts = line.split("|")
        cmd, args = parts[1], parts[2:]
        b = self.b
        if cmd == "":
            # A blank line closes an action, so later residual damage can't be blamed on its move
            self.current = None
        elif cmd == "gametype" and args and args[0] != "singles":
            raise UnsupportedReplay(f"{args[0].capitalize()} battles are not supported yet; only singles.")
        elif cmd == "player" and len(args) >= 2 and args[0] in SIDES and args[1]:
            b.players[args[0]] = args[1]
        elif cmd == "teamsize" and len(args) >= 2 and args[0] in SIDES and args[1].isdigit():
            b.teamsize[args[0]] = int(args[1])
        elif cmd == "poke" and len(args) >= 2 and args[0] in SIDES:
            b.preview[args[0]].append(species_of(args[1]))
        elif cmd == "turn":
            self.close_turn()
            self.turn_no = int(args[0]) if args and args[0].isdigit() else self.turn_no + 1
            self.phase, self.order, self.current, self.pending_dbond = "action", 0, None, None
            self.turn = Turn(self.turn_no, self.snapshot(), {s: b.hazards(s) for s in SIDES},
                             self._weather(), self._terrain(), self._trick_room())
            b.turns.append(self.turn)
        elif cmd == "upkeep":
            self.phase, self.current = "end", None
        elif cmd in ("switch", "drag"):
            self.on_switch(args, cmd)
        elif cmd == "replace":
            self.on_replace(args)
        elif cmd == "detailschange" and len(args) >= 2:
            mon = self.resolve(args[0])
            if mon:
                mon.species = species_of(args[1])
        elif cmd == "-mega" and len(args) >= 3:
            mon = self.resolve(args[0])
            if mon and args[2] and not mon.item:
                mon.item, mon.item_turn = args[2], self.turn_no
        elif cmd == "-terastallize" and len(args) >= 2:
            mon = self.resolve(args[0])
            if mon:
                mon.tera, mon.tera_turn = args[1], self.turn_no
                self.log(kind="tera", side=mon.side, ident=mon.ident, type=args[1])
        elif cmd == "-transform":
            mon = self.resolve(args[0]) if args else None
            if mon:
                mon.transformed = True
        elif cmd == "move":
            self.on_move(args)
        elif cmd == "cant":
            self.on_cant(args)
        elif cmd == "-damage":
            self.on_damage(args)
        elif cmd in ("-heal", "-sethp"):
            self.on_heal(args, cmd)
        elif cmd == "faint":
            self.on_faint(args)
        elif cmd == "-activate" and len(args) >= 2:
            mon = self.resolve(args[0])
            effect = args[1]
            if _effect(effect)[1] == "Destiny Bond" and mon:
                self.pending_dbond = mon.ident
            elif mon and _effect(effect)[0] in ("item", "ability"):
                self.reveal(mon, effect)
        elif cmd == "-status" and len(args) >= 2:
            mon = self.resolve(args[0])
            if mon:
                mon.status = args[1]
                tags = _tags(args[2:])
                if isinstance(tags.get("from"), str):
                    self.reveal(self.owner(mon, tags), tags["from"])
                mover = self.current
                mon.status_by = mover[1] if mover and mover[0] != mon.side else None
        elif cmd == "-curestatus" and args:
            mon = self.resolve(args[0])
            if mon:
                mon.status, mon.status_by = None, None
        elif cmd == "-cureteam" and args:
            mon = self.resolve(args[0])
            if mon:
                for m in b.mons[mon.side].values():
                    m.status, m.status_by = None, None
        elif cmd in ("-boost", "-unboost", "-setboost", "-clearboost", "-clearnegativeboost",
                     "-clearpositiveboost"):
            self.on_boost(cmd, args)
        elif cmd == "-clearallboost":
            for side in SIDES:
                m = self.get(self.active[side]) if self.active[side] else None
                if m:
                    m.boosts = {}
        elif cmd in ("-sidestart", "-sideend"):
            self.on_sidecondition(cmd, args)
        elif cmd == "-swapsideconditions":
            b.conditions["p1"], b.conditions["p2"] = b.conditions["p2"], b.conditions["p1"]
        elif cmd == "-weather":
            self.on_weather(args)
            if args and args[0] != "none" and not _tags(args[1:]).get("upkeep"):
                self.field["weather"] = args[0]
            elif args and args[0] == "none":
                self.field.pop("weather", None)
        elif cmd in ("-fieldstart", "-fieldend") and args:
            name = _effect(args[0])[1]
            if cmd == "-fieldstart":
                self.field["terrain" if "Terrain" in name else name] = name
            else:
                self.field.pop("terrain" if "Terrain" in name else name, None)
            tags = _tags(args[1:])
            if isinstance(tags.get("from"), str) and isinstance(tags.get("of"), str):
                self.reveal(self.resolve(tags["of"]), tags["from"])
        elif cmd == "-start":
            self.on_start(args)
        elif cmd == "-end" and len(args) >= 2 and _effect(args[1])[1] in DELAYED_MOVES:
            # The delayed hit resolves now: its damage line has no [from], so treat it as that move
            side, _ = parse_ident(args[0])
            if side and side in self.delayed:
                self.current = self.delayed.pop(side)
        elif cmd in ("-item", "-enditem") and len(args) >= 2:
            mon = self.resolve(args[0])
            tags = _tags(args[2:])
            if mon and not mon.transformed:
                # Trick and Switcheroo move items around; only the first item seen is the held item
                swapped = isinstance(tags.get("from"), str) and _effect(tags["from"])[1] in ("Trick", "Switcheroo")
                if not mon.item and not swapped:
                    mon.item, mon.item_turn = args[1], self.turn_no
                if cmd == "-enditem":
                    mon.item_lost = True
            if isinstance(tags.get("from"), str) and _effect(tags["from"])[0] == "ability":
                self.reveal(self.owner(mon, tags) if tags.get("of") else mon, tags["from"])
        elif cmd == "-ability" and len(args) >= 2:
            mon = self.resolve(args[0])
            tags = _tags(args[2:])
            src = tags.get("from") if isinstance(tags.get("from"), str) else ""
            if mon and _effect(src)[1] in ("Trace", "Receiver", "Power of Alchemy"):
                self.reveal(mon, src)
                of = self.resolve(tags["of"]) if isinstance(tags.get("of"), str) else None
                self.reveal(of, f"ability: {args[1]}")
            elif mon and not src.startswith("move:"):
                self.reveal(mon, f"ability: {args[1]}")
        elif cmd == "-immune" and args:
            mon = self.resolve(args[0])
            tags = _tags(args[1:])
            src = tags.get("from") if isinstance(tags.get("from"), str) else ""
            if mon and _effect(src)[0] == "ability":
                self.reveal(mon, src)
            if mon and self.current and self.current[0] != mon.side:
                self.b.immune.append({"turn": self.turn_no, "side": self.current[0], "ident": self.current[1],
                                      "move": self.current[2], "target": mon.ident,
                                      "source": _effect(src)[1] if src else None})
        elif cmd == "win" and args:
            name = to_id(args[0])
            for side in SIDES:
                if to_id(b.players[side]) == name:
                    b.winner = side
        elif cmd == "tie":
            b.winner = "tie"

    def _weather(self):
        return self.field.get("weather")

    def _terrain(self):
        return self.field.get("terrain")

    def _trick_room(self):
        return "Trick Room" in self.field


def parse_battle(log, players=None, format_id="", format_name=""):
    """Battle for a full replay log. Raises UnsupportedReplay for doubles and other non singles games."""
    battle = Battle(format_id=format_id, format_name=format_name)
    if players:
        for side, name in zip(SIDES, players):
            if name:
                battle.players[side] = name
    parser = _Parser(battle)
    for line in (log or "").split("\n"):
        parser.feed(line.rstrip("\r"))
    parser.close_turn()
    if not battle.mons["p1"] and not battle.mons["p2"]:
        raise UnsupportedReplay("This battle ended at team preview, before any Pokémon was sent out.")
    return battle

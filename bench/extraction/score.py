"""
Extraction benchmark: scores the query planner's reading of a question (intent, who is who, and
every stated constraint) against hand labels, slot by slot, separately from answer accuracy.

  python bench/extraction/score.py                      # gold_dev.jsonl with the current planner
  python bench/extraction/score.py --split test         # the held out half: run once per milestone
  python bench/extraction/score.py --src <dir>          # another checkout's src, e.g. an older commit
  python bench/extraction/score.py --show 15            # print the first 15 wrong questions

Each label becomes a set of facts ("opponent.nature=Timid", "screens.defender=Reflect"); precision,
recall and F1 are reported per slot type, plus exact match per question and the invented slot rate
on questions that state no constraints.
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

TEAMS = {
    "A": """Great Tusk @ Booster Energy
Ability: Protosynthesis
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Headlong Rush
- Ice Spinner
- Knock Off
- Rapid Spin

Rillaboom @ Choice Scarf
Ability: Grassy Surge
EVs: 252 Atk / 4 SpD / 252 Spe
Adamant Nature
- Wood Hammer
- Grassy Glide
- U-turn
- Knock Off

Corviknight @ Leftovers
Ability: Pressure
EVs: 252 HP / 168 Def / 88 SpD
Impish Nature
- Brave Bird
- U-turn
- Roost
- Defog""",
    "B": """Gholdengo @ Choice Specs
Ability: Good as Gold
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Trick
- Focus Blast

Dragonite @ Heavy-Duty Boots
Ability: Multiscale
EVs: 252 Atk / 4 Def / 252 Spe
Adamant Nature
- Extreme Speed
- Earthquake
- Fire Punch
- Dragon Dance

Toxapex @ Black Sludge
Ability: Regenerator
EVs: 252 HP / 252 Def / 4 SpD
Bold Nature
- Surf
- Toxic
- Recover
- Haze

Iron Valiant @ Booster Energy
Ability: Quark Drive
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Moonblast
- Close Combat
- Knock Off
- Psyshock""",
}
SCREEN_NAMES = {"isReflect": "Reflect", "isLightScreen": "Light Screen", "isAuroraVeil": "Aurora Veil"}
SIDE_KEYS = ("nature", "evs", "max", "min", "uninvested", "item", "no_speed_item", "ability", "tera", "boosts", "moves")


def side_facts(prefix, side):
    out = set()
    for key in SIDE_KEYS:
        if key not in (side or {}):
            continue
        v = side[key]
        if key in ("evs", "boosts"):
            out |= {(f"{prefix}.{key}", f"{k}={n}") for k, n in v.items()}
        elif key in ("max", "min", "moves"):
            out |= {(f"{prefix}.{key}", str(x).lower()) for x in v}
        elif key in ("uninvested", "no_speed_item"):
            if v:
                out.add((f"{prefix}.{key}", "true"))
        else:
            out.add((f"{prefix}.{key}", str(v).lower() or "none"))
    return out


def facts(slots):
    """A label (or a plan rendered as one) as a set of (slot, value) facts."""
    out = {("intent", slots.get("intent") or "open")}
    for who in ("user_pokemon", "opponent_pokemon"):
        if slots.get(who):
            out.add((who, slots[who].lower()))
    out |= side_facts("user", slots.get("user")) | side_facts("opponent", slots.get("opponent"))
    out |= {(f"conditions.{k}", str(v).lower()) for k, v in (slots.get("conditions") or {}).items()}
    out |= {(f"screens.{side}", s.lower()) for side, names in (slots.get("screens") or {}).items() for s in names}
    if slots.get("raw_stats"):
        out.add(("raw_stats", "true"))
    out |= {("unhandled", u.lower()) for u in slots.get("unhandled") or []}
    return out


def plan_slots(plan):
    """The planner's Plan in the label schema. Older planners lack some fields, so every read has a default."""
    intent = plan.intent
    if intent == "ko" and getattr(plan, "survive", False):
        intent = "survive"
    if intent == "clarify":
        intent = "open"
    screens = {side: sorted(SCREEN_NAMES[f] for f in flags) for side, flags in (getattr(plan, "screens", {}) or {}).items()}
    return {
        "intent": intent,
        "user_pokemon": plan.user["Pokemon"] if plan.user else None,
        "opponent_pokemon": plan.opponent,
        "user": getattr(plan, "user_overrides", {}) or {},
        "opponent": plan.opp_overrides or {},
        "conditions": getattr(plan, "conditions", {}) or {},
        "screens": screens,
        "raw_stats": bool(getattr(plan, "raw_stats", False)),
        # Stated conditions the planner found, whether the answer counts them or reports them as not counted
        "unhandled": (getattr(plan, "unhandled", []) or []) + (getattr(plan, "counted", []) or []),
    }


def group(slot):
    """Slot type for the per type table: 'opponent.nature' and 'user.nature' both count as 'nature'."""
    head = slot.split(".")
    if head[0] in ("user", "opponent"):
        return head[1]
    return head[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--src", default=str(HERE.parent.parent / "src"))
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument("--out", help="write per question predictions to this JSONL")
    args = ap.parse_args()
    sys.path.insert(0, args.src)
    from metamatch.engine.planner import plan_query
    from metamatch.team import readTeam

    teams = {k: readTeam(v, "gen9ou")[0] for k, v in TEAMS.items()}
    items = [json.loads(line) for line in open(HERE / f"gold_{args.split}.jsonl", encoding="utf-8") if line.strip()]
    tp, fp, fn = Counter(), Counter(), Counter()
    exact, wrong, invented, empty_qs = 0, [], 0, 0
    rows = []
    for it in items:
        gold = facts(it["slots"])
        pred_slots = plan_slots(plan_query(it["question"], teams[it["team"]]))
        pred = facts(pred_slots)
        for s, _ in pred & gold:
            tp[group(s)] += 1
        for s, _ in pred - gold:
            fp[group(s)] += 1
        for s, _ in gold - pred:
            fn[group(s)] += 1
        core = {"intent", "user_pokemon", "opponent_pokemon"}
        if not {f for f in gold if f[0] not in core}:
            empty_qs += 1
            invented += bool({f for f in pred if f[0] not in core})
        if pred == gold:
            exact += 1
        else:
            wrong.append((it, sorted(gold - pred), sorted(pred - gold)))
        rows.append({"id": it["id"], "pred": pred_slots, "missed": sorted(gold - pred), "extra": sorted(pred - gold)})

    def prf(g):
        p = tp[g] / (tp[g] + fp[g]) if tp[g] + fp[g] else 1.0
        r = tp[g] / (tp[g] + fn[g]) if tp[g] + fn[g] else 1.0
        return p, r, (2 * p * r / (p + r) if p + r else 0.0)

    groups = sorted(set(tp) | set(fp) | set(fn), key=lambda g: -(tp[g] + fn[g]))
    print(f"{'slot':16s} {'gold':>5s} {'P':>6s} {'R':>6s} {'F1':>6s}")
    for g in groups:
        p, r, f = prf(g)
        print(f"{g:16s} {tp[g] + fn[g]:5d} {p:6.3f} {r:6.3f} {f:6.3f}")
    T, P, N = sum(tp.values()), sum(fp.values()), sum(fn.values())
    mp, mr = T / (T + P) if T + P else 1, T / (T + N) if T + N else 1
    print(f"\nmicro P {mp:.3f}  R {mr:.3f}  F1 {2 * mp * mr / (mp + mr):.3f}")
    print(f"exact match {exact}/{len(items)} ({100 * exact / len(items):.1f}%)")
    print(f"questions stating nothing that got invented slots: {invented}/{empty_qs}")
    for it, missed, extra in wrong[:args.show]:
        print(f"\n[{it['id']}] {it['question']}\n  missed: {missed}\n  extra:  {extra}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(r) + "\n" for r in rows)


if __name__ == "__main__":
    main()

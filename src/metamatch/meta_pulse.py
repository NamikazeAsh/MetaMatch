"""
Meta Pulse: what is moving in a format's ladder this month.

Usage history lives in data/json/usage_history.json as {format id: {"YYYY-MM": [[name, usage %], ...]}},
top 100 per month. scripts/backfill_usage_history.py fills past months and scripts/update_meta.py
appends each new one. Cards are picked by fixed rules from that history plus the current chaos
file, and every headline is a template, so nothing here needs an LLM.
"""
import json
import re
from functools import lru_cache

from metamatch import config
from metamatch.engine.dex import dex_for_format, get_dex, to_id

HISTORY_PATH = config.JSON_DIR / "usage_history.json"
MANIFEST_PATH = config.STATS_DIR / "manifest.json"
KEEP_TOP = 100
SPARK_MONTHS = 6
FEATURE_MONTHS = 12   # the featured story's chart
RISER_FLOOR = 3.0      # usage % a riser must have now (a faller had last month), so tiny tiers can't headline
NEWCOMER_TOP = 30
FASTEST_POOL = 20
SPRITE_ROOT = "https://play.pokemonshowdown.com/sprites/home-centered/"

_ROW = re.compile(r"^\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([\d.]+)%")


def parse_usage_text(text, top_n=KEEP_TOP):
    """[(name, usage %)] in rank order from a Smogon usage .txt table."""
    rows = []
    for line in text.splitlines():
        m = _ROW.match(line)
        if m:
            rows.append((m.group(2), round(float(m.group(3)), 3)))
    return rows[:top_n] if top_n else rows


def load_history(path=HISTORY_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(path, data, **dump_args):
    """Writes through a temp file and swaps it in, retrying briefly: on Windows a reader (the app, a virus
    scan) can hold the file for a moment, and a half written history would lose months."""
    import os
    import time
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, **dump_args)
    for attempt in range(10):
        try:
            os.replace(tmp, path)
            return
        except OSError:
            if attempt == 9:
                raise
            time.sleep(0.3)


def save_history(history, path=HISTORY_PATH):
    ordered = {fid: dict(sorted(months.items())) for fid, months in sorted(history.items())}
    write_json(path, ordered, indent=1)


def record_month(history, format_id, month, rows):
    """Stores one month of [(name, usage %)] for a format (replacing any earlier copy of that month)."""
    history.setdefault(format_id, {})[month] = [[n, u] for n, u in rows[:KEEP_TOP]]
    return history


def record_local_stats(history, month):
    """Adds `month` for every format from the usage .txt files currently in data/stats."""
    for fid, fmt in config.FORMATS.items():
        path = config.STATS_DIR / (fmt["stats"] + ".txt")
        if path.exists():
            rows = parse_usage_text(path.read_text(encoding="utf-8"))
            if rows:
                record_month(history, fid, month, rows)
    return history


def current_month():
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            return json.load(f).get("month")
    except (OSError, json.JSONDecodeError):
        return None


def month_label(month):
    """'2026-10' -> 'October 2026'."""
    names = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]
    try:
        year, mon = month.split("-")
        return f"{names[int(mon) - 1]} {year}"
    except (AttributeError, ValueError, IndexError):
        return month or ""


@lru_cache(maxsize=1)
def _base_species():
    """Forme name -> base species name, from the dexes' otherFormes lists."""
    base = {}
    for game in ("sv", "champions"):
        dex = get_dex(game)
        if not dex:
            continue
        for name, entry in dex.species_data.items():
            for forme in entry.get("otherFormes", []) or []:
                base.setdefault(forme, name)
    return base


def sprite_urls(name):
    """(forme sprite, base species sprite) URLs on Showdown's static sprite server."""
    base = _base_species().get(name)
    if base and name.startswith(base + "-"):
        forme_id = f"{to_id(base)}-{to_id(name[len(base) + 1:])}"
    else:
        forme_id = to_id(name)
    return SPRITE_ROOT + forme_id + ".png", SPRITE_ROOT + to_id(base or name) + ".png"


def _months(history, format_id, month):
    """Months on record for a format up to and including `month`, oldest first."""
    months = sorted(m for m in history.get(format_id, {}) if not month or m <= month)
    return months


def _table(history, format_id, month):
    """{name: (rank, usage %)} for one month."""
    rows = history.get(format_id, {}).get(month, [])
    return {n: (i + 1, u) for i, (n, u) in enumerate(rows)}


def _past_set(name, format_id, month):
    """A past month's standard set from the stored moveset history (no Speed: spreads aren't kept)."""
    from metamatch.meta_trends import sets_history
    entry = (sets_history().get(format_id, {}).get(month) or {}).get(name)
    dex = dex_for_format(format_id)
    species = dex.species(name) if dex else None
    if not entry:
        return {"types": species["types"] if species else []}
    top = lambda key: entry[key][0][0] if entry.get(key) else None
    return {
        "item": top("items"), "ability": top("abilities"),
        "tera": top("tera") if config.format_game(format_id) != "champions" else None,
        "moves": [m for m, _ in entry.get("moves", [])[:4]],
        "teammates": [m for m, _ in entry.get("teammates", [])[:3]],
        "speed": None, "types": species["types"] if species else [],
    }


def _set_summary(name, format_id, month=None):
    """Standard set, teammates and common speed from the current chaos file, or {} without data.
    For an earlier month the set comes from that month's stored moveset history instead."""
    if month and month != current_month():
        return _past_set(name, format_id, month)
    from metamatch.engine.sets import chaos_entry, likely_set
    s = likely_set(name, format_id)
    if not s:
        return {}
    _, entry = chaos_entry(name, format_id)
    mates = sorted((entry or {}).get("Teammates", {}).items(), key=lambda x: x[1], reverse=True)
    dex = dex_for_format(format_id)
    species = dex.species(name) if dex else None
    return {
        "item": s["item"],
        "ability": s["ability"],
        "tera": s["tera"][0] if s.get("tera") and config.format_game(format_id) != "champions" else None,
        "moves": [m for m, _ in s["moves"]],
        "teammates": [m for m, _ in mates[:3]],
        "speed": s["speeds"][0][0] if s.get("speeds") else None,
        "types": species["types"] if species else [],
    }


def _partner(name, format_id, now, month=None):
    """What a partner hover card shows: types, this month's rank and usage, and its most common item."""
    from metamatch.engine.sets import likely_set
    dex = dex_for_format(format_id)
    species = dex.species(name) if dex else None
    s = (_past_set(name, format_id, month) if month and month != current_month() else likely_set(name, format_id)) or {}
    rank, usage = now.get(name, (None, None))
    return {"name": name, "types": species["types"] if species else [], "rank": rank, "usage": usage,
            "item": s.get("item"), "ability": s.get("ability")}


def _headline(card, label):
    """One line of news under the card's name, so it never repeats the name."""
    rank, prev_rank, kind = card["rank"], card["prev_rank"], card["kind"]
    if kind == "top":
        streak = card.get("streak", 1)
        if streak >= 3:
            return f"#1 for a {_ordinal(streak)} straight month"
        if streak == 2:
            return "Holds onto the #1 spot"
        return "Takes the #1 spot" if prev_rank else f"Most used Pokémon in {label}"
    if kind == "riser":
        if prev_rank and prev_rank - rank >= 3:
            return f"Climbs {prev_rank - rank} ranks to #{rank}"
        return f"Gains {card['delta']:.1f} points of usage"
    if kind == "faller":
        if prev_rank and rank and rank - prev_rank >= 3:
            return f"Slides {rank - prev_rank} ranks to #{rank}"
        return f"Drops {abs(card['delta']):.1f} points of usage"
    if kind == "newcomer":
        return f"Breaks into the top {NEWCOMER_TOP}" + (f", up from #{prev_rank}" if prev_rank else "")
    if kind == "fastest":
        return f"Fastest common threat at {card['speed']} Speed"
    return f"Top {label} staple"


def _ordinal(n):
    return {3: "third", 4: "fourth", 5: "fifth", 6: "sixth"}.get(n, f"{n}th")


BADGES = {
    "top": ("👑", "#1"),
    "riser": ("🔥", "Rising"),
    "faller": ("📉", "Falling"),
    "newcomer": ("🆕", "Newcomer"),
    "fastest": ("⚡", "Fastest"),
    "staple": ("📌", "Staple"),
}


def pulse(format_id, n=8, history=None, month=None, with_sets=True):
    """
    Cards for the Meta Pulse feed, most newsworthy first. Each card is a dict with name, kind,
    badge, rank, usage, prev_rank, prev_usage, delta (usage points vs last month, None without
    history), series [(month, usage %)] for the sparkline, headline, and the standard set fields.
    """
    history = load_history() if history is None else history
    month = month or current_month()
    months = _months(history, format_id, month)
    if not months:
        return []
    now_month = months[-1]
    now = _table(history, format_id, now_month)
    prev = _table(history, format_id, months[-2]) if len(months) >= 2 else {}
    ranked = sorted(now, key=lambda x: now[x][0])
    picks = []

    def add(name, kind):
        if name in now and name not in [p[0] for p in picks]:
            picks.append((name, kind))

    if ranked:
        add(ranked[0], "top")
    if prev:
        deltas = {nm: now[nm][1] - prev[nm][1] for nm in now if nm in prev}
        # A Pokemon that just entered the top 30 is a newcomer, not a riser, so riser slots go to established names
        prev_top = {nm for nm, (r, _) in prev.items() if r <= NEWCOMER_TOP}
        newcomers = [nm for nm in ranked[:NEWCOMER_TOP] if nm not in prev_top]
        risers = sorted((nm for nm in deltas if deltas[nm] > 0 and now[nm][1] >= RISER_FLOOR and nm not in newcomers),
                        key=lambda nm: deltas[nm], reverse=True)
        for nm in risers[:2]:
            add(nm, "riser")
        fallers = sorted((nm for nm in deltas if deltas[nm] < 0 and prev[nm][1] >= RISER_FLOOR),
                         key=lambda nm: deltas[nm])
        for nm in fallers[:1]:
            add(nm, "faller")
        for nm in newcomers[:2]:
            add(nm, "newcomer")

    sets = {}
    if with_sets:
        pool = ranked[:FASTEST_POOL]
        for nm in pool:
            sets[nm] = _set_summary(nm, format_id, now_month)
        shown = {p[0] for p in picks}
        speeds = sorted(((sets[nm].get("speed") or 0, nm) for nm in pool if nm not in shown), reverse=True)
        if speeds and speeds[0][0]:
            add(speeds[0][1], "fastest")

    for nm in ranked:
        if len(picks) >= n:
            break
        add(nm, "staple")

    label = config.format_info(format_id)["label"]
    cards = []
    for name, kind in picks[:n]:
        rank, usage = now[name]
        prev_rank, prev_usage = prev.get(name, (None, None))
        long_series = [(m, (_table(history, format_id, m).get(name) or (None, None))[1]) for m in months[-FEATURE_MONTHS:]]
        series = long_series[-SPARK_MONTHS:]
        rank_series = [(m, (_table(history, format_id, m).get(name) or (None,))[0]) for m in months[-SPARK_MONTHS:]]
        best = None
        for m in months:
            row = _table(history, format_id, m).get(name)
            if row and (best is None or row[0] < best[0]):
                best = (row[0], m)
        streak = 0
        for m in reversed(months):
            t = _table(history, format_id, m)
            if t.get(name, (None,))[0] == 1:
                streak += 1
            else:
                break
        card = {
            "name": name, "kind": kind, "badge": BADGES[kind], "rank": rank, "usage": usage,
            "prev_rank": prev_rank, "prev_usage": prev_usage,
            "delta": round(usage - prev_usage, 2) if prev_usage is not None else None,
            "series": series, "long_series": long_series, "rank_series": rank_series, "streak": streak, "peak": best,
        }
        if with_sets:
            card.update(sets.get(name) or _set_summary(name, format_id, now_month))
            card["partners"] = [_partner(m, format_id, now, now_month) for m in card.get("teammates") or []]
        card["headline"] = _headline(card, label)
        cards.append(card)
    return cards


def leaderboard(format_id, n=10, history=None, month=None):
    """Top `n` by usage this month: [{name, rank, usage, prev_rank, types}] (prev_rank None if new or unknown)."""
    history = load_history() if history is None else history
    months = _months(history, format_id, month or current_month())
    if not months:
        return []
    now = _table(history, format_id, months[-1])
    prev = _table(history, format_id, months[-2]) if len(months) >= 2 else None
    dex = dex_for_format(format_id)
    rows = []
    for name in sorted(now, key=lambda x: now[x][0])[:n]:
        species = dex.species(name) if dex else None
        rows.append({
            "name": name, "rank": now[name][0], "usage": now[name][1],
            "prev_rank": prev.get(name, (None,))[0] if prev is not None else None,
            "has_prev": prev is not None,
            "types": species["types"] if species else [],
        })
    return rows


def featured_index(cards):
    """Which card leads the section: the biggest riser inside the top 10, else the #1."""
    risers = [i for i, c in enumerate(cards) if c["kind"] == "riser" and c["rank"] <= 10]
    if risers:
        return max(risers, key=lambda i: cards[i]["delta"] or 0)
    return next((i for i, c in enumerate(cards) if c["kind"] == "top"), 0)

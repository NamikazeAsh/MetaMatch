"""
MetaFlash trends beyond usage: which Pokemon lead games, how sets change month to month, what the top of the
ladder runs more than the rest, and which pairs players are building together more often.

Everything comes from Smogon's monthly files (leads, moveset and the 1500+ usage table) and is stored in small
JSON histories by scripts/backfill_usage_history.py and scripts/update_meta.py, so the start screen never
downloads anything. Every line shown is a template over these numbers; nothing here needs an LLM.
"""
import json
import re

from metamatch import config
from metamatch.meta_pulse import _months, _table, load_history, parse_usage_text, write_json

LEADS_PATH = config.JSON_DIR / "leads_history.json"
SETS_PATH = config.JSON_DIR / "sets_history.json"
WIDE_PATH = config.JSON_DIR / "wide_usage_history.json"
LEADS_TOP = 30
SETS_TOP = 40
WIDE_RATING = "1500"
# Moveset sections kept, and how many options of each
SECTIONS = {"Abilities": ("abilities", 3), "Items": ("items", 6), "Moves": ("moves", 10),
            "Tera Types": ("tera", 6), "Teammates": ("teammates", 12)}
OTHER_SECTIONS = {"Spreads", "Checks and Counters"}
_ENTRY = re.compile(r"^(.+?)\s+([\d.]+)%$")

SET_TREND_POOL = 25      # top Pokemon whose sets are compared
SET_TREND_FLOOR = 5.0    # points an option must move to count as news
NEW_OPTION_FLOOR = 10.0  # share a newly listed option needs (or a dropped one had), so small noise stays out
FAVORITE_FLOOR = 2.0     # usage % a top players' pick needs at the format's rating
CORE_POOL = 30
CATEGORY_WORDS = {"items": "item", "tera": "Tera type", "moves": "move", "abilities": "ability"}


# --- Storage -------------------------------------------------------------------------------------

def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save(path, data, compact=False):
    ordered = {fid: dict(sorted(months.items())) for fid, months in sorted(data.items())}
    write_json(path, ordered, indent=None if compact else 1, separators=(",", ":") if compact else None)


_SETS_CACHE = {}


def sets_history():
    """The stored moveset history, read once per file version (it's the largest of the histories)."""
    import os
    try:
        key = os.path.getmtime(SETS_PATH)
    except OSError:
        return {}
    if _SETS_CACHE.get("key") != key:
        _SETS_CACHE.update(key=key, data=load(SETS_PATH))
    return _SETS_CACHE["data"]


def wide_stem(stats_stem):
    """'gen9ou-1825' -> 'gen9ou-1500': the same format's usage across most of the ladder."""
    return stats_stem.rsplit("-", 1)[0] + "-" + WIDE_RATING


def parse_moveset_text(text, top_n=SETS_TOP):
    """{name: {"raw", "abilities", "items", "moves", "tera", "teammates"}} for the first `top_n` Pokemon of a
    Smogon moveset .txt (they come in usage order). Each list holds [option, share %] without 'Other'."""
    out, name, section, after_rule = {}, None, None, False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("+"):
            after_rule = True
            continue
        if not s.startswith("|"):
            continue
        cell = s.strip("|").strip()
        if after_rule:
            after_rule = False
            if cell in SECTIONS or cell in OTHER_SECTIONS:
                section = cell
                continue
            if cell.startswith("Raw count"):
                section = None
                if name:
                    out[name]["raw"] = int(re.sub(r"\D", "", cell) or 0)
                continue
            if len(out) >= top_n:
                break
            name, section = cell, None
            out[name] = {key: [] for key, _ in SECTIONS.values()}
            continue
        if name and section in SECTIONS:
            m = _ENTRY.match(cell)
            key, keep = SECTIONS[section]
            if m and m.group(1) != "Other" and len(out[name][key]) < keep:
                out[name][key].append([m.group(1), round(float(m.group(2)), 2)])
    return out


def fetch_month(month, kinds=("leads", "sets", "wide"), formats=None, session=None, histories=None):
    """Downloads one month of leads, moveset and 1500+ usage for every format and records them.
    Returns {kind: number of formats recorded}. Months a format didn't exist yet are skipped."""
    import requests
    session = session or requests.Session()
    histories = histories or {k: load(p) for k, p in (("leads", LEADS_PATH), ("sets", SETS_PATH), ("wide", WIDE_PATH))}
    root = f"https://www.smogon.com/stats/{month}/"
    done = {k: 0 for k in kinds}
    for fid, fmt in (formats or config.FORMATS).items():
        stem = fmt["stats"]
        urls = {"leads": f"{root}leads/{stem}.txt", "sets": f"{root}moveset/{stem}.txt", "wide": f"{root}{wide_stem(stem)}.txt"}
        for kind in kinds:
            if month in histories[kind].get(fid, {}):
                continue
            try:
                r = session.get(urls[kind], timeout=90)
            except requests.RequestException:
                continue
            if r.status_code != 200:
                continue
            text = r.content.decode("utf-8", errors="replace")
            data = (parse_usage_text(text, LEADS_TOP) if kind == "leads" else
                    parse_moveset_text(text) if kind == "sets" else parse_usage_text(text))
            if data:
                histories[kind].setdefault(fid, {})[month] = [[n, u] for n, u in data] if kind != "sets" else data
                done[kind] += 1
    return done, histories


def save_all(histories):
    save(LEADS_PATH, histories["leads"])
    save(WIDE_PATH, histories["wide"])
    save(SETS_PATH, histories["sets"], compact=True)


# --- Analysis ------------------------------------------------------------------------------------

def _now_prev(history, format_id, month):
    """(this month, last month or None) among the months a history has for a format, up to `month`."""
    months = _months(history, format_id, month)
    if not months or (month and months[-1] != month):
        return None, None
    return months[-1], (months[-2] if len(months) >= 2 else None)


def leads(format_id, month, n=8, history=None):
    """Most common leads: [{name, rank, share, prev_rank, delta}], or [] without lead data for the month."""
    history = load(LEADS_PATH) if history is None else history
    now_m, prev_m = _now_prev(history, format_id, month)
    if not now_m:
        return []
    now, prev = _table(history, format_id, now_m), (_table(history, format_id, prev_m) if prev_m else {})
    rows = []
    for name in sorted(now, key=lambda x: now[x][0])[:n]:
        rank, share = now[name]
        prev_rank, prev_share = prev.get(name, (None, None))
        rows.append({"name": name, "rank": rank, "share": share, "prev_rank": prev_rank, "has_prev": bool(prev),
                     "delta": round(share - prev_share, 2) if prev_share is not None else None})
    return rows


def _share(entry, key, option):
    return next((p for o, p in (entry or {}).get(key, []) if o == option), None)


def _floor(entry, key):
    """The smallest share a category lists: an option missing from the list is below it."""
    shares = [p for _, p in (entry or {}).get(key, [])]
    return min(shares) if shares else 0.0


def set_trends(format_id, month, n=6, history=None, usage=None):
    """Biggest set changes among the format's most used Pokemon, one per Pokemon:
    [{name, category, option, share, prev, delta, new, series}] sorted by size of the change."""
    history = sets_history() if history is None else history
    usage = load_history() if usage is None else usage
    now_m, prev_m = _now_prev(history, format_id, month)
    if not now_m or not prev_m:
        return []
    now, prev = history[format_id][now_m], history[format_id][prev_m]
    ranked = [nm for nm, _ in sorted(_table(usage, format_id, now_m).items(), key=lambda x: x[1][0])][:SET_TREND_POOL]
    months = _months(history, format_id, now_m)[-6:]
    found = []
    for name in ranked:
        if name not in now or name not in prev:
            continue
        best = None
        for key in ("items", "tera", "moves", "abilities"):
            for option, share in now[name].get(key, []):
                before = _share(prev[name], key, option)
                new = before is None
                before = _floor(prev[name], key) if new else before
                delta = share - before
                # A newly listed option only counts when it provably rose: its old share was below the list
                if new and (share < NEW_OPTION_FLOOR or delta < SET_TREND_FLOOR):
                    continue
                if abs(delta) >= SET_TREND_FLOOR and (best is None or abs(delta) > abs(best["delta"])):
                    best = {"name": name, "category": key, "option": option, "share": share, "prev": before,
                            "delta": round(delta, 1), "new": new}
            # Options that dropped out of the list entirely are falls too
            for option, before in prev[name].get(key, []):
                if _share(now[name], key, option) is None and before >= NEW_OPTION_FLOOR:
                    share = _floor(now[name], key)
                    delta = share - before   # an upper bound: it is now below the shortest listed share
                    if delta <= -SET_TREND_FLOOR and (best is None or abs(delta) > abs(best["delta"])):
                        best = {"name": name, "category": key, "option": option, "share": share, "prev": before,
                                "delta": round(delta, 1), "new": False, "gone": True}
        if best:
            best["series"] = [(m, _share(history[format_id][m].get(name), best["category"], best["option"])) for m in months]
            found.append(best)
    found.sort(key=lambda x: abs(x["delta"]), reverse=True)
    return found[:n]


def set_trend_text(t):
    """'Choice Scarf on 45% of Gholdengo, up from 38%'."""
    what = t["option"] if t["category"] != "tera" else f"Tera {t['option']}"
    if t.get("gone"):
        return f"{what} dropped from {t['prev']:.0f}% of sets to under {max(t['share'], 1):.0f}%"
    if t["new"]:
        return f"{what} jumped to {t['share']:.0f}% of sets from under {max(t['prev'], 1):.0f}%"
    return f"{what} on {t['share']:.0f}% of sets, {'up' if t['delta'] > 0 else 'down'} from {t['prev']:.0f}%"


def ladder_favorites(format_id, month, n=6, wide=None, usage=None):
    """Pokemon the top of the ladder uses more than the ladder at 1500+:
    [{name, top, wide, gap}], biggest gap first. [] without the 1500+ table for the month."""
    wide = load(WIDE_PATH) if wide is None else wide
    usage = load_history() if usage is None else usage
    if month not in wide.get(format_id, {}) or month not in usage.get(format_id, {}):
        return []
    top, broad = _table(usage, format_id, month), _table(wide, format_id, month)
    rows = [{"name": nm, "top": u, "wide": broad.get(nm, (None, 0.0))[1], "rank": r}
            for nm, (r, u) in top.items() if u >= FAVORITE_FLOOR]
    for r in rows:
        r["gap"] = round(r["top"] - r["wide"], 2)
    rows = [r for r in rows if r["gap"] > 0]
    rows.sort(key=lambda r: r["gap"], reverse=True)
    return rows[:n]


def _pair_share(usage_now, sets_month, a, b):
    """Estimated share of all teams with both: usage(A) x share of A's teams with B, from either side.
    (share, exact) where exact is False when the pair was below both teammate lists (an upper bound)."""
    estimates = []
    for x, y in ((a, b), (b, a)):
        ux = usage_now.get(x, (None, None))[1]
        entry = sets_month.get(x)
        if ux is None or not entry:
            continue
        s = _share(entry, "teammates", y)
        if s is not None:
            estimates.append((ux * s / 100, True))
        else:
            estimates.append((ux * _floor(entry, "teammates") / 100, False))
    exact = [e for e, ok in estimates if ok]
    if exact:
        return round(max(exact), 2), True
    return (round(min(e for e, _ in estimates), 2), False) if estimates else (None, False)


def rising_cores(format_id, month, n=4, history=None, usage=None):
    """Pairs among the top 30 that more teams are using together than last month:
    [{pair, share, prev, delta, new, series}], biggest gain first."""
    history = sets_history() if history is None else history
    usage = load_history() if usage is None else usage
    now_m, prev_m = _now_prev(history, format_id, month)
    if not now_m or not prev_m:
        return []
    u_now, u_prev = _table(usage, format_id, now_m), _table(usage, format_id, prev_m)
    pool = [nm for nm, _ in sorted(u_now.items(), key=lambda x: x[1][0])][:CORE_POOL]
    s_now, s_prev = history[format_id][now_m], history[format_id][prev_m]
    months = _months(history, format_id, now_m)[-6:]
    out = []
    for i, a in enumerate(pool):
        for b in pool[i + 1:]:
            share, exact = _pair_share(u_now, s_now, a, b)
            if not exact or share is None:
                continue
            before, before_exact = _pair_share(u_prev, s_prev, a, b)
            if before is None:
                continue
            delta = share - before
            if delta > 0.3:
                out.append({"pair": [a, b], "share": share, "prev": before, "delta": round(delta, 2),
                            "new": not before_exact})
    out.sort(key=lambda x: x["delta"], reverse=True)
    picked, seen = [], {}
    for c in out:
        # At most two cores per Pokemon, so one popular name can't fill the section
        if any(seen.get(p, 0) >= 2 for p in c["pair"]):
            continue
        for p in c["pair"]:
            seen[p] = seen.get(p, 0) + 1
        c["series"] = [(m, _pair_share(_table(usage, format_id, m), history[format_id][m], *c["pair"])[0])
                       for m in months if m in usage.get(format_id, {})]
        picked.append(c)
        if len(picked) == n:
            break
    return picked


def history_span(format_id, history=None):
    """(first month, last month, count) of usage on record for a format."""
    history = load_history() if history is None else history
    months = sorted(history.get(format_id, {}))
    return (months[0], months[-1], len(months)) if months else (None, None, 0)


def peak(format_id, name, history=None, month=None):
    """(best rank, month it was first reached) for a Pokemon across the usage history up to `month`."""
    history = load_history() if history is None else history
    best = None
    for m in _months(history, format_id, month):
        row = _table(history, format_id, m).get(name)
        if row and (best is None or row[0] < best[0]):
            best = (row[0], m)
    return best


def team_report(team, format_id, month, rows=None, usage=None, n=12):
    """A saved team against this month's most used Pokemon (the Threat Board's top `n`):
    {answered, total, new: threats that just entered the top n, rising: climbing threats it answers thinly}.
    Each threat is {name, rank, prev_rank, answers}. Only meaningful for the month the calc sets come from."""
    usage = load_history() if usage is None else usage
    if rows is None:
        from metamatch.engine import threat_board as tb
        rows = [{"name": r.name, "answers": r.answers, "losses": r.losses} for r in tb.threat_board(team, n=n, format_id=format_id)]
    months = _months(usage, format_id, month)
    now = _table(usage, format_id, month)
    prev = _table(usage, format_id, months[-2]) if len(months) >= 2 else {}
    out = {"answered": sum(1 for r in rows if r["answers"]), "total": len(rows), "new": [], "rising": [], "thin": []}
    for r in rows:
        rank, prev_rank = now.get(r["name"], (None,))[0], prev.get(r["name"], (None,))[0]
        item = {"name": r["name"], "rank": rank, "prev_rank": prev_rank, "answers": list(r["answers"])}
        if prev and (prev_rank is None or prev_rank > n):
            out["new"].append(item)
        elif rank and prev_rank and prev_rank > rank and len(r["answers"]) <= 1:
            out["rising"].append(item)
        if len(r["answers"]) <= 1:
            out["thin"].append(item)
    return out

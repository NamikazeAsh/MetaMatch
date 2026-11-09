"""
Team banner at the top of the team page: the archetype and the jobs the team covers, one raised card per Pokemon
(sprite with its held item, typing and Tera as icons, ability, moves; spread, matchups and Speed on hover), and
four team stats. Every number comes from the Threat Board, the type chart and real Speed against ladder spreads.
"""
import dataclasses
import json
from html import escape

import streamlit as st

from metamatch import config
from metamatch.sprites import get_item_icon, get_sprite, get_tera_icon, get_type_icon

TYPES = ["Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison", "Ground",
         "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy"]
JOB_ORDER = ["Setup Sweeper", "Hazard Setter", "Hazard Remover", "Pivot", "Wall", "Tank", "Priority User", "Revenge Killer",
             "Spin Blocker", "Special Sweeper", "Physical Sweeper", "Fast Sweeper", "Bulky Attacker", "Speed Control"]
ROLE_CHIPS = [("Hazard Setter", "Hazard setter"), ("Hazard Remover", "Hazard removal"), ("Pivot", "Pivots"),
              ("Priority User", "Priority")]
CORE = {"Hazard Setter", "Hazard Remover", "Pivot"}
FAST = 0.9   # outspeeds at least this share of the top 25's ladder sets

STYLE = """
<style>
.bn { position:relative; border-radius:18px; margin:4px 0 6px; border:1px solid rgba(0,212,255,0.22);
  background:radial-gradient(circle at 85% 15%, rgba(119,102,238,0.16), transparent 45%),
             linear-gradient(135deg, rgba(0,212,255,0.08), rgba(255,255,255,0.015) 55%); }
.bn-top { padding:22px 26px 12px; }
.bn-k { font-size:0.7rem; font-weight:800; letter-spacing:2.4px; text-transform:uppercase; color:#00d4ff; }
.bn-t { font-weight:900; font-size:2.6rem; line-height:1.05; letter-spacing:-0.5px; margin-top:4px;
  background:linear-gradient(90deg, #ffffff 0%, #9cf1ff 55%, #00ffcc 100%); -webkit-background-clip:text; background-clip:text; color:transparent;
  filter:drop-shadow(0 0 18px rgba(0,212,255,0.25)); }
.bn-chips { display:flex; flex-wrap:wrap; gap:6px; margin-top:12px; }
.bn-chip { font-size:0.74rem; font-weight:700; padding:3px 10px; border-radius:999px; border:1px solid; }
.bn-chip.ok { color:#5fd38d; background:rgba(95,211,141,0.12); border-color:rgba(95,211,141,0.28); }
.bn-chip.no { color:#ffd866; background:rgba(255,216,102,0.10); border-color:rgba(255,216,102,0.28); }
.bn-team { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:14px; padding:4px 22px 16px; }
.bn-tile { position:relative; display:grid; grid-template-columns:88px minmax(0, 1fr); gap:14px; align-items:stretch; border-radius:18px;
  padding:14px 14px 12px; min-width:0; outline:none;
  background:radial-gradient(circle at 12% 30%, var(--tc33), transparent 46%), linear-gradient(145deg, #1c2232, #141924);
  border:1px solid rgba(255,255,255,0.06);
  box-shadow:10px 10px 24px rgba(0,0,0,0.45), -6px -6px 16px rgba(255,255,255,0.025), inset 1px 1px 0 rgba(255,255,255,0.05);
  transition:transform .15s ease, box-shadow .15s ease; }
.bn-tile:hover, .bn-tile:focus-visible { transform:translateY(-4px); z-index:20;
  box-shadow:12px 14px 28px rgba(0,0,0,0.5), inset 1px 1px 0 rgba(255,255,255,0.06), 0 0 0 1px var(--tc88); }
.bn-ped { position:relative; width:88px; height:88px; border-radius:50%; display:grid; place-items:center; margin-top:2px;
  background:radial-gradient(circle at 50% 60%, var(--tc33), rgba(0,0,0,0.25) 70%);
  box-shadow:inset 0 -8px 16px rgba(0,0,0,0.35), inset 0 2px 0 rgba(255,255,255,0.05), 0 0 0 1px rgba(255,255,255,0.05); }
.bn-ped > img { width:80px; height:80px; object-fit:contain; transition:transform .15s ease;
  filter:drop-shadow(0 6px 8px rgba(0,0,0,0.55)) drop-shadow(0 0 10px var(--tc88)); }
.bn-tile:hover .bn-ped > img { transform:scale(1.06) translateY(-2px); }
.bn-body { display:flex; flex-direction:column; min-width:0; }
.bn-nm { font-weight:800; color:#fff; font-size:1.02rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.bn-icons { display:flex; align-items:center; gap:6px; margin-top:6px; }
.bn-sep { width:1px; height:20px; background:rgba(255,255,255,0.12); margin:0 3px; }
.bn-ico { position:relative; display:inline-grid; place-items:center; outline:none; cursor:help; flex-shrink:0; }
.bn-tip { position:absolute; bottom:calc(100% + 7px); left:50%; transform:translateX(-50%) translateY(3px); white-space:nowrap;
  font-size:0.68rem; font-weight:700; color:#fff; background:#0b0f17; border:1px solid rgba(255,255,255,0.14); padding:3px 8px;
  border-radius:7px; opacity:0; visibility:hidden; transition:opacity .12s ease, transform .12s ease, visibility .12s; pointer-events:none;
  z-index:45; box-shadow:0 6px 16px rgba(0,0,0,0.5); }
.bn-ico:hover .bn-tip, .bn-ico:focus .bn-tip { opacity:1; visibility:visible; transform:translateX(-50%) translateY(0); }
.bn-type { width:28px; height:28px; border-radius:50%; transition:transform .12s ease;
  background:radial-gradient(circle at 35% 30%, color-mix(in srgb, var(--c) 75%, #fff), var(--c) 60%);
  box-shadow:0 0 12px -3px var(--c), inset 0 -3px 5px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.3); }
.bn-type:hover { transform:scale(1.12); }
.bn-type i { display:block; width:15px; height:15px; background-size:contain; background-repeat:no-repeat; background-position:center;
  filter:drop-shadow(0 1px 1px rgba(0,0,0,0.35)); }
.bn-type.sm { width:22px; height:22px; } .bn-type.sm i { width:12px; height:12px; }
.bn-tera img { width:32px; height:32px; filter:drop-shadow(0 0 7px var(--c)); transition:transform .12s ease; }
.bn-tera:hover img { transform:scale(1.12) rotate(-6deg); }
.bn-item { position:absolute; right:-6px; bottom:-4px; width:36px; height:36px; border-radius:50%;
  background:radial-gradient(circle at 40% 32%, #58627a, #2e3648 70%); border:1px solid rgba(255,255,255,0.28);
  box-shadow:0 4px 12px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.08); }
.bn-item img { width:26px; height:26px; image-rendering:pixelated; }
.bn-ability { display:inline-flex; align-items:center; gap:6px; align-self:flex-start; font-size:0.74rem; font-weight:600; color:#d6dbe6;
  padding:3px 10px 3px 8px; border-radius:999px; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); margin-top:8px;
  max-width:100%; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.bn-ability::before { content:""; width:6px; height:6px; border-radius:50%; background:#7fe6ff; flex-shrink:0; }
.bn-abw { align-self:flex-start; max-width:100%; margin-top:8px; }
.bn-abw .bn-ability { margin-top:0; }
.bn-abw:hover .bn-ability, .bn-abw:focus .bn-ability { border-color:rgba(127,230,255,0.45); color:#fff; }
.bn-tip.wide { left:0; transform:translateY(3px); width:230px; white-space:normal; font-weight:500; line-height:1.4;
  padding:7px 10px; color:#d6dbe6; }
.bn-tip.wide b { display:block; color:#fff; font-weight:800; margin-bottom:2px; }
.bn-abw:hover .bn-tip.wide, .bn-abw:focus .bn-tip.wide { transform:translateY(0); }
.bn-moves { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:4px; margin-top:auto; padding-top:10px; }
.bn-mv { font-size:0.72rem; color:#e6eaf2; padding:4px 8px; border-radius:8px; background:rgba(255,255,255,0.045);
  border:1px solid rgba(255,255,255,0.06); border-left:3px solid var(--mc); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.bn-hover { position:absolute; left:14px; right:14px; top:calc(100% + 8px); z-index:30; padding:12px 14px; border-radius:14px;
  background:linear-gradient(160deg, color-mix(in srgb, var(--tcx) 16%, #141a26), #141a26 60%);
  border:1px solid color-mix(in srgb, var(--tcx) 50%, transparent); box-shadow:0 14px 32px rgba(0,0,0,0.6);
  opacity:0; visibility:hidden; transform:translateY(4px); transition:opacity .14s ease, transform .14s ease, visibility .14s; pointer-events:none; }
.bn-hover::before { content:""; position:absolute; left:40px; bottom:100%; border:7px solid transparent;
  border-bottom-color:color-mix(in srgb, var(--tcx) 50%, transparent); }
.bn-tile:hover .bn-hover, .bn-tile:focus-visible .bn-hover { opacity:1; visibility:visible; transform:translateY(0); }
.bn-tile:has(.bn-ico:hover) .bn-hover { opacity:0; visibility:hidden; }
.bn-hk { font-size:0.62rem; font-weight:800; letter-spacing:0.1em; text-transform:uppercase; color:#8a93a6; }
.bn-hl { font-size:0.82rem; color:#d6dbe6; margin:2px 0 8px; }
.bn-hl b { color:#fff; }
.bn-names { display:flex; flex-wrap:wrap; gap:4px; margin:4px 0 8px; }
.bn-names span { font-size:0.7rem; padding:2px 8px; border-radius:999px; background:rgba(95,211,141,0.12); color:#8ff0b5; border:1px solid rgba(95,211,141,0.25); }
.bn-names.bad span { background:rgba(255,123,123,0.10); color:#ffb0b0; border-color:rgba(255,123,123,0.25); }
.bn-stats { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:14px; padding:4px 22px 22px; }
.bn-stat { padding:16px 18px; display:flex; gap:14px; align-items:center; min-width:0; border-radius:16px;
  background:linear-gradient(145deg, #1b2130, #141924); border:1px solid rgba(255,255,255,0.06);
  box-shadow:10px 10px 24px rgba(0,0,0,0.45), -6px -6px 16px rgba(255,255,255,0.025), inset 1px 1px 0 rgba(255,255,255,0.05);
  transition:transform .15s ease, box-shadow .15s ease; }
.bn-stat:hover { transform:translateY(-3px); box-shadow:12px 14px 28px rgba(0,0,0,0.5), inset 1px 1px 0 rgba(255,255,255,0.06), 0 0 0 1px rgba(0,212,255,0.18); }
.bn-ring { --p:0; width:56px; height:56px; border-radius:50%; flex-shrink:0; display:grid; place-items:center;
  background:conic-gradient(#5fd38d calc(var(--p) * 1%), rgba(255,255,255,0.08) 0); }
.bn-ring span { width:44px; height:44px; border-radius:50%; background:#141a26; display:grid; place-items:center; font-weight:900; font-size:0.82rem; color:#fff; }
.bn-big { font-weight:900; font-size:1.7rem; color:#fff; line-height:1; flex-shrink:0; font-variant-numeric:tabular-nums; }
.bn-big small { font-size:0.9rem; color:#8a93a6; font-weight:700; }
.bn-lbl { font-size:0.7rem; font-weight:800; letter-spacing:0.1em; text-transform:uppercase; color:#8a93a6; }
.bn-txt { font-size:0.84rem; color:#d6dbe6; margin-top:2px; }
.bn-wk { display:inline-flex; align-items:center; gap:5px; font-size:0.74rem; font-weight:700; color:#e6eaf2; margin:4px 8px 0 0; }
.bn-fast { display:flex; flex-shrink:0; }
.bn-fast img { width:34px; height:34px; object-fit:contain; margin-right:-6px; }
@media (max-width: 1100px) { .bn-team { grid-template-columns:repeat(2, minmax(0, 1fr)); } .bn-stats { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
@media (max-width: 640px) { .bn-team, .bn-stats { grid-template-columns:minmax(0, 1fr); padding:4px 14px 14px; } .bn-t { font-size:2rem; } }
@media (prefers-reduced-motion: reduce) { .bn-tile, .bn-stat, .bn-ped > img { transition:none; } .bn-tile:hover, .bn-stat:hover { transform:none; } }
</style>
"""


def archetype(team):
    """The team's archetype from member roles (kept from the old dashboard metric)."""
    roles = [r for p in team.values() for r in p.get("Roles", [])]
    mon_roles = [set(p.get("Roles", [])) for p in team.values() if isinstance(p, dict)]
    if roles.count("Trick Room Setter") >= 1:
        return "Trick Room"
    if roles.count("Weather Setter") >= 1 and roles.count("Weather Setter") + roles.count("Weather Abuser") >= 2:
        return "Weather Offense"
    if roles.count("Pivot") >= 3:
        return "Volt Turn"
    if sum(1 for r in mon_roles if r & {"Wall", "Tank"}) >= 4:
        return "Stall"
    if sum(1 for r in mon_roles if any("Sweeper" in x or "Breaker" in x for x in r)) >= 4:
        return "Hyper Offense"
    if sum(1 for r in mon_roles if r & {"Bulky Attacker", "Tank"}) >= 3:
        return "Bulky Offense"
    return "Balanced"


@st.cache_data(show_spinner=False, max_entries=16)
def _facts(team_json, format_id, stats_month):
    """(Threat Board rows, per member facts) for the banner, cached per team, format and stats month."""
    from metamatch.engine.guide import member_facts
    from metamatch.tabs.tab_threats import _board
    rows = _board(team_json, format_id, stats_month)
    team = json.loads(team_json)
    return rows, [dataclasses.asdict(m) for m in member_facts(team, format_id, rows)]


def _type_icon(t, type_map, small=False):
    color = type_map.get(t, {}).get("color", "#777")
    glyph = get_type_icon(t)
    inner = f'<i style="background-image:url({glyph})"></i>' if glyph else ""
    return (f'<span class="bn-ico bn-type{" sm" if small else ""}" tabindex="0" style="--c:{color}">{inner}'
            f'<span class="bn-tip">{escape(t)}</span></span>')


def _spread(p, game):
    raw = (p.get("SP") if game == "champions" else p.get("EVs")) or {}
    return ", ".join(f"{v} {k}" for k, v in raw.items() if v)


def _tile(p, facts, type_map, game):
    name = p["Pokemon"]
    color = type_map.get((p.get("Type") or ["Normal"])[0], {}).get("color", "#00d4ff")
    item_icon = get_item_icon(p.get("Item"))
    item = (f'<span class="bn-ico bn-item" tabindex="0"><img src="{escape(item_icon)}" alt="">'
            f'<span class="bn-tip">{escape(p.get("Item") or "")}</span></span>') if item_icon else ""
    tera_type = p.get("Tera Type") if game != "champions" else None
    tera_icon = get_tera_icon(tera_type)
    tera = (f'<span class="bn-sep"></span><span class="bn-ico bn-tera" tabindex="0" style="--c:{type_map.get(tera_type, {}).get("color", "#777")}">'
            f'<img src="{escape(tera_icon)}" alt=""><span class="bn-tip">Tera {escape(tera_type)}</span></span>') if tera_icon else ""
    moves = "".join(f'<span class="bn-mv" style="--mc:{type_map.get(m.get("type"), {}).get("color", "#5a6375")}">{escape(m["name"])}</span>'
                    for m in p.get("Moves", []))
    jobs = [j for j in JOB_ORDER if j in p.get("Roles", [])][:2] or p.get("Roles", [])[:2]
    beats = "".join(f"<span>{escape(n)}</span>" for n in facts["beats"])
    loses = facts["loses"]
    lose_html = "".join(f"<span>{escape(n)}</span>" for n in loses[:4]) + (f"<span>+{len(loses) - 4} more</span>" if len(loses) > 4 else "")
    set_line = " · ".join(escape(x) for x in (p.get("Item"), p.get("Nature"), _spread(p, game)) if x)
    hover = (f'<div class="bn-hover" role="tooltip"><div class="bn-hk">Set</div>'
             f'<div class="bn-hl">{set_line}<br><span style="color:#7fe6ff">{escape(" · ".join(jobs))}</span></div>'
             f'<div class="bn-hk">Against the {facts["n"]} most used</div><div class="bn-hl">Beats <b>{len(facts["beats"])}</b> one on one</div>'
             + (f'<div class="bn-names">{beats}</div>' if beats else "")
             + (f'<div class="bn-hk">Loses to</div><div class="bn-names bad">{lose_html}</div>' if loses else "")
             + f'<div class="bn-hk">Speed</div><div class="bn-hl" style="margin-bottom:0"><b>{facts["speed"]}</b> with its item, outspeeds '
               f'<b>{facts["outspeeds"] * 100:.0f}%</b> of the top 25&#39;s ladder sets</div></div>')
    return (f'<div class="bn-tile" tabindex="0" style="--tc33:{color}40;--tc88:{color}88;--tcx:{color}">'
            f'<div class="bn-ped"><img src="{escape(get_sprite(name) or "")}" alt="">{item}</div>'
            f'<div class="bn-body"><div class="bn-nm">{escape(name)}</div>'
            f'<div class="bn-icons">{"".join(_type_icon(t, type_map) for t in p.get("Type") or [])}{tera}</div>'
            + _ability_pill(p.get("Ability"))
            + f'<div class="bn-moves">{moves}</div></div>{hover}</div>')


def _ability_pill(ability):
    """The ability pill, with Showdown's description of the ability on hover."""
    if not ability:
        return ""
    from metamatch.engine.abilities import describe
    text = describe(ability)
    if not text:
        return f'<span class="bn-ability">{escape(ability)}</span>'
    return (f'<span class="bn-ico bn-abw" tabindex="0"><span class="bn-ability">{escape(ability)}</span>'
            f'<span class="bn-tip wide"><b>{escape(ability)}</b>{escape(text)}</span></span>')


def _stats(team, rows, facts, coverage, weakness, type_map):
    answered, total = sum(1 for r in rows if r["answers"]), len(rows)
    pct = round(100 * answered / total) if total else 0
    threats_txt = (f"Something on the team beats each of the {total} most used Pokémon" if answered == total
                   else f"{total - answered} of the {total} most used Pokémon have no answer on the team")
    missing = [t.capitalize() for t, ok in coverage.items() if not ok]
    covered = len(coverage) - len(missing)
    cov_txt = ("Nothing hits " + "".join(f'<span class="bn-wk">{_type_icon(t, type_map, True)}{escape(t)}</span>' for t in missing)
               + " super effectively") if missing else "Something hits every type super effectively"
    worst = max((v["weak"] for v in weakness.values()), default=0)
    shared = [t.capitalize() for t, v in weakness.items() if v["weak"] == worst and worst >= 2]
    weak_html = ("".join(f'<span class="bn-wk">{_type_icon(t, type_map, True)}{escape(t)}</span>' for t in shared)
                 + f'<div class="bn-txt">{worst} members weak to {"each" if len(shared) > 1 else "it"}</div>') if shared \
        else '<div class="bn-txt">No type hits more than one member hard</div>'
    fast = [f for f in facts if f["outspeeds"] >= FAST]
    if fast:
        names = [f["name"] for f in fast]
        joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        speed_txt = f"{escape(joined)} {'outspeeds' if len(names) == 1 else 'outspeed'} {min(f['outspeeds'] for f in fast) * 100:.0f}% of the top 25"
    else:
        top = max(facts, key=lambda f: f["speed"]) if facts else None
        fast = [top] if top else []
        speed_txt = (f"{escape(top['name'])} is your fastest, outspeeding {top['outspeeds'] * 100:.0f}% of the top 25" if top
                     else "No Speed data")
    sprites = "".join(f'<img src="{escape(get_sprite(f["name"]) or "")}" alt="">' for f in fast[:3])
    return (f'<div class="bn-stats">'
            f'<div class="bn-stat"><div class="bn-ring" style="--p:{pct}"><span>{answered}/{total}</span></div>'
            f'<div><div class="bn-lbl">Top threats</div><div class="bn-txt">{threats_txt}</div></div></div>'
            f'<div class="bn-stat"><div class="bn-big">{covered}<small>/{len(coverage)}</small></div>'
            f'<div style="min-width:0"><div class="bn-lbl">Types hit hard</div><div class="bn-txt">{cov_txt}</div></div></div>'
            f'<div class="bn-stat"><div style="min-width:0"><div class="bn-lbl">Shared weaknesses</div>{weak_html}</div></div>'
            f'<div class="bn-stat"><div class="bn-fast">{sprites}</div>'
            f'<div style="min-width:0"><div class="bn-lbl">Speed</div><div class="bn-txt">{speed_txt}</div></div></div></div>')


def render(team, coverage, weakness, type_map, team_name=None):
    from metamatch.tabs.tab_threats import _stats_month
    format_id = config.team_format(team)
    game = config.format_game(format_id)
    with st.spinner("Sizing up your team..."):
        rows, facts = _facts(json.dumps(team, sort_keys=True, default=str), format_id, _stats_month())
    by_name = {f["name"]: dict(f, n=len(rows)) for f in facts}
    roles = {r for p in team.values() for r in p.get("Roles", [])}
    chips = "".join(f'<span class="bn-chip ok">✓ {label}</span>' for role, label in ROLE_CHIPS if role in roles)
    chips += "".join(f'<span class="bn-chip no">! No {label.lower()}</span>' for role, label in ROLE_CHIPS
                     if role in CORE and role not in roles)
    label = config.format_info(format_id)["label"]
    kicker = f"{label} team" + (f" · saved as {team_name}" if team_name else "")
    tiles = "".join(_tile(p, by_name.get(p["Pokemon"], {"beats": [], "loses": [], "speed": p.get("Speed", 0), "outspeeds": 0, "n": len(rows)}),
                          type_map, game) for p in team.values())
    st.html(STYLE + f'<div class="bn"><div class="bn-top"><div class="bn-k">{escape(kicker)}</div>'
                    f'<div class="bn-t">{escape(archetype(team))}</div><div class="bn-chips">{chips}</div></div>'
                    f'<div class="bn-team">{tiles}</div>{_stats(team, rows, facts, coverage, weakness, type_map)}</div>')

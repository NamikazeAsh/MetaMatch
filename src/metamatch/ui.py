"""
Shared headers in the MetaFlash style, so every page and tab reads as one product: a page header (kicker,
gradient title, one line on what the page does, and the format and stats month on the right) and a smaller
section header for the parts of a page.
"""
from html import escape

import streamlit as st

from metamatch import config

# The team page's analysis tabs, in order (the guided tour opens them by these labels). Without a local model the
# last tab searches the strategy analyses instead of chatting (tabs/tab_strategy_search.py)
DASHBOARD_TABS = ("Coach Guide", "Team Overview", "Audit", "Threat Board", "Recommendations", "Matchup Matrices",
                  "Speed Tiers", "Coach Chat" if config.CHAT_ENABLED else "Strategy Search")

CSS = """
<style>
.ui-ph { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; padding-bottom:14px; margin:6px 2px 14px;
  position:relative; }
.ui-ph::after { content:""; position:absolute; left:0; right:0; bottom:0; height:1px;
  background:linear-gradient(90deg, rgba(0,212,255,0.7), rgba(0,255,204,0.25) 40%, transparent); }
.ui-ph-k { font-size:0.7rem; font-weight:800; letter-spacing:2.4px; text-transform:uppercase; color:#00d4ff; }
.ui-ph-t { font-weight:900; font-size:2.4rem; line-height:1.05; letter-spacing:-0.5px; margin-top:2px;
  background:linear-gradient(90deg, #ffffff 0%, #9cf1ff 55%, #00ffcc 100%); -webkit-background-clip:text; background-clip:text;
  color:transparent; filter:drop-shadow(0 0 18px rgba(0,212,255,0.25)); }
.ui-ph-tag { font-size:1rem; color:#aab3c5; margin-top:4px; max-width:88ch; }
.ui-ph-meta { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:6px; flex-shrink:0; }
.ui-chip { display:inline-flex; align-items:center; gap:6px; padding:5px 11px; border-radius:999px; font-size:0.78rem;
  color:#aab3c5; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.1); white-space:nowrap; }
.ui-chip b { color:#e8ecf3; font-weight:700; }
.ui-chip-fmt { color:#dff9ff; font-weight:700; background:rgba(0,212,255,0.12); border-color:rgba(0,212,255,0.5);
  box-shadow:0 0 10px rgba(0,212,255,0.14); }
.ui-sh { margin:10px 2px 10px; }
.ui-sh-k { font-size:0.64rem; font-weight:800; letter-spacing:2px; text-transform:uppercase; color:#00d4ff; }
.ui-sh-t { font-weight:900; font-size:1.4rem; color:#ffffff; letter-spacing:-0.3px; margin-top:2px; line-height:1.2; }
.ui-sh-c { font-size:0.88rem; color:#aab3c5; margin-top:3px; }
@media (max-width: 640px) {
  .ui-ph { flex-direction:column; align-items:flex-start; } .ui-ph-meta { justify-content:flex-start; } .ui-ph-t { font-size:1.9rem; }
}
</style>
"""


def _meta(format_id):
    """Chips for the right side of a page header, like MetaFlash's: the format lit in cyan, then which month of
    Smogon's stats the page answers from."""
    from metamatch import config, meta_pulse
    if not format_id:
        return ""
    label = config.format_info(format_id)["label"]
    # Showdown's Scarlet and Violet formats name their generation; Champions is its own game
    if config.format_game(format_id) == "sv":
        label = f"Gen 9 {label}"
    month = meta_pulse.month_label(meta_pulse.current_month())
    return (f'<div class="ui-ph-meta"><span class="ui-chip ui-chip-fmt">{escape(label)}</span>'
            f'<span class="ui-chip"><b>{escape(month)}</b> stats</span></div>')


def page_header(kicker, title, tagline="", format_id=None):
    """The top of a page. format_id adds the format and stats month the page answers from."""
    tag = f'<div class="ui-ph-tag">{escape(tagline)}</div>' if tagline else ""
    st.html(CSS + f'<div class="ui-ph"><div><div class="ui-ph-k">{escape(kicker)}</div><div class="ui-ph-t">{escape(title)}</div>'
                  f'{tag}</div>{_meta(format_id)}</div>')


# Each tool's "How it works": three steps (Material icon, title, one line) and a tip, shown in a dialog
GUIDES = {
    "quick-match": ("Quick Match", (
        ("search", "Pick one you like", "Search for a Pokémon you want to build around. One is enough to start."),
        ("group_add", "Add its partners",
         "Cards show who players pair with it most this month. Add the ones you like until you have six."),
        ("rocket_launch", "Analyze or play",
         "Every member gets its usual set. Analyze the team, export it to Showdown or share a PokéPaste link."),
    ), "Hover a member to see its full set, or switch it to a Smogon set."),
    "move-search": ("Move Search", (
        ("search", "Pick your moves", "Choose up to four moves, like Knock Off and U-turn."),
        ("format_list_bulleted", "See who runs them",
         "Every Pokémon that runs all of them, most used first, and how often they come together."),
        ("group_add", "Take one to your team", "Add any result to Quick Match in one click, with its Smogon set."),
    ), "Hidden picks are Pokémon that can learn every move but rarely run them."),
    "spread-lab": ("Spread Lab", (
        ("person_search", "Pick a Pokémon", "Choose one from your team or any Pokémon in the format, and set its item."),
        ("flag", "Set your benchmarks",
         "Outspeed a threat, knock out a target in one or two hits, or survive a specific attack."),
        ("content_copy", "Copy your spread",
         "The smallest spread that clears every benchmark, how the ladder's usual spreads compare, and a set ready to "
         "paste into Showdown."),
    ), "A benchmark no spread can reach is named with the reason, and the rest are still solved."),
    "matchup-preview": ("Matchup Preview", (
        ("content_paste", "Paste their team",
         "A full paste, or just the six names from team preview: each name gets its usual set."),
        ("grid_view", "Read every matchup",
         "Who wins each one on one between your team and theirs. Hover a cell to see how it plays out."),
        ("swords", "Plan your picks",
         "Look closer at any of their Pokémon to see who handles it. In Champions, get the three to bring."),
    ), "No team open? Paste yours too, or try the sample."),
    "replay-auditor": ("Replay Auditor", (
        ("link", "Paste a replay link", "Any public or shared Showdown replay, in any singles format."),
        ("person", "Pick your side", "Say which player you were, so the review is written from your side."),
        ("monitoring", "Read the review",
         "Health over the game, why every Pokémon fainted, and the mistakes worth fixing, each tied to its turn."),
    ), "Every review gets its own link, so you can reopen it or share it."),
}

GUIDE_CSS = """
<style>
.hiw-grid { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:12px; margin:2px 0 4px; }
.hiw-card { position:relative; padding:16px 16px 18px; border-radius:14px; border:1px solid rgba(0,212,255,0.22);
  background:linear-gradient(180deg, rgba(0,212,255,0.07), rgba(0,212,255,0.015) 70%); }
.hiw-top { display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; }
.hiw-num { width:26px; height:26px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center;
  font-size:0.8rem; font-weight:800; color:#0b1220; background:linear-gradient(135deg, #00d4ff, #00ffcc);
  box-shadow:0 0 12px rgba(0,212,255,0.35); }
.hiw-ic { font-family:'Material Symbols Rounded'; font-size:28px; line-height:1; color:#00d4ff; font-weight:normal;
  font-style:normal; letter-spacing:normal; text-transform:none; white-space:nowrap; font-feature-settings:'liga';
  -webkit-font-smoothing:antialiased; opacity:0.9; }
.hiw-t { font-size:1rem; font-weight:700; color:#eef3fb; margin-bottom:6px; letter-spacing:-0.1px; }
.hiw-d { font-size:0.86rem; line-height:1.5; color:#aab3c5; }
.hiw-tip { display:flex; align-items:center; gap:8px; margin-top:12px; padding:9px 12px; border-radius:10px;
  background:rgba(255,255,255,0.03); border:1px dashed rgba(255,255,255,0.1); font-size:0.84rem; color:#aab3c5; }
.hiw-tip .hiw-ic { font-size:18px; color:#ffd166; opacity:1; }
@media (max-width: 720px) { .hiw-grid { grid-template-columns:minmax(0, 1fr); } }
[class*="st-key-hiw_open_"] button { border-radius:999px !important; padding:4px 14px 4px 10px !important;
  min-height:0 !important; border:1px solid rgba(0,212,255,0.32) !important; background:rgba(0,212,255,0.06) !important;
  color:#bdefff !important; }
[class*="st-key-hiw_open_"] button:hover { background:rgba(0,212,255,0.13) !important; border-color:rgba(0,212,255,0.55) !important; }
[class*="st-key-hiw_open_"] button p { font-size:0.85rem; font-weight:600; }
</style>
"""


def _guide_body(page):
    _, steps, tip = GUIDES[page]
    cards = "".join(
        f'<div class="hiw-card"><div class="hiw-top"><span class="hiw-num">{n}</span>'
        f'<span class="hiw-ic">{icon}</span></div><div class="hiw-t">{escape(title)}</div>'
        f'<div class="hiw-d">{escape(text)}</div></div>'
        for n, (icon, title, text) in enumerate(steps, 1))
    st.html(GUIDE_CSS + f'<div class="hiw-grid">{cards}</div>'
            f'<div class="hiw-tip"><span class="hiw-ic">lightbulb</span>{escape(tip)}</div>')
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button("Got it", type="primary", key=f"hiw_done_{page}"):
            st.rerun()


def how_it_works(page):
    """A 'How it works' button under the page header that opens the tool's three step guide in a dialog."""
    name = GUIDES[page][0]
    st.html(GUIDE_CSS)
    if st.button("How it works", icon=":material/help:", key=f"hiw_open_{page}"):
        st.dialog(f"How {name} works", width="large", icon=":material/help:")(_guide_body)(page)


def section_header(kicker, title, caption=""):
    """A part of a page or tab: small kicker, bold title, optional one line caption."""
    cap = f'<div class="ui-sh-c">{escape(caption)}</div>' if caption else ""
    st.html(CSS + f'<div class="ui-sh"><div class="ui-sh-k">{escape(kicker)}</div><div class="ui-sh-t">{escape(title)}</div>{cap}</div>')

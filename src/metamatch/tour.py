"""
Guided tour for new users: a short spotlight walkthrough of the real app. Each step lights up one part of a page
(everything else is dimmed but stays usable, so hover cards still open) and a card explains it, with Back, Skip and
Next. The tour opens the sample team when it needs a team and switches the dashboard tabs itself.

The state functions take any dict like mapping: st.session_state in the app, a plain dict in tests.
"""
from dataclasses import dataclass
from html import escape

import streamlit as st

from metamatch import config, storage
from metamatch.ui import DASHBOARD_TABS

STEP_KEY = "tour_step"    # index of the current step, None when the tour is off
TAB_KEY = "tour_tab"      # dashboard tab to open on the next team page render
SEEN_KEY = "tour_seen"    # the first visit offer was taken or dismissed


@dataclass(frozen=True)
class Step:
    page: str                  # "home" or "team"
    target: str                # CSS selector, every match lit as one area; "A || B" falls back to B when A isn't shown
    title: str
    text: str
    tab: str | None = None     # dashboard tab the step opens
    top: bool = False          # card at the top right, for targets low on the screen


STEPS = (
    Step("home", ".st-key-team_hero", "Start with your team",
         "Paste a Showdown export or a PokéPaste link and pick the format above it. The whole dashboard builds in "
         "about a second."),
    Step("home", ".mp-mag", "MetaFlash",
         "What moved on the ladder this month, from Smogon's usage stats. Hover a partner sprite for its rank and "
         "usual item."),
    Step("team", ".bn", "Your team at a glance",
         "The team's style, the jobs it covers and every member's set. Hover a member for who it beats one on one "
         "and how fast it really is."),
    Step("team", '.st-key-dashboard_tab [role="tablist"]', "Go deeper",
         "Each tab looks at the team one way: types, legality, threats, teammates, type charts, Speed and a game "
         "plan. Only the open tab is worked out, so switching is quick.", tab="Team Overview"),
    Step("team", "table.tb", "Threat Board",
         "Your six against the 12 most used Pokémon, one matchup at a time, every verdict from the damage "
         "calculator. Hover a cell for the numbers.", tab="Threat Board"),
    Step("team", ".cg-win", "Coach Guide",
         "A game plan written from those numbers: the win condition, the leads, the Tera plan and the pairs that "
         "cover each other.", tab="Coach Guide"),
    Step("team", ".st-key-speed_chart_card", "Speed Tiers",
         "Your real Speed against every spread the top Pokémon run. Hover a dot for the spreads behind it, and test "
         "a Speed under the chart to see what it costs.", tab="Speed Tiers"),
    Step("team", '[data-testid="stTopNavLinkContainer"] || [data-testid="stExpandSidebarButton"]', "More tools",
         "Quick Match finds partners for a core, Move Search finds sets, Spread Lab builds a spread, Matchup Preview "
         "checks a team you're about to face and Replay Auditor reviews a game. On a phone they're in the menu.",
         top=True),
)


# --- State -------------------------------------------------------------------------------------

def _go(state, i, steps=STEPS):
    state[STEP_KEY] = i
    if steps[i].tab:
        state[TAB_KEY] = steps[i].tab


def start(state, steps=STEPS):
    _go(state, 0, steps)


def next_step(state, steps=STEPS):
    """The next step, or the end of the tour after the last one."""
    i = state.get(STEP_KEY)
    if i is None:
        return
    if i + 1 >= len(steps):
        stop(state)
    else:
        _go(state, i + 1, steps)


def back(state, steps=STEPS):
    i = state.get(STEP_KEY)
    if i:
        _go(state, i - 1, steps)


def stop(state):
    state[STEP_KEY] = None
    state.pop(TAB_KEY, None)


def current(state, steps=STEPS):
    """(index, Step) while the tour runs, else None."""
    i = state.get(STEP_KEY)
    return (i, steps[i]) if isinstance(i, int) and 0 <= i < len(steps) else None


def pending_tab(state):
    """The dashboard tab a step asked for, once: the team page applies it before drawing its tabs."""
    tab = state.pop(TAB_KEY, None)
    return tab if tab in DASHBOARD_TABS else None


def seen(state):
    """True once the first visit offer was taken or dismissed (remembered on this machine in local mode)."""
    if state.get(SEEN_KEY):
        return True
    if config.LOCAL_MODE and storage.get_pref(SEEN_KEY):
        state[SEEN_KEY] = True
        return True
    return False


def mark_seen(state):
    state[SEEN_KEY] = True
    if config.LOCAL_MODE:
        storage.set_pref(SEEN_KEY, True)


def begin(state):
    mark_seen(state)
    start(state)


# --- UI ----------------------------------------------------------------------------------------

CARD_CSS = """
<style>
[class*="st-key-tour_card"] { position: fixed !important; right: 24px; bottom: 24px; width: 360px !important;
  z-index: 1000001; padding: 16px 18px 10px !important; gap: 8px !important; border-radius: 16px;
  background: linear-gradient(160deg, rgba(28,36,52,0.98), rgba(16,21,31,0.98));
  border: 1px solid rgba(0,212,255,0.35); box-shadow: 0 20px 50px rgba(0,0,0,0.6); }
.st-key-tour_card_top { top: 84px; bottom: auto; }
.tr-k { font-size: 0.7rem; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; color: #00d4ff; }
.tr-t { font-size: 1.08rem; font-weight: 800; color: #fff; margin: 2px 0 4px; }
.tr-x { font-size: 0.88rem; line-height: 1.5; color: #c8d0dc; }
.tr-bar { height: 3px; border-radius: 3px; background: rgba(255,255,255,0.08); margin-top: 10px; overflow: hidden; }
.tr-bar > i { display: block; height: 100%; background: linear-gradient(90deg, #00d4ff, #00ffcc); }
.st-key-tour_btns { gap: 6px !important; }
.st-key-tour_btns .stButton > button { width: auto !important; transform: none !important; }
.st-key-tour_back button, .st-key-tour_skip button { background: transparent !important; border: none !important;
  box-shadow: none !important; color: #9aa3b2 !important; padding: 4px 8px !important; font-weight: 600 !important; }
.st-key-tour_back button:hover, .st-key-tour_skip button:hover { color: #fff !important; }
.st-key-tour_back button:disabled { opacity: 0.35; }
.st-key-tour_offer_go button { border-radius: 999px !important; padding: 2px 16px !important; }
/* Top right of Home, level with the centred logo. Out of the flow, and its wrapper gives back the gap after it,
   so nothing below moves */
div:has(> .st-key-tour_offer) { position: relative; margin-bottom: -1rem; }
.st-key-tour_offer { position: absolute !important; top: 0; right: 0; width: auto !important; z-index: 2; }
@media (max-width: 640px) {
  div:has(> .st-key-tour_offer) { margin-bottom: 0; }
  .st-key-tour_offer { position: relative !important; }
  [class*="st-key-tour_card"] { left: 12px; right: 12px; width: auto !important; bottom: 12px; }
  .st-key-tour_card_top { top: 68px; bottom: auto; }
}
</style>
"""

SPOTLIGHT_JS = """
export default function (component) {
  const data = component.data || {}
  const sel = data.selector
  const g = window.__mmTour || (window.__mmTour = {})
  clearInterval(g.timer)
  if (g.place) { window.removeEventListener("scroll", g.place, true); window.removeEventListener("resize", g.place) }
  let hole = document.getElementById("mm-tour-hole")
  if (!sel) { if (hole) hole.remove(); g.step = -1; return }
  if (!hole) {
    hole = document.createElement("div")
    hole.id = "mm-tour-hole"
    Object.assign(hole.style, { position: "fixed", zIndex: "1000000", pointerEvents: "none", borderRadius: "14px",
      boxShadow: "0 0 0 3px rgba(0,212,255,0.85), 0 0 26px 6px rgba(0,212,255,0.25), 0 0 0 200vmax rgba(5,8,14,0.72)",
      transition: "left .25s ease, top .25s ease, width .25s ease, height .25s ease", display: "none" })
    document.body.appendChild(hole)
  }
  // A rerun of the same step (a slider moved, a hover card opened) never scrolls the page again
  let scrolled = g.step === data.step
  g.step = data.step
  const started = Date.now()
  const shown = (el) => { const q = el.getBoundingClientRect(); return q.width > 0 && q.height > 0 }
  const matches = () => {
    for (const alt of sel.split("||")) {
      const els = [...document.querySelectorAll(alt.trim())].filter(shown)
      if (els.length) return els
    }
    return []
  }
  const place = () => {
    const els = matches()
    let l = Infinity, t = Infinity, r = -Infinity, b = -Infinity
    for (const el of els) {
      const q = el.getBoundingClientRect()
      if (!q.width || !q.height) continue
      l = Math.min(l, q.left); t = Math.min(t, q.top); r = Math.max(r, q.right); b = Math.max(b, q.bottom)
    }
    if (l === Infinity) { hole.style.display = "none"; return false }
    const pad = 8
    Object.assign(hole.style, { display: "block", left: (l - pad) + "px", top: (t - pad) + "px",
      width: (r - l + 2 * pad) + "px", height: (b - t + 2 * pad) + "px" })
    if (!scrolled) {
      scrolled = true
      const box = els[0].closest('[data-testid="stMain"]') || document.scrollingElement
      const h = b - t, tall = h > window.innerHeight * 0.55
      box.scrollBy({ top: t - (tall ? 96 : (window.innerHeight - h) / 2), behavior: "smooth" })
    }
    return true
  }
  g.place = place
  // Targets appear late (tab content, calc results), so keep looking for a while, then keep the hole on them
  g.timer = setInterval(() => { if (!place() && Date.now() - started > 10000) clearInterval(g.timer) }, 150)
  window.addEventListener("scroll", place, true)
  window.addEventListener("resize", place)
  return () => {
    clearInterval(g.timer)
    window.removeEventListener("scroll", place, true)
    window.removeEventListener("resize", place)
    const h = document.getElementById("mm-tour-hole")
    if (h) h.remove()
  }
}
"""

_SPOTLIGHT = None


def _spotlight(selector, step):
    """Mounts the spotlight; with no selector it clears any veil a previous step left."""
    global _SPOTLIGHT
    if _SPOTLIGHT is None:
        _SPOTLIGHT = st.components.v2.component("metamatch_tour_spotlight", html="<span></span>", js=SPOTLIGHT_JS)
    _SPOTLIGHT(data={"selector": selector, "step": step}, key="tour_spot", height=0)


def offer():
    """First visit only: a small pill in Home's top right corner offering the tour, with a way to say no thanks."""
    if current(st.session_state) or seen(st.session_state):
        return
    with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center", gap="small",
                      key="tour_offer"):
        st.button("New here? Take the 1 minute tour", icon=":material/explore:", key="tour_offer_go",
                  on_click=begin, args=(st.session_state,))
        st.button("", icon=":material/close:", key="tour_offer_x", type="tertiary", help="No thanks",
                  on_click=mark_seen, args=(st.session_state,))


def start_button():
    """'Take the tour', always in the sidebar."""
    st.button("Take the tour", icon=":material/explore:", key="tour_sidebar", width="stretch",
              on_click=begin, args=(st.session_state,))


def redirect(page, to_home, to_team, has_team=True):
    """Moves to the page the current step is on, opening a team for team steps when none is loaded. to_home and
    to_team switch pages, so they don't return."""
    cur = current(st.session_state)
    if not cur:
        return
    if cur[1].page == "home" and page != "home":
        to_home()
    elif cur[1].page == "team" and (page != "team" or not has_team):
        to_team()


def render():
    """The current step's card and spotlight; draws nothing visible when the tour is off. Also carries the tour's
    CSS for the offer pill, at the end of the page, so a style only block never adds a gap above the pill."""
    st.html(CARD_CSS)
    cur = current(st.session_state)
    if cur:
        i, step = cur
        last = i == len(STEPS) - 1
        with st.container(key="tour_card_top" if step.top else "tour_card"):
            st.html(f'<div class="tr-k">Step {i + 1} of {len(STEPS)}</div><div class="tr-t">{escape(step.title)}</div>'
                    f'<div class="tr-x">{escape(step.text)}</div>'
                    f'<div class="tr-bar"><i style="width:{(i + 1) / len(STEPS) * 100:.0f}%"></i></div>')
            with st.container(horizontal=True, vertical_alignment="center", key="tour_btns"):
                st.button("Back", key="tour_back", type="tertiary", disabled=i == 0, on_click=back, args=(st.session_state,))
                st.button("Skip tour", key="tour_skip", type="tertiary", on_click=stop, args=(st.session_state,))
                st.space("stretch")
                st.button("Finish" if last else "Next", key="tour_next", type="primary",
                          icon=":material/check:" if last else ":material/arrow_forward:", icon_position="right",
                          on_click=next_step, args=(st.session_state,))
    _spotlight(cur[1].target if cur else None, cur[0] if cur else -1)

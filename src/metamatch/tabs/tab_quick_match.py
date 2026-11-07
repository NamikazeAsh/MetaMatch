"""Quick Match: partners for a core of 1 to 5 Pokemon, from how often players really pair them in this format."""
from html import escape

import streamlit as st

from metamatch import config
from metamatch.auditor import load_chaos_data
from metamatch.engine.completer import core_partners
from metamatch.tabs.tab_recommender import STYLE as CARD_STYLE
from metamatch.sprites import get_sprite

QM_STYLE = """
<style>
.qm-card { background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.08); border-radius: 12px; padding: 12px;
  text-align: center; margin-bottom: 14px; }
.qm-card img.sprite { width: 72px; height: 72px; object-fit: contain; }
.qm-card .tc-tip { text-align: left; }
.qm-name { font-weight: 700; margin-top: 4px; }
.qm-share { font-size: .82rem; color: #c6d1e3; margin-top: 4px; }
.qm-sets { max-height: 0; overflow: hidden; opacity: 0; transition: max-height .3s ease, opacity .3s ease; text-align: left; }
.qm-card:hover .qm-sets { max-height: 300px; opacity: 1; }
.qm-set { background: rgba(0,0,0,.25); border-radius: 6px; padding: 6px 10px; margin-top: 6px; border-left: 3px solid #22d3ee; }
.qm-set b { display: block; font-size: .8rem; }
.qm-set span { font-size: .72rem; color: #aab4c6; }
</style>
"""


def _options(format_id):
    """The format's Pokemon, most used first."""
    data = load_chaos_data(format_id) or {}
    ranked = sorted(data.items(), key=lambda kv: kv[1].get("usage", 0), reverse=True)
    return [name for name, entry in ranked if entry.get("usage", 0) > 0.001]


def _chip(r):
    member, share, lift = r["pairs"][0]
    if lift >= 1.5:
        cls, text = "pair", f"Players often pair it with {escape(member)}"
    elif lift >= 1.15:
        cls, text = "pair", f"Sometimes paired with {escape(member)}"
    elif r["lift"] <= 0.8:
        cls, text = "flat", "Popular, but not with this core"
    else:
        cls, text = "flat", "Popular on every kind of team"
    rows = "".join(
        f'<div class="tc-trow"><span>On teams with {escape(m)}</span><b>{s * 100:.1f}%</b>'
        f'<em class="{"up" if l_ >= 1.15 else "down" if l_ <= 0.85 else ""}">{l_:.1f}x</em></div>' for m, s, l_ in r["pairs"][:3])
    tip = (f'<span class="tc-tip"><span class="tc-tt">How often {escape(r["name"])} shows up</span>{rows}'
           f'<div class="tc-trow all"><span>On all teams</span><b>{r["usage"]:.1f}%</b><em></em></div>'
           '<span class="tc-tfoot">From this month&#39;s ladder teams. 2.0x means twice as often as on an average team.</span></span>')
    return f'<span class="tc-chip {cls} tc-pop">{text}{tip}</span>'


def _sets_html(name, strat_data, label):
    sets = [(s, info) for s, info in (strat_data.get(name, {}).get("sets", {}) or {}).items() if f"({label})" in s][:3]
    if not sets:
        return ""
    out = []
    for set_name, info in sets:
        item = info.get("item", "")
        item = item[0] if isinstance(item, list) and item else item
        ability = info.get("ability", "")
        ability = ability[0] if isinstance(ability, list) and ability else ability
        detail = " · ".join(x for x in (item, ability) if x and x != "None")
        out.append(f'<div class="qm-set"><b>{escape(set_name.rsplit(" (", 1)[0])}</b><span>{escape(detail)}</span></div>')
    return '<div class="qm-sets">' + "".join(out) + "</div>"


def render(get_strat_data_fn):
    format_id = st.session_state.get("format_id") or config.DEFAULT_FORMAT
    label = config.format_info(format_id)["label"]
    st.caption(f"Pick 1 to 5 Pokémon to find the partners players actually build with them in {label}.")
    core = st.multiselect("Your core (up to 5)", options=_options(format_id), max_selections=5,
                          placeholder="Search for a Pokémon...", key=f"quick_match_select_{format_id}")
    if not core:
        return
    partners = core_partners(core, format_id, n=16)
    if not partners:
        st.caption("No ladder data pairs with this core yet.")
        return
    strat_data = get_strat_data_fn()
    st.markdown("**Best partners for your core**")
    for i in range(0, len(partners), 4):
        cols = st.columns(4)
        for col, r in zip(cols, partners[i:i + 4]):
            with col:
                sprite = escape(get_sprite(r["name"]) or "")
                core_word = "your core" if len(core) > 1 else escape(core[0])
                st.markdown(
                    CARD_STYLE + QM_STYLE +
                    f'<div class="qm-card"><img class="sprite" src="{sprite}" alt="">'
                    f'<div class="qm-name">{escape(r["name"])}</div>'
                    f'<div class="qm-share">On {r["share"] * 100:.0f}% of teams with {core_word}</div>'
                    f'<div>{_chip(r)}</div>{_sets_html(r["name"], strat_data, label)}</div>',
                    unsafe_allow_html=True)
    st.caption("Ranked by how often teams with your core run each partner, boosted when that's well above its usual usage. "
               "Hover a card for its sets and a chip for the numbers.")

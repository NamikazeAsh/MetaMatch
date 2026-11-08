"""
Shared headers in the MetaFlash style, so every page and tab reads as one product: a page header (kicker,
gradient title, one line on what the page does, and the format and stats month on the right) and a smaller
section header for the parts of a page. No emojis in either.
"""
from html import escape

import streamlit as st

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
.ui-ph-tag { font-size:1rem; color:#aab3c5; margin-top:4px; max-width:70ch; }
.ui-ph-meta { font-size:0.78rem; color:#8a93a6; text-align:right; line-height:1.5; flex-shrink:0; }
.ui-ph-meta b { color:#d6dbe6; font-weight:700; }
.ui-sh { margin:10px 2px 10px; }
.ui-sh-k { font-size:0.64rem; font-weight:800; letter-spacing:2px; text-transform:uppercase; color:#00d4ff; }
.ui-sh-t { font-weight:900; font-size:1.4rem; color:#ffffff; letter-spacing:-0.3px; margin-top:2px; line-height:1.2; }
.ui-sh-c { font-size:0.88rem; color:#aab3c5; margin-top:3px; }
@media (max-width: 640px) {
  .ui-ph { flex-direction:column; align-items:flex-start; } .ui-ph-meta { text-align:left; } .ui-ph-t { font-size:1.9rem; }
}
</style>
"""


def _meta(format_id):
    """'OU · October 2026 / Smogon usage stats' for the right side of a page header."""
    from metamatch import config, meta_pulse
    if not format_id:
        return ""
    label = config.format_info(format_id)["label"]
    month = meta_pulse.month_label(meta_pulse.current_month())
    return f'<div class="ui-ph-meta"><b>{escape(label)}</b> · {escape(month)}<br>Smogon usage stats</div>'


def page_header(kicker, title, tagline="", format_id=None):
    """The top of a page. format_id adds the format and stats month the page answers from."""
    tag = f'<div class="ui-ph-tag">{escape(tagline)}</div>' if tagline else ""
    st.html(CSS + f'<div class="ui-ph"><div><div class="ui-ph-k">{escape(kicker)}</div><div class="ui-ph-t">{escape(title)}</div>'
                  f'{tag}</div>{_meta(format_id)}</div>')


def section_header(kicker, title, caption=""):
    """A part of a page or tab: small kicker, bold title, optional one line caption."""
    cap = f'<div class="ui-sh-c">{escape(caption)}</div>' if caption else ""
    st.html(CSS + f'<div class="ui-sh"><div class="ui-sh-k">{escape(kicker)}</div><div class="ui-sh-t">{escape(title)}</div>{cap}</div>')

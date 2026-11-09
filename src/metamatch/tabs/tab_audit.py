from html import escape

import streamlit as st
from metamatch.sprites import get_sprite
from metamatch.ui import section_header


CHECK_STYLE = """
<style>
.ck { display: grid; grid-template-columns: 26px 1fr; gap: 10px; align-items: start; padding: 9px 12px; margin-bottom: 6px;
  border-radius: 10px; background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.07); }
.ck b { font-size: .95rem; }
.ck.ok b { color: #34d399; } .ck.fix b { color: #f87171; } .ck.note b { color: #facc15; }
.au-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 4px 0 8px; }
.au-card { padding: 12px 14px; border-radius: 12px; background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.07); }
.au-card.ok { border-color: rgba(52,211,153,.28); } .au-card.note { border-color: rgba(250,204,21,.32); background: rgba(250,204,21,.04); }
.au-head { display: flex; align-items: center; gap: 8px; font-weight: 700; margin-bottom: 6px; }
.au-mark { width: 22px; height: 22px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
  font-size: .8rem; flex-shrink: 0; }
.ok .au-mark { background: rgba(52,211,153,.16); color: #34d399; } .note .au-mark { background: rgba(250,204,21,.16); color: #facc15; }
.au-card span { color: #c8ccd4; font-size: .9rem; line-height: 1.45; }
.au-clean { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 2px 0 10px; color: #9aa3b2; font-size: .9rem; }
.au-chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px 2px 2px; border-radius: 999px;
  background: rgba(52,211,153,.08); border: 1px solid rgba(52,211,153,.25); color: #d1fae5; font-size: .85rem; }
.au-chip img { width: 28px; height: 28px; object-fit: contain; }
.au-mons { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.au-mon { display: grid; grid-template-columns: 64px 1fr; gap: 12px; padding: 12px 14px; border-radius: 12px;
  background: rgba(255,255,255,.03); border: 1px solid rgba(250,204,21,.28); }
.au-mon img { width: 64px; height: 64px; object-fit: contain; }
.au-mon .au-name { font-weight: 700; color: #00d4ff; margin-bottom: 4px; }
.au-mon .ck { margin: 0 0 4px; padding: 6px 8px; grid-template-columns: 18px 1fr; font-size: .88rem; }
.au-conv { display: flex; flex-wrap: wrap; gap: 6px; margin: 2px 0 4px; }
.au-conv span { padding: 3px 10px; border-radius: 999px; background: rgba(0,212,255,.06); border: 1px solid rgba(0,212,255,.2);
  color: #c8d3e0; font-size: .8rem; }
.au-conv b { color: #7fe6ff; }
@media (max-width: 900px) { .au-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .au-mons { grid-template-columns: 1fr; } }
</style>
"""
MARKS = {"ok": "✓", "fix": "✗", "note": "!"}


def render_team_check():
    """Legality in plain English, then copy, convert and download."""
    from metamatch import config
    from metamatch.engine import team_check
    team = st.session_state.analysis["team"]
    format_id = config.team_format(team)
    checks = team_check.check(team, format_id)
    section_header("Legality", "Team Check")
    st.markdown(CHECK_STYLE + "".join(
        f'<div class="ck {level}"><b>{MARKS[level]}</b><span>{escape(msg)}</span></div>' for level, msg in checks),
        unsafe_allow_html=True)
    paste = st.session_state.get("pokemon_data") or ""
    champions = config.format_game(format_id) == "champions"
    with st.expander("Export and convert"):
        st.caption("Copy the team, convert its spread for the other game, or download a report to share.")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Showdown export**")
            st.code(paste.strip(), language=None)
        with c2:
            st.markdown("**As Champions stat points**" if not champions else "**As SV EVs**")
            st.code(team_check.convert_paste(paste, to_champions=not champions).strip(), language=None)
            chips = (["<b>8</b> EVs is about <b>1</b> stat point", "<b>252</b> EVs → <b>32</b>", "<b>4</b> EVs → <b>1</b>",
                      "Tera lines dropped: Champions has no Tera"] if not champions else
                     ["<b>1</b> stat point is about <b>8</b> EVs", "<b>32</b> → <b>252</b> EVs", "<b>1</b> → <b>8</b> EVs"])
            st.markdown(CHECK_STYLE + '<div class="au-conv">' + "".join(f"<span>{c}</span>" for c in chips) + "</div>",
                        unsafe_allow_html=True)
        try:
            from metamatch.tabs.tab_threats import _board, _stats_month
            import json
            month = _stats_month()
            board = _board(json.dumps(team, sort_keys=True, default=str), format_id, month)
        except Exception:
            month, board = "", None
        try:
            from metamatch import meta_pulse
            pdf = team_check.report_pdf(team, format_id, checks, board, meta_pulse.month_label(month) if month else "")
        except Exception:
            pdf = None   # fpdf2 missing: the Markdown report still works
        b1, b2, _ = st.columns([1.3, 1, 2])
        if pdf:
            b1.download_button("Download team report", pdf, file_name="metamatch_team_report.pdf", mime="application/pdf",
                               icon=":material/picture_as_pdf:", type="primary", width="stretch")
        (b2 if pdf else b1).download_button("Markdown", team_check.report_markdown(team, format_id, paste, checks, board),
                                            file_name="metamatch_team_report.md", mime="text/markdown",
                                            icon=":material/description:", width="stretch")
    st.markdown("---")


def _team_audit(items):
    section_header("Roles and coverage", "Team Audit")
    st.caption("The jobs most teams cover, and whether every type has something that hits it hard.")
    cards = "".join(
        f'<div class="au-card {"ok" if it["ok"] else "note"}"><div class="au-head"><span class="au-mark">'
        f'{MARKS["ok" if it["ok"] else "note"]}</span>{escape(it["label"])}</div><span>{escape(it["text"])}</span></div>'
        for it in items)
    st.markdown(CHECK_STYLE + f'<div class="au-grid">{cards}</div>', unsafe_allow_html=True)


def _per_member(findings):
    section_header("Sets", "Per Pokémon Findings")
    st.caption("Each set compared with what ladder players run on that Pokémon.")
    clean = [name for name, issues in findings.items() if not issues]
    flagged = {name: issues for name, issues in findings.items() if issues}
    html = ""
    if clean:
        chips = "".join(f'<span class="au-chip"><img src="{escape(get_sprite(n) or "")}" alt="">{escape(n)}</span>'
                        for n in clean)
        lead = "Every set matches what ladder players run:" if not flagged else "Match what ladder players run:"
        html += f'<div class="au-clean">{lead}{chips}</div>'
    if flagged:
        html += '<div class="au-mons">' + "".join(
            f'<div class="au-mon"><img src="{escape(get_sprite(name) or "")}" alt=""><div>'
            f'<div class="au-name">{escape(name)}</div>'
            + "".join(f'<div class="ck note"><b>{MARKS["note"]}</b><span>{escape(i)}</span></div>' for i in issues)
            + '</div></div>' for name, issues in flagged.items()) + '</div>'
    st.markdown(CHECK_STYLE + html, unsafe_allow_html=True)


def render():
    analysis = st.session_state.analysis
    if not analysis.get("team"):
        st.info("Run analysis to see the audit.")
        return
    render_team_check()
    sugg = analysis.get("suggestions") or {}
    if sugg.get("team_analysis"):
        _team_audit(sugg["team_analysis"])
        st.markdown("---")
    if sugg.get("pokemon_specific"):
        _per_member(sugg["pokemon_specific"])

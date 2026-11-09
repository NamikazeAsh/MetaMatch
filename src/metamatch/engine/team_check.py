"""
Team Check: legality in plain English (species, abilities, moves, spreads, Tera, clauses) and conversions
between SV EVs and Champions stat points. Learnsets and full ability lists aren't bundled (the calc's dex
keeps one ability per species), so moves and abilities are checked to exist, not that the Pokemon gets them.
"""
import math
import re

from metamatch import config
from metamatch.engine.dex import dex_for_format, to_id

TYPES = {"Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison", "Ground", "Flying", "Psychic",
         "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy", "Stellar"}
NATURES = {"Hardy", "Lonely", "Brave", "Adamant", "Naughty", "Bold", "Docile", "Relaxed", "Impish", "Lax", "Timid", "Hasty",
           "Serious", "Jolly", "Naive", "Modest", "Mild", "Quiet", "Bashful", "Rash", "Calm", "Gentle", "Sassy", "Careful", "Quirky"}
STAT_ORDER = ("HP", "Atk", "Def", "SpA", "SpD", "Spe")


def ev_to_sp(ev):
    """EVs to Champions stat points (1 SP is about 8 EVs), capped at 32 per stat."""
    return min(32, math.ceil(ev / 8))


def sp_to_ev(sp):
    return min(252, sp * 8)


def _base_name(name):
    return re.split(r"-Mega", name or "")[0]


def check(team, format_id):
    """[(level, message)] with level 'ok', 'fix' or 'note', fixes first."""
    dex = dex_for_format(format_id)
    game = config.format_game(format_id)
    label = config.format_info(format_id)["label"]
    out = []
    if not dex:
        return [("note", "The bundled dex for this format is missing, so legality can't be checked.")]
    members = list(team.values())
    if len(members) < 6:
        out.append(("note", f"The team has {len(members)} Pokémon. Most formats expect 6."))
    for p in members:
        name = p["Pokemon"]
        species = dex.species(name)
        if not species:
            out.append(("fix", f"{name} isn't in the {label} dex."))
            continue
        # The bundled dex only lists each species' first ability, so this checks the ability exists, not who can have it
        ability = p.get("Ability")
        if ability and not dex.ability_name(ability):
            out.append(("fix", f"{name}: {ability} isn't an ability in {label}."))
        moves = [m["name"] for m in p.get("Moves", [])]
        unknown = [m for m in moves if not dex.move_name(m)]
        if unknown:
            out.append(("fix", f"{name}: {', '.join(unknown)} isn't a move in {label}."))
        if not moves:
            out.append(("fix", f"{name} has no moves."))
        elif len(moves) > 4:
            out.append(("fix", f"{name} has {len(moves)} moves. The limit is 4."))
        dupes = {m for m in moves if moves.count(m) > 1}
        if dupes:
            out.append(("fix", f"{name} lists {', '.join(sorted(dupes))} twice."))
        item = p.get("Item")
        if item and not dex.item_name(item):
            out.append(("fix", f"{name}: {item} isn't an item in {label}."))
        nature = p.get("Nature")
        if nature and nature not in NATURES:
            out.append(("fix", f"{name}: {nature} isn't a nature."))
        if game == "champions":
            sp = p.get("SP") or {}
            over = [f"{v} {k}" for k, v in sp.items() if v > 32]
            if over:
                out.append(("fix", f"{name} has {', '.join(over)}. Champions allows at most 32 stat points in one stat."))
            if sum(sp.values()) > 66:
                out.append(("fix", f"{name} has {sum(sp.values())} stat points. Champions allows 66 in total."))
        else:
            evs = p.get("EVs") or {}
            over = [f"{v} {k}" for k, v in evs.items() if v > 252]
            if over:
                out.append(("fix", f"{name} has {', '.join(over)}. The most one stat can take is 252 EVs."))
            if sum(evs.values()) > 510:
                out.append(("fix", f"{name} has {sum(evs.values())} EVs. The total limit is 510."))
            tera = p.get("Tera Type")
            if tera and tera not in TYPES:
                out.append(("fix", f"{name}: {tera} isn't a Tera type."))
            if p.get("Forme", "").find("-Mega") > 0 and format_id != "gen9natdex":
                out.append(("fix", f"{name} holds a Mega Stone, but Mega Evolution isn't allowed in {label}."))

    bases = [_base_name(p.get("Forme") or p["Pokemon"]) for p in members]
    dupes = sorted({b for b in bases if bases.count(b) > 1})
    if dupes:
        out.append(("fix", f"Species Clause: only one of each Pokémon. {', '.join(dupes)} appears more than once."))
    megas = [p["Pokemon"] for p in members if "-Mega" in (p.get("Forme") or "")]
    if len(megas) > 1:
        out.append(("note", f"{len(megas)} Mega Stones ({', '.join(megas)}). Only one Pokémon can Mega Evolve per battle."))
    if game == "champions":
        items = [p.get("Item") for p in members if p.get("Item")]
        repeated = sorted({i for i in items if items.count(i) > 1})
        if repeated:
            out.append(("note", f"{', '.join(repeated)} is held more than once. Bring 3 play uses Item Clause (each item once)."))

    fixes = [x for x in out if x[0] == "fix"]
    if not fixes:
        out.insert(0, ("ok", f"Legal for {label}: species, abilities, moves, items and spreads all check out."))
    return sorted(out, key=lambda x: {"fix": 0, "note": 1, "ok": 2}[x[0]])


def convert_paste(text, to_champions):
    """A Showdown paste with every 'EVs:' line converted between SV EVs and Champions stat points."""
    def convert(m):
        parts = []
        for chunk in m.group(1).split("/"):
            bits = chunk.strip().split(" ")
            if len(bits) >= 2 and bits[0].isdigit():
                v = int(bits[0])
                v = ev_to_sp(v) if to_champions else sp_to_ev(v)
                if v:
                    parts.append(f"{v} {bits[1]}")
        return "EVs: " + " / ".join(parts) if parts else ""
    lines = [re.sub(r"^EVs:\s*(.*)$", convert, line) for line in text.splitlines()]
    if to_champions:
        lines = [line for line in lines if not line.startswith("Tera Type:")]
    return "\n".join(lines)


def report_markdown(team, format_id, paste, checks, board_rows=None):
    """A shareable Markdown report: the team, its checks and (optionally) its Threat Board summary."""
    label = config.format_info(format_id)["label"]
    lines = [f"# MetaMatch team report ({label})", "", "## Team", "", "```", paste.strip(), "```", "", "## Team Check", ""]
    mark = {"ok": "OK", "fix": "Fix", "note": "Note"}
    lines += [f"- **{mark[level]}:** {msg}" for level, msg in checks]
    if board_rows:
        lines += ["", "## Threat Board", "", "| Threat | Usage | Answers |", "| --- | --- | --- |"]
        lines += [f"| {r['name']} | {r['usage']:g}% | {', '.join(r['answers']) or 'none'} |" for r in board_rows]
    lines += ["", "Made with MetaMatch. Every matchup is worked out by the Smogon damage calculator."]
    return "\n".join(lines)


TYPE_COLORS = {"Fire": "#FF4422", "Water": "#3399FF", "Grass": "#77CC55", "Electric": "#FFCC33", "Psychic": "#FF5599",
               "Ice": "#66CCFF", "Fighting": "#BB5544", "Poison": "#AA5599", "Ground": "#DDBB55", "Flying": "#8899FF",
               "Bug": "#AABB22", "Rock": "#BBAA66", "Ghost": "#6666BB", "Dragon": "#7766EE", "Dark": "#775544",
               "Steel": "#AAAABB", "Fairy": "#EE99AA", "Normal": "#AAAA99", "Stellar": "#44AACC"}
INK, MUTED, LINE, ACCENT = (24, 28, 38), (104, 112, 128), (222, 226, 234), (0, 150, 180)
MARK_COLORS = {"ok": (16, 163, 107), "fix": (220, 38, 38), "note": (217, 154, 0)}


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _latin(text):
    """The PDF's built in fonts cover Latin-1 only (which has é and ·); anything else becomes '?'."""
    return str(text).encode("latin-1", "replace").decode("latin-1")


def _spread(p):
    """'Timid · 252 SpA / 4 SpD / 252 Spe' from a parsed member, in EVs or Champions stat points."""
    points, unit = (p.get("SP"), " SP") if p.get("SP") else (p.get("EVs") or {}, "")
    spread = " / ".join(f"{v} {k}" for k, v in points.items() if v)
    return " · ".join(x for x in (p.get("Nature"), spread + (unit if spread else "")) if x)


def report_pdf(team, format_id, checks, board_rows=None, month_label=""):
    """The team report as a one or two page PDF: the six sets, Team Check and the Threat Board summary."""
    from fpdf import FPDF
    from fpdf.fonts import FontFace
    from metamatch.sprites import sprite_file

    class Doc(FPDF):
        def footer(self):
            self.set_y(-11)
            self.set_font("Helvetica", "", 7.5)
            self.set_text_color(*MUTED)
            half = (self.w - self.l_margin - self.r_margin) / 2
            self.cell(half, 4, _latin("Made with MetaMatch · every matchup worked out by the Smogon damage calculator"))
            self.cell(half, 4, f"{self.page_no()} / {{nb}}", align="R")

    label = config.format_info(format_id)["label"]
    pdf = Doc(format="A4")
    pdf.set_margins(14, 14, 14)
    pdf.set_auto_page_break(True, margin=16)
    pdf.set_title(f"MetaMatch team report ({label})")
    pdf.set_creator("MetaMatch")
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    # Header band
    pdf.set_fill_color(15, 18, 25)
    pdf.rect(0, 0, pdf.w, 34, style="F")
    pdf.set_xy(14, 9)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(0, 212, 255)
    pdf.cell(0, 4, "METAMATCH", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, "Team report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(14)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(170, 179, 197)
    pdf.cell(0, 5, _latin(" · ".join(x for x in (label, month_label and f"{month_label} ladder stats") if x)))
    pdf.set_y(42)

    def heading(text):
        if pdf.get_y() > pdf.h - 40:
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*INK)
        pdf.cell(0, 7, _latin(text), new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*ACCENT)
        pdf.set_line_width(0.6)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 16, pdf.get_y())
        pdf.ln(4)

    # The six sets, two per row
    heading("Team")
    members = list(team.values())
    gap, card_h = 6, 31
    card_w = (width - gap) / 2
    for i, p in enumerate(members):
        col = i % 2
        if col == 0 and pdf.get_y() + card_h > pdf.h - 16:
            pdf.add_page()
        x, y = pdf.l_margin + col * (card_w + gap), pdf.get_y()
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.3)
        pdf.set_fill_color(248, 249, 252)
        pdf.rect(x, y, card_w, card_h, style="DF", round_corners=True, corner_radius=3)
        sprite = sprite_file(p.get("Forme") or p["Pokemon"])
        if sprite:
            try:
                pdf.image(str(sprite), x + 3, y + 5, w=19, h=19)
            except Exception:
                pass
        tx = x + 25
        pdf.set_xy(tx, y + 3)
        head = _latin(p["Pokemon"] + (f" @ {p['Item']}" if p.get("Item") else ""))
        size = 10.5
        pdf.set_font("Helvetica", "B", size)
        while size > 7.5 and pdf.get_string_width(head) > card_w - 28:
            size -= 0.5
            pdf.set_font("Helvetica", "B", size)
        pdf.set_text_color(*INK)
        pdf.cell(card_w - 27, 5, head, new_x="LEFT", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*MUTED)
        meta = " · ".join(x for x in (p.get("Ability"), p.get("Tera Type") and f"Tera {p['Tera Type']}") if x)
        pdf.cell(card_w - 27, 4.2, _latin(meta), new_x="LEFT", new_y="NEXT")
        pdf.cell(card_w - 27, 4.2, _latin(_spread(p)), new_x="LEFT", new_y="NEXT")
        moves = p.get("Moves") or []
        mw = (card_w - 27) / 2
        for k, m in enumerate(moves[:4]):
            mx, my = tx + (k % 2) * mw, y + 16.5 + (k // 2) * 6.2
            pdf.set_fill_color(*_rgb(TYPE_COLORS.get(m.get("type"), "#AAAA99")))
            pdf.rect(mx, my + 1.2, 1.4, 4, style="F")
            pdf.set_xy(mx + 2.6, my)
            pdf.set_font("Helvetica", "", 8.5)
            pdf.set_text_color(*INK)
            pdf.cell(mw - 3, 6.4, _latin(m.get("name", "")))
        if col == 1 or i == len(members) - 1:
            pdf.set_xy(pdf.l_margin, y + card_h + 3)
        else:
            pdf.set_xy(pdf.l_margin, y)

    # Team Check, one marked line each
    heading("Team Check")
    for level, msg in checks:
        y = pdf.get_y()
        pdf.set_fill_color(*MARK_COLORS[level])
        pdf.ellipse(pdf.l_margin, y + 1.1, 3, 3, style="F")
        pdf.set_xy(pdf.l_margin + 6, y)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*INK)
        pdf.multi_cell(width - 6, 5, _latin(msg), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
    pdf.ln(1)

    # Threat Board summary: who answers each of the most used Pokemon
    if board_rows:
        heading(f"Against the {len(board_rows)} most used Pokémon")
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*INK)
        pdf.set_draw_color(*LINE)
        pdf.set_fill_color(255, 255, 255)   # unstriped rows take the current fill colour
        heads = FontFace(emphasis="BOLD", color=MUTED, fill_color=(240, 243, 248))
        unanswered = FontFace(color=MARK_COLORS["fix"], emphasis="BOLD")
        with pdf.table(col_widths=(52, 22, 108), line_height=4.6, padding=1, borders_layout="HORIZONTAL_LINES",
                       headings_style=heads, cell_fill_color=(248, 249, 252), cell_fill_mode="ROWS",
                       text_align=("LEFT", "RIGHT", "LEFT")) as table:
            head = table.row()
            for title in ("Threat", "On teams", "Answered by"):
                head.cell(title)
            for r in board_rows:
                row = table.row()
                row.cell(_latin(r["name"]))
                row.cell(f"{r['usage']:g}%")
                answers = ", ".join(r["answers"])
                row.cell(_latin(answers)) if answers else row.cell("Nobody on the team", style=unanswered)
        pdf.ln(1.5)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(width, 4, _latin("One on one against each threat's most common set. Switching, hazards and setup "
                                        "turns aren't simulated."))

    return bytes(pdf.output())

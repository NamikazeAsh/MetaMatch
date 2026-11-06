"""
Shared chunk shaping for the RAG index. Every chunk starts with one short header line naming the
Pokemon, the section and the source, so both the embedder and BM25 see what the passage is about
(the cheap, non LLM form of contextual retrieval). Bodies are split at sentence boundaries into
300 to 900 characters: short enough for bge small's 512 token window and for a prompt slot, long
enough to keep an argument together.
"""
import re

from bs4 import BeautifulSoup

MIN_CHARS, MAX_CHARS = 300, 900
TAIL_SLACK = 150  # a short last piece may stretch the previous chunk this far rather than stand alone


def header(pokemon, section, source):
    return f"Pokemon: {pokemon} | Section: {section} | Format: {source}\n"


def html_paragraphs(html):
    """Visible paragraphs and list items of an analysis HTML fragment."""
    soup = BeautifulSoup(html or "", "html.parser")
    paras = [el.get_text(" ", strip=True) for el in soup.find_all(["p", "li"])]
    paras = [p for p in paras if p]
    if not paras:
        text = soup.get_text(" ", strip=True)
        paras = [text] if text else []
    return paras


def split_paragraphs(paras, lo=MIN_CHARS, hi=MAX_CHARS):
    """Packs paragraphs into chunks of lo..hi characters, cutting only between sentences.
    A short tail joins the previous chunk instead of standing alone."""
    out, cur = [], ""
    for p in paras:
        for sentence in re.split(r"(?<=[.!?])\s+", p):
            if len(cur) + len(sentence) > hi and len(cur) >= lo:
                out.append(cur.strip())
                cur = ""
            cur += sentence + " "
        if len(cur) >= lo:
            out.append(cur.strip())
            cur = ""
    if cur.strip():
        if out and len(cur) < lo and len(out[-1]) + len(cur) <= hi + TAIL_SLACK:
            out[-1] += " " + cur.strip()
        else:
            out.append(cur.strip())
    return [c for c in out if len(c) >= 40]


def body(text):
    """A chunk's text without its header line, for prompts and source lists."""
    first, _, rest = text.partition("\n")
    return rest if first.startswith("Pokemon: ") and rest else text

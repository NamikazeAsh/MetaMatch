"""
Smogon technique and archetype guides (articles, The Smog, the beginner resources) as RAG chunks, for questions the
engine has no function for. Only the prose that explains how to think is kept: what an archetype or role is, how it
wins and loses, how to play each phase, how to build around it. Sample sets, sample teams and sections that list
Pokemon are dropped. Most of these were written for Gen 5 to 8, so every chunk carries its year and generation and a
note when it mentions mechanics the current games lack; the chat shows them as cited cards, never as engine facts.
The text is Smogon's and its authors': the cache (data/knowledge/guides/) is gitignored and never redistributed.
  python scripts/fetch_guides.py      # fills the cache politely (one request every few seconds, cached pages skipped)
Research and selection: docs/research/knowledge_sources_2026_11_15.md
"""
import re
import time
import urllib.request

from bs4 import BeautifulSoup

from metamatch import config
from metamatch.rag.chunking import header

CACHE_DIR = config.DATA_DIR / "knowledge" / "guides"
BASE = "https://www.smogon.com/"
USER_AGENT = "MetaMatch/0.1 (personal study tool; fetches a short list of Smogon guides once)"
DELAY = 3.0
# path under smogon.com -> (year written, generation it was written for)
GUIDES = {
    "articles/getting-started": (2021, 8),
    "articles/hyper-offense-smou": (2019, 7),
    "articles/hyper-offense-in-ou": (2015, 6),
    "articles/bulky-offense-sspu": (2021, 8),
    "articles/ou-stall-ages": (2019, 7),
    "articles/voltturn-in-ou": (2017, 7),
    "articles/pivots-sm-ou": (2018, 7),
    "articles/entry-hazards-ou-1": (2018, 7),
    "articles/entry-hazards-ou-2": (2019, 7),
    "articles/sm-ou-cores": (2019, 7),
    "articles/ou-setup-sweepers": (2017, 7),
    "articles/usm-ou-wallbreakers": (2018, 7),
    "articles/lures-in-ou": (2016, 6),
    "articles/trick-room-ou": (2018, 7),
    "articles/terrains-ou": (2018, 7),
    "articles/sandstorm-rages": (2016, 6),
    "articles/svou-tera-poison": (2024, 9),
    "articles/sv-ou-mixed-attackers": (2025, 9),
    "tiers/uu/uu201": (2012, 5),
    "resources/beginner/synergy": (2015, 6),
    "resources/beginner/bw_risk_reward": (2012, 5),
    "smog/issue1/introduction_to_prediction": (2009, 4),
    "smog/issue40/identifying-threats": (2014, 6),
    "smog/issue28/teambuilding": (2012, 5),
    "smog/issue20/control_luck": (2011, 5),
    "resources/archive/competitive/rs/long_term_thinking": (2005, 3),
}
OLD_MECHANICS = re.compile(r"\b(?:Mega(?:\s+Evol\w*|-?[A-Z]\w+)?|Z-?Moves?|Z-Crystal|\w+ium Z|Dynamax\w*|Max (?:Airstream|"
                           r"Quake|Knuckle|Steelspike|Overgrowth|Flare|Geyser)|Hidden Power|Pursuit|Hail|"
                           r"permanent (?:weather|rain|sun|sand))\b")
# Sections that are sets, sample teams or lists of Pokemon rather than reasoning
DROP_HEADING = re.compile(r"sample|example|users\b|notable|viable|honou?rable|mentions|credits|replays?|what pok|"
                          r"further reading|resources|links|\bteam ?\d|puzzle|answers|errata|contents", re.I)
# Set lines, and move slash lists ("- Fire Fang / Focus Punch / Brick Break")
SET_LINE = re.compile(r"\bEVs:|\bAbility:|\bIVs:|@ [A-Z][\w' -]+ (?:Ability|EVs)|^- |^[\w' -]+(?: / [\w' -]+){2,}$")
CREDIT = re.compile(r"^(?:Art|HTML|Written|Grammar|Edited|Article|Banner)\b.*\bby\b", re.I)
WORDS_PER_CHUNK = 220


def _about_one_pokemon(text):
    """A paragraph that opens with a Pokemon's name ("Landorus-T is another common user of Defog...") is a write up
    of that Pokemon's old set, not reasoning that carries over to the current game."""
    from metamatch.engine.names import find_pokemon_spans
    spans = find_pokemon_spans(text[:40])
    return bool(spans) and spans[0][0] == 0


def _file(path):
    return CACHE_DIR / (path.replace("/", "__") + ".html")


def fetch_all(paths=None, force=False):
    """Caches each guide page once; returns how many were fetched now."""
    import ssl
    import certifi
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Python's bundled roots can lag behind; certifi's are current (verification stays on)
    context = ssl.create_default_context(cafile=certifi.where())
    fetched = 0
    for path in paths or GUIDES:
        out = _file(path)
        if out.exists() and not force:
            continue
        req = urllib.request.Request(BASE + path, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=60, context=context) as r:
                out.write_bytes(r.read())
            fetched += 1
            print(f"{path}: saved")
        except Exception as e:
            print(f"{path}: failed ({e})")
        time.sleep(DELAY)
    return fetched


def sections(html):
    """(title, [(section heading, [paragraphs])]) of one guide page, with sets, credits and list sections removed."""
    soup = BeautifulSoup(html, "html.parser")
    for bad in soup.select("table#articlehead, table#articlefoot, div.author, script, style, img"):
        bad.decompose()
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else ""
    layout = {id(t) for t in h1.find_parents("table")} if h1 else set()
    out, h2, h3, paras = [], "Introduction", "", []

    def close():
        name = f"{h2}: {h3}" if h3 else h2
        # A subsection is judged by its own heading: "Hazard Control and Users: Defog" is about Defog
        if paras and not DROP_HEADING.search(h3 or h2):
            out.append((name, list(paras)))
        paras.clear()

    for el in (h1.find_all_next(["h2", "h3", "p", "li"]) if h1 else []):
        if el.name in ("h2", "h3"):
            close()
            text = el.get_text(" ", strip=True)
            if el.name == "h2":
                h2, h3 = text, ""
            else:
                h3 = text
            continue
        if el.name == "p" and el.find_parent("li"):
            continue
        text = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
        if len(text.split()) < 8 or SET_LINE.search(text) or CREDIT.search(text) or _about_one_pokemon(text):
            continue
        # Tables inside the content are sample teams or stat grids; older pages wrap the whole layout in one
        if any(id(t) not in layout for t in el.find_parents("table")):
            continue
        paras.append(text)
    close()
    return title, out


def _windows(paras, size=WORDS_PER_CHUNK):
    """Paragraphs joined into chunks of about `size` words, never splitting a paragraph."""
    out, cur, n = [], [], 0
    for p in paras:
        w = len(p.split())
        if cur and n + w > size:
            out.append(" ".join(cur))
            cur, n = [], 0
        cur.append(p)
        n += w
    if cur:
        out.append(" ".join(cur))
    return out


def label(meta):
    """'VoltTurn in OU (Smogon, 2017, written for Gen 7)' for a guide chunk's card."""
    return f"{meta['title']} (Smogon, {meta['year']}, written for Gen {meta['gen']})"


def build_chunks():
    """Chunks for every cached guide. Each carries title, section, url, year, generation and an old mechanics note."""
    chunks = []
    for path, (year, gen) in GUIDES.items():
        f = _file(path)
        if not f.exists():
            continue
        title, secs = sections(f.read_text(encoding="utf-8", errors="replace"))
        for name, paras in secs:
            for i, text in enumerate(_windows(paras)):
                old = OLD_MECHANICS.search(text)
                meta = {"pokemon": "Guide", "type": "guide", "title": title, "section": name, "source": "smogon_guide",
                        "url": BASE + path, "year": year, "gen": gen, "game": "any", "play": "singles", "format": "any",
                        "old_mechanics": old.group(0) if old and gen < 9 else ""}
                chunks.append({"pokemon": "Guide", "text": header("Guide", f"{title}: {name}", "Smogon guide") + text,
                               "metadata": meta})
    print(f"Loaded {len(chunks)} guide chunks.")
    return chunks

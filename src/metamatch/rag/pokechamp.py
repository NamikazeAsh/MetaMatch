import re
import sys
import json
import time
import hashlib
import requests
from bs4 import BeautifulSoup
from pathlib import Path

# Add 'src' directory to path so "import metamatch" works
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(SRC_DIR))

from metamatch import config

# Unofficial Champions community guides. Stored reworded (never verbatim) and tagged
# so retrieval only serves them to Champions teams, with doubles advice kept apart.
SITEMAP_URL = "https://www.pokechamp.io/sitemap.xml"
CACHE_FILE = config.DATA_DIR / "knowledge" / "pokechamp_guides.json"
HEADERS = {"User-Agent": "MetaMatch/1.0 (personal RAG index)"}
REQUEST_DELAY = 1.0  # seconds between page fetches
LLM_RETRIES = 3

# Sections from the "Claims Behind/From ..." heading on are generic claims about unrelated
# Pokemon, takeaways and related links, so parsing stops there
# Headings are worded differently per guide ("Claims From ...", "Guide Claims, Distilled")
STOP_HEADING = re.compile(r"\bclaims\b|\btakeaways\b|^related |^quick links", re.I)
# UI labels and boilerplate lines that carry no strategy content
BOILERPLATE = {"tip", "pros", "cons", "pokemon", "pros & cons", "structured statements for faster conclusion reading."}

DOUBLES_KEYWORDS = [
    "doubles", "vgc", "redirection", "follow me", "rage powder", "spread move",
    "spread attack", "helping hand", "wide guard", "both foes", "both opponents",
]


def is_doubles(sentence):
    s = sentence.lower()
    return any(kw in s for kw in DOUBLES_KEYWORDS)


def clean_text(text):
    """The site serves some characters as U+FFFD (é, apostrophes, dashes); repair the common ones."""
    text = text.replace("Pok\ufffdmon", "Pokemon")
    text = re.sub("\ufffd(?=(?:s|t|re|ll|ve)\\b)", "'", text)
    return text.replace("\ufffd", " ")


def split_sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]


def fetch_guide_urls():
    res = requests.get(SITEMAP_URL, headers=HEADERS, timeout=15)
    res.raise_for_status()
    urls = re.findall(r'<loc>(.*?)</loc>', res.text)
    return [u for u in urls if "/guides/" in u and not u.rstrip("/").endswith(("/search", "/category"))]


def known_species():
    try:
        with open(config.JSON_DIR / "topPoke.json", "r") as f:
            return [n for n in json.load(f) if "-Mega" not in n]
    except Exception:
        return []


def guide_subject(title, species=None):
    """
    'Mega Absol High-Risk Sweeper Lines...' -> 'Absol-Mega', 'Mega Charizard X ...' -> 'Charizard-Mega-X'
    (Smogon naming). Falls back to the longest known species named in the title, else 'General'.
    """
    species = known_species() if species is None else species
    named = [s for s in species if re.search(rf"\b{re.escape(s)}\b", title)]
    if not named:
        return "General"
    base = max(named, key=len)
    m = re.search(rf"\bMega {re.escape(base)}(?: ([XYZ])\b)?", title)
    if m:
        return f"{base}-Mega" + (f"-{m.group(1)}" if m.group(1) else "")
    return base


def parse_guide(html):
    """
    Splits a guide page into {"title", "pokemon", "sections": [{"heading", "singles", "doubles"}]}.
    Sentences mentioning doubles mechanics go to "doubles", the rest to "singles".
    """
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.body
    h1 = main.find("h1")
    title = clean_text(h1.get_text(" ", strip=True)) if h1 else ""

    sections = []
    current = None
    for el in main.find_all(["h2", "h3", "p", "li"]):
        text = clean_text(el.get_text(" ", strip=True))
        if not text:
            continue
        if el.name in ("h2", "h3"):
            if STOP_HEADING.search(text):
                break
            current = {"heading": text, "singles": [], "doubles": []}
            sections.append(current)
            continue
        # Skip breadcrumbs/intro before the first heading, labels, and Pokemon slug cards
        if current is None or text.lower() in BOILERPLATE or len(text) < 25:
            continue
        for sentence in split_sentences(text):
            current["doubles" if is_doubles(sentence) else "singles"].append(sentence)

    sections = [s for s in sections if s["singles"] or s["doubles"]]
    return {"title": title, "pokemon": guide_subject(title), "sections": sections}


REWRITE_PROMPT = """Rewrite these Pokemon Champions guide notes as short bullet points in your own words.
Rules:
- Do NOT copy sentences. Paraphrase tersely, one fact or tip per bullet.
- Do NOT add any information that is not in the notes.
- Keep Pokemon, move, item and ability names exactly as written.
- Drop filler and motivational phrasing.
- Output only lines starting with "- ".

Notes:
{notes}"""


def reword(client, model, sentences):
    """Paraphrases a list of sentences into terse bullets with the local LLM."""
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": REWRITE_PROMPT.format(notes="\n".join(sentences))}],
        temperature=0.0,
        stream=False,
    )
    text = completion.choices[0].message.content or ""
    return [line[2:].strip() for line in text.splitlines() if line.startswith("- ") and len(line) > 4]


def section_key(url, heading, play):
    return hashlib.sha1(f"{url}|{heading}|{play}".encode("utf-8")).hexdigest()[:16]


def load_cache():
    if CACHE_FILE.exists():
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def update_guides(limit=None):
    """
    Fetches every guide, rewords each section with the local LLM, and caches the result.
    Already reworded sections are skipped, so this can be re-run after an interruption.
    """
    from metamatch.agents.client import get_agent_client
    client, model = get_agent_client()

    cache = load_cache()
    urls = fetch_guide_urls()[:limit]
    print(f"Found {len(urls)} Pokechamp guides. Rewording with {model}...")

    for i, url in enumerate(urls, 1):
        try:
            res = requests.get(url, headers=HEADERS, timeout=20)
            res.raise_for_status()
        except requests.RequestException as e:
            print(f"  [{i}/{len(urls)}] fetch failed: {e}")
            continue
        guide = parse_guide(res.text)
        print(f"  [{i}/{len(urls)}] {guide['title'][:70]}")

        for section in guide["sections"]:
            for play in ("singles", "doubles"):
                sentences = section[play]
                key = section_key(url, section["heading"], play)
                if not sentences or key in cache:
                    continue
                bullets = None
                for attempt in range(1, LLM_RETRIES + 1):
                    try:
                        bullets = reword(client, model, sentences)
                        break
                    except Exception as e:
                        print(f"    LLM error ({e}), attempt {attempt}/{LLM_RETRIES}")
                        time.sleep(5 * attempt)
                if bullets is None:
                    print("    LLM unavailable. Start Ollama and re-run; progress is saved.")
                    save_cache(cache)
                    return cache
                if bullets:
                    cache[key] = {
                        "url": url, "title": guide["title"], "pokemon": guide["pokemon"],
                        "heading": section["heading"], "play": play, "bullets": bullets,
                    }
        save_cache(cache)
        time.sleep(REQUEST_DELAY)

    print(f"Cached {len(cache)} reworded sections to {CACHE_FILE}")
    return cache


def build_chunks():
    """Turns the reworded cache into RAG chunks. Never touches the network or the LLM."""
    chunks = []
    for entry in load_cache().values():
        label = "DOUBLES ONLY" if entry["play"] == "doubles" else "Champions singles"
        text = (
            f"UNOFFICIAL COMMUNITY GUIDE ({label}): {entry['pokemon']}. "
            f"[{entry['heading']}] " + " ".join(entry["bullets"])
        )
        chunks.append({
            "pokemon": entry["pokemon"],
            "category": "Community Guide",
            "text": text,
            "metadata": {
                "pokemon": entry["pokemon"], "type": "community_guide", "source": "pokechamp",
                "game": "champions", "play": entry["play"], "title": entry["heading"],
            },
        })
    return chunks


if __name__ == "__main__":
    update_guides(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)

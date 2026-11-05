"""
Captures every screenshot in showcase/ from the running app, so the visual tour can be
regenerated whenever the UI changes. Everything shown is real: real ladder data, real engine
verdicts and real answers from the local model. Nothing is mocked or edited.

The app runs against a throwaway user store (METAMATCH_USER_DIR), so no personal saved teams or
history ever appear. Demo teams are built from this month's most common ladder sets.

Needs (dev only, not in requirements.txt): playwright + `playwright install chromium`, Pillow, and Ollama with the coach model pulled for the chat and guide shots (it is started if it isn't running;
set OLLAMA_MODELS if your models live outside the default folder).

Usage:
  python scripts/capture_showcase.py                     # everything
  python scripts/capture_showcase.py --only home,chat    # some sections: home, dashboard, chat, tools, extras
  python scripts/capture_showcase.py --no-llm            # skip shots that need the local model
"""
import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SHOW = ROOT / "showcase"
IMG = SHOW / "images"
PORT, OFFLINE_PORT = 8620, 8621
URL = f"http://localhost:{PORT}"
SIZE_LIMIT_MB = 20
REPLAY_ID = "gen9ou-2704070726"
SECTIONS = ["home", "dashboard", "chat", "tools", "extras"]

sys.path.insert(0, str(ROOT / "src"))


# --- Data and processes --------------------------------------------------------

def sample_team():
    """The app's built in OU sample team, read from app.py without importing (and so running) the app."""
    src = (ROOT / "src" / "metamatch" / "app.py").read_text(encoding="utf-8")
    return re.search(r'SAMPLE_TEAM = """(.*?)"""', src, re.S).group(1)


def ladder_team(names, format_id):
    """A Showdown export of each Pokemon's most common ladder set this month."""
    from metamatch import config
    from metamatch.engine.sets import likely_set
    labels = {"hp": "HP", "atk": "Atk", "def": "Def", "spa": "SpA", "spd": "SpD", "spe": "Spe"}
    blocks = []
    for name in names:
        s = likely_set(name, format_id)
        head = f"{name} @ {s['item']}" if s.get("item") else name
        lines = [head, f"Ability: {s['ability']}"]
        if s.get("tera") and config.format_game(format_id) != "champions":
            lines.append(f"Tera Type: {s['tera'][0]}")
        evs = " / ".join(f"{v} {labels[k]}" for k, v in s["evs"].items() if v)
        lines += [f"EVs: {evs}", f"{s['nature']} Nature"] + [f"- {m}" for m, _ in s["moves"]]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def seed_store(user_dir):
    """Recent and saved demo teams for the sidebar shots, in the throwaway store."""
    os.environ["METAMATCH_USER_DIR"] = str(user_dir)
    from metamatch import storage
    storage.DB_PATH = Path(user_dir) / "metamatch.db"
    storage.LEGACY_JSON = Path(user_dir) / "default.json"
    storage.save_team("Champions Core", ladder_team(
        ["Samurott-Hisui", "Corviknight", "Garchomp", "Slowking-Galar", "Glimmora", "Hatterene"], "gen9championsou"),
        "gen9championsou")
    storage.remember_team(ladder_team(
        ["Great Tusk", "Raging Bolt", "Ogerpon-Wellspring", "Dragonite", "Iron Valiant", "Samurott-Hisui"], "gen9ou"), "gen9ou")


def wait_http(url, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except Exception:
            time.sleep(1)
    return False


def start_app(port, user_dir, extra_env=None):
    env = dict(os.environ, METAMATCH_USER_DIR=str(user_dir), **(extra_env or {}))
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "src/metamatch/app.py", "--server.headless", "true",
                             "--server.port", str(port)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not wait_http(f"http://localhost:{port}/_stcore/health"):
        proc.kill()
        raise SystemExit(f"App didn't start on port {port}")
    return proc


def ensure_ollama():
    """True if the local model server is up, starting it if needed."""
    if wait_http("http://localhost:11434/api/tags", timeout=2):
        return None, True
    exe = shutil.which("ollama")
    if not exe:
        return None, False
    proc = subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc, wait_http("http://localhost:11434/api/tags", timeout=30)


# --- Browser helpers ------------------------------------------------------------

def idle(page, timeout=240):
    """Waits until Streamlit has finished running the script (the status widget disappears)."""
    page.wait_for_timeout(500)
    end = time.time() + timeout
    while time.time() < end:
        if not page.locator('[data-testid="stStatusWidget"]').count():
            page.wait_for_timeout(400)
            if not page.locator('[data-testid="stStatusWidget"]').count():
                return
        page.wait_for_timeout(250)
    raise TimeoutError("App kept running")


def check(page, where):
    errors = [e.inner_text()[:300] for e in page.locator('[data-testid="stException"]').all()]
    if errors:
        raise SystemExit(f"Exception on {where}: {errors[0]}")


FRAME_W, FRAME_H = 1920, 1080   # every still is 16:9 at this size
VIEW = {"width": 1600, "height": 900}
SCALE = FRAME_W / VIEW["width"]   # 1.2: a 1600x900 viewport renders straight to 1920x1080
BG = (15, 18, 25)


def save(im, name):
    """A PIL image -> showcase/images/<name>.webp, always exactly 1920x1080."""
    im = im.convert("RGB")
    if im.size != (FRAME_W, FRAME_H):
        im = im.resize((FRAME_W, FRAME_H), Image.LANCZOS)
    path = IMG / f"{name}.webp"
    im.save(path, "WEBP", quality=85, method=6)
    print(f"  {path.relative_to(ROOT)}  {im.width}x{im.height}  {path.stat().st_size // 1024} KB")
    return path


def new_page(b):
    return b.new_page(viewport=VIEW, device_scale_factor=SCALE)


def scroll_to(page, target, offset=80):
    """Scrolls the app so `target` (selector or locator) sits just under the sticky navbar."""
    loc = page.locator(target).first if isinstance(target, str) else target
    loc.evaluate("(el, off) => { const s = el.closest('[data-testid=stMain]') || document.scrollingElement;"
                 " const r = el.getBoundingClientRect(); const top = s.getBoundingClientRect ? s.getBoundingClientRect().top : 0;"
                 " s.scrollBy(0, r.top - top - off); }", offset)
    page.wait_for_timeout(500)


def frame(page, name, target=None, offset=80):
    """A 16:9 frame of the app as a viewer sees it, optionally scrolled to `target` first."""
    if target is not None:
        scroll_to(page, target, offset)
    return save(Image.open(io.BytesIO(page.screenshot())), name)


def collapse_sidebar(page):
    """Hides the sidebar so content frames show the content, not the same recent teams every time."""
    if not page.locator('[data-testid="stSidebar"][aria-expanded="true"]').count():
        return
    page.locator('[data-testid="stSidebarHeader"]').first.hover()
    page.locator('[data-testid="stSidebarCollapseButton"] button').first.click()
    page.wait_for_timeout(900)


def open_sample(page):
    page.goto(URL)
    page.wait_for_selector(".mp-card", timeout=120000)
    idle(page)
    page.get_by_role("button", name="Try a sample team").click()
    page.wait_for_selector("text=Team Dashboard", timeout=120000)
    idle(page)


def tab(page, name):
    """Opens a dashboard tab and waits for its panel to have real content (charts render a beat later)."""
    page.get_by_role("tab", name=name, exact=True).click()
    idle(page)
    panel = page.locator('[role="tabpanel"]:visible').first
    end = time.time() + 15
    while time.time() < end and (panel.bounding_box() or {"height": 0})["height"] < 300:
        page.wait_for_timeout(300)
    page.wait_for_timeout(800)
    return panel


def send(page, question, typed=False):
    """Sends a chat question and waits for the reply bubble to finish; returns (question, reply) locators."""
    msgs = page.locator('[data-testid="stChatMessage"]')
    before = msgs.count()
    box = page.locator('[data-testid="stChatInput"] textarea')
    if typed:
        box.press_sequentially(question, delay=45)
    else:
        box.fill(question)
    box.press("Enter")
    end = time.time() + 300
    while time.time() < end and msgs.count() < before + 2:
        page.wait_for_timeout(300)
    # Done when the streaming cursor is gone and the text has stopped changing for a moment
    reply, last, steady = msgs.nth(before + 1), None, 0
    while time.time() < end and steady < 4:
        text = reply.inner_text()
        steady = steady + 1 if text == last and "▌" not in text else 0
        last = text
        page.wait_for_timeout(400)
    idle(page, timeout=300)
    page.wait_for_timeout(400)
    return msgs.nth(before), reply


def ask(page, question, tries=3):
    """Asks the coach; retries (fresh question each time) until the reply passed the fact check."""
    for attempt in range(1, tries + 1):
        q, reply = send(page, question)
        text = reply.inner_text()
        if "didn't pass the fact check" not in text and "offline" not in text.lower():
            print(f"  '{question}' answered on attempt {attempt}")
            return q, reply
    print(f"  '{question}': no verified reply after {tries} tries, keeping the last one")
    return q, reply


# --- Sections -------------------------------------------------------------------

def wait_home(page, url=None):
    page.goto(url or URL)
    page.wait_for_selector(".mp-stories", timeout=120000)
    idle(page)
    page.wait_for_timeout(1500)  # sprites from the CDN


def capture_home(b):
    page = new_page(b)
    wait_home(page)
    check(page, "home")
    frame(page, "home")
    frame(page, "metaflash", ".mp-head", offset=70)
    frame(page, "metaflash_stories", ".mp-stories", offset=200)
    # A partner hover card, in context on its story card
    scroll_to(page, ".mp-stories", offset=330)
    page.locator(".mp-stories .mp-card:nth-child(2) .mp-mate-wrap").first.hover()
    page.wait_for_timeout(400)
    frame(page, "metaflash_hover")
    page.mouse.move(5, 5)
    page.locator("[data-testid=stButtonGroup] button", has_text="Champions OU").click()
    idle(page)
    page.wait_for_timeout(1500)
    frame(page, "metaflash_champions", ".mp-head", offset=70)
    # Back to OU: the pick is remembered, and later shots should open on OU
    page.locator("[data-testid=stButtonGroup] button", has_text="OU").first.click()
    idle(page)
    page.close()


def capture_dashboard(b, llm):
    page = new_page(b)
    open_sample(page)
    check(page, "dashboard")
    frame(page, "dashboard")
    frame(page, "squad", "text=Your Squad", offset=90)
    collapse_sidebar(page)
    for name, slug in [("Team Overview", "tab_overview"), ("Audit", "tab_audit"), ("Meta Threats", "tab_threats"),
                       ("Recommendations", "tab_recommendations"), ("Matchup Matrices", "tab_matrices"),
                       ("Speed Tiers", "tab_speed")]:
        tab(page, name)
        page.wait_for_timeout(800)
        check(page, name)
        frame(page, slug, 'text=Detailed Analysis', offset=85)
    if llm:
        tab(page, "Coach Guide")
        page.get_by_role("button", name="Write my pilot guide").click()
        page.wait_for_selector("text=Team Pilot Guide", timeout=300000)
        idle(page)
        frame(page, "tab_guide", 'text=Detailed Analysis', offset=85)
    page.close()


def capture_chat(b):
    """One clean conversation per shot: the team's saved chat is cleared and the page reloaded first."""
    from metamatch import storage
    page = new_page(b)
    open_sample(page)
    team_url = page.url
    tid = re.search(r"[?&]t=([0-9a-f]+)", team_url).group(1)
    for question, slug in [("Does my Great Tusk outspeed Iron Valiant?", "chat_clemont"),
                           ("How do I beat Raging Bolt?", "chat_oak"),
                           ("What item does Kingambit usually run?", "chat_brock"),
                           ("Does it outspeed my Dragapult?", "chat_clarify")]:
        storage.clear_chat(tid)
        page.goto(team_url)
        page.wait_for_selector("text=Team Dashboard", timeout=120000)
        idle(page)
        collapse_sidebar(page)
        tab(page, "Coach Chat")
        q, _ = ask(page, question)
        check(page, slug)
        frame(page, slug, "text=Ask the Coach", offset=85)
    page.close()


def pick(page, values):
    """Types each value into the page's first multiselect and confirms it."""
    for value in values:
        box = page.locator('[data-testid="stMultiSelect"] input').first
        box.click()
        box.fill(value)
        page.keyboard.press("Enter")
        idle(page)
    page.keyboard.press("Escape")
    page.wait_for_timeout(800)


def capture_tools(b):
    page = new_page(b)
    page.goto(URL + "/quick-match")
    idle(page)
    pick(page, ["Great Tusk", "Kingambit"])
    page.wait_for_timeout(1500)
    check(page, "quick match")
    frame(page, "quick_match", "h2", offset=80)

    page.goto(URL + "/move-search")
    idle(page)
    pick(page, ["Knock Off", "U-turn"])
    page.get_by_role("button", name="Find Sets").click()
    idle(page)
    page.wait_for_timeout(1000)
    check(page, "move search")
    frame(page, "move_search", "h2", offset=80)

    page.goto(URL + f"/replay-auditor?id={REPLAY_ID}")
    page.wait_for_selector("text=Team Health", timeout=120000)
    idle(page)
    page.wait_for_timeout(1500)
    check(page, "replay")
    frame(page, "replay_auditor", "h2", offset=80)
    frame(page, "replay_details", "text=Mistakes", offset=90)
    page.close()


def capture_extras(b, user_dir):
    # Sidebar memory: recent teams and a saved team's set cards
    page = new_page(b)
    wait_home(page)
    page.locator('[data-testid="stSidebar"] [data-testid="stSelectbox"]').first.click()
    page.get_by_role("option", name="Champions Core").click()
    idle(page)
    page.wait_for_timeout(1200)
    page.locator('[data-testid="stSidebar"] .mm-sprite').nth(1).hover()
    page.wait_for_timeout(400)
    frame(page, "sidebar")
    page.close()

    # Offline mode: a second app whose model server can't be reached
    offline = start_app(OFFLINE_PORT, user_dir, {"OLLAMA_HOST": "http://127.0.0.1:9"})
    try:
        page = new_page(b)
        wait_home(page, f"http://localhost:{OFFLINE_PORT}")
        page.get_by_role("button", name="Try a sample team").click()
        page.wait_for_selector("text=Team Dashboard", timeout=120000)
        idle(page)
        # Same store as the chat shots: start from an empty conversation
        from metamatch import storage
        storage.clear_chat(re.search(r"[?&]t=([0-9a-f]+)", page.url).group(1))
        page.reload()
        page.wait_for_selector("text=Team Dashboard", timeout=120000)
        idle(page)
        collapse_sidebar(page)
        tab(page, "Coach Chat")
        q, _ = send(page, "What are my biggest threats?")
        frame(page, "offline_mode", q, offset=90)
        page.close()
    finally:
        offline.kill()

    # Phone trio on a 16:9 canvas: home, MetaFlash, dashboard
    phone = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    shots = []
    wait_home(phone)
    shots.append(phone.screenshot())
    scroll_to(phone, ".mp-head", offset=75)
    shots.append(phone.screenshot())
    phone.get_by_role("button", name="Try a sample team").click()
    phone.wait_for_selector("text=Team Dashboard", timeout=120000)
    idle(phone)
    phone.wait_for_timeout(1000)
    shots.append(phone.screenshot())
    phone.close()
    ims = [Image.open(io.BytesIO(s)).convert("RGB") for s in shots]
    h = 980
    ims = [im.resize((round(im.width * h / im.height), h), Image.LANCZOS) for im in ims]
    gap = 60
    total = sum(im.width for im in ims) + gap * (len(ims) - 1)
    canvas = Image.new("RGB", (FRAME_W, FRAME_H), BG)
    x = (FRAME_W - total) // 2
    for im in ims:
        canvas.paste(im, (x, (FRAME_H - h) // 2))
        x += im.width + gap
    save(canvas, "phone")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma separated sections: " + ", ".join(SECTIONS))
    parser.add_argument("--no-llm", action="store_true", help="skip shots that need the local model")
    args = parser.parse_args()
    wanted = set(args.only.split(",")) if args.only else set(SECTIONS)
    IMG.mkdir(parents=True, exist_ok=True)

    ollama, llm = (None, False) if args.no_llm else ensure_ollama()
    if not args.no_llm and not llm:
        print("Ollama isn't reachable: skipping the model shots (run with --no-llm to silence this)")
    user_dir = Path(tempfile.mkdtemp(prefix="metamatch_showcase_"))
    seed_store(user_dir)
    app = start_app(PORT, user_dir)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            for section in SECTIONS:
                if section not in wanted:
                    continue
                print(f"[{section}]")
                if section == "home":
                    capture_home(b)
                elif section == "dashboard":
                    capture_dashboard(b, llm)
                elif section == "chat" and llm:
                    capture_chat(b)
                elif section == "tools":
                    capture_tools(b)
                elif section == "extras":
                    capture_extras(b, user_dir)
            b.close()
    finally:
        app.kill()
        if ollama:
            ollama.kill()
        shutil.rmtree(user_dir, ignore_errors=True)

    total = sum(f.stat().st_size for f in SHOW.rglob("*") if f.is_file()) / 1e6
    print(f"showcase/ is {total:.1f} MB")
    if total > SIZE_LIMIT_MB:
        raise SystemExit(f"showcase/ is over the {SIZE_LIMIT_MB} MB budget")


if __name__ == "__main__":
    main()

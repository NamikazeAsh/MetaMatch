"""
Local persistence in one SQLite file (data/user/metamatch.db, gitignored).

* teams: every analysed paste, keyed by a short hash of format + paste. A team with a name is a
  saved team; any team is a recent team. Only the paste is stored, never the analysis: reopening
  a team re-runs the engine (about a second), so it always reflects current code and stats.
* chats: coach conversation per team.
* prefs: small key/value settings such as the last format.

SQLite instead of JSON files because writes are atomic (a crash or two tabs saving at once can't
truncate the file and lose every saved team, which the old read, modify, write JSON could) and
because recent teams, pruning and chats are one query each.
"""
import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from metamatch import config
from metamatch.utils import extract_pokemon_names

DB_PATH = config.USER_DIR / "metamatch.db"
LEGACY_JSON = config.USER_DIR / "default.json"
KEEP_RECENT = 20

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id         TEXT PRIMARY KEY,
    raw_text   TEXT NOT NULL,
    format     TEXT NOT NULL,
    name       TEXT UNIQUE,
    created_at TEXT NOT NULL,
    opened_at  TEXT NOT NULL,
    opened_seq INTEGER NOT NULL DEFAULT 0,
    saved_at   TEXT
);
CREATE INDEX IF NOT EXISTS teams_opened ON teams(opened_seq);
CREATE TABLE IF NOT EXISTS chats (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id    TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    name       TEXT,
    avatar     TEXT,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chats_team ON chats(team_id, id);
CREATE TABLE IF NOT EXISTS prefs (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_ready = set()
_init_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@contextmanager
def _db():
    """A short lived connection per call: safe across Streamlit's threads, committed on success."""
    path = DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    # Autocommit mode with explicit BEGIN IMMEDIATE: a writer takes the lock up front and others wait
    # (timeout) instead of failing with "database is locked" when upgrading a read lock mid transaction
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        if str(path) not in _ready:
            with _init_lock:
                if str(path) not in _ready:
                    conn.execute("PRAGMA journal_mode = WAL")  # readers never block the writer, two tabs are fine
                    conn.executescript(SCHEMA)
                    conn.execute("BEGIN IMMEDIATE")
                    migrated = _migrate_legacy_json(conn)
                    conn.execute("COMMIT")
                    if migrated:  # only once the import is committed
                        LEGACY_JSON.replace(LEGACY_JSON.with_name(LEGACY_JSON.name + ".bak"))
                    _ready.add(str(path))
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def normalise(raw_text):
    """Paste text with line endings and trailing spaces evened out, so the same team gets the same id."""
    lines = (raw_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()


def team_id(raw_text, format_id):
    return hashlib.sha1(f"{format_id}\n{normalise(raw_text)}".encode("utf-8")).hexdigest()[:10]


def _row(r):
    if r is None:
        return None
    d = dict(r)
    d["pokemon_names"] = extract_pokemon_names(d["raw_text"])
    d["updated_at"] = d.get("saved_at") or d.get("opened_at")
    return d


# --- Teams -----------------------------------------------------------------

def remember_team(raw_text, format_id):
    """Records an analysed team (or bumps it to most recent) and returns its id."""
    text = normalise(raw_text)
    tid = team_id(text, format_id)
    now = _now()
    with _db() as c:
        # opened_seq orders recent teams: Windows clock ticks are too coarse for timestamps to break ties
        seq = c.execute("SELECT COALESCE(MAX(opened_seq), 0) + 1 FROM teams").fetchone()[0]
        c.execute("INSERT INTO teams (id, raw_text, format, created_at, opened_at, opened_seq) VALUES (?, ?, ?, ?, ?, ?) "
                  "ON CONFLICT(id) DO UPDATE SET opened_at = excluded.opened_at, opened_seq = excluded.opened_seq",
                  (tid, text, format_id, now, now, seq))
        # Unnamed teams beyond the newest KEEP_RECENT are dropped; saved teams are never pruned
        c.execute("DELETE FROM teams WHERE name IS NULL AND id NOT IN "
                  "(SELECT id FROM teams WHERE name IS NULL ORDER BY opened_seq DESC LIMIT ?)", (KEEP_RECENT,))
    return tid


def get_team(tid):
    """{id, raw_text, format, name, pokemon_names, ...} or None."""
    with _db() as c:
        return _row(c.execute("SELECT * FROM teams WHERE id = ?", (tid,)).fetchone())


def recent_teams(limit=5):
    with _db() as c:
        return [_row(r) for r in c.execute("SELECT * FROM teams ORDER BY opened_seq DESC LIMIT ?", (limit,))]


def save_team(name, raw_text, format_id):
    """Names a team so it shows under Saved teams. Reusing a name moves it to this team. Returns the id."""
    tid = remember_team(raw_text, format_id)
    with _db() as c:
        c.execute("UPDATE teams SET name = NULL, saved_at = NULL WHERE name = ? AND id != ?", (name, tid))
        c.execute("UPDATE teams SET name = ?, saved_at = ? WHERE id = ?", (name, _now(), tid))
    return tid


def list_teams_detailed():
    """Saved teams, newest first."""
    with _db() as c:
        return [_row(r) for r in c.execute("SELECT * FROM teams WHERE name IS NOT NULL ORDER BY saved_at DESC, opened_seq DESC")]


def delete_team(name):
    """Removes a team from Saved teams (it stays in recent history until pruned). True if it existed."""
    with _db() as c:
        cur = c.execute("UPDATE teams SET name = NULL, saved_at = NULL WHERE name = ?", (name,))
        return cur.rowcount > 0


# --- Chats -----------------------------------------------------------------

def chat_messages(tid):
    with _db() as c:
        rows = c.execute("SELECT * FROM chats WHERE team_id = ? ORDER BY id", (tid,)).fetchall()
    # Same shape the chat tab builds live: user messages have no name or avatar keys at all
    return [{k: r[k] for k in ("role", "name", "avatar", "content") if r[k] is not None} for r in rows]


def add_chat_message(tid, role, content, name=None, avatar=None):
    with _db() as c:
        if c.execute("SELECT 1 FROM teams WHERE id = ?", (tid,)).fetchone():
            c.execute("INSERT INTO chats (team_id, role, name, avatar, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                      (tid, role, name, avatar, content, _now()))


def clear_chat(tid):
    with _db() as c:
        c.execute("DELETE FROM chats WHERE team_id = ?", (tid,))


# --- Prefs -----------------------------------------------------------------

def get_pref(key, default=None):
    with _db() as c:
        r = c.execute("SELECT value FROM prefs WHERE key = ?", (key,)).fetchone()
    return json.loads(r["value"]) if r else default


def set_pref(key, value):
    with _db() as c:
        c.execute("INSERT INTO prefs (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                  (key, json.dumps(value)))


# --- One time import of the old JSON store -----------------------------------

def _migrate_legacy_json(conn):
    """Imports data/user/default.json saved teams; True if the caller should rename the file once committed."""
    if not LEGACY_JSON.exists():
        return False
    try:
        with open(LEGACY_JSON, encoding="utf-8") as f:
            teams = (json.load(f) or {}).get("teams", {})
    except (OSError, json.JSONDecodeError):
        return False  # leave an unreadable file alone rather than risk losing it
    for name, t in teams.items():
        raw = normalise(t.get("raw_text", ""))
        if not raw:
            continue
        fmt = config.team_format(((t.get("analysis") or {}).get("team")) or {})
        tid = team_id(raw, fmt)
        when = t.get("updated_at") or _now()
        conn.execute("INSERT OR IGNORE INTO teams (id, raw_text, format, created_at, opened_at) VALUES (?, ?, ?, ?, ?)",
                     (tid, raw, fmt, when, when))
        conn.execute("UPDATE teams SET name = NULL, saved_at = NULL WHERE name = ? AND id != ?", (name, tid))
        conn.execute("UPDATE teams SET name = ?, saved_at = ? WHERE id = ?", (name, when, tid))
    return True

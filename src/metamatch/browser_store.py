"""
Saved teams, chats and prefs kept in the visitor's own browser (localStorage) on a shared deployment.

On Streamlit Cloud (METAMATCH_LOCAL_MODE=0) there is one server for every visitor, and its disk is wiped whenever
the app sleeps or redeploys, so the SQLite store in storage.py can't be used: visitors would share it and lose it.
Instead each browser keeps its own copy under one localStorage key, private to that device:
  * an invisible component (mount(), once per run, after the page has drawn) reads the browser's copy once per
    visit and hands it to Python, then writes the copy back whenever Python changed it
  * Python keeps the working copy in st.session_state and answers storage.py's calls from it
Nothing is ever written before the browser's copy has been read, so a slow load can't wipe someone's teams.
storage.py routes here; the rest of the app only asks storage.enabled().
"""
import json
from datetime import datetime, timezone

import streamlit as st

from metamatch import config

STATE ="_mm_browser_store"      # the working copy: {"teams", "chats", "prefs", "seq"}
VERSION = "_mm_browser_store_v"  # bumped on every change, so the component knows to write
KEY = "mm_browser_store"         # the component's key (its state holds what the browser sent)
STORAGE_KEY = "metamatch.v1"     # the localStorage key
KEEP_RECENT = 20
KEEP_MESSAGES = config.CHAT_KEEP_MESSAGES   # per team: chats are the bulk of the size
MAX_BYTES = 2_000_000            # localStorage gives about 5 MB per site; stay well under it

_JS = """
export default function (component) {
  const { data, setStateValue } = component
  const KEY = data.storageKey
  // Read once per visit: hand the browser's copy to Python
  if (!data.loaded) {
    let store = null, blocked = false
    try {
      const raw = window.localStorage.getItem(KEY)
      store = raw ? JSON.parse(raw) : null
    } catch (e) {
      blocked = true   // private mode or blocked storage: the app still works, it just can't remember
    }
    setStateValue("loaded", { ok: true, store: store, blocked: blocked })
    return
  }
  // Write back whenever Python's copy changed
  window.__mmStoreWritten = window.__mmStoreWritten || 0
  if (data.save && data.version && data.version !== window.__mmStoreWritten) {
    try {
      window.localStorage.setItem(KEY, data.save)
      window.__mmStoreWritten = data.version
    } catch (e) {}
  }
}
"""

_COMPONENT = st.components.v2.component("mm_browser_store", html="<div></div>", js=_JS)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _empty():
    return {"teams": {}, "chats": {}, "prefs": {}, "seq": 0}


def loaded():
    """True once this visit's browser copy has been read (or the browser refused storage)."""
    return STATE in st.session_state


def _store():
    return st.session_state[STATE]


def _changed():
    st.session_state[VERSION] = st.session_state.get(VERSION, 0) + 1


def _absorb():
    """Takes the browser's copy into session state the first time the component reports it."""
    if loaded():
        return
    comp = st.session_state.get(KEY)
    sent = (comp.get("loaded") if hasattr(comp, "get") else getattr(comp, "loaded", None)) if comp is not None else None
    if not sent:
        return
    store = sent.get("store") if isinstance(sent.get("store"), dict) else None
    base = _empty()
    if store:
        base.update({k: store.get(k, base[k]) for k in base})
    st.session_state[STATE] = base


def mount():
    """Draws the invisible component once per run. Call it after the page so a read never delays the page, and
    before st.stop() when a page must wait for the browser's copy."""
    if st.session_state.get("_mm_store_mounted") == st.session_state.get("_mm_run"):
        return
    st.session_state["_mm_store_mounted"] = st.session_state.get("_mm_run")
    _absorb()
    data = {"storageKey": STORAGE_KEY, "loaded": loaded()}
    if loaded() and st.session_state.get(VERSION):
        data.update(save=_serialise(), version=st.session_state[VERSION])
    with st.container(key="mm_store_slot", height=1, border=False):
        _COMPONENT(key=KEY, data=data, on_loaded_change=lambda: None)


def start_run():
    """Marks a new script run (mount() draws once per run) and absorbs the browser's copy if it just arrived."""
    import uuid
    st.session_state["_mm_run"] = uuid.uuid4().hex
    _absorb()


def _serialise():
    """The store as JSON, trimmed under MAX_BYTES by dropping the oldest chat messages first."""
    store = _store()
    text = json.dumps(store, separators=(",", ":"))
    while len(text.encode("utf-8")) > MAX_BYTES and any(store["chats"].values()):
        longest = max(store["chats"], key=lambda t: len(store["chats"][t]))
        store["chats"][longest] = store["chats"][longest][len(store["chats"][longest]) // 2:]
        text = json.dumps(store, separators=(",", ":"))
    return text


def _row(tid, t):
    from metamatch.utils import extract_pokemon_names
    d = {"id": tid, **t}
    d["pokemon_names"] = extract_pokemon_names(d["raw_text"])
    d["updated_at"] = d.get("saved_at") or d.get("opened_at")
    return d


# --- The storage.py API, on the browser's copy --------------------------------------------------

def remember_team(text, format_id, tid):
    store = _store()
    store["seq"] += 1
    now = _now()
    t = store["teams"].get(tid) or {"raw_text": text, "format": format_id, "name": None, "created_at": now,
                                     "saved_at": None}
    t.update(opened_at=now, opened_seq=store["seq"], in_recent=1)
    store["teams"][tid] = t
    unnamed = sorted((k for k, v in store["teams"].items() if not v.get("name")),
                     key=lambda k: store["teams"][k]["opened_seq"], reverse=True)
    for old in unnamed[KEEP_RECENT:]:
        store["teams"].pop(old, None)
        store["chats"].pop(old, None)
    _changed()
    return tid


def get_team(tid):
    t = _store()["teams"].get(tid)
    return _row(tid, t) if t else None


def recent_teams(limit=5):
    teams = _store()["teams"]
    order = sorted((k for k, v in teams.items() if v.get("in_recent")), key=lambda k: teams[k]["opened_seq"], reverse=True)
    return [_row(k, teams[k]) for k in order[:limit]]


def forget_team(tid):
    store = _store()
    t = store["teams"].get(tid)
    if not t:
        return False
    if not t.get("name"):
        store["teams"].pop(tid)
        store["chats"].pop(tid, None)
    else:
        t["in_recent"] = 0
    _changed()
    return True


def save_team(name, tid):
    store = _store()
    for k, v in store["teams"].items():
        if v.get("name") == name and k != tid:
            v["name"], v["saved_at"] = None, None
    store["teams"][tid].update(name=name, saved_at=_now())
    _changed()
    return tid


def list_teams_detailed():
    teams = _store()["teams"]
    named = [k for k, v in teams.items() if v.get("name")]
    named.sort(key=lambda k: (teams[k].get("saved_at") or "", teams[k]["opened_seq"]), reverse=True)
    return [_row(k, teams[k]) for k in named]


def delete_team(name):
    hit = False
    for v in _store()["teams"].values():
        if v.get("name") == name:
            v["name"], v["saved_at"], hit = None, None, True
    if hit:
        _changed()
    return hit


def chat_messages(tid):
    return [dict(m) for m in _store()["chats"].get(tid, [])]


def add_chat_message(tid, role, content, name=None, avatar=None):
    store = _store()
    if tid not in store["teams"]:
        return
    msg = {k: v for k, v in (("role", role), ("name", name), ("avatar", avatar), ("content", content)) if v is not None}
    store["chats"].setdefault(tid, []).append(msg)
    store["chats"][tid] = store["chats"][tid][-KEEP_MESSAGES:]
    _changed()


def clear_chat(tid):
    if _store()["chats"].pop(tid, None) is not None:
        _changed()


def get_pref(key, default=None):
    return _store()["prefs"].get(key, default)


def set_pref(key, value):
    _store()["prefs"][key] = value
    _changed()

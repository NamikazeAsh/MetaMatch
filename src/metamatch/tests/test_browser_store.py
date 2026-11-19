"""The browser store behind saving on a shared deployment: same rules as the SQLite store, on a per visitor copy."""
import json
import unittest
from unittest.mock import patch

from metamatch import browser_store as bs


class _FakeSt:
    def __init__(self):
        self.session_state = {bs.STATE: bs._empty()}


class TestBrowserStore(unittest.TestCase):
    def setUp(self):
        self.fake = _FakeSt()
        self.patch = patch.object(bs, "st", self.fake)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_recent_saved_and_forgotten(self):
        bs.remember_team("Gholdengo", "gen9ou", "a")
        bs.remember_team("Kingambit", "gen9ou", "b")
        self.assertEqual([t["id"] for t in bs.recent_teams()], ["b", "a"])
        bs.save_team("Main", "a")
        self.assertEqual([t["name"] for t in bs.list_teams_detailed()], ["Main"])
        bs.save_team("Main", "b")                       # reusing a name moves it
        self.assertEqual([t["id"] for t in bs.list_teams_detailed()], ["b"])
        self.assertTrue(bs.forget_team("b"))            # saved: leaves recents, stays saved
        self.assertEqual([t["id"] for t in bs.recent_teams()], ["a"])
        self.assertEqual(bs.get_team("b")["name"], "Main")
        self.assertTrue(bs.forget_team("a"))            # unsaved: gone
        self.assertIsNone(bs.get_team("a"))
        self.assertTrue(self.fake.session_state[bs.VERSION] > 0)   # every change asks the browser to write

    def test_unsaved_teams_beyond_the_limit_are_dropped_with_their_chats(self):
        for i in range(bs.KEEP_RECENT + 3):
            bs.remember_team(f"team {i}", "gen9ou", f"t{i}")
            bs.add_chat_message(f"t{i}", "user", "hi")
        self.assertEqual(len(bs.recent_teams(limit=100)), bs.KEEP_RECENT)
        self.assertIsNone(bs.get_team("t0"))
        self.assertEqual(bs.chat_messages("t0"), [])

    def test_chats_are_capped_and_trimmed_to_fit(self):
        bs.remember_team("x", "gen9ou", "x")
        for i in range(bs.KEEP_MESSAGES + 5):
            bs.add_chat_message("x", "assistant", f"answer {i}", name="Oak")
        msgs = bs.chat_messages("x")
        self.assertEqual(len(msgs), bs.KEEP_MESSAGES)
        self.assertEqual(msgs[-1], {"role": "assistant", "name": "Oak", "content": f"answer {bs.KEEP_MESSAGES + 4}"})
        with patch.object(bs, "MAX_BYTES", 2000):
            text = bs._serialise()
        self.assertLessEqual(len(text.encode("utf-8")), 2000)
        self.assertTrue(json.loads(text)["teams"])     # trimming drops chat, never teams

    def test_prefs(self):
        self.assertIsNone(bs.get_pref("format"))
        bs.set_pref("format", "gen9uu")
        self.assertEqual(bs.get_pref("format"), "gen9uu")


if __name__ == "__main__":
    unittest.main()

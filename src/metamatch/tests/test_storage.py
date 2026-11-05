import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from metamatch import storage

TEAM = "Great Tusk @ Booster Energy\nAbility: Protosynthesis\n- Headlong Rush"
TEAM_CHAMPS = "Garchomp @ Garchompite\nAbility: Rough Skin\n- Earthquake"


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [patch.object(storage, "DB_PATH", root / "test.db"),
                        patch.object(storage, "LEGACY_JSON", root / "default.json")]
        for p in self.patches:
            p.start()
        self.root = root

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()


class TestTeams(StorageTest):
    def test_id_ignores_line_endings_and_trailing_spaces(self):
        messy = TEAM.replace("\n", "  \r\n") + "\n\n"
        self.assertEqual(storage.team_id(messy, "gen9ou"), storage.team_id(TEAM, "gen9ou"))
        self.assertNotEqual(storage.team_id(TEAM, "gen9ou"), storage.team_id(TEAM, "gen9uu"))

    def test_remember_and_get(self):
        tid = storage.remember_team(TEAM, "gen9ou")
        t = storage.get_team(tid)
        self.assertEqual((t["raw_text"], t["format"], t["name"]), (TEAM, "gen9ou", None))
        self.assertEqual(t["pokemon_names"], ["Great Tusk"])
        self.assertIsNone(storage.get_team("nope"))

    def test_recent_order_and_reopen_bumps(self):
        a = storage.remember_team(TEAM, "gen9ou")
        b = storage.remember_team(TEAM_CHAMPS, "gen9championsou")
        self.assertEqual([t["id"] for t in storage.recent_teams()], [b, a])
        storage.remember_team(TEAM, "gen9ou")
        self.assertEqual([t["id"] for t in storage.recent_teams()], [a, b])

    def test_pruning_keeps_saved_teams(self):
        saved = storage.save_team("Keeper", TEAM, "gen9ou")
        for i in range(storage.KEEP_RECENT + 5):
            storage.remember_team(f"Pikachu\n- Move {i}", "gen9ou")
        self.assertIsNotNone(storage.get_team(saved))
        self.assertEqual(len(storage.recent_teams(limit=100)), storage.KEEP_RECENT + 1)

    def test_forget_recent(self):
        loose = storage.remember_team(TEAM_CHAMPS, "gen9championsou")
        storage.add_chat_message(loose, "user", "hi")
        kept = storage.save_team("Keeper", TEAM, "gen9ou")
        self.assertTrue(storage.forget_team(loose))
        self.assertIsNone(storage.get_team(loose))  # unsaved: gone, chat with it
        self.assertEqual(storage.chat_messages(loose), [])
        self.assertTrue(storage.forget_team(kept))
        self.assertEqual(storage.recent_teams(), [])  # saved: hidden from recent...
        self.assertEqual([t["name"] for t in storage.list_teams_detailed()], ["Keeper"])  # ...but still saved
        storage.remember_team(TEAM, "gen9ou")  # reopening brings it back
        self.assertEqual([t["id"] for t in storage.recent_teams()], [kept])
        self.assertFalse(storage.forget_team("nope"))

    def test_old_database_gets_new_columns(self):
        import sqlite3
        conn = sqlite3.connect(storage.DB_PATH)
        conn.execute("CREATE TABLE teams (id TEXT PRIMARY KEY, raw_text TEXT NOT NULL, format TEXT NOT NULL, name TEXT UNIQUE,"
                     " created_at TEXT NOT NULL, opened_at TEXT NOT NULL, opened_seq INTEGER NOT NULL DEFAULT 0, saved_at TEXT)")
        conn.execute("INSERT INTO teams VALUES ('abc', 'Pikachu', 'gen9ou', NULL, 'x', 'x', 1, NULL)")
        conn.commit(); conn.close()
        self.assertEqual([t["id"] for t in storage.recent_teams()], ["abc"])

    def test_save_rename_and_delete(self):
        a = storage.save_team("Main", TEAM, "gen9ou")
        b = storage.save_team("Main", TEAM_CHAMPS, "gen9championsou")  # name moves to the new team
        names = {t["id"]: t["name"] for t in storage.list_teams_detailed()}
        self.assertEqual(names, {b: "Main"})
        self.assertIsNone(storage.get_team(a)["name"])
        self.assertTrue(storage.delete_team("Main"))
        self.assertFalse(storage.delete_team("Main"))
        self.assertEqual(storage.list_teams_detailed(), [])

    def test_concurrent_saves_lose_nothing(self):
        errors = []

        def worker(i):
            try:
                storage.save_team(f"Team {i}", f"Pikachu\n- Move {i}", "gen9ou")
            except Exception as e:  # noqa: BLE001
                errors.append(e)
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(storage.list_teams_detailed()), 12)


class TestChatsAndPrefs(StorageTest):
    def test_chat_is_per_team_and_deleted_with_it(self):
        a = storage.remember_team(TEAM, "gen9ou")
        b = storage.remember_team(TEAM_CHAMPS, "gen9championsou")
        storage.add_chat_message(a, "user", "How do I beat Kingambit?")
        storage.add_chat_message(a, "assistant", "Engine check...", name="Professor Oak", avatar="📜")
        msgs = storage.chat_messages(a)
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant"])
        self.assertNotIn("name", msgs[0])  # a None name crashed st.chat_message on restore
        self.assertEqual(msgs[1]["name"], "Professor Oak")
        self.assertEqual(storage.chat_messages(b), [])
        storage.clear_chat(a)
        self.assertEqual(storage.chat_messages(a), [])
        storage.add_chat_message("missing", "user", "ignored")  # unknown team: no error, nothing stored

    def test_prefs_round_trip(self):
        self.assertEqual(storage.get_pref("format", "gen9ou"), "gen9ou")
        storage.set_pref("format", "gen9championsou")
        storage.set_pref("format", "gen9uu")
        self.assertEqual(storage.get_pref("format"), "gen9uu")


class TestUserDirOverride(unittest.TestCase):
    def test_env_moves_the_store(self):
        import importlib
        from metamatch import config
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"METAMATCH_USER_DIR": tmp}):
            importlib.reload(config)
            importlib.reload(storage)
            self.assertEqual(storage.DB_PATH, Path(tmp) / "metamatch.db")
        # Back to the real paths for every other test
        importlib.reload(config)
        importlib.reload(storage)
        self.assertEqual(storage.DB_PATH, config.DATA_DIR / "user" / "metamatch.db")


class TestLegacyMigration(StorageTest):
    def test_old_json_teams_are_imported_once(self):
        legacy = {"teams": {"Rain": {"name": "Rain", "raw_text": TEAM, "updated_at": "2026-03-01T10:00:00",
                                     "analysis": {"team": {"0": {"Pokemon": "Great Tusk", "Format": "gen9uu"}}}},
                            "Empty": {"name": "Empty", "raw_text": ""}}}
        (self.root / "default.json").write_text(json.dumps(legacy), encoding="utf-8")
        teams = storage.list_teams_detailed()
        self.assertEqual([(t["name"], t["format"]) for t in teams], [("Rain", "gen9uu")])
        self.assertFalse((self.root / "default.json").exists())
        self.assertTrue((self.root / "default.json.bak").exists())

    def test_unreadable_json_is_left_alone(self):
        (self.root / "default.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(storage.list_teams_detailed(), [])
        self.assertTrue((self.root / "default.json").exists())


if __name__ == "__main__":
    unittest.main()

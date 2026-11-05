"""
Guards the frozen MetaBench fresh set (bench/questions_fresh.jsonl). It is a held out test set:
nothing may be tuned on it, and any edit to it, to its hand written source or to the stats snapshot
its answer key was built from must fail CI. Hashes normalise CRLF to LF so a Windows checkout passes.
"""
import hashlib
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BENCH = ROOT / "bench"
SNAP = BENCH / "fixtures" / "stats_2026_10"

QUESTIONS_SHA256 = "50fe639caa29db35a3a60c2066ec2885cb04110d62ced100c0b01245a8147ff6"
HANDWRITTEN_SHA256 = "974c67f7d460f4caed6db5a7451200eeabc2c3d9fd648139e3d69f913752d23b"


def lf_sha256(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class TestBenchFrozen(unittest.TestCase):
    def test_questions_unchanged(self):
        self.assertEqual(lf_sha256(BENCH / "questions_fresh.jsonl"), QUESTIONS_SHA256,
                         "questions_fresh.jsonl is frozen; build a new set instead of editing it")

    def test_handwritten_source_unchanged(self):
        self.assertEqual(lf_sha256(BENCH / "fresh_handwritten.jsonl"), HANDWRITTEN_SHA256)

    def test_manifest_matches(self):
        manifest = json.loads((SNAP / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["frozen"]["questions_fresh.jsonl"]["sha256_lf"], QUESTIONS_SHA256)
        for name, digest in manifest["files"].items():
            self.assertEqual(lf_sha256(SNAP / name), digest, name)

    @unittest.skipUnless(shutil.which("node") and (ROOT / "src" / "metamatch" / "engine" / "node_modules").exists(),
                         "needs node and the pinned @smogon/calc install")
    def test_generator_reproduces_frozen_set(self):
        result = subprocess.run([sys.executable, str(BENCH / "generate_fresh.py"), "--check"],
                                capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()

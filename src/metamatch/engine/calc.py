"""
Python client for the @smogon/calc sidecar (calc_server.js).

One Node process is started lazily and kept alive; requests are JSON lines.
If Node or the npm package is missing every call returns None, so callers can
fall back to type only facts instead of crashing.
"""
import atexit
import itertools
import json
import shutil
import subprocess
import threading
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
SERVER = ENGINE_DIR / "calc_server.js"


class CalcClient:
    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._broken = False

    def available(self):
        return self._ensure() is not None

    def _ensure(self):
        if self._proc and self._proc.poll() is None:
            return self._proc
        if self._broken:
            return None
        node = shutil.which("node")
        if not node or not (ENGINE_DIR / "node_modules" / "@smogon" / "calc").exists():
            print("Damage calc unavailable: install Node and run `npm install` in src/metamatch/engine")
            self._broken = True
            return None
        self._proc = subprocess.Popen(
            [node, str(SERVER)], cwd=ENGINE_DIR, text=True, encoding="utf-8",
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1,
        )
        return self._proc

    def calculate_many(self, requests):
        """Runs a batch of calc requests. Returns one result dict (or None on error) per request."""
        if not requests:
            return []
        with self._lock:
            proc = self._ensure()
            if proc is None:
                return [None] * len(requests)
            ids = []
            try:
                for req in requests:
                    rid = next(self._ids)
                    ids.append(rid)
                    proc.stdin.write(json.dumps({**req, "id": rid}) + "\n")
                proc.stdin.flush()
                by_id = {}
                for _ in ids:
                    resp = json.loads(proc.stdout.readline())
                    by_id[resp.get("id")] = resp
            except (OSError, ValueError):
                self.close()
                return [None] * len(requests)
        return [by_id.get(rid) if by_id.get(rid, {}).get("ok") else None for rid in ids]

    def calculate(self, request):
        return self.calculate_many([request])[0]

    def close(self):
        if self._proc and self._proc.poll() is None:
            self._proc.kill()
        self._proc = None


_client = CalcClient()
atexit.register(_client.close)


def calculate(request):
    return _client.calculate(request)


def calculate_many(requests):
    return _client.calculate_many(requests)


def available():
    return _client.available()

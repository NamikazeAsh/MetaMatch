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
CHUNK = 32  # requests in flight per round trip


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
        """Runs a batch of calc requests. Returns one result dict (or None on error) per request.
        Requests are written on a separate thread while this one reads the answers: writing a whole batch before
        reading deadlocks once Node's answers fill its stdout pipe (answers with long descriptions did it at 32)."""
        if not requests:
            return []
        if len(requests) > CHUNK:
            out = []
            for start in range(0, len(requests), CHUNK):
                out.extend(self.calculate_many(requests[start:start + CHUNK]))
            return out
        with self._lock:
            proc = self._ensure()
            if proc is None:
                return [None] * len(requests)
            ids = [next(self._ids) for _ in requests]
            lines = "".join(json.dumps({**req, "id": rid}) + "\n" for req, rid in zip(requests, ids))
            failed = []

            def write():
                try:
                    proc.stdin.write(lines)
                    proc.stdin.flush()
                except OSError as e:
                    failed.append(e)

            writer = threading.Thread(target=write, daemon=True)
            writer.start()
            by_id = {}
            try:
                for _ in ids:
                    line = proc.stdout.readline()
                    if not line:
                        raise OSError("calc sidecar closed its output")
                    resp = json.loads(line)
                    by_id[resp.get("id")] = resp
            except (OSError, ValueError):
                self.close()
                return [None] * len(requests)
            writer.join()
            if failed:
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

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
from collections import deque
from pathlib import Path

from pob_engine.errors import EngineError
from pob_engine.paths import EnginePaths, git_head


class PobProcess:
    """One long-lived headless Path of Building process."""

    def __init__(self, paths: EnginePaths, revision: str):
        self.paths = paths
        self.revision = revision
        self._lock = threading.Lock()
        self._next_id = 1
        self._stderr: deque[str] = deque(maxlen=200)
        self.user_dir = Path(tempfile.mkdtemp(prefix="pob-user-"))
        self.info: dict = {}
        env = os.environ.copy()
        env.pop("POB_SELFTEST", None)
        env.update(
            {
                "POB_SRC": str(paths.src),
                "POB_RUNTIME": str(paths.runtime),
                "POB_UTF8_DIR": str(paths.utf8_dir),
                "POB_USER": str(self.user_dir),
                "POB_ENGINE_REVISION": revision,
                "POB_ENGINE_COMMIT_TIME": str(paths.pin.get("commitTime", "")),
            }
        )
        self.proc = subprocess.Popen(
            [str(paths.luajit), str(paths.adapter)],
            cwd=str(paths.src),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        banner = self._read_line(timeout=120)
        try:
            ready = json.loads(banner)
        except json.JSONDecodeError as exc:
            self.close()
            raise EngineError(f"Engine banner was not JSON: {banner[:200]}") from exc
        if not ready.get("ready"):
            self.close()
            raise EngineError(f"Engine did not become ready: {ready}")
        self.info = ready.get("result") or {}

    @classmethod
    def start(cls, paths: EnginePaths) -> PobProcess:
        missing = [
            label
            for label, path in (
                ("LuaJIT", paths.luajit),
                ("PoB src", paths.src / "HeadlessWrapper.lua"),
                ("adapter", paths.adapter),
                ("lua-utf8", paths.utf8_dir / "lua-utf8.so"),
                ("runtime xml", paths.runtime / "lua" / "xml.lua"),
            )
            if not path.exists()
        ]
        if missing:
            raise EngineError(
                "Path of Building is not bootstrapped ("
                + ", ".join(missing)
                + "). Run scripts/bootstrap_engine.sh."
            )
        revision = git_head(paths.src)
        return cls(paths, revision)

    def _drain_stderr(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            self._stderr.append(line.rstrip())

    def _read_line(self, timeout: float) -> str:
        holder: dict[str, str] = {}

        def read() -> None:
            assert self.proc.stdout is not None
            holder["line"] = self.proc.stdout.readline()

        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            self.close()
            raise EngineError("Timed out waiting for the Path of Building process.")
        line = holder.get("line", "")
        if line == "" and self.proc.poll() is not None:
            tail = "\n".join(self._stderr)
            raise EngineError(f"Path of Building exited.\n{tail}")
        return line

    def request(self, action: str, timeout: float = 60, **params) -> dict:
        with self._lock:
            if self.proc.poll() is not None:
                raise EngineError("Path of Building is not running.")
            request_id = self._next_id
            self._next_id += 1
            payload = {"id": request_id, "action": action}
            payload.update({key: value for key, value in params.items() if value is not None})
            assert self.proc.stdin is not None
            self.proc.stdin.write(json.dumps(payload) + "\n")
            self.proc.stdin.flush()
            raw = self._read_line(timeout)
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise EngineError(f"Engine returned invalid JSON: {raw[:200]}") from exc
            if not data.get("ok"):
                raise EngineError(str(data.get("error") or "engine request failed"))
            result = data.get("result")
            if not isinstance(result, dict):
                raise EngineError(f"{action} returned no result")
            return result

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=5)

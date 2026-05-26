from __future__ import annotations

import json
import os
import time
from pathlib import Path

from xcode_cli.paths import ensure_xcode_home


class RuntimeStatusStore:
    def __init__(self) -> None:
        root = ensure_xcode_home()
        self._dir = root / "sessions"
        self._pid = os.getpid()

    @property
    def _path(self) -> Path:
        return self._dir / f"{self._pid}.json"

    def create(self, session_id: str, cwd: str) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        data = {
            "pid": self._pid,
            "sessionId": session_id,
            "cwd": cwd,
            "status": "idle",
            "updatedAt": int(time.time() * 1000),
        }
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def update(self, status: str) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        data["status"] = status
        data["updatedAt"] = int(time.time() * 1000)
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def update_session_id(self, session_id: str) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        data["sessionId"] = session_id
        data["updatedAt"] = int(time.time() * 1000)
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def delete(self) -> None:
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            pass

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from xcode_cli.paths import ensure_xcode_home


@dataclass
class Message:
    role: str
    content: str
    ts: str


class SessionStore:
    def __init__(self) -> None:
        root = ensure_xcode_home()
        self.sessions_dir: Path = root / "sessions"

    def new_session_id(self) -> str:
        return datetime.utcnow().strftime("%Y%m%d-%H%M%S")

    def append(self, session_id: str, role: str, content: str) -> None:
        path = self.sessions_dir / f"{session_id}.jsonl"
        msg = Message(role=role, content=content, ts=datetime.utcnow().isoformat())
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(msg), ensure_ascii=False) + "\n")

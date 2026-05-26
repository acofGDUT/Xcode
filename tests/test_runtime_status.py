from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from xcode_cli.core.runtime_status import RuntimeStatusStore


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_store(tmp_path: Path, monkeypatch) -> RuntimeStatusStore:
    import xcode_cli.paths

    xcode_dir = tmp_path / ".xcode"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    for sub in ("sessions", "skills", "bin"):
        (xcode_dir / sub).mkdir(parents=True, exist_ok=True)

    return RuntimeStatusStore()


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

class TestCreate:
    def test_creates_file(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        store.create("sid-123", "D:\\Xcode")
        assert store._path.exists()

    def test_file_uses_pid(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        store.create("sid-123", "D:\\Xcode")
        assert store._path.name == f"{os.getpid()}.json"

    def test_content_has_expected_fields(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        store.create("sid-456", "D:\\Work")
        data = json.loads(store._path.read_text(encoding="utf-8"))
        assert data["pid"] == os.getpid()
        assert data["sessionId"] == "sid-456"
        assert data["cwd"] == "D:\\Work"
        assert data["status"] == "idle"
        assert isinstance(data["updatedAt"], int)


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------

class TestUpdate:
    def test_update_status(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        store.create("sid-1", "D:\\Xcode")
        store.update("busy")
        data = json.loads(store._path.read_text(encoding="utf-8"))
        assert data["status"] == "busy"

    def test_update_updates_timestamp(self, tmp_path: Path, monkeypatch) -> None:
        import time

        store = _make_store(tmp_path, monkeypatch)
        store.create("sid-1", "D:\\Xcode")
        first_ts = json.loads(store._path.read_text(encoding="utf-8"))["updatedAt"]
        time.sleep(0.05)
        store.update("idle")
        second_ts = json.loads(store._path.read_text(encoding="utf-8"))["updatedAt"]
        assert second_ts >= first_ts

    def test_update_noop_when_file_missing(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        store.update("busy")

    def test_update_session_id(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        store.create("sid-1", "D:\\Xcode")
        store.update_session_id("sid-2")
        data = json.loads(store._path.read_text(encoding="utf-8"))
        assert data["sessionId"] == "sid-2"
        assert data["pid"] == os.getpid()

    def test_update_session_id_noop_when_missing(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        store.update_session_id("sid-2")


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

class TestDelete:
    def test_deletes_file(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        store.create("sid-1", "D:\\Xcode")
        store.delete()
        assert not store._path.exists()

    def test_delete_noop_when_missing(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        store.delete()

    def test_create_update_delete_lifecycle(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        store.create("sid-life", "D:\\Xcode")
        assert store._path.exists()
        store.update("busy")
        assert json.loads(store._path.read_text(encoding="utf-8"))["status"] == "busy"
        store.update("idle")
        assert json.loads(store._path.read_text(encoding="utf-8"))["status"] == "idle"
        store.delete()
        assert not store._path.exists()

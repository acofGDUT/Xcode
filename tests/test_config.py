from __future__ import annotations

import json
from pathlib import Path

from xcode_cli.core.config import Config, ConfigStore


def test_config_default_max_tokens() -> None:
    c = Config()
    assert c.max_tokens == 128000


def test_config_max_tokens_is_stored(tmp_path: Path) -> None:
    """Save config with custom max_tokens and reload."""
    config_path = tmp_path / "config.json"
    store = ConfigStore()
    store.path = config_path

    cfg = Config()
    cfg.max_tokens = 64000
    cfg.model = "test-model"
    store.save(cfg)

    loaded = store.load()
    assert loaded.max_tokens == 64000
    assert loaded.model == "test-model"


def test_config_load_invalid_max_tokens_falls_back_to_default(tmp_path: Path) -> None:
    """Non-integer or negative max_tokens should fall back to 128000."""
    config_path = tmp_path / "config.json"
    store = ConfigStore()
    store.path = config_path

    # Write bad data directly
    config_path.write_text(json.dumps({"max_tokens": "not_an_integer"}), encoding="utf-8")
    loaded = store.load()
    assert loaded.max_tokens == 128000

    config_path.write_text(json.dumps({"max_tokens": -1}), encoding="utf-8")
    loaded = store.load()
    assert loaded.max_tokens == 128000

    config_path.write_text(json.dumps({"max_tokens": 0}), encoding="utf-8")
    loaded = store.load()
    assert loaded.max_tokens == 128000


def test_config_load_missing_max_tokens_uses_default(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    store = ConfigStore()
    store.path = config_path

    config_path.write_text(json.dumps({"model": "foo"}), encoding="utf-8")
    loaded = store.load()
    assert loaded.max_tokens == 128000
    assert loaded.model == "foo"


def test_config_store_creates_new_config_when_missing() -> None:
    store = ConfigStore()
    store.path = Path("/nonexistent/path/config.json")
    loaded = store.load()
    assert loaded.max_tokens == 128000
    assert isinstance(loaded, Config)


def test_config_syntax_theme_default() -> None:
    c = Config()
    assert c.syntax_theme == "monokai"


def test_config_syntax_theme_invalid_fallback(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    store = ConfigStore()
    store.path = config_path

    config_path.write_text(json.dumps({"syntax_theme": ""}), encoding="utf-8")
    loaded = store.load()
    assert loaded.syntax_theme == "monokai"

    config_path.write_text(json.dumps({"syntax_theme": "   "}), encoding="utf-8")
    loaded = store.load()
    assert loaded.syntax_theme == "monokai"

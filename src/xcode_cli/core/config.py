from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from xcode_cli.paths import ensure_xcode_home


@dataclass
class Config:
    enabled_skills: list[str] = field(default_factory=list)
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    provider: str = "openai-compatible"
    auto_memory: bool = True
    max_tokens: int = 128000
    response_render_mode: str = "buffer_then_render"


class ConfigStore:
    def __init__(self) -> None:
        root = ensure_xcode_home()
        self.path: Path = root / "config.json"

    def load(self) -> Config:
        if not self.path.exists():
            return Config()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        response_render_mode = data.get("response_render_mode", "streaming_plus_final_render")
        if response_render_mode not in {"streaming_plus_final_render", "buffer_then_render"}:
            response_render_mode = "buffer_then_render"

        max_tokens = data.get("max_tokens", 128000)
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            max_tokens = 128000

        return Config(
            enabled_skills=data.get("enabled_skills", []),
            api_key=data.get("api_key", ""),
            base_url=data.get("base_url", ""),
            model=data.get("model", ""),
            provider=data.get("provider", "openai-compatible"),
            auto_memory=data.get("auto_memory", True),
            max_tokens=max_tokens,
            response_render_mode=response_render_mode,
        )

    def save(self, config: Config) -> None:
        payload = {
            "enabled_skills": config.enabled_skills,
            "api_key": config.api_key,
            "base_url": config.base_url,
            "model": config.model,
            "provider": config.provider,
            "auto_memory": config.auto_memory,
            "max_tokens": config.max_tokens,
            "response_render_mode": config.response_render_mode,
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

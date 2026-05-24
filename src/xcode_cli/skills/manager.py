from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from xcode_cli.paths import ensure_xcode_home


@dataclass
class InstalledSkill:
    name: str
    path: Path
    description: str


class SkillManager:
    def __init__(self) -> None:
        root = ensure_xcode_home()
        self.skills_root: Path = root / "skills"

    def install(self, source_dir: str) -> InstalledSkill:
        src = Path(source_dir).resolve()
        manifest_path = src / "skill.json"
        if not src.exists() or not src.is_dir():
            raise ValueError(f"Skill source not found: {src}")
        if not manifest_path.exists():
            raise ValueError("Missing skill.json in skill directory")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        name = manifest.get("name")
        description = manifest.get("description", "")
        if not name:
            raise ValueError("skill.json must include 'name'")

        dest = self.skills_root / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)

        return InstalledSkill(name=name, path=dest, description=description)

    def list_installed(self) -> list[InstalledSkill]:
        items: list[InstalledSkill] = []
        for d in sorted(self.skills_root.iterdir()):
            if not d.is_dir():
                continue
            manifest = d / "skill.json"
            if not manifest.exists():
                continue
            data = json.loads(manifest.read_text(encoding="utf-8"))
            items.append(
                InstalledSkill(
                    name=data.get("name", d.name),
                    path=d,
                    description=data.get("description", ""),
                )
            )
        return items

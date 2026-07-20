from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.memory_extraction_policy import validate_v2_topic_text
from xcode_cli.core.permissions import PermissionManager
from xcode_cli.core.tool_registry import ToolDef, ToolOutput, ToolRegistry


@dataclass
class MemoryToolAudit:
    read_paths: set[Path] = field(default_factory=set)
    saved_topic_paths: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def create_memory_extraction_tools(
    memory: MemoryManager,
    permissions: PermissionManager,
) -> tuple[ToolRegistry, MemoryToolAudit]:
    audit = MemoryToolAudit()
    tools = ToolRegistry()

    def read_file(path: str) -> ToolOutput:
        resolved = _resolve_auto_memory_path(memory, path)
        if resolved is None:
            return ToolOutput(content="Error: path outside auto memory")
        try:
            content = resolved.read_text(encoding="utf-8")
        except Exception as exc:
            return ToolOutput(content=f"Error: {exc}")
        audit.read_paths.add(resolved)
        return ToolOutput(content=content)

    def write_file(path: str, content: str, append: bool = False) -> ToolOutput:
        resolved = _resolve_auto_memory_path(memory, path)
        if resolved is None:
            return ToolOutput(content="Error: path outside auto memory")
        if permissions.check("write_file", is_read_only=False) == "deny":
            return ToolOutput(content="Error: permission denied")
        candidate_content = content
        if append and resolved.exists():
            try:
                candidate_content = resolved.read_text(encoding="utf-8") + content
            except Exception as exc:
                return ToolOutput(content=f"Error: {exc}")
        if resolved.name != "MEMORY.md":
            policy = validate_v2_topic_text(candidate_content)
            if not policy.accepted:
                return ToolOutput(content=f"Error: policy rejected: {policy.reason}")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        if append:
            with resolved.open("a", encoding="utf-8") as handle:
                handle.write(content)
        else:
            resolved.write_text(content, encoding="utf-8")
        _record_saved_topic(memory, audit, resolved)
        return ToolOutput(content=f"Wrote {resolved}")

    def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> ToolOutput:
        resolved = _resolve_auto_memory_path(memory, path)
        if resolved is None:
            return ToolOutput(content="Error: path outside auto memory")
        if resolved not in audit.read_paths:
            return ToolOutput(content="Error: edit_file requires prior read_file")
        if permissions.check("write_file", is_read_only=False) == "deny":
            return ToolOutput(content="Error: permission denied")
        try:
            text = resolved.read_text(encoding="utf-8")
        except Exception as exc:
            return ToolOutput(content=f"Error: {exc}")
        count = -1 if replace_all else 1
        if old_string not in text:
            return ToolOutput(content="Error: old_string not found")
        new_text = text.replace(old_string, new_string, count)
        if resolved.name != "MEMORY.md":
            policy = validate_v2_topic_text(new_text)
            if not policy.accepted:
                return ToolOutput(content=f"Error: policy rejected: {policy.reason}")
        resolved.write_text(new_text, encoding="utf-8")
        _record_saved_topic(memory, audit, resolved)
        return ToolOutput(content=f"Edited {resolved}")

    def glob(pattern: str = "*.md") -> ToolOutput:
        root = memory.memory_dir_path()
        files = sorted(path.name for path in root.glob(pattern) if _resolve_auto_memory_path(memory, path) is not None)
        return ToolOutput(content="\n".join(files))

    tools.register(
        ToolDef(
            "read_file",
            "Read an auto memory file.",
            {"path": {"type": "string"}},
            ["path"],
            read_file,
            True,
        )
    )
    tools.register(
        ToolDef(
            "write_file",
            "Write an auto memory file.",
            {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "append": {"type": "boolean"},
            },
            ["path", "content"],
            write_file,
            False,
        )
    )
    tools.register(
        ToolDef(
            "edit_file",
            "Edit an already-read auto memory file.",
            {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean"},
            },
            ["path", "old_string", "new_string"],
            edit_file,
            False,
        )
    )
    tools.register(
        ToolDef(
            "glob",
            "List auto memory files.",
            {"pattern": {"type": "string"}},
            [],
            glob,
            True,
        )
    )
    return tools, audit


def _resolve_auto_memory_path(memory: MemoryManager, path: str | Path) -> Path | None:
    try:
        resolved = Path(path).expanduser().resolve(strict=False)
    except Exception:
        return None

    memory_root = memory.memory_dir_path().resolve(strict=False)
    try:
        if not resolved.is_relative_to(memory_root):
            return None
    except ValueError:
        return None
    if resolved.name == "MEMORY.md":
        return resolved
    if resolved.suffix.lower() == ".md":
        return resolved
    return None


def _record_saved_topic(memory: MemoryManager, audit: MemoryToolAudit, path: Path) -> None:
    resolved = path.resolve(strict=False)
    if resolved.name == "MEMORY.md":
        return
    if resolved.suffix.lower() == ".md" and resolved not in audit.saved_topic_paths:
        audit.saved_topic_paths.append(resolved)

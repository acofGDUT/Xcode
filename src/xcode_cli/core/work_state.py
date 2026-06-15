from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FileExcerpt:
    path: str
    sha256: str
    observed_at: str
    line_start: int
    line_end: int
    excerpt: str
    source: str
    stale: bool = False


@dataclass(frozen=True)
class DiagnosticItem:
    source: str
    path: str
    line: int | None
    column: int | None
    severity: str
    message: str
    command: str = ""


@dataclass(frozen=True)
class CommandStatus:
    kind: str
    command: str
    cwd: str
    exit_code: int | None
    observed_at: str
    output_excerpt: str
    failed_tests: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SearchSummary:
    tool: str
    pattern: str
    path: str
    match_count: int
    sample: list[str]


@dataclass(frozen=True)
class WorkStateSnapshot:
    active_file: str = ""
    recent_files: list[FileExcerpt] = field(default_factory=list)
    diagnostics: list[DiagnosticItem] = field(default_factory=list)
    latest_build: CommandStatus | None = None
    latest_test: CommandStatus | None = None
    current_plan: str = ""
    invoked_skills: list[dict[str, str]] = field(default_factory=list)
    recent_searches: list[SearchSummary] = field(default_factory=list)


class WorkStateTracker:
    """Best-effort compact work-site state for restored context."""

    def __init__(
        self,
        *,
        cwd: str = "",
        max_recent_files: int = 4,
        max_file_excerpt_chars: int = 4000,
        max_command_excerpt_chars: int = 2000,
        max_restored_context_chars: int = 8000,
    ) -> None:
        self.cwd = cwd
        self.max_recent_files = max_recent_files
        self.max_file_excerpt_chars = max_file_excerpt_chars
        self.max_command_excerpt_chars = max_command_excerpt_chars
        self.max_restored_context_chars = max_restored_context_chars
        self._active_file = ""
        self._recent_files: list[FileExcerpt] = []
        self._diagnostics: list[DiagnosticItem] = []
        self._latest_build: CommandStatus | None = None
        self._latest_test: CommandStatus | None = None
        self._current_plan = ""
        self._invoked_skills: list[dict[str, str]] = []
        self._recent_searches: list[SearchSummary] = []

    def record_tool_call(self, tool_name: str, args: dict[str, Any], output: str) -> None:
        try:
            if tool_name == "read_file":
                self._record_read_file(args, output)
            elif tool_name in {"write_file", "edit_file"}:
                self._record_write_like(args)
            elif tool_name in {"grep", "glob"}:
                self._record_search(tool_name, args, output)
            elif tool_name == "run_shell":
                self._record_shell(args, output)
            elif tool_name == "skill":
                self._record_skill(args, output)
            elif tool_name in {"write_plan", "exit_plan_mode"}:
                self.update_current_plan(str(args.get("content") or args.get("plan_summary") or ""))
        except Exception:
            return

    def update_current_plan(self, plan: str) -> None:
        self._current_plan = _redact(plan.strip())[:2000]

    def snapshot(self) -> WorkStateSnapshot:
        return WorkStateSnapshot(
            active_file=self._active_file,
            recent_files=list(self._recent_files),
            diagnostics=list(self._diagnostics),
            latest_build=self._latest_build,
            latest_test=self._latest_test,
            current_plan=self._current_plan,
            invoked_skills=list(self._invoked_skills),
            recent_searches=list(self._recent_searches),
        )

    def restored_context_sections(self) -> list[str]:
        snapshot = self.snapshot()
        sections: list[str] = []
        if snapshot.active_file:
            sections.append("active_file")
        if snapshot.diagnostics:
            sections.append("diagnostics")
        if snapshot.latest_build:
            sections.append("latest_build")
        if snapshot.latest_test:
            sections.append("latest_test")
        if snapshot.current_plan:
            sections.append("current_plan")
        if snapshot.recent_files:
            sections.append("recent_files")
        if snapshot.invoked_skills:
            sections.append("invoked_skills")
        if snapshot.recent_searches:
            sections.append("recent_searches")
        return sections

    def render_restored_context(self) -> str:
        snapshot = self.snapshot()
        if not self.restored_context_sections():
            return ""

        blocks: list[tuple[str, list[str]]] = []
        if snapshot.active_file:
            blocks.append(("active_file", [f"- Active file: {snapshot.active_file}"]))
        if snapshot.diagnostics:
            lines = ["- Latest diagnostics:"]
            for item in snapshot.diagnostics[:12]:
                location = item.path
                if item.line is not None:
                    location += f":{item.line}"
                if item.column is not None:
                    location += f":{item.column}"
                lines.append(f"  - {location} {item.severity}: {_redact(item.message)}")
            blocks.append(("diagnostics", lines))
        if snapshot.latest_build:
            blocks.append(("latest_build", self._render_command("Latest build", snapshot.latest_build)))
        if snapshot.latest_test:
            blocks.append(("latest_test", self._render_command("Latest tests", snapshot.latest_test)))
        if snapshot.current_plan:
            blocks.append(("current_plan", ["- Current plan:", *_indent_lines(snapshot.current_plan, "  - ")]))
        if snapshot.recent_files:
            lines = ["- Recently read files:"]
            for item in snapshot.recent_files[: self.max_recent_files]:
                lines.append(f"  - {item.path} {item.sha256} lines {item.line_start}-{item.line_end}")
                if item.excerpt:
                    lines.extend(_indent_lines(_redact(item.excerpt), "    "))
            omitted = max(0, len(snapshot.recent_files) - self.max_recent_files)
            if omitted:
                lines.append(f"  - omitted {omitted} older file(s) due to restored-context budget")
            blocks.append(("recent_files", lines))
        if snapshot.invoked_skills:
            lines = ["- Invoked skills:"]
            for skill in snapshot.invoked_skills[:8]:
                suffix = f" {skill.get('source_hash', '')}".rstrip()
                lines.append(f"  - {skill.get('name', '')}{suffix}")
            blocks.append(("invoked_skills", lines))
        if snapshot.recent_searches:
            lines = ["- Recent searches:"]
            for search in snapshot.recent_searches[:6]:
                lines.append(
                    f"  - {search.tool} {search.pattern} in {search.path}: "
                    f"{search.match_count} match(es)"
                )
            blocks.append(("recent_searches", lines))

        lines = ["Compact restored context:"]
        omitted_sections = 0
        for _, block in blocks:
            candidate = "\n".join([*lines, *block])
            if len(candidate) <= self.max_restored_context_chars:
                lines.extend(block)
            else:
                omitted_sections += 1
        if omitted_sections:
            lines.append(f"- omitted {omitted_sections} lower-priority section(s) due to restored-context budget")
        rendered = "\n".join(lines)
        if len(rendered) > self.max_restored_context_chars:
            budget = max(0, self.max_restored_context_chars - len("\n- omitted content due to restored-context budget"))
            rendered = rendered[:budget].rstrip() + "\n- omitted content due to restored-context budget"
        return rendered

    def _record_read_file(self, args: dict[str, Any], output: str) -> None:
        path = str(args.get("path", "")).strip()
        if not path:
            return
        target = Path(path)
        sha = _sha256_file(target)
        offset = _coerce_int(args.get("offset"), 1) or 1
        limit = _coerce_int(args.get("limit"), 0) or 0
        lines = output.splitlines()
        line_end = offset + min(limit or len(lines), len(lines)) - 1 if lines else offset
        excerpt = _redact(output[: self.max_file_excerpt_chars])
        self._active_file = path
        self._upsert_recent_file(
            FileExcerpt(
                path=path,
                sha256=sha,
                observed_at=_now(),
                line_start=offset,
                line_end=max(offset, line_end),
                excerpt=excerpt,
                source="read_file",
                stale=False,
            )
        )

    def _record_write_like(self, args: dict[str, Any]) -> None:
        path = str(args.get("path", "")).strip()
        if not path:
            return
        self._active_file = path
        self._upsert_recent_file(
            FileExcerpt(
                path=path,
                sha256=_sha256_file(Path(path)),
                observed_at=_now(),
                line_start=1,
                line_end=1,
                excerpt="",
                source="write",
                stale=False,
            )
        )

    def _record_search(self, tool_name: str, args: dict[str, Any], output: str) -> None:
        lines = [line for line in output.splitlines() if line.strip()]
        summary = SearchSummary(
            tool=tool_name,
            pattern=str(args.get("pattern", "")),
            path=str(args.get("path", "")),
            match_count=0 if output.startswith("No ") else len(lines),
            sample=[_redact(line)[:240] for line in lines[:5]],
        )
        self._recent_searches.insert(0, summary)
        del self._recent_searches[6:]

    def _record_shell(self, args: dict[str, Any], output: str) -> None:
        command = str(args.get("command", ""))
        cwd = str(args.get("cwd") or self.cwd)
        kind = _classify_command(command)
        status = CommandStatus(
            kind=kind,
            command=_redact(command)[:300],
            cwd=cwd,
            exit_code=_extract_exit_code(output),
            observed_at=_now(),
            output_excerpt=_redact(output[: self.max_command_excerpt_chars]),
            failed_tests=_extract_failed_tests(output),
        )
        diagnostics = _extract_diagnostics(output, command=command)
        if diagnostics:
            self._diagnostics = [*diagnostics, *self._diagnostics][:12]
        if kind == "test":
            self._latest_test = status
        elif kind == "build":
            self._latest_build = status
        else:
            self._latest_build = status if status.exit_code not in (0, None) else self._latest_build

    def _record_skill(self, args: dict[str, Any], output: str) -> None:
        name = str(args.get("skill") or args.get("name") or "").strip().lstrip("/")
        if not name:
            match = re.search(r"<xcode_loaded_skill\s+name=\"([^\"]+)\"", output)
            name = match.group(1) if match else ""
        if not name:
            return
        source_hash = str(args.get("source_hash") or args.get("skill_source_hash") or "")
        item = {"name": name, "source_hash": source_hash}
        self._invoked_skills = [existing for existing in self._invoked_skills if existing.get("name") != name]
        self._invoked_skills.insert(0, item)
        del self._invoked_skills[8:]

    def _upsert_recent_file(self, item: FileExcerpt) -> None:
        self._recent_files = [existing for existing in self._recent_files if existing.path != item.path]
        self._recent_files.insert(0, item)
        del self._recent_files[self.max_recent_files * 2 :]

    @staticmethod
    def _render_command(title: str, status: CommandStatus) -> list[str]:
        lines = [
            f"- {title}:",
            f"  - kind: {status.kind}, exit_code: {status.exit_code}",
            f"  - command: {status.command}",
        ]
        if status.failed_tests:
            lines.append("  - failed tests:")
            lines.extend(f"    - {test}" for test in status.failed_tests[:20])
        if status.output_excerpt:
            lines.append("  - output excerpt:")
            lines.extend(_indent_lines(status.output_excerpt[:500], "    "))
        return lines


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        data = str(path).encode("utf-8", errors="replace")
    return "sha256:" + hashlib.sha256(data).hexdigest()[:16]


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _classify_command(command: str) -> str:
    lowered = command.lower()
    test_markers = (
        "pytest",
        "npm test",
        "pnpm test",
        "yarn test",
        "npm run test",
        "pnpm run test",
        "yarn run test",
        "swift test",
        "xcodebuild test",
    )
    if any(marker in lowered for marker in test_markers):
        return "test"
    build_markers = ("xcodebuild", "swift build", "npm run build", "pnpm build", "yarn build")
    if any(marker in lowered for marker in build_markers):
        return "build"
    return "command"


def _extract_exit_code(output: str) -> int | None:
    match = re.search(r"exit_code=(-?\d+)", output)
    return int(match.group(1)) if match else None


def _extract_failed_tests(output: str) -> list[str]:
    tests: list[str] = []
    for line in output.splitlines():
        match = re.search(r"\bFAILED\s+([^\s]+)", line)
        if match:
            tests.append(match.group(1))
    return tests[:20]


def _extract_diagnostics(output: str, *, command: str) -> list[DiagnosticItem]:
    diagnostics: list[DiagnosticItem] = []
    pattern = re.compile(r"(?P<path>.+?):(?P<line>\d+)(?::(?P<column>\d+))?:\s*(?P<severity>error|warning):\s*(?P<message>.+)", re.IGNORECASE)
    for line in output.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        diagnostics.append(
            DiagnosticItem(
                source="run_shell",
                path=match.group("path").strip(),
                line=int(match.group("line")),
                column=int(match.group("column")) if match.group("column") else None,
                severity=match.group("severity").lower(),
                message=_redact(match.group("message").strip()),
                command=command,
            )
        )
    return diagnostics[:12]


def _redact(text: str) -> str:
    patterns = [
        r"(Authorization\s*:\s*(?:Bearer|QQBot|Basic|Token)\s+)[^\s]+",
        r"((?:client_secret|access_token|api_key|app_secret|QQ_BOT_CLIENT_SECRET)\s*[:=]\s*)[^\s,'\"]+",
        r"(--(?:client-secret|access-token|api-key)\s+)[^\s]+",
    ]
    result = text
    for pattern in patterns:
        result = re.sub(pattern, r"\1[REDACTED]", result, flags=re.IGNORECASE)
    return result


def _indent_lines(text: str, prefix: str) -> list[str]:
    return [prefix + line for line in text.splitlines() if line.strip()]

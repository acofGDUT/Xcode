from __future__ import annotations

from rich.console import Console

from xcode_cli.core.config import ConfigStore
from xcode_cli.skills.manager import SkillManager


class SkillCommandService:
    """REPL /skill 和 CLI xcode skill 子命令的共享服务。

    不依赖 AgentRuntime，只依赖 SkillManager、ConfigStore 和 Console。
    """

    def __init__(
        self,
        skill_manager: SkillManager,
        config_store: ConfigStore,
        console: Console,
    ) -> None:
        self._skills = skill_manager
        self._config = config_store
        self._console = console

    # ------------------------------------------------------------------
    # REPL 入口
    # ------------------------------------------------------------------

    def run(self, parts: list[str]) -> None:
        """处理 REPL /skill 命令。parts 已按空格 split。"""
        if len(parts) == 1:
            self._console.print(
                "/skill list | /skill install <path> | /skill enable <name> | /skill disable <name>"
            )
            return
        action = parts[1].lower()
        if action == "list":
            self.list_installed()
        elif action == "install" and len(parts) >= 3:
            self.install(" ".join(parts[2:]))
        elif action == "enable" and len(parts) >= 3:
            self.enable(" ".join(parts[2:]))
        elif action == "disable" and len(parts) >= 3:
            self.disable(" ".join(parts[2:]))
        else:
            self._console.print(
                "Usage: /skill list|install <path>|enable <name>|disable <name>"
            )

    # ------------------------------------------------------------------
    # CLI 入口（也供 run() 内部复用）
    # ------------------------------------------------------------------

    def list_installed(self) -> None:
        """列出已安装的 skill 及 enable/disable 状态。"""
        cfg = self._config.load()
        enabled = set(cfg.enabled_skills)
        skills = self._skills.list_installed()
        if not skills:
            self._console.print("No skills installed.")
            return
        for s in skills:
            status = "enabled" if s.name in enabled else "disabled"
            self._console.print(f"- {s.name} \\[{status}\\] - {s.description}")

    def install(self, path: str) -> None:
        """从本地路径安装 skill。"""
        installed = self._skills.install(path)
        self._console.print(
            f"Installed skill: [bold]{installed.name}[/bold] -> {installed.path}"
        )

    def enable(self, name: str) -> None:
        """启用 skill（幂等）。"""
        cfg = self._config.load()
        if name not in cfg.enabled_skills:
            cfg.enabled_skills.append(name)
            self._config.save(cfg)
        self._console.print(f"Enabled skill: {name}")

    def disable(self, name: str) -> None:
        """禁用 skill（幂等）。"""
        cfg = self._config.load()
        cfg.enabled_skills = [s for s in cfg.enabled_skills if s != name]
        self._config.save(cfg)
        self._console.print(f"Disabled skill: {name}")

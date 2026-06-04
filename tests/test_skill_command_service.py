from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

from rich.console import Console

# 待实现后取消注释
# from xcode_cli.core.commands.skill import SkillCommandService


def _make_console() -> Console:
    output = StringIO()
    # force_terminal=True 阻止 Rich 把 [enabled]/[disabled] 当 markup 吞掉
    return Console(file=output, force_terminal=True, width=120)


def _captured(console: Console) -> str:
    console.file.seek(0)
    return console.file.read()


class TestSkillCommandServiceList:
    """SkillCommandService.list() 行为测试"""

    def test_list_when_empty_outputs_no_skills_installed(self) -> None:
        """list() 在无 skill 时输出 'No skills installed.'"""
        from xcode_cli.core.commands.skill import SkillCommandService

        skill_manager = MagicMock()
        skill_manager.list_installed.return_value = []
        config_store = MagicMock()
        console = _make_console()

        svc = SkillCommandService(skill_manager, config_store, console)
        svc.list_installed()

        output = _captured(console)
        assert "No skills installed." in output

    def test_list_shows_installed_skills_with_status(self) -> None:
        """list() 展示已安装 skill 及其 enable/disable 状态"""
        from xcode_cli.core.commands.skill import SkillCommandService
        from xcode_cli.skills.manager import InstalledSkill

        skill_manager = MagicMock()
        skill_manager.list_installed.return_value = [
            InstalledSkill(name="foo", path=Path("/tmp/foo"), description="A foo skill"),
            InstalledSkill(name="bar", path=Path("/tmp/bar"), description="A bar skill"),
        ]
        config_store = MagicMock()
        config_store.load.return_value.enabled_skills = ["foo"]
        console = _make_console()

        svc = SkillCommandService(skill_manager, config_store, console)
        svc.list_installed()

        output = _captured(console)
        assert "foo" in output
        assert "bar" in output
        assert "enabled" in output
        assert "disabled" in output


class TestSkillCommandServiceInstall:
    """SkillCommandService.install() 行为测试"""

    def test_install_calls_skill_manager_and_outputs_installed(self) -> None:
        """install(path) 调用 SkillManager.install() 并输出 installed skill"""
        from xcode_cli.core.commands.skill import SkillCommandService
        from xcode_cli.skills.manager import InstalledSkill

        skill_manager = MagicMock()
        installed = InstalledSkill(name="myskill", path=Path("/tmp/skills/myskill"), description="A test skill")
        skill_manager.install.return_value = installed
        config_store = MagicMock()
        console = _make_console()

        svc = SkillCommandService(skill_manager, config_store, console)
        svc.install("/path/to/skill")

        skill_manager.install.assert_called_once_with("/path/to/skill")
        output = _captured(console)
        assert "Installed skill" in output
        assert "myskill" in output


class TestSkillCommandServiceEnable:
    """SkillCommandService.enable() 行为测试"""

    def test_enable_writes_to_config(self) -> None:
        """enable(name) 将 name 写入 Config.enabled_skills"""
        from xcode_cli.core.commands.skill import SkillCommandService

        skill_manager = MagicMock()
        config_store = MagicMock()
        cfg_mock = MagicMock()
        cfg_mock.enabled_skills = []
        config_store.load.return_value = cfg_mock
        console = _make_console()

        svc = SkillCommandService(skill_manager, config_store, console)
        svc.enable("foo")

        assert "foo" in cfg_mock.enabled_skills
        config_store.save.assert_called_once_with(cfg_mock)
        output = _captured(console)
        assert "Enabled skill" in output
        assert "foo" in output

    def test_enable_duplicate_does_not_add_twice(self) -> None:
        """重复 enable 同一 skill 不会重复添加"""
        from xcode_cli.core.commands.skill import SkillCommandService

        skill_manager = MagicMock()
        config_store = MagicMock()
        cfg_mock = MagicMock()
        cfg_mock.enabled_skills = ["foo"]
        config_store.load.return_value = cfg_mock
        console = _make_console()

        svc = SkillCommandService(skill_manager, config_store, console)
        svc.enable("foo")

        assert cfg_mock.enabled_skills == ["foo"]


class TestSkillCommandServiceDisable:
    """SkillCommandService.disable() 行为测试"""

    def test_disable_removes_from_config(self) -> None:
        """disable(name) 从 Config.enabled_skills 删除指定 skill"""
        from xcode_cli.core.commands.skill import SkillCommandService

        skill_manager = MagicMock()
        config_store = MagicMock()
        cfg_mock = MagicMock()
        cfg_mock.enabled_skills = ["foo", "bar"]
        config_store.load.return_value = cfg_mock
        console = _make_console()

        svc = SkillCommandService(skill_manager, config_store, console)
        svc.disable("foo")

        assert cfg_mock.enabled_skills == ["bar"]
        config_store.save.assert_called_once_with(cfg_mock)
        output = _captured(console)
        assert "Disabled skill" in output
        assert "foo" in output

    def test_disable_nonexistent_is_noop(self) -> None:
        """disable 不存在的 skill 不会崩溃"""
        from xcode_cli.core.commands.skill import SkillCommandService

        skill_manager = MagicMock()
        config_store = MagicMock()
        cfg_mock = MagicMock()
        cfg_mock.enabled_skills = ["foo"]
        config_store.load.return_value = cfg_mock
        console = _make_console()

        svc = SkillCommandService(skill_manager, config_store, console)
        svc.disable("nonexistent")

        assert cfg_mock.enabled_skills == ["foo"]


class TestSkillCommandServiceRun:
    """SkillCommandService.run() — REPL /skill 命令路由"""

    def test_run_with_no_args_shows_usage(self) -> None:
        """无子命令时显示用法"""
        from xcode_cli.core.commands.skill import SkillCommandService

        skill_manager = MagicMock()
        config_store = MagicMock()
        console = _make_console()

        svc = SkillCommandService(skill_manager, config_store, console)
        svc.run(["/skill"])

        output = _captured(console)
        assert "Usage" in output.lower() or "list" in output.lower() or "/skill" in output

    def test_run_list_delegates_to_list_installed(self) -> None:
        """/skill list 委托给 list_installed()"""
        from xcode_cli.core.commands.skill import SkillCommandService

        skill_manager = MagicMock()
        skill_manager.list_installed.return_value = []
        config_store = MagicMock()
        config_store.load.return_value.enabled_skills = []
        console = _make_console()

        svc = SkillCommandService(skill_manager, config_store, console)
        svc.run(["/skill", "list"])

        output = _captured(console)
        # 没有 skill 时应该显示 "No skills installed."
        assert "No skills installed." in output

    def test_run_install_delegates_to_install(self) -> None:
        """/skill install <path> 委托给 install()"""
        from xcode_cli.core.commands.skill import SkillCommandService
        from xcode_cli.skills.manager import InstalledSkill

        skill_manager = MagicMock()
        installed = InstalledSkill(name="foo", path=Path("/tmp/foo"), description="desc")
        skill_manager.install.return_value = installed
        config_store = MagicMock()
        console = _make_console()

        svc = SkillCommandService(skill_manager, config_store, console)
        svc.run(["/skill", "install", "/path/to/foo"])

        skill_manager.install.assert_called_once_with("/path/to/foo")

    def test_run_enable_delegates_to_enable(self) -> None:
        """/skill enable <name> 委托给 enable()"""
        from xcode_cli.core.commands.skill import SkillCommandService

        skill_manager = MagicMock()
        config_store = MagicMock()
        cfg_mock = MagicMock()
        cfg_mock.enabled_skills = []
        config_store.load.return_value = cfg_mock
        console = _make_console()

        svc = SkillCommandService(skill_manager, config_store, console)
        svc.run(["/skill", "enable", "foo"])

        assert "foo" in cfg_mock.enabled_skills

    def test_run_disable_delegates_to_disable(self) -> None:
        """/skill disable <name> 委托给 disable()"""
        from xcode_cli.core.commands.skill import SkillCommandService

        skill_manager = MagicMock()
        config_store = MagicMock()
        cfg_mock = MagicMock()
        cfg_mock.enabled_skills = ["foo"]
        config_store.load.return_value = cfg_mock
        console = _make_console()

        svc = SkillCommandService(skill_manager, config_store, console)
        svc.run(["/skill", "disable", "foo"])

        assert "foo" not in cfg_mock.enabled_skills

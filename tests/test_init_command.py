from __future__ import annotations

from prompt_toolkit.document import Document

from xcode_cli.core.commands.slash import INIT_PROMPT, PROMPT_COMMANDS, SlashCompleter, init_handler


def test_init_handler_returns_repository_initialization_prompt() -> None:
    prompt = init_handler("")

    assert prompt == INIT_PROMPT
    assert "create an XCODE.md file" in prompt
    assert "future instances of xcode" in prompt
    assert "AGENTS.md" in prompt
    assert "CLAUDE.md" in prompt
    assert ".github/copilot-instructions.md" in prompt
    assert "README.md" in prompt
    assert "# XCODE.md" in prompt
    assert "This file provides guidance to xcode" in prompt
    assert "which files you used as sources" in prompt


def test_init_is_registered_as_prompt_command() -> None:
    command = PROMPT_COMMANDS["/init"]

    assert command.name == "init"
    assert command.kind == "prompt"
    assert command.description == "Initialize a new XCODE.md file with codebase documentation"
    assert command.handler("") == INIT_PROMPT


def test_slash_completer_includes_init() -> None:
    completer = SlashCompleter()
    completions = list(completer.get_completions(Document("/in"), None))

    assert any(completion.text == "/init" for completion in completions)
    assert any("Initialize a new XCODE.md" in str(completion.display_text) for completion in completions)

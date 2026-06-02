"""Tests for SlashCommandResult."""
import pytest

from xcode_cli.core.commands.result import Redaction, SlashCommandResult


class TestSlashCommandResult:
    """Tests for SlashCommandResult."""

    def test_default_result(self):
        """Test default SlashCommandResult."""
        result = SlashCommandResult()
        assert result.display == "system"
        assert result.model_visible is False
        assert result.persist_ui is True
        assert result.should_start_agent_turn is False
        assert result.next_input is None
        assert result.submit_next_input is False
        assert result.redactions is None
        assert result.content == ""
        assert result.error is None

    def test_skip_result(self):
        """Test skip result factory."""
        result = SlashCommandResult.skip()
        assert result.display == "skip"
        assert result.persist_ui is False

    def test_system_result(self):
        """Test system result factory."""
        result = SlashCommandResult.system("System message")
        assert result.display == "system"
        assert result.content == "System message"
        assert result.model_visible is False
        assert result.persist_ui is True

    def test_system_result_model_visible(self):
        """Test system result with model_visible=True."""
        result = SlashCommandResult.system("System message", model_visible=True)
        assert result.model_visible is True

    def test_user_result(self):
        """Test user result factory."""
        result = SlashCommandResult.user("User message")
        assert result.display == "user"
        assert result.content == "User message"
        assert result.model_visible is True
        assert result.persist_ui is True

    def test_user_result_model_not_visible(self):
        """Test user result with model_visible=False."""
        result = SlashCommandResult.user("User message", model_visible=False)
        assert result.model_visible is False

    def test_prompt_expansion_result(self):
        """Test prompt expansion result factory."""
        result = SlashCommandResult.prompt_expansion("expanded input")
        assert result.display == "skip"
        assert result.next_input == "expanded input"
        assert result.submit_next_input is False
        assert result.persist_ui is False

    def test_prompt_expansion_with_submit(self):
        """Test prompt expansion result with submit."""
        result = SlashCommandResult.prompt_expansion("expanded input", submit=True)
        assert result.submit_next_input is True

    def test_prompt_expansion_with_display(self):
        """Test prompt expansion result with display."""
        result = SlashCommandResult.prompt_expansion(
            "expanded input",
            display="system",
        )
        assert result.display == "system"

    def test_agent_turn_result(self):
        """Test agent turn result factory."""
        result = SlashCommandResult.agent_turn("Agent turn content")
        assert result.display == "system"
        assert result.content == "Agent turn content"
        assert result.should_start_agent_turn is True
        assert result.persist_ui is True

    def test_agent_turn_result_default_content(self):
        """Test agent turn result with default content."""
        result = SlashCommandResult.agent_turn()
        assert result.content == ""

    def test_agent_turn_result_with_display(self):
        """Test agent turn result with display."""
        result = SlashCommandResult.agent_turn(display="user")
        assert result.display == "user"

    def test_error_result(self):
        """Test error result factory."""
        result = SlashCommandResult.error_result("Error message")
        assert result.display == "system"
        assert result.error == "Error message"
        assert result.persist_ui is True

    def test_with_redaction(self):
        """Test adding redaction metadata."""
        redactions = [
            Redaction(start=0, end=5, replacement="***"),
            Redaction(start=10, end=15, replacement="***"),
        ]
        result = SlashCommandResult.system("test").with_redaction(redactions)
        assert result.redactions == redactions

    def test_apply_redactions(self):
        """Test applying redactions to text."""
        redactions = [
            Redaction(start=0, end=5, replacement="***"),
            Redaction(start=10, end=15, replacement="***"),
        ]
        result = SlashCommandResult.system("test").with_redaction(redactions)
        text = "hello world foo bar"
        redacted = result.apply_redactions(text)
        # "hello" (0-5) -> "***", "d foo" (10-15) -> "***"
        assert redacted == "*** worl*** bar"

    def test_apply_redactions_no_redactions(self):
        """Test applying redactions when none exist."""
        result = SlashCommandResult.system("test")
        text = "hello world"
        redacted = result.apply_redactions(text)
        assert redacted == "hello world"

    def test_apply_redactions_reverse_order(self):
        """Test that redactions are applied in reverse order."""
        redactions = [
            Redaction(start=10, end=15, replacement="***"),
            Redaction(start=0, end=5, replacement="***"),
        ]
        result = SlashCommandResult.system("test").with_redaction(redactions)
        text = "hello world foo bar"
        redacted = result.apply_redactions(text)
        # "hello" (0-5) -> "***", "d foo" (10-15) -> "***"
        assert redacted == "*** worl*** bar"

    def test_local_display_only_command(self):
        """Test representing a local display-only command."""
        result = SlashCommandResult.system("Help content")
        assert result.display == "system"
        assert result.model_visible is False
        assert result.persist_ui is True
        assert result.should_start_agent_turn is False

    def test_prompt_expansion_without_immediate_submit(self):
        """Test representing prompt expansion without immediate submit."""
        result = SlashCommandResult.prompt_expansion("/compact", submit=False)
        assert result.next_input == "/compact"
        assert result.submit_next_input is False
        assert result.should_start_agent_turn is False

    def test_prompt_expansion_with_immediate_submit(self):
        """Test representing prompt expansion with immediate submit."""
        result = SlashCommandResult.prompt_expansion("some input", submit=True)
        assert result.next_input == "some input"
        assert result.submit_next_input is True

    def test_sensitive_result_with_redaction_metadata(self):
        """Test representing a sensitive result with redaction metadata."""
        redactions = [
            Redaction(start=0, end=10, replacement="***"),
        ]
        result = SlashCommandResult.user(
            "API_KEY=secret123 value"
        ).with_redaction(redactions)
        assert result.redactions is not None
        assert len(result.redactions) == 1
        assert result.redactions[0].start == 0
        assert result.redactions[0].end == 10

    def test_display_types(self):
        """Test valid display types."""
        for display in ["skip", "system", "user"]:
            result = SlashCommandResult(display=display)
            assert result.display == display

    def test_result_with_error(self):
        """Test result with error."""
        result = SlashCommandResult.error_result("Something went wrong")
        assert result.error == "Something went wrong"
        assert result.display == "system"
        assert result.persist_ui is True

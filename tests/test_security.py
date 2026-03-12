"""Tests for the security validator."""
from __future__ import annotations

import pytest

from matlab_mcp.config import SecurityConfig
from matlab_mcp.security.validator import BlockedFunctionError, SecurityValidator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_validator():
    """Validator using default SecurityConfig (blocking enabled)."""
    return SecurityValidator(SecurityConfig())


@pytest.fixture
def disabled_validator():
    """Validator with blocking disabled."""
    return SecurityValidator(SecurityConfig(blocked_functions_enabled=False))


@pytest.fixture
def custom_validator():
    """Validator blocking only 'system'."""
    return SecurityValidator(SecurityConfig(
        blocked_functions_enabled=True,
        blocked_functions=["system"],
    ))


# ---------------------------------------------------------------------------
# BlockedFunctionError
# ---------------------------------------------------------------------------

class TestBlockedFunctionError:
    def test_is_exception(self):
        err = BlockedFunctionError("blocked")
        assert isinstance(err, Exception)

    def test_message_preserved(self):
        err = BlockedFunctionError("not allowed")
        assert "not allowed" in str(err)


# ---------------------------------------------------------------------------
# check_code — blocked functions
# ---------------------------------------------------------------------------

class TestCheckCodeBlockedFunctions:
    def test_blocks_system_call(self, default_validator):
        with pytest.raises(BlockedFunctionError, match="system"):
            default_validator.check_code("result = system('ls');")

    def test_blocks_unix_call(self, default_validator):
        with pytest.raises(BlockedFunctionError, match="unix"):
            default_validator.check_code("[s, r] = unix('ls');")

    def test_blocks_dos_call(self, default_validator):
        with pytest.raises(BlockedFunctionError, match="dos"):
            default_validator.check_code("dos('dir');")

    def test_blocks_shell_escape(self, default_validator):
        with pytest.raises(BlockedFunctionError):
            default_validator.check_code("!ls -la")

    def test_blocks_shell_escape_with_leading_whitespace(self, default_validator):
        with pytest.raises(BlockedFunctionError):
            default_validator.check_code("   !ls")

    def test_blocks_shell_escape_multiline(self, default_validator):
        code = "x = 1;\n!rm -rf /;\ny = 2;"
        with pytest.raises(BlockedFunctionError):
            default_validator.check_code(code)


class TestCheckCodeAllowedCode:
    def test_allows_normal_arithmetic(self, default_validator):
        # Should not raise
        default_validator.check_code("x = 1 + 2;")

    def test_allows_matrix_ops(self, default_validator):
        default_validator.check_code("A = [1 2; 3 4]; b = A * A';")

    def test_allows_function_defs(self, default_validator):
        default_validator.check_code("function y = f(x)\n  y = x^2;\nend")

    def test_allows_for_loop(self, default_validator):
        default_validator.check_code("for i = 1:10\n  disp(i);\nend")

    def test_allows_comment_with_blocked_word(self, default_validator):
        # Comments should not trigger (they don't match the function call pattern)
        default_validator.check_code("% system('cmd') - this is a comment")

    def test_empty_code_allowed(self, default_validator):
        default_validator.check_code("")

    def test_allows_variable_named_system_ish(self, default_validator):
        # 'systematic' should not match 'system' due to word boundary
        default_validator.check_code("systematic = 5;")


class TestCheckCodeStringLiterals:
    def test_system_in_string_literal_allowed(self, default_validator):
        """'system' appearing inside a string should not be flagged."""
        default_validator.check_code("msg = 'call system for help';")

    def test_system_in_double_quoted_string_allowed(self, default_validator):
        default_validator.check_code('msg = "use system command";')

    def test_unix_in_string_allowed(self, default_validator):
        default_validator.check_code("desc = 'this is a unix-style path';")

    def test_blocked_function_after_string_is_caught(self, default_validator):
        """Blocked call after a string literal must still be detected."""
        with pytest.raises(BlockedFunctionError):
            default_validator.check_code("msg = 'hello'; system('cmd');")

    def test_exclamation_in_string_not_blocked(self, default_validator):
        """A ! inside a string should not trigger the shell escape check."""
        default_validator.check_code("msg = 'hello!';")


class TestCheckCodeDisabled:
    def test_disabled_allows_system(self, disabled_validator):
        # Should not raise
        disabled_validator.check_code("system('ls');")

    def test_disabled_allows_unix(self, disabled_validator):
        disabled_validator.check_code("unix('ls');")

    def test_disabled_allows_shell_escape(self, disabled_validator):
        disabled_validator.check_code("!ls")

    def test_disabled_allows_all_blocked(self, disabled_validator):
        disabled_validator.check_code("system('a'); unix('b'); dos('c'); !cmd")


class TestCheckCodeCustomBlocklist:
    def test_custom_blocks_system(self, custom_validator):
        with pytest.raises(BlockedFunctionError):
            custom_validator.check_code("system('ls');")

    def test_custom_allows_unix(self, custom_validator):
        # unix is not in the custom blocklist
        custom_validator.check_code("unix('ls');")

    def test_custom_allows_dos(self, custom_validator):
        custom_validator.check_code("dos('dir');")


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------

class TestSanitizeFilenameValid:
    def test_simple_name(self, default_validator):
        assert default_validator.sanitize_filename("script.m") == "script.m"

    def test_name_with_numbers(self, default_validator):
        assert default_validator.sanitize_filename("model123.mat") == "model123.mat"

    def test_name_with_hyphen(self, default_validator):
        assert default_validator.sanitize_filename("my-script.m") == "my-script.m"

    def test_name_with_underscore_via_dot(self, default_validator):
        assert default_validator.sanitize_filename("my_file.m") == "my_file.m"

    def test_uppercase(self, default_validator):
        assert default_validator.sanitize_filename("MyScript.M") == "MyScript.M"


class TestSanitizeFilenameInvalid:
    def test_empty_filename(self, default_validator):
        with pytest.raises(ValueError, match="empty"):
            default_validator.sanitize_filename("")

    def test_path_traversal_dotdot(self, default_validator):
        with pytest.raises(ValueError, match="traversal"):
            default_validator.sanitize_filename("../etc/passwd")

    def test_path_traversal_embedded(self, default_validator):
        with pytest.raises(ValueError, match="traversal"):
            default_validator.sanitize_filename("dir/../secret.m")

    def test_slash_in_filename(self, default_validator):
        with pytest.raises(ValueError):
            default_validator.sanitize_filename("dir/file.m")

    def test_backslash_in_filename(self, default_validator):
        with pytest.raises(ValueError):
            default_validator.sanitize_filename("dir\\file.m")

    def test_space_in_filename(self, default_validator):
        with pytest.raises(ValueError):
            default_validator.sanitize_filename("my script.m")

    def test_semicolon_in_filename(self, default_validator):
        with pytest.raises(ValueError):
            default_validator.sanitize_filename("file;name.m")

    def test_null_byte_in_filename(self, default_validator):
        with pytest.raises(ValueError):
            default_validator.sanitize_filename("file\x00name.m")

    def test_pipe_in_filename(self, default_validator):
        with pytest.raises(ValueError):
            default_validator.sanitize_filename("file|name.m")


class TestSecurityMonitoringEvents:
    def test_blocked_function_records_event(self):
        from unittest.mock import MagicMock
        from matlab_mcp.security.validator import SecurityValidator
        from matlab_mcp.config import load_config
        config = load_config(None)
        collector = MagicMock()
        validator = SecurityValidator(config.security, collector=collector)
        with pytest.raises(Exception):
            validator.check_code("result = system('ls')")
        collector.record_event.assert_called_once()
        assert collector.record_event.call_args[0][0] == "blocked_function"

    def test_no_collector_does_not_crash(self):
        from matlab_mcp.security.validator import SecurityValidator
        from matlab_mcp.config import load_config
        validator = SecurityValidator(load_config(None).security)
        with pytest.raises(Exception):
            validator.check_code("result = system('ls')")

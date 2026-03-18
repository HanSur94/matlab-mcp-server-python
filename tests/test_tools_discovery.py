"""Tests for toolbox and function discovery tool implementations."""
from __future__ import annotations

import pytest

from matlab_mcp.tools.discovery import (
    _validate_matlab_name,
    get_help_impl,
    list_functions_impl,
    list_toolboxes_impl,
)


# ---------------------------------------------------------------------------
# Helpers / Mocks
# ---------------------------------------------------------------------------


class MockExecutor:
    """Minimal executor that returns a canned result and records calls."""

    def __init__(self, result: dict | None = None) -> None:
        self._result = result or {
            "status": "completed",
            "job_id": "j-1",
            "text": "mock output",
        }
        self.calls: list[tuple[str, str]] = []

    async def execute(self, session_id: str, code: str) -> dict:
        self.calls.append((session_id, code))
        return self._result


class MockToolboxConfig:
    """Minimal stand-in for ToolboxesConfig."""

    def __init__(
        self,
        mode: str = "all",
        toolbox_list: list[str] | None = None,
    ) -> None:
        self.mode = mode
        self.list = toolbox_list or ["Signal Processing", "Image Processing"]


# ---------------------------------------------------------------------------
# _validate_matlab_name
# ---------------------------------------------------------------------------


class TestValidateMatlabName:
    """Validation of MATLAB identifiers / toolbox names."""

    # -- valid names --------------------------------------------------------

    @pytest.mark.parametrize(
        "name",
        [
            "fft",
            "myFunc",
            "toolbox_utils",
            "Signal Processing",
            "image/transforms",
            "pkg.subpkg.func",
            "a123",
            "A",
        ],
    )
    def test_valid_names_pass(self, name: str) -> None:
        safe, err = _validate_matlab_name(name, "function_name")
        assert err is None
        assert safe == name

    def test_valid_name_with_leading_trailing_spaces_stripped(self) -> None:
        safe, err = _validate_matlab_name("  fft  ", "function_name")
        assert err is None
        assert safe == "fft"

    def test_quotes_are_stripped_before_validation(self) -> None:
        """Single and double quotes should be removed before matching."""
        safe, err = _validate_matlab_name("'fft'", "function_name")
        assert err is None
        assert safe == "fft"

        safe, err = _validate_matlab_name('"plot"', "function_name")
        assert err is None
        assert safe == "plot"

    # -- invalid names ------------------------------------------------------

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "   ",
            ";drop table",
            "func;",
            "123abc",
            "!cmd",
            "@decorator",
            "$var",
            "(expr)",
        ],
    )
    def test_invalid_names_return_error(self, name: str) -> None:
        safe, err = _validate_matlab_name(name, "toolbox_name")
        assert safe is None
        assert err is not None
        assert err["status"] == "failed"
        assert "toolbox_name" in err
        assert "Invalid toolbox_name" in err["error"]

    def test_error_dict_uses_original_name(self) -> None:
        """The error dict should contain the raw caller-supplied name."""
        raw = ";malicious"
        _, err = _validate_matlab_name(raw, "function_name")
        assert err is not None
        assert err["function_name"] == raw

    def test_name_that_becomes_empty_after_quote_strip(self) -> None:
        """A name consisting only of quotes should fail validation."""
        safe, err = _validate_matlab_name("'''\"", "function_name")
        assert safe is None
        assert err is not None

    def test_label_appears_in_error_key_and_message(self) -> None:
        """The *label* argument should drive both the dict key and the message."""
        _, err = _validate_matlab_name("!!!", "my_label")
        assert err is not None
        assert "my_label" in err
        assert "Invalid my_label" in err["error"]


# ---------------------------------------------------------------------------
# list_toolboxes_impl
# ---------------------------------------------------------------------------


class TestListToolboxesImpl:
    """Tests for list_toolboxes_impl."""

    async def test_basic_call_returns_executor_result(self) -> None:
        executor = MockExecutor()
        result = await list_toolboxes_impl("s-1", executor)

        assert result["status"] == "completed"
        assert result["job_id"] == "j-1"
        assert result["text"] == "mock output"

    async def test_executor_receives_ver_command(self) -> None:
        executor = MockExecutor()
        await list_toolboxes_impl("s-1", executor)

        assert len(executor.calls) == 1
        session_id, code = executor.calls[0]
        assert session_id == "s-1"
        assert code == "ver"

    async def test_without_toolbox_config(self) -> None:
        """When no toolbox_config is passed, no extra keys should be added."""
        executor = MockExecutor()
        result = await list_toolboxes_impl("s-1", executor, toolbox_config=None)

        assert "toolbox_mode" not in result
        assert "toolbox_list" not in result

    async def test_with_toolbox_config(self) -> None:
        """Toolbox config info should be annotated onto the result dict."""
        executor = MockExecutor()
        config = MockToolboxConfig(mode="include", toolbox_list=["DSP System"])
        result = await list_toolboxes_impl("s-1", executor, toolbox_config=config)

        assert result["toolbox_mode"] == "include"
        assert result["toolbox_list"] == ["DSP System"]

    async def test_propagates_executor_status(self) -> None:
        """Executor failures should be propagated through."""
        executor = MockExecutor({"status": "failed", "job_id": "j-2", "text": ""})
        result = await list_toolboxes_impl("s-1", executor)

        assert result["status"] == "failed"

    async def test_missing_text_defaults_to_empty(self) -> None:
        """If the executor result omits 'text', the output should default to ''."""
        executor = MockExecutor({"status": "completed", "job_id": "j-3"})
        result = await list_toolboxes_impl("s-1", executor)

        assert result["text"] == ""


# ---------------------------------------------------------------------------
# list_functions_impl
# ---------------------------------------------------------------------------


class TestListFunctionsImpl:
    """Tests for list_functions_impl."""

    async def test_valid_toolbox_name(self) -> None:
        executor = MockExecutor()
        result = await list_functions_impl("Signal Processing", "s-1", executor)

        assert result["status"] == "completed"
        assert result["toolbox_name"] == "Signal Processing"
        assert result["text"] == "mock output"

    async def test_executor_receives_help_command(self) -> None:
        executor = MockExecutor()
        await list_functions_impl("signal", "s-1", executor)

        assert len(executor.calls) == 1
        _, code = executor.calls[0]
        assert code == "help signal"

    async def test_invalid_toolbox_name_returns_error(self) -> None:
        executor = MockExecutor()
        result = await list_functions_impl(";drop", "s-1", executor)

        assert result["status"] == "failed"
        assert "toolbox_name" in result
        assert "Invalid toolbox_name" in result["error"]
        # Executor should NOT have been called
        assert len(executor.calls) == 0

    async def test_empty_toolbox_name_returns_error(self) -> None:
        executor = MockExecutor()
        result = await list_functions_impl("", "s-1", executor)

        assert result["status"] == "failed"
        assert len(executor.calls) == 0

    async def test_result_contains_original_toolbox_name(self) -> None:
        """The result dict should carry the original name, not the sanitised one."""
        executor = MockExecutor()
        result = await list_functions_impl("  signal  ", "s-1", executor)

        # Original name preserved in result; sanitised name used in command
        assert result["toolbox_name"] == "  signal  "

    async def test_dotted_toolbox_name_accepted(self) -> None:
        executor = MockExecutor()
        result = await list_functions_impl("pkg.subpkg", "s-1", executor)

        assert result["status"] == "completed"
        _, code = executor.calls[0]
        assert code == "help pkg.subpkg"


# ---------------------------------------------------------------------------
# get_help_impl
# ---------------------------------------------------------------------------


class TestGetHelpImpl:
    """Tests for get_help_impl."""

    async def test_valid_function_name(self) -> None:
        executor = MockExecutor(
            {"status": "completed", "job_id": "j-help", "text": "FFT help text"}
        )
        result = await get_help_impl("fft", "s-1", executor)

        assert result["status"] == "completed"
        assert result["function_name"] == "fft"
        assert result["text"] == "FFT help text"

    async def test_executor_receives_help_command(self) -> None:
        executor = MockExecutor()
        await get_help_impl("plot", "s-1", executor)

        assert len(executor.calls) == 1
        session_id, code = executor.calls[0]
        assert session_id == "s-1"
        assert code == "help plot"

    async def test_invalid_function_name_returns_error(self) -> None:
        executor = MockExecutor()
        result = await get_help_impl(";malicious", "s-1", executor)

        assert result["status"] == "failed"
        assert "function_name" in result
        assert "Invalid function_name" in result["error"]
        assert len(executor.calls) == 0

    async def test_empty_function_name_returns_error(self) -> None:
        executor = MockExecutor()
        result = await get_help_impl("", "s-1", executor)

        assert result["status"] == "failed"
        assert len(executor.calls) == 0

    async def test_function_name_with_quotes_sanitised(self) -> None:
        """Quotes should be stripped; the cleaned name should reach the executor."""
        executor = MockExecutor()
        result = await get_help_impl("'fft'", "s-1", executor)

        assert result["status"] == "completed"
        _, code = executor.calls[0]
        assert code == "help fft"

    async def test_result_preserves_original_function_name(self) -> None:
        executor = MockExecutor()
        result = await get_help_impl("'fft'", "s-1", executor)

        # The result dict should contain the caller's original value
        assert result["function_name"] == "'fft'"

    async def test_propagates_executor_failure(self) -> None:
        executor = MockExecutor(
            {"status": "failed", "job_id": "j-err", "text": "Function not found"}
        )
        result = await get_help_impl("nonexistent", "s-1", executor)

        assert result["status"] == "failed"
        assert result["text"] == "Function not found"

    async def test_slashed_function_name_accepted(self) -> None:
        executor = MockExecutor()
        result = await get_help_impl("toolbox/func", "s-1", executor)

        assert result["status"] == "completed"
        _, code = executor.calls[0]
        assert code == "help toolbox/func"

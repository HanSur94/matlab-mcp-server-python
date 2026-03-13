"""Tests for output formatter, thumbnail, and plotly_convert modules."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import pytest

from matlab_mcp.config import AppConfig, OutputConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(max_inline: int = 100, large_threshold: int = 10) -> AppConfig:
    """Return an AppConfig with custom output settings."""
    config = AppConfig()
    config.output = OutputConfig(
        max_inline_text_length=max_inline,
        large_result_threshold=large_threshold,
    )
    return config


# ---------------------------------------------------------------------------
# ResultFormatter.format_text
# ---------------------------------------------------------------------------

class TestFormatText:
    def test_short_text_inline(self):
        """Text shorter than max_inline_text_length should be returned inline."""
        from matlab_mcp.output.formatter import ResultFormatter

        config = _make_config(max_inline=100)
        fmt = ResultFormatter(config)

        result = fmt.format_text("hello world")

        assert result["inline"] == "hello world"
        assert result["truncated"] is False
        assert result["saved_path"] is None

    def test_exact_length_inline(self):
        """Text exactly at the limit should not be truncated."""
        from matlab_mcp.output.formatter import ResultFormatter

        config = _make_config(max_inline=10)
        fmt = ResultFormatter(config)

        result = fmt.format_text("1234567890")

        assert result["truncated"] is False
        assert result["inline"] == "1234567890"

    def test_long_text_truncated(self):
        """Text longer than max_inline_text_length should be truncated."""
        from matlab_mcp.output.formatter import ResultFormatter

        config = _make_config(max_inline=10)
        fmt = ResultFormatter(config)

        long_text = "A" * 50
        result = fmt.format_text(long_text)

        assert result["truncated"] is True
        assert len(result["inline"]) == 10
        assert result["inline"] == "A" * 10

    def test_truncated_text_saved_to_file(self, tmp_path):
        """Truncated text should be saved when save_dir is provided."""
        from matlab_mcp.output.formatter import ResultFormatter

        config = _make_config(max_inline=5)
        fmt = ResultFormatter(config)

        long_text = "B" * 20
        result = fmt.format_text(long_text, save_dir=str(tmp_path))

        assert result["truncated"] is True
        assert result["saved_path"] is not None
        saved = Path(result["saved_path"])
        assert saved.exists()
        assert saved.read_text(encoding="utf-8") == long_text

    def test_truncated_text_no_save_without_dir(self):
        """Without save_dir, truncated text should have saved_path = None."""
        from matlab_mcp.output.formatter import ResultFormatter

        config = _make_config(max_inline=5)
        fmt = ResultFormatter(config)

        long_text = "C" * 20
        result = fmt.format_text(long_text)

        assert result["truncated"] is True
        assert result["saved_path"] is None

    def test_empty_text_inline(self):
        """Empty string should be returned inline without truncation."""
        from matlab_mcp.output.formatter import ResultFormatter

        config = _make_config(max_inline=10)
        fmt = ResultFormatter(config)

        result = fmt.format_text("")

        assert result["inline"] == ""
        assert result["truncated"] is False


# ---------------------------------------------------------------------------
# ResultFormatter.format_variables
# ---------------------------------------------------------------------------

class TestFormatVariables:
    def test_empty_variables(self):
        """format_variables with empty dict should return empty list."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config())
        result = fmt.format_variables({})
        assert result == []

    def test_scalar_variable(self):
        """Scalar numeric variable should include value inline."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config(large_threshold=100))
        result = fmt.format_variables({"x": 42})

        assert len(result) == 1
        entry = result[0]
        assert entry["name"] == "x"
        assert entry["type"] == "int"
        assert entry["value"] == 42

    def test_string_variable(self):
        """String variable should include value inline."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config(large_threshold=100))
        result = fmt.format_variables({"msg": "hello"})

        entry = result[0]
        assert entry["name"] == "msg"
        assert entry["type"] == "str"
        assert entry["value"] == "hello"

    def test_large_list_truncated(self):
        """List larger than large_result_threshold should show placeholder value."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config(large_threshold=5))
        big_list = list(range(100))
        result = fmt.format_variables({"data": big_list})

        entry = result[0]
        assert entry["name"] == "data"
        # Value should be the placeholder string, not the actual list
        assert isinstance(entry["value"], str)
        assert "list" in entry["value"]

    def test_multiple_variables(self):
        """Multiple variables should all be represented."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config(large_threshold=100))
        result = fmt.format_variables({"a": 1, "b": 2.5, "c": "text"})

        names = [e["name"] for e in result]
        assert "a" in names
        assert "b" in names
        assert "c" in names

    def test_variable_has_required_keys(self):
        """Each variable entry should have name, type, size, value."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config())
        result = fmt.format_variables({"x": 1})

        entry = result[0]
        assert "name" in entry
        assert "type" in entry
        assert "size" in entry
        assert "value" in entry


# ---------------------------------------------------------------------------
# ResultFormatter.build_success_response
# ---------------------------------------------------------------------------

class TestBuildSuccessResponse:
    def test_success_response_status(self):
        """build_success_response should have status='completed'."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config())
        response = fmt.build_success_response(
            job_id="j-001",
            text="result",
            variables={},
            figures=[],
            files=[],
            warnings=[],
            execution_time=1.5,
        )

        assert response["status"] == "completed"

    def test_success_response_job_id(self):
        """build_success_response should include job_id."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config())
        response = fmt.build_success_response(
            job_id="j-123",
            text="",
            variables={},
            figures=[],
            files=[],
            warnings=[],
            execution_time=None,
        )

        assert response["job_id"] == "j-123"

    def test_success_response_output_key(self):
        """build_success_response should include formatted output."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config())
        response = fmt.build_success_response(
            job_id="j-001",
            text="hello",
            variables={},
            figures=[],
            files=[],
            warnings=[],
            execution_time=0.1,
        )

        assert "output" in response
        assert response["output"]["inline"] == "hello"

    def test_success_response_variables_formatted(self):
        """build_success_response should include formatted variables list."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config(large_threshold=1000))
        response = fmt.build_success_response(
            job_id="j-001",
            text="",
            variables={"x": 42},
            figures=[],
            files=[],
            warnings=[],
            execution_time=0.0,
        )

        assert isinstance(response["variables"], list)
        assert len(response["variables"]) == 1
        assert response["variables"][0]["name"] == "x"

    def test_success_response_figures_and_files(self):
        """build_success_response should pass figures and files through."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config())
        fig = {"type": "scatter", "data": []}
        response = fmt.build_success_response(
            job_id="j-001",
            text="",
            variables={},
            figures=[fig],
            files=["/tmp/out.mat"],
            warnings=["a warning"],
            execution_time=2.0,
        )

        assert response["figures"] == [fig]
        assert response["files"] == ["/tmp/out.mat"]
        assert response["warnings"] == ["a warning"]
        assert response["execution_time"] == 2.0

    def test_success_response_all_keys_present(self):
        """build_success_response should contain all expected keys."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config())
        response = fmt.build_success_response(
            job_id="j-001",
            text="",
            variables={},
            figures=[],
            files=[],
            warnings=[],
            execution_time=None,
        )

        expected_keys = {"status", "job_id", "output", "variables",
                         "figures", "files", "warnings", "execution_time"}
        assert expected_keys.issubset(response.keys())


# ---------------------------------------------------------------------------
# ResultFormatter.build_error_response
# ---------------------------------------------------------------------------

class TestBuildErrorResponse:
    def test_error_response_status(self):
        """build_error_response should have status='failed'."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config())
        response = fmt.build_error_response(
            job_id="j-err",
            error_type="MatlabError",
            message="something broke",
            execution_time=0.5,
        )

        assert response["status"] == "failed"

    def test_error_response_job_id(self):
        """build_error_response should include job_id."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config())
        response = fmt.build_error_response(
            job_id="j-err-42",
            error_type="TypeError",
            message="bad type",
            execution_time=None,
        )

        assert response["job_id"] == "j-err-42"

    def test_error_response_error_dict(self):
        """build_error_response should contain nested error dict."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config())
        response = fmt.build_error_response(
            job_id="j-001",
            error_type="MatlabExecutionError",
            message="Undefined variable",
            execution_time=1.0,
            matlab_id="MATLAB:UndefinedVariable",
            stack_trace="at line 3",
        )

        error = response["error"]
        assert error["type"] == "MatlabExecutionError"
        assert error["message"] == "Undefined variable"
        assert error["matlab_id"] == "MATLAB:UndefinedVariable"
        assert error["stack_trace"] == "at line 3"

    def test_error_response_optional_fields_none(self):
        """build_error_response should set matlab_id/stack_trace to None when omitted."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config())
        response = fmt.build_error_response(
            job_id="j-001",
            error_type="RuntimeError",
            message="crash",
            execution_time=None,
        )

        assert response["error"]["matlab_id"] is None
        assert response["error"]["stack_trace"] is None

    def test_error_response_execution_time(self):
        """build_error_response should include execution_time."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config())
        response = fmt.build_error_response(
            job_id="j-001",
            error_type="Error",
            message="oops",
            execution_time=3.14,
        )

        assert response["execution_time"] == 3.14

    def test_error_response_all_keys_present(self):
        """build_error_response should contain all expected keys."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config())
        response = fmt.build_error_response(
            job_id="j-001",
            error_type="Error",
            message="oops",
            execution_time=None,
        )

        expected_keys = {"status", "job_id", "error", "execution_time"}
        assert expected_keys.issubset(response.keys())


# ---------------------------------------------------------------------------
# Thumbnail
# ---------------------------------------------------------------------------

class TestGenerateThumbnail:
    def _make_png(self, tmp_path: Path, width: int = 800, height: int = 600) -> Path:
        """Create a minimal PNG image file for testing."""
        from PIL import Image

        img = Image.new("RGB", (width, height), color=(128, 64, 32))
        path = tmp_path / "test.png"
        img.save(str(path))
        return path

    def test_returns_base64_string(self, tmp_path):
        """generate_thumbnail should return a non-empty base64 string."""
        from matlab_mcp.output.thumbnail import generate_thumbnail

        img_path = self._make_png(tmp_path)
        result = generate_thumbnail(str(img_path), max_width=200)

        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_result_is_valid_base64(self, tmp_path):
        """generate_thumbnail result should be valid base64."""
        from matlab_mcp.output.thumbnail import generate_thumbnail

        img_path = self._make_png(tmp_path)
        result = generate_thumbnail(str(img_path), max_width=200)

        assert result is not None
        decoded = base64.b64decode(result)
        assert len(decoded) > 0

    def test_thumbnail_width_constrained(self, tmp_path):
        """Thumbnail should be at most max_width pixels wide."""
        from PIL import Image
        from matlab_mcp.output.thumbnail import generate_thumbnail

        img_path = self._make_png(tmp_path, width=800, height=600)
        result = generate_thumbnail(str(img_path), max_width=100)

        assert result is not None
        decoded = base64.b64decode(result)
        img = Image.open(io.BytesIO(decoded))
        assert img.width <= 100

    def test_small_image_not_enlarged(self, tmp_path):
        """Image smaller than max_width should not be enlarged."""
        from PIL import Image
        from matlab_mcp.output.thumbnail import generate_thumbnail

        img_path = self._make_png(tmp_path, width=50, height=30)
        result = generate_thumbnail(str(img_path), max_width=400)

        assert result is not None
        decoded = base64.b64decode(result)
        img = Image.open(io.BytesIO(decoded))
        assert img.width == 50

    def test_nonexistent_file_returns_none(self, tmp_path):
        """generate_thumbnail should return None for a non-existent file."""
        from matlab_mcp.output.thumbnail import generate_thumbnail

        result = generate_thumbnail(str(tmp_path / "missing.png"))
        assert result is None


# ---------------------------------------------------------------------------
# Plotly JSON loader
# ---------------------------------------------------------------------------

class TestLoadPlotlyJson:
    def test_load_valid_json_with_schema_version(self, tmp_path):
        """load_plotly_json should parse a valid JSON file with schema_version 1."""
        from matlab_mcp.output.plotly_convert import load_plotly_json

        data = {"schema_version": 1, "layout_type": "single", "axes": []}
        json_file = tmp_path / "fig.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        result = load_plotly_json(str(json_file))

        assert result is not None
        assert result["schema_version"] == 1

    def test_load_missing_schema_version_returns_none(self, tmp_path):
        """load_plotly_json should return None when schema_version is absent."""
        from matlab_mcp.output.plotly_convert import load_plotly_json

        data = {"data": [{"type": "scatter"}], "layout": {}}
        json_file = tmp_path / "fig.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        result = load_plotly_json(str(json_file))
        assert result is None

    def test_load_future_schema_version_returns_none(self, tmp_path):
        """load_plotly_json should return None for unsupported schema_version."""
        from matlab_mcp.output.plotly_convert import load_plotly_json

        data = {"schema_version": 99, "layout_type": "single", "axes": []}
        json_file = tmp_path / "fig.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        result = load_plotly_json(str(json_file))
        assert result is None

    def test_load_empty_dict_returns_none(self, tmp_path):
        """load_plotly_json should return None for {} (no schema_version)."""
        from matlab_mcp.output.plotly_convert import load_plotly_json

        empty_file = tmp_path / "empty.json"
        empty_file.write_text("{}", encoding="utf-8")

        result = load_plotly_json(str(empty_file))
        assert result is None

    def test_load_missing_file_returns_none(self, tmp_path):
        """load_plotly_json should return None for a non-existent file."""
        from matlab_mcp.output.plotly_convert import load_plotly_json

        result = load_plotly_json(str(tmp_path / "missing.json"))
        assert result is None

    def test_load_invalid_json_returns_none(self, tmp_path):
        """load_plotly_json should return None for invalid JSON."""
        from matlab_mcp.output.plotly_convert import load_plotly_json

        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json", encoding="utf-8")

        result = load_plotly_json(str(bad_file))
        assert result is None

    def test_load_non_dict_json_returns_none(self, tmp_path):
        """load_plotly_json should return None for a JSON list."""
        from matlab_mcp.output.plotly_convert import load_plotly_json

        list_file = tmp_path / "list.json"
        list_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        result = load_plotly_json(str(list_file))
        assert result is None

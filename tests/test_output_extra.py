"""Extra coverage tests for output/formatter.py and output/thumbnail.py.

Targets uncovered lines:
- formatter.py: 81-82 (save_dir write failure), 116-119 (shape attribute),
  130-131 (non-JSON-serializable values)
- thumbnail.py: 40-42 (Pillow ImportError), 53 (RGBA conversion),
  67-69 (image open failure)
"""
from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from matlab_mcp.config import AppConfig, OutputConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(max_inline: int = 100, large_threshold: int = 10) -> AppConfig:
    config = AppConfig()
    config.output = OutputConfig(
        max_inline_text_length=max_inline,
        large_result_threshold=large_threshold,
    )
    return config


# ---------------------------------------------------------------------------
# formatter.py — format_text: save_dir write failure (lines 81-82)
# ---------------------------------------------------------------------------

class TestFormatTextSaveDirFailure:
    def test_truncated_text_save_failure_returns_none_saved_path(self, tmp_path):
        """When the save_dir write raises, saved_path should be None."""
        from matlab_mcp.output.formatter import ResultFormatter

        config = _make_config(max_inline=5)
        fmt = ResultFormatter(config)

        # Use a path that cannot be written to (file masquerading as directory)
        blocker = tmp_path / "blocker"
        blocker.write_text("I am a file, not a directory")
        # On most systems, trying to mkdir inside a file path will fail
        bad_dir = str(blocker / "subdir")

        long_text = "X" * 20
        result = fmt.format_text(long_text, save_dir=bad_dir)

        assert result["truncated"] is True
        assert result["saved_path"] is None
        assert len(result["inline"]) == 5


# ---------------------------------------------------------------------------
# formatter.py — format_variables: shape attribute (lines 116-119)
# ---------------------------------------------------------------------------

class TestFormatVariablesShapeAttribute:
    def test_object_with_shape_attribute(self):
        """Variables with a .shape attribute should use shape for size."""
        from matlab_mcp.output.formatter import ResultFormatter

        class FakeArray:
            """Mimics a numpy-like array with a shape attribute."""
            shape = (3, 4)

        fmt = ResultFormatter(_make_config(large_threshold=100))
        result = fmt.format_variables({"arr": FakeArray()})

        assert len(result) == 1
        entry = result[0]
        assert entry["name"] == "arr"
        assert entry["size"] == [3, 4]
        # size is 3*4=12, which is <= 100, so value should be present
        assert "value" in entry

    def test_object_with_shape_exceeds_threshold(self):
        """Large shaped object should show placeholder value."""
        from matlab_mcp.output.formatter import ResultFormatter

        class BigArray:
            shape = (1000, 1000)

        fmt = ResultFormatter(_make_config(large_threshold=100))
        result = fmt.format_variables({"big": BigArray()})

        entry = result[0]
        assert entry["size"] == [1000, 1000]
        assert isinstance(entry["value"], str)
        assert "1000000" in entry["value"]  # 1000*1000 elements


# ---------------------------------------------------------------------------
# formatter.py — format_variables: non-JSON-serializable (lines 130-131)
# ---------------------------------------------------------------------------

class TestFormatVariablesNonSerializable:
    def test_non_json_serializable_value_uses_str(self):
        """Values that cannot be JSON-serialized should fall back to str()."""
        from matlab_mcp.output.formatter import ResultFormatter

        class Custom:
            def __str__(self):
                return "CustomObj<42>"

        fmt = ResultFormatter(_make_config(large_threshold=100))
        result = fmt.format_variables({"obj": Custom()})

        entry = result[0]
        assert entry["name"] == "obj"
        assert entry["value"] == "CustomObj<42>"

    def test_set_value_uses_str_fallback(self):
        """A set is not JSON-serializable; should fall back to str()."""
        from matlab_mcp.output.formatter import ResultFormatter

        fmt = ResultFormatter(_make_config(large_threshold=100))
        result = fmt.format_variables({"s": {1, 2, 3}})

        entry = result[0]
        assert entry["name"] == "s"
        # set is not JSON serializable, so value should be str representation
        assert isinstance(entry["value"], str)


# ---------------------------------------------------------------------------
# thumbnail.py — Pillow ImportError (lines 40-42)
# ---------------------------------------------------------------------------

class TestThumbnailPillowUnavailable:
    def test_returns_none_when_pillow_missing(self, tmp_path):
        """generate_thumbnail returns None when Pillow is not importable."""
        from matlab_mcp.output import thumbnail

        # Create a real image file so the path exists
        img_file = tmp_path / "test.png"
        img_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "PIL" or name == "PIL.Image":
                raise ImportError("mocked: no Pillow")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            # We need to reload the function's local import to trigger the ImportError.
            # Since PIL is imported lazily inside the function, patching __import__ works.
            result = thumbnail.generate_thumbnail(str(img_file))

        assert result is None


# ---------------------------------------------------------------------------
# thumbnail.py — RGBA conversion (line 53)
# ---------------------------------------------------------------------------

class TestThumbnailRGBAConversion:
    def test_rgba_image_converted(self, tmp_path):
        """An RGBA image should be converted to RGB and returned as base64 PNG."""
        from PIL import Image

        from matlab_mcp.output.thumbnail import generate_thumbnail

        img = Image.new("RGBA", (200, 100), color=(128, 64, 32, 200))
        img_path = tmp_path / "rgba_test.png"
        img.save(str(img_path))

        result = generate_thumbnail(str(img_path), max_width=100)

        assert result is not None
        decoded = base64.b64decode(result)
        thumb = Image.open(io.BytesIO(decoded))
        assert thumb.width <= 100

    def test_palette_mode_image_converted(self, tmp_path):
        """A palette-mode (P) image should be converted to RGB."""
        from PIL import Image

        from matlab_mcp.output.thumbnail import generate_thumbnail

        img = Image.new("P", (200, 100))
        img_path = tmp_path / "palette_test.png"
        img.save(str(img_path))

        result = generate_thumbnail(str(img_path), max_width=100)

        assert result is not None


# ---------------------------------------------------------------------------
# thumbnail.py — image open failure (lines 67-69)
# ---------------------------------------------------------------------------

class TestThumbnailOpenFailure:
    def test_corrupt_file_returns_none(self, tmp_path):
        """generate_thumbnail returns None for a corrupt/unreadable image file."""
        from matlab_mcp.output.thumbnail import generate_thumbnail

        bad_file = tmp_path / "corrupt.png"
        bad_file.write_bytes(b"this is not a valid image at all")

        result = generate_thumbnail(str(bad_file))

        assert result is None

    def test_nonexistent_file_returns_none(self):
        """generate_thumbnail returns None for a path that does not exist."""
        from matlab_mcp.output.thumbnail import generate_thumbnail

        result = generate_thumbnail("/tmp/definitely_nonexistent_image_12345.png")

        assert result is None

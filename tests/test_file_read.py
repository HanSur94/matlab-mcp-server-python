"""Tests for file read tools (read_script, read_data, read_image)."""
from __future__ import annotations

import base64
from unittest.mock import AsyncMock

import pytest
from pathlib import Path

from matlab_mcp.security.validator import SecurityValidator
from matlab_mcp.config import SecurityConfig
from matlab_mcp.tools.files import read_script_impl, read_image_impl, read_data_impl


@pytest.fixture
def security():
    return SecurityValidator(SecurityConfig())


@pytest.fixture
def tmp_session_dir(tmp_path):
    d = tmp_path / "session_temp"
    d.mkdir()
    return str(d)


class TestReadScript:
    async def test_success(self, security, tmp_session_dir):
        """Reads a .m file and returns its text content."""
        p = Path(tmp_session_dir) / "test_script.m"
        p.write_text("x = magic(3);\ndisp(x);", encoding="utf-8")
        result = await read_script_impl(
            filename="test_script.m",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_inline_text_length=50000,
        )
        assert result["status"] == "ok"
        assert "x = magic(3)" in result["content"]

    async def test_not_found(self, security, tmp_session_dir):
        """Returns error when file doesn't exist."""
        result = await read_script_impl(
            filename="missing.m",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_inline_text_length=50000,
        )
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    async def test_invalid_extension(self, security, tmp_session_dir):
        """Rejects non-.m files."""
        p = Path(tmp_session_dir) / "data.csv"
        p.write_text("a,b,c", encoding="utf-8")
        result = await read_script_impl(
            filename="data.csv",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_inline_text_length=50000,
        )
        assert result["status"] == "error"
        assert ".m" in result["message"]

    async def test_case_insensitive_extension(self, security, tmp_session_dir):
        """Accepts uppercase .M extension."""
        p = Path(tmp_session_dir) / "Script.M"
        p.write_text("disp('hello');", encoding="utf-8")
        result = await read_script_impl(
            filename="Script.M",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_inline_text_length=50000,
        )
        assert result["status"] == "ok"

    async def test_path_traversal(self, security, tmp_session_dir):
        """Rejects path traversal attempts."""
        result = await read_script_impl(
            filename="../../etc/passwd",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_inline_text_length=50000,
        )
        assert result["status"] == "error"

    async def test_truncation(self, security, tmp_session_dir):
        """Truncates content that exceeds max_inline_text_length."""
        p = Path(tmp_session_dir) / "big.m"
        p.write_text("x" * 1000, encoding="utf-8")
        result = await read_script_impl(
            filename="big.m",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_inline_text_length=100,
        )
        assert result["status"] == "ok"
        assert len(result["content"]) == 100
        assert "truncated" in result.get("message", "").lower()


class TestReadImage:
    async def test_png(self, security, tmp_session_dir):
        """Returns Image object for PNG files."""
        import struct
        import zlib

        def make_png():
            sig = b"\x89PNG\r\n\x1a\n"
            ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
            ihdr_crc = struct.pack(
                ">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
            )
            ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + ihdr_crc
            raw = b"\x00\x00\x00\x00"
            idat_data = zlib.compress(raw)
            idat_crc = struct.pack(
                ">I", zlib.crc32(b"IDAT" + idat_data) & 0xFFFFFFFF
            )
            idat = (
                struct.pack(">I", len(idat_data)) + b"IDAT" + idat_data + idat_crc
            )
            iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
            iend = struct.pack(">I", 0) + b"IEND" + iend_crc
            return sig + ihdr + idat + iend

        p = Path(tmp_session_dir) / "plot.png"
        p.write_bytes(make_png())
        result = await read_image_impl(
            filename="plot.png",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_size_mb=100,
        )
        from fastmcp.utilities.types import Image

        assert isinstance(result, Image)
        assert result._mime_type == "image/png"

    async def test_jpg(self, security, tmp_session_dir):
        """Returns Image object for JPEG files."""
        from PIL import Image as PILImage
        import io

        img = PILImage.new("RGB", (2, 2), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        p = Path(tmp_session_dir) / "photo.jpg"
        p.write_bytes(buf.getvalue())
        result = await read_image_impl(
            filename="photo.jpg",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_size_mb=100,
        )
        from fastmcp.utilities.types import Image

        assert isinstance(result, Image)
        assert result._mime_type == "image/jpeg"

    async def test_not_found(self, security, tmp_session_dir):
        """Returns error dict when file doesn't exist."""
        result = await read_image_impl(
            filename="missing.png",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_size_mb=100,
        )
        assert isinstance(result, dict)
        assert result["status"] == "error"

    async def test_invalid_extension(self, security, tmp_session_dir):
        """Rejects non-image files."""
        p = Path(tmp_session_dir) / "data.csv"
        p.write_text("a,b,c")
        result = await read_image_impl(
            filename="data.csv",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_size_mb=100,
        )
        assert isinstance(result, dict)
        assert result["status"] == "error"

    async def test_path_traversal(self, security, tmp_session_dir):
        """Rejects path traversal."""
        result = await read_image_impl(
            filename="../../etc/passwd",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_size_mb=100,
        )
        assert isinstance(result, dict)
        assert result["status"] == "error"


@pytest.fixture
def mock_executor():
    executor = AsyncMock()
    executor.execute = AsyncMock(return_value={
        "status": "completed",
        "output": "Name      Size       Bytes  Class\nx         3x3          72  double\ny         1x10         80  double\n",
    })
    return executor


class TestReadData:
    async def test_csv_summary(self, security, tmp_session_dir, mock_executor):
        p = Path(tmp_session_dir) / "data.csv"
        p.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
        result = await read_data_impl(
            filename="data.csv",
            format="summary",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_size_mb=100,
            max_inline_text_length=50000,
            executor=mock_executor,
            session_id="test-session",
        )
        assert result["status"] == "ok"
        assert "a,b,c" in result["content"]

    async def test_csv_raw(self, security, tmp_session_dir, mock_executor):
        p = Path(tmp_session_dir) / "data.csv"
        p.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
        result = await read_data_impl(
            filename="data.csv",
            format="raw",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_size_mb=100,
            max_inline_text_length=50000,
            executor=mock_executor,
            session_id="test-session",
        )
        assert result["status"] == "ok"
        assert "a,b,c" in result["content"]

    async def test_mat_summary(self, security, tmp_session_dir, mock_executor):
        p = Path(tmp_session_dir) / "data.mat"
        p.write_bytes(b"fake-mat-content")
        result = await read_data_impl(
            filename="data.mat",
            format="summary",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_size_mb=100,
            max_inline_text_length=50000,
            executor=mock_executor,
            session_id="test-session",
        )
        assert result["status"] == "ok"
        mock_executor.execute.assert_called_once()
        call_args = mock_executor.execute.call_args
        # Check that whos was called (could be positional or keyword)
        code_arg = call_args.kwargs.get("code", "") or (
            call_args.args[1] if len(call_args.args) > 1 else ""
        )
        assert "whos" in code_arg

    async def test_mat_raw(self, security, tmp_session_dir, mock_executor):
        content = b"fake-mat-content"
        p = Path(tmp_session_dir) / "data.mat"
        p.write_bytes(content)
        result = await read_data_impl(
            filename="data.mat",
            format="raw",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_size_mb=100,
            max_inline_text_length=50000,
            executor=mock_executor,
            session_id="test-session",
        )
        assert result["status"] == "ok"
        assert result["encoding"] == "base64"
        decoded = base64.b64decode(result["content"])
        assert decoded == content

    async def test_not_found(self, security, tmp_session_dir, mock_executor):
        result = await read_data_impl(
            filename="missing.csv",
            format="summary",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_size_mb=100,
            max_inline_text_length=50000,
            executor=mock_executor,
            session_id="test-session",
        )
        assert result["status"] == "error"

    async def test_xlsx_returns_base64(self, security, tmp_session_dir, mock_executor):
        p = Path(tmp_session_dir) / "sheet.xlsx"
        p.write_bytes(b"PK\x03\x04fake-xlsx")
        result = await read_data_impl(
            filename="sheet.xlsx",
            format="summary",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_size_mb=100,
            max_inline_text_length=50000,
            executor=mock_executor,
            session_id="test-session",
        )
        assert result["status"] == "ok"
        assert result["encoding"] == "base64"

"""Tests for file management tools: upload, delete, list, and uncovered read paths.

Covers the lines in tools/files.py not exercised by test_file_read.py:
- upload_data_impl  (lines 54-95)
- delete_file_impl  (lines 125-151)
- list_files_impl   (lines 174-196)
- read_data_impl    additional branches (.mat raw, .xlsx binary, text truncation,
                    unicode decode error, unsupported extension, size exceeded)
- read_image_impl   additional branches (size exceeded)
"""
from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from matlab_mcp.config import SecurityConfig
from matlab_mcp.security.validator import SecurityValidator
from matlab_mcp.tools.files import (
    delete_file_impl,
    list_files_impl,
    read_data_impl,
    read_image_impl,
    upload_data_impl,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def security() -> SecurityValidator:
    return SecurityValidator(SecurityConfig())


@pytest.fixture
def tmp_session_dir(tmp_path: Path) -> str:
    d = tmp_path / "session_temp"
    d.mkdir()
    return str(d)


def _encode(data: bytes) -> str:
    """Helper: base64-encode bytes to a str."""
    return base64.b64encode(data).decode("ascii")


def _make_minimal_png() -> bytes:
    """Create the smallest valid PNG (1x1 RGB)."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + ihdr_crc
    raw = b"\x00\x00\x00\x00"
    idat_data = zlib.compress(raw)
    idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + idat_data) & 0xFFFFFFFF)
    idat = struct.pack(">I", len(idat_data)) + b"IDAT" + idat_data + idat_crc
    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    iend = struct.pack(">I", 0) + b"IEND" + iend_crc
    return sig + ihdr + idat + iend


# ===========================================================================
# upload_data_impl
# ===========================================================================


class TestUploadData:
    async def test_valid_upload(self, security: SecurityValidator, tmp_session_dir: str) -> None:
        """A valid base64 payload is decoded and written to disk."""
        payload = b"hello, MATLAB!"
        result = await upload_data_impl(
            filename="data.csv",
            content_base64=_encode(payload),
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert result["status"] == "ok"
        assert result["filename"] == "data.csv"
        assert result["size_bytes"] == len(payload)
        written = Path(result["path"]).read_bytes()
        assert written == payload

    async def test_invalid_filename_path_traversal(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """Path-traversal filenames are rejected before any I/O."""
        result = await upload_data_impl(
            filename="../evil.m",
            content_base64=_encode(b"x"),
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert result["status"] == "error"
        assert "Invalid filename" in result["message"]

    async def test_invalid_filename_empty(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """Empty filenames are rejected."""
        result = await upload_data_impl(
            filename="",
            content_base64=_encode(b"x"),
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert result["status"] == "error"
        assert "Invalid filename" in result["message"]

    async def test_invalid_filename_special_chars(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """Filenames with disallowed characters (e.g. slashes) are rejected."""
        result = await upload_data_impl(
            filename="foo/bar.txt",
            content_base64=_encode(b"x"),
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert result["status"] == "error"
        assert "Invalid filename" in result["message"]

    async def test_bad_base64(self, security: SecurityValidator, tmp_session_dir: str) -> None:
        """Corrupt base64 input returns a decode error."""
        result = await upload_data_impl(
            filename="data.csv",
            content_base64="NOT_VALID_BASE64!@#$",
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert result["status"] == "error"
        assert "decode" in result["message"].lower()

    async def test_file_too_large(self, security: SecurityValidator, tmp_session_dir: str) -> None:
        """Files exceeding max_size_mb are rejected after decode."""
        # 2 bytes with a 1-byte limit (max_size_mb=0 means 0 bytes allowed)
        big_payload = b"AB"
        result = await upload_data_impl(
            filename="big.bin",
            content_base64=_encode(big_payload),
            session_temp_dir=tmp_session_dir,
            security=security,
            max_size_mb=0,
        )
        assert result["status"] == "error"
        assert "exceeds maximum" in result["message"]

    async def test_creates_temp_dir_if_missing(
        self, security: SecurityValidator, tmp_path: Path
    ) -> None:
        """The session temp dir is created on-the-fly if it does not exist."""
        nonexistent = str(tmp_path / "new_dir" / "sub")
        result = await upload_data_impl(
            filename="file.txt",
            content_base64=_encode(b"data"),
            session_temp_dir=nonexistent,
            security=security,
        )
        assert result["status"] == "ok"
        assert Path(nonexistent).exists()


# ===========================================================================
# delete_file_impl
# ===========================================================================


class TestDeleteFile:
    async def test_successful_delete(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """Deleting an existing file returns ok and removes it from disk."""
        p = Path(tmp_session_dir) / "to_delete.csv"
        p.write_text("data", encoding="utf-8")
        assert p.exists()

        result = await delete_file_impl(
            filename="to_delete.csv",
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert result["status"] == "ok"
        assert result["filename"] == "to_delete.csv"
        assert not p.exists()

    async def test_file_not_found(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """Attempting to delete a nonexistent file returns an error."""
        result = await delete_file_impl(
            filename="ghost.txt",
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    async def test_invalid_filename(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """Path-traversal filenames are rejected."""
        result = await delete_file_impl(
            filename="../etc/passwd",
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert result["status"] == "error"
        assert "Invalid filename" in result["message"]

    async def test_invalid_filename_empty(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """Empty filename is rejected."""
        result = await delete_file_impl(
            filename="",
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert result["status"] == "error"
        assert "Invalid filename" in result["message"]


# ===========================================================================
# list_files_impl
# ===========================================================================


class TestListFiles:
    async def test_nonexistent_directory(self, tmp_path: Path) -> None:
        """A nonexistent session dir returns an empty file list."""
        result = await list_files_impl(
            session_temp_dir=str(tmp_path / "does_not_exist"),
        )
        assert result["files"] == []
        assert result["count"] == 0

    async def test_empty_directory(self, tmp_session_dir: str) -> None:
        """An empty session dir returns an empty file list."""
        result = await list_files_impl(session_temp_dir=tmp_session_dir)
        assert result["files"] == []
        assert result["count"] == 0

    async def test_directory_with_files(self, tmp_session_dir: str) -> None:
        """Files are listed with name, size, and path."""
        td = Path(tmp_session_dir)
        (td / "alpha.csv").write_text("a,b,c", encoding="utf-8")
        (td / "beta.mat").write_bytes(b"\x00" * 10)

        result = await list_files_impl(session_temp_dir=tmp_session_dir)
        assert result["count"] == 2
        names = [f["name"] for f in result["files"]]
        assert "alpha.csv" in names
        assert "beta.mat" in names

        for entry in result["files"]:
            assert "size" in entry
            assert "path" in entry
            assert entry["size"] >= 0

    async def test_subdirectories_are_excluded(self, tmp_session_dir: str) -> None:
        """Only regular files are listed; subdirectories are skipped."""
        td = Path(tmp_session_dir)
        (td / "subdir").mkdir()
        (td / "file.txt").write_text("hello")

        result = await list_files_impl(session_temp_dir=tmp_session_dir)
        assert result["count"] == 1
        assert result["files"][0]["name"] == "file.txt"

    async def test_files_are_sorted(self, tmp_session_dir: str) -> None:
        """File entries are sorted by name."""
        td = Path(tmp_session_dir)
        (td / "zebra.txt").write_text("z")
        (td / "apple.txt").write_text("a")

        result = await list_files_impl(session_temp_dir=tmp_session_dir)
        names = [f["name"] for f in result["files"]]
        assert names == sorted(names)


# ===========================================================================
# read_data_impl  —  additional uncovered branches
# ===========================================================================


class TestReadDataAdditionalPaths:
    async def test_mat_raw_format(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """.mat file with format='raw' returns base64-encoded bytes."""
        content = b"\x00MAT-FILE-BYTES"
        p = Path(tmp_session_dir) / "vars.mat"
        p.write_bytes(content)

        result = await read_data_impl(
            filename="vars.mat",
            format="raw",
            session_temp_dir=tmp_session_dir,
            security=security,
            executor=None,
            session_id="",
        )
        assert result["status"] == "ok"
        assert result["encoding"] == "base64"
        assert result["size_bytes"] == len(content)
        assert base64.b64decode(result["content"]) == content

    async def test_mat_summary_without_executor(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """.mat file with format='summary' but no executor falls back to base64."""
        content = b"\x00MAT"
        p = Path(tmp_session_dir) / "vars.mat"
        p.write_bytes(content)

        result = await read_data_impl(
            filename="vars.mat",
            format="summary",
            session_temp_dir=tmp_session_dir,
            security=security,
            executor=None,
            session_id="",
        )
        # Without an executor, the else branch returns base64
        assert result["status"] == "ok"
        assert result["encoding"] == "base64"

    async def test_mat_summary_executor_failure(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """.mat summary returns error when the MATLAB executor raises."""
        p = Path(tmp_session_dir) / "bad.mat"
        p.write_bytes(b"\x00")

        executor = AsyncMock()
        executor.execute = AsyncMock(side_effect=RuntimeError("engine crashed"))

        result = await read_data_impl(
            filename="bad.mat",
            format="summary",
            session_temp_dir=tmp_session_dir,
            security=security,
            executor=executor,
            session_id="s1",
        )
        assert result["status"] == "error"
        assert "whos failed" in result["message"].lower()

    async def test_xlsx_returns_base64(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """.xlsx files always return base64 regardless of format."""
        content = b"PK\x03\x04fake-xlsx-data"
        p = Path(tmp_session_dir) / "report.xlsx"
        p.write_bytes(content)

        result = await read_data_impl(
            filename="report.xlsx",
            format="raw",
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert result["status"] == "ok"
        assert result["encoding"] == "base64"
        assert result["size_bytes"] == len(content)
        assert base64.b64decode(result["content"]) == content

    async def test_text_file_truncation(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """Text content exceeding max_inline_text_length is truncated."""
        long_text = "x" * 500
        p = Path(tmp_session_dir) / "big.csv"
        p.write_text(long_text, encoding="utf-8")

        result = await read_data_impl(
            filename="big.csv",
            format="raw",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_inline_text_length=100,
        )
        assert result["status"] == "ok"
        assert len(result["content"]) == 100
        assert "truncated" in result["message"].lower()

    async def test_unicode_decode_error_fallback(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """Files that fail UTF-8 decoding fall back to latin-1."""
        # 0xFF 0xFE are valid latin-1 but invalid as standalone UTF-8
        content = bytes([0xFF, 0xFE, 0x41, 0x42])
        p = Path(tmp_session_dir) / "encoded.csv"
        p.write_bytes(content)

        result = await read_data_impl(
            filename="encoded.csv",
            format="raw",
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert result["status"] == "ok"
        # latin-1 decode should succeed and contain "AB"
        assert "AB" in result["content"]

    async def test_unsupported_extension(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """An unsupported file extension produces an error."""
        p = Path(tmp_session_dir) / "data.hdf5"
        p.write_bytes(b"\x89HDF")

        result = await read_data_impl(
            filename="data.hdf5",
            format="raw",
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert result["status"] == "error"
        assert "unsupported" in result["message"].lower()

    async def test_file_too_large(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """Files exceeding max_size_mb are rejected."""
        p = Path(tmp_session_dir) / "huge.csv"
        p.write_bytes(b"x" * 10)

        result = await read_data_impl(
            filename="huge.csv",
            format="raw",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_size_mb=0,
        )
        assert result["status"] == "error"
        assert "exceeds maximum" in result["message"]

    async def test_invalid_filename(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """Invalid filename with path traversal is rejected."""
        result = await read_data_impl(
            filename="../secret.csv",
            format="raw",
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert result["status"] == "error"
        assert "Invalid filename" in result["message"]

    async def test_json_file_reads_as_text(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """.json files are read as text and returned inline."""
        p = Path(tmp_session_dir) / "config.json"
        p.write_text('{"key": "value"}', encoding="utf-8")

        result = await read_data_impl(
            filename="config.json",
            format="raw",
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert result["status"] == "ok"
        assert '"key"' in result["content"]


# ===========================================================================
# read_image_impl  —  additional uncovered branches
# ===========================================================================


class TestReadImageAdditionalPaths:
    async def test_file_too_large(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """Images exceeding max_size_mb are rejected."""
        p = Path(tmp_session_dir) / "huge.png"
        p.write_bytes(_make_minimal_png())

        result = await read_image_impl(
            filename="huge.png",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_size_mb=0,
        )
        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert "exceeds maximum" in result["message"]

    async def test_valid_png_returns_image(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """A valid PNG file returns a FastMCP Image object."""
        p = Path(tmp_session_dir) / "chart.png"
        p.write_bytes(_make_minimal_png())

        result = await read_image_impl(
            filename="chart.png",
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        from fastmcp.utilities.types import Image

        assert isinstance(result, Image)

    async def test_unsupported_format(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """Unsupported image extensions are rejected."""
        p = Path(tmp_session_dir) / "image.bmp"
        p.write_bytes(b"BM" + b"\x00" * 50)

        result = await read_image_impl(
            filename="image.bmp",
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert "unsupported" in result["message"].lower()

    async def test_file_not_found(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """Missing image file returns error dict."""
        result = await read_image_impl(
            filename="missing.png",
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    async def test_invalid_filename(
        self, security: SecurityValidator, tmp_session_dir: str
    ) -> None:
        """Path traversal in image filename is rejected."""
        result = await read_image_impl(
            filename="../hack.png",
            session_temp_dir=tmp_session_dir,
            security=security,
        )
        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert "Invalid filename" in result["message"]

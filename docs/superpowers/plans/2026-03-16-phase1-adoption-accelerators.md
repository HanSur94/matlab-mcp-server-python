# Phase 1: Adoption Accelerators — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Docker support, CI/CD, three file download tools, and PyPI publishing to lower the adoption barrier.

**Architecture:** New tools follow the existing `*_impl` pattern in `tools/files.py`, registered via `@mcp.tool` in `server.py`. Docker and CI are standalone config files. PyPI metadata added to existing `pyproject.toml`.

**Tech Stack:** Python 3.9+, FastMCP 2.x, GitHub Actions, Docker, hatchling

**Spec:** `docs/superpowers/specs/2026-03-16-phase1-adoption-accelerators-design.md`

---

## Chunk 1: File Download Tools (read_script, read_data, read_image)

### Task 1: `read_script` — tests

**Files:**
- Create: `tests/test_file_read.py`

- [ ] **Step 1: Write failing tests for `read_script_impl`**

Create `tests/test_file_read.py`:

```python
"""Tests for file read tools (read_script, read_data, read_image)."""
from __future__ import annotations

import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from matlab_mcp.security.validator import SecurityValidator
from matlab_mcp.config import SecurityConfig
from matlab_mcp.tools.files import read_script_impl


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
        assert len(result["content"]) == 100  # exactly max_inline_text_length
        assert "truncated" in result.get("message", "").lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_file_read.py::TestReadScript -v`
Expected: FAIL — `ImportError: cannot import name 'read_script_impl'`

- [ ] **Step 3: Commit test file**

```bash
git add tests/test_file_read.py
git commit -m "test: add failing tests for read_script tool"
```

### Task 2: `read_script` — implementation

**Files:**
- Modify: `src/matlab_mcp/tools/files.py`

- [ ] **Step 1: Implement `read_script_impl`**

Add to the end of `src/matlab_mcp/tools/files.py`:

```python
async def read_script_impl(
    filename: str,
    session_temp_dir: str,
    security: Any,
    max_inline_text_length: int = 50000,
) -> dict:
    """Read a MATLAB .m script from the session's temporary directory.

    Parameters
    ----------
    filename:
        Filename (basename only) with ``.m`` extension.
    session_temp_dir:
        Path to the session's temporary directory.
    security:
        A :class:`~matlab_mcp.security.validator.SecurityValidator` instance.
    max_inline_text_length:
        Maximum number of characters to return inline.

    Returns
    -------
    dict
        Result dict with ``status``, ``filename``, and ``content``.
    """
    # Validate filename
    try:
        safe_name = security.sanitize_filename(filename)
    except ValueError as exc:
        return {"status": "error", "message": f"Invalid filename: {exc}"}

    # Check extension (case-insensitive)
    if not safe_name.lower().endswith(".m"):
        return {
            "status": "error",
            "message": f"Invalid extension: expected .m file, got '{safe_name}'",
        }

    target = Path(session_temp_dir) / safe_name
    if not target.exists():
        return {"status": "error", "message": f"File not found: {safe_name}"}

    try:
        content = target.read_text(encoding="utf-8")
    except Exception as exc:
        return {"status": "error", "message": f"Failed to read file: {exc}"}

    result: dict = {"status": "ok", "filename": safe_name}
    if len(content) > max_inline_text_length:
        result["content"] = content[:max_inline_text_length]
        result["message"] = (
            f"Content truncated from {len(content)} to "
            f"{max_inline_text_length} characters"
        )
    else:
        result["content"] = content

    return result
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_file_read.py::TestReadScript -v`
Expected: All 6 tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/matlab_mcp/tools/files.py
git commit -m "feat: implement read_script tool"
```

### Task 3: `read_image` — tests

**Files:**
- Modify: `tests/test_file_read.py`

- [ ] **Step 1: Write failing tests for `read_image_impl`**

Add `read_image_impl` to the imports block at the top of `tests/test_file_read.py` (next to the existing `read_script_impl` import):

```python
from matlab_mcp.tools.files import read_script_impl, read_image_impl
```

Then add the test class at the end of the file:

```python
class TestReadImage:
    async def test_png(self, security, tmp_session_dir):
        """Returns Image object for PNG files."""
        # Create a minimal 1x1 PNG (smallest valid PNG)
        import struct, zlib
        def make_png():
            sig = b'\x89PNG\r\n\x1a\n'
            ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
            ihdr_crc = struct.pack('>I', zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff)
            ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + ihdr_crc
            raw = b'\x00\x00\x00\x00'  # filter + 1 pixel RGB
            idat_data = zlib.compress(raw)
            idat_crc = struct.pack('>I', zlib.crc32(b'IDAT' + idat_data) & 0xffffffff)
            idat = struct.pack('>I', len(idat_data)) + b'IDAT' + idat_data + idat_crc
            iend_crc = struct.pack('>I', zlib.crc32(b'IEND') & 0xffffffff)
            iend = struct.pack('>I', 0) + b'IEND' + iend_crc
            return sig + ihdr + idat + iend

        p = Path(tmp_session_dir) / "plot.png"
        p.write_bytes(make_png())
        result = await read_image_impl(
            filename="plot.png",
            session_temp_dir=tmp_session_dir,
            security=security,
            max_size_mb=100,
        )
        # FastMCP Image object with correct MIME type
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_file_read.py::TestReadImage -v`
Expected: FAIL — `ImportError: cannot import name 'read_image_impl'`

- [ ] **Step 3: Commit**

```bash
git add tests/test_file_read.py
git commit -m "test: add failing tests for read_image tool"
```

### Task 4: `read_image` — implementation

**Files:**
- Modify: `src/matlab_mcp/tools/files.py`

- [ ] **Step 1: Implement `read_image_impl`**

Add to `src/matlab_mcp/tools/files.py`. Also add the `Image` import at the top of the file:

```python
# Add import near the top:
from fastmcp.utilities.types import Image
from typing import Union
```

Add the implementation at the end:

```python
_IMAGE_EXTENSIONS = {
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".gif": "gif",
}


async def read_image_impl(
    filename: str,
    session_temp_dir: str,
    security: Any,
    max_size_mb: int = _DEFAULT_MAX_SIZE_MB,
) -> Union[Image, dict]:
    """Read an image file from the session's temporary directory.

    Parameters
    ----------
    filename:
        Image filename (basename only). Supported: .png, .jpg, .jpeg, .gif
    session_temp_dir:
        Path to the session's temporary directory.
    security:
        A :class:`~matlab_mcp.security.validator.SecurityValidator` instance.
    max_size_mb:
        Maximum allowed file size in megabytes.

    Returns
    -------
    Image | dict
        FastMCP ``Image`` on success, or error dict on failure.
    """
    # Validate filename
    try:
        safe_name = security.sanitize_filename(filename)
    except ValueError as exc:
        return {"status": "error", "message": f"Invalid filename: {exc}"}

    # Check extension
    ext = Path(safe_name).suffix.lower()
    if ext not in _IMAGE_EXTENSIONS:
        supported = ", ".join(sorted(_IMAGE_EXTENSIONS))
        return {
            "status": "error",
            "message": f"Unsupported image format '{ext}'. Supported: {supported}",
        }

    target = Path(session_temp_dir) / safe_name
    if not target.exists():
        return {"status": "error", "message": f"File not found: {safe_name}"}

    # Size check
    file_size = target.stat().st_size
    max_bytes = max_size_mb * 1024 * 1024
    if file_size > max_bytes:
        return {
            "status": "error",
            "message": (
                f"File size {file_size} bytes exceeds maximum of "
                f"{max_size_mb} MB ({max_bytes} bytes)"
            ),
        }

    data = target.read_bytes()
    return Image(data=data, format=_IMAGE_EXTENSIONS[ext])
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_file_read.py::TestReadImage -v`
Expected: All 5 tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/matlab_mcp/tools/files.py
git commit -m "feat: implement read_image tool"
```

### Task 5: `read_data` — tests

**Files:**
- Modify: `tests/test_file_read.py`

- [ ] **Step 1: Write failing tests for `read_data_impl`**

Add `read_data_impl` and `base64` to the imports block at the top of `tests/test_file_read.py`:

```python
import base64
from matlab_mcp.tools.files import read_script_impl, read_image_impl, read_data_impl
```

Then add the fixture and test class at the end of the file:

```python
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
        """Reads CSV file as text in summary mode."""
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
        """Reads CSV file as text in raw mode (same as summary for text files)."""
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
        """Calls executor.execute for .mat summary mode."""
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
        assert "whos" in call_args[1].get("code", call_args[0][1] if len(call_args[0]) > 1 else "")

    async def test_mat_raw(self, security, tmp_session_dir, mock_executor):
        """Returns base64-encoded content for .mat raw mode."""
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
        """Returns error when file doesn't exist."""
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
        """XLSX files always return base64 regardless of format mode."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_file_read.py::TestReadData -v`
Expected: FAIL — `ImportError: cannot import name 'read_data_impl'`

- [ ] **Step 3: Commit**

```bash
git add tests/test_file_read.py
git commit -m "test: add failing tests for read_data tool"
```

### Task 6: `read_data` — implementation

**Files:**
- Modify: `src/matlab_mcp/tools/files.py`

- [ ] **Step 1: Implement `read_data_impl`**

Add to the end of `src/matlab_mcp/tools/files.py`:

```python
_DATA_EXTENSIONS = {".mat", ".xlsx", ".csv", ".txt", ".json", ".yaml", ".yml", ".xml"}


async def read_data_impl(
    filename: str,
    format: str,
    session_temp_dir: str,
    security: Any,
    max_size_mb: int = _DEFAULT_MAX_SIZE_MB,
    max_inline_text_length: int = 50000,
    executor: Any = None,
    session_id: str = "",
) -> dict:
    """Read a data file from the session's temporary directory.

    Parameters
    ----------
    filename:
        Filename (basename only).
    format:
        ``"summary"`` (default) or ``"raw"``.
    session_temp_dir:
        Path to the session's temporary directory.
    security:
        A :class:`~matlab_mcp.security.validator.SecurityValidator` instance.
    max_size_mb:
        Maximum allowed file size in megabytes.
    max_inline_text_length:
        Maximum characters for inline text content.
    executor:
        A :class:`~matlab_mcp.jobs.executor.JobExecutor` (needed for .mat summary).
    session_id:
        Session ID (needed for executor.execute).

    Returns
    -------
    dict
        Result dict with ``status``, ``filename``, ``content``, and optionally
        ``encoding`` (``"base64"`` for binary) or ``message``.
    """
    # Validate filename
    try:
        safe_name = security.sanitize_filename(filename)
    except ValueError as exc:
        return {"status": "error", "message": f"Invalid filename: {exc}"}

    target = Path(session_temp_dir) / safe_name
    if not target.exists():
        return {"status": "error", "message": f"File not found: {safe_name}"}

    # Size check
    file_size = target.stat().st_size
    max_bytes = max_size_mb * 1024 * 1024
    if file_size > max_bytes:
        return {
            "status": "error",
            "message": (
                f"File size {file_size} bytes exceeds maximum of "
                f"{max_size_mb} MB ({max_bytes} bytes)"
            ),
        }

    ext = Path(safe_name).suffix.lower()
    if ext not in _DATA_EXTENSIONS:
        supported = ", ".join(sorted(_DATA_EXTENSIONS))
        return {
            "status": "error",
            "message": f"Unsupported data file type '{ext}'. Supported: {supported}",
        }

    # .mat files — summary uses MATLAB, raw returns base64
    if ext == ".mat":
        if format == "summary" and executor is not None:
            mat_path = str(target).replace("'", "''")
            code = (
                f"s = whos('-file', '{mat_path}');\n"
                f"for i = 1:length(s)\n"
                f"    fprintf('%s  %s  %s\\n', s(i).name, mat2str(s(i).size), s(i).class);\n"
                f"end"
            )
            try:
                mat_result = await executor.execute(
                    session_id=session_id,
                    code=code,
                )
                return {
                    "status": "ok",
                    "filename": safe_name,
                    "content": mat_result.get("output", ""),
                }
            except Exception as exc:
                return {"status": "error", "message": f"MATLAB whos failed: {exc}"}
        else:
            data = target.read_bytes()
            return {
                "status": "ok",
                "filename": safe_name,
                "content": base64.b64encode(data).decode("ascii"),
                "encoding": "base64",
                "size_bytes": len(data),
            }

    # .xlsx — always base64 (no text preview without openpyxl)
    if ext == ".xlsx":
        data = target.read_bytes()
        return {
            "status": "ok",
            "filename": safe_name,
            "content": base64.b64encode(data).decode("ascii"),
            "encoding": "base64",
            "size_bytes": len(data),
        }

    # Text files (.csv, .txt, .json, etc.)
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = target.read_text(encoding="latin-1")
    except Exception as exc:
        return {"status": "error", "message": f"Failed to read file: {exc}"}

    result: dict = {"status": "ok", "filename": safe_name}
    if len(content) > max_inline_text_length:
        result["content"] = content[:max_inline_text_length]
        result["message"] = (
            f"Content truncated from {len(content)} to "
            f"{max_inline_text_length} characters"
        )
    else:
        result["content"] = content

    return result
```

- [ ] **Step 2: Run all file read tests**

Run: `pytest tests/test_file_read.py -v`
Expected: All tests PASS (TestReadScript + TestReadImage + TestReadData)

- [ ] **Step 3: Run full test suite to verify no regressions**

Run: `pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/matlab_mcp/tools/files.py
git commit -m "feat: implement read_data tool"
```

### Task 7: Register new tools in server.py

**Files:**
- Modify: `src/matlab_mcp/server.py`

- [ ] **Step 1: Update imports in server.py**

In `src/matlab_mcp/server.py`, change the files import (line 38):

```python
# Before:
from matlab_mcp.tools.files import delete_file_impl, list_files_impl, upload_data_impl

# After:
from matlab_mcp.tools.files import (
    delete_file_impl,
    list_files_impl,
    read_data_impl,
    read_image_impl,
    read_script_impl,
    upload_data_impl,
)
```

- [ ] **Step 2: Register `read_script` tool**

Add after the `list_files` tool registration (after line ~541):

```python
    @mcp.tool
    async def read_script(ctx: Context, filename: str) -> dict:
        """Read a MATLAB .m script file from the session's temporary directory.

        Returns the file content as text. Use list_files to see available files.
        """
        session_id = state._get_session_id(ctx)
        temp_dir = state._get_temp_dir(session_id)
        return await read_script_impl(
            filename=filename,
            session_temp_dir=temp_dir,
            security=state.security,
            max_inline_text_length=config.output.max_inline_text_length,
        )
```

- [ ] **Step 3: Register `read_data` tool**

Add after `read_script`:

```python
    @mcp.tool
    async def read_data(
        ctx: Context,
        filename: str,
        format: str = "summary",
    ) -> dict:
        """Read a data file (.mat, .csv, .json, .txt, .xlsx) from the session temp directory.

        For .mat files, 'summary' mode shows variable names/sizes/types via MATLAB,
        'raw' mode returns base64-encoded content. Text files return inline content.
        """
        session_id = state._get_session_id(ctx)
        temp_dir = state._get_temp_dir(session_id)
        return await read_data_impl(
            filename=filename,
            format=format,
            session_temp_dir=temp_dir,
            security=state.security,
            max_size_mb=config.security.max_upload_size_mb,
            max_inline_text_length=config.output.max_inline_text_length,
            executor=state.executor,
            session_id=session_id,
        )
```

- [ ] **Step 4: Register `read_image` tool**

Add after `read_data`:

```python
    @mcp.tool
    async def read_image(ctx: Context, filename: str):
        """Read an image file (.png, .jpg, .gif) from the session temp directory.

        Returns the image as an inline content block that renders in agent UIs.
        """
        session_id = state._get_session_id(ctx)
        temp_dir = state._get_temp_dir(session_id)
        return await read_image_impl(
            filename=filename,
            session_temp_dir=temp_dir,
            security=state.security,
            max_size_mb=config.security.max_upload_size_mb,
        )
```

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Run linter**

Run: `ruff check src/matlab_mcp/server.py src/matlab_mcp/tools/files.py tests/test_file_read.py`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add src/matlab_mcp/server.py
git commit -m "feat: register read_script, read_data, read_image tools"
```

---

## Chunk 2: Docker, CI/CD, PyPI

### Task 8: Dockerfile + .dockerignore

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**

```
.git
tests/
docs/
wiki/
logs/
temp/
results/
monitoring/
__pycache__
*.pyc
.env
.venv
.ruff_cache
.pytest_cache
.claude/
*.egg-info
dist/
build/
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install third-party deps first for layer caching
COPY pyproject.toml README.md LICENSE ./
RUN pip install --no-cache-dir \
    "fastmcp>=2.0.0,<3.0.0" "pydantic>=2.0.0" "pyyaml>=6.0" \
    "Pillow>=9.0.0" "aiosqlite>=0.19.0" "plotly>=5.9.0" \
    "psutil>=5.9.0" "uvicorn>=0.20.0"

# Copy source and install the package itself
COPY src/ ./src/
COPY examples/ ./examples/
RUN pip install --no-cache-dir --no-deps .

EXPOSE 8765 8766

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/health')" || exit 1

ENTRYPOINT ["matlab-mcp"]
CMD ["--transport", "sse"]
```

- [ ] **Step 3: Verify Docker build**

Run: `docker build -t matlab-mcp-test .`
Expected: Build succeeds (image won't run without MATLAB, but it builds)

- [ ] **Step 4: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: add Dockerfile and .dockerignore"
```

### Task 9: docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
services:
  matlab-mcp:
    build: .
    ports:
      - "8765:8765"
      - "8766:8766"
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./custom_tools.yaml:/app/custom_tools.yaml:ro
      # Mount your MATLAB installation (adjust path for your system):
      # - /usr/local/MATLAB/R2024b:/opt/matlab:ro          # Linux
      # - /Applications/MATLAB_R2024b.app:/opt/matlab:ro    # macOS
      - results:/app/results
      - monitoring_data:/app/monitoring
    environment:
      - MATLAB_MCP_SERVER_TRANSPORT=sse
      - MATLAB_MCP_POOL_MAX_ENGINES=4
      # - MATLAB_MCP_POOL_MATLAB_ROOT=/opt/matlab  # Uncomment when mounting MATLAB

volumes:
  results:
  monitoring_data:
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add docker-compose.yml"
```

### Task 10: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create directory and CI workflow**

```bash
mkdir -p .github/workflows
```

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [master]
  pull_request:
    branches: [master]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: ruff check src/ tests/

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.9", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev,monitoring]"
      - run: pytest tests/ -v --cov=matlab_mcp --cov-report=term-missing
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions CI workflow (lint + test matrix)"
```

### Task 11: GitHub Actions Publish

**Files:**
- Create: `.github/workflows/publish.yml`

- [ ] **Step 1: Create publish workflow**

Create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      id-token: write  # Required for OIDC Trusted Publishing
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build twine
      - run: python -m build
      - run: twine check dist/*
      - uses: pypa/gh-action-pypi-publish@release/v1
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/publish.yml
git commit -m "ci: add PyPI publish workflow with OIDC Trusted Publishing"
```

### Task 12: Update pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update package metadata**

In `pyproject.toml`, update the `[project]` section:

- Change `name` from `"matlab-mcp-server"` to `"matlab-mcp-python"`
- Change `version` from `"0.1.0"` to `"1.0.0"`
- Add `authors`, `keywords`, `classifiers`, `[project.urls]`

The full `[project]` section should become:

```toml
[project]
name = "matlab-mcp-python"
version = "1.0.0"
description = "MCP server exposing MATLAB capabilities to AI agents"
readme = "README.md"
license = "MIT"
requires-python = ">=3.9"
authors = [
    { name = "Hannes Suhr" },
]
keywords = ["matlab", "mcp", "model-context-protocol", "ai", "agent"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Intended Audience :: Science/Research",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Scientific/Engineering",
    "Topic :: Software Development :: Libraries",
]
dependencies = [
    "fastmcp>=2.0.0,<3.0.0",
    "pydantic>=2.0.0",
    "pyyaml>=6.0",
    "Pillow>=9.0.0",
    "aiosqlite>=0.19.0",
    "plotly>=5.9.0",
]

[project.urls]
Homepage = "https://github.com/HanSur94/matlab-mcp-server-python"
Repository = "https://github.com/HanSur94/matlab-mcp-server-python"
Issues = "https://github.com/HanSur94/matlab-mcp-server-python/issues"
Wiki = "https://github.com/HanSur94/matlab-mcp-server-python/wiki"
```

- [ ] **Step 2: Verify build works**

Run: `python -m build`
Expected: Builds `.tar.gz` and `.whl` in `dist/`

- [ ] **Step 3: Verify package installs**

Run: `pip install dist/matlab_mcp_python-1.0.0-py3-none-any.whl && matlab-mcp --help`
Expected: CLI help output appears

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat: update pyproject.toml for PyPI as matlab-mcp-python v1.0.0"
```

---

## Chunk 3: Documentation Updates

### Task 13: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add badges after title block**

After the closing `</p>` of the nav links (line 14), before the `---`, add:

```html
<p align="center">
  <a href="https://github.com/HanSur94/matlab-mcp-server-python/actions/workflows/ci.yml">
    <img src="https://github.com/HanSur94/matlab-mcp-server-python/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
  <a href="https://pypi.org/project/matlab-mcp-python/">
    <img src="https://img.shields.io/pypi/v/matlab-mcp-python" alt="PyPI">
  </a>
  <a href="https://pypi.org/project/matlab-mcp-python/">
    <img src="https://img.shields.io/pypi/pyversions/matlab-mcp-python" alt="Python">
  </a>
</p>
```

- [ ] **Step 2: Add `pip install` option to Quick Start**

In the "Install the server" section, add before the git clone:

```bash
# Option 1: Install from PyPI
pip install matlab-mcp-python

# Option 2: Install from source
git clone ...
```

- [ ] **Step 3: Add Docker Quickstart section**

After the "Connect to Cursor" section (after line ~106), add:

```markdown
### Run with Docker

```bash
# Build the image
docker build -t matlab-mcp .

# Run with your MATLAB mounted
docker run -p 8765:8765 -p 8766:8766 \
  -v /path/to/MATLAB:/opt/matlab:ro \
  -e MATLAB_MCP_POOL_MATLAB_ROOT=/opt/matlab \
  matlab-mcp

# Or use docker-compose (edit docker-compose.yml to set your MATLAB path)
docker compose up
```

> **Note:** The Docker image does not include MATLAB. You must mount your own MATLAB installation. See the [wiki](https://github.com/HanSur94/matlab-mcp-server-python/wiki/Installation) for details.
```

- [ ] **Step 4: Add 3 new tools to MCP Tools Reference table**

Add a "File Reading" section after the "File Management" table:

```markdown
### File Reading

| Tool | Parameters | Description |
|------|-----------|-------------|
| `read_script` | `filename: str` | Read a MATLAB `.m` script file as text |
| `read_data` | `filename: str, format: str` | Read data files (`.mat`, `.csv`, `.json`, `.txt`, `.xlsx`). `format`: `summary` or `raw` |
| `read_image` | `filename: str` | Read image files (`.png`, `.jpg`, `.gif`) — renders inline in agent UIs |
```

- [ ] **Step 5: Update tool count in architecture diagram**

Change `17 tools + custom tools` to `20 tools + custom tools` (line ~555).

- [ ] **Step 6: Add `pip install` to Security migration note**

In the Security table, no changes needed. But add a note after the Install section about the package rename:

```markdown
> **Upgrading?** If you previously installed from source as `matlab-mcp-server`, uninstall it first: `pip uninstall matlab-mcp-server && pip install matlab-mcp-python`
```

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "docs: add badges, Docker quickstart, new tools, PyPI install to README"
```

### Task 14: Update wiki pages

**Files:**
- Modify: `wiki/Home.md` — tool count 17→20
- Modify: `wiki/MCP-Tools-Reference.md` — tool count 17→20, add File Reading section
- Modify: `wiki/Architecture.md` — tool count 17→20
- Modify: `wiki/SETUP_WIKI.md` — tool count 17→20

- [ ] **Step 1: Update tool counts**

Change "17" to "20" in all four wiki files (same locations as the previous 14→17 fix).

- [ ] **Step 2: Add File Reading section to MCP-Tools-Reference.md**

After the Admin section (after `get_pool_status`), before the Monitoring section, add:

```markdown
## File Reading

### `read_script`

Read a MATLAB `.m` script file from the session temp directory.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filename` | string | yes | `.m` file to read |

Returns the file content as inline text.

### `read_data`

Read a data file from the session temp directory.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filename` | string | yes | Data file to read |
| `format` | string | no | `summary` (default) or `raw` |

**Behavior by file type:**
- `.mat` summary: shows variable names, sizes, types via MATLAB `whos`
- `.mat` raw: returns base64-encoded content
- `.csv`, `.txt`, `.json`: returns text content
- `.xlsx`: returns base64-encoded content

### `read_image`

Read an image file from the session temp directory. Returns an inline image that renders in agent UIs.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filename` | string | yes | Image file (`.png`, `.jpg`, `.gif`) |
```

- [ ] **Step 3: Commit**

```bash
git add wiki/Home.md wiki/MCP-Tools-Reference.md wiki/Architecture.md wiki/SETUP_WIKI.md
git commit -m "docs: update wiki with new file reading tools and tool count 20"
```

### Task 15: Final verification

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v --cov=matlab_mcp --cov-report=term-missing`
Expected: All tests PASS, coverage report shows new code covered

- [ ] **Step 2: Run linter**

Run: `ruff check src/ tests/`
Expected: No errors

- [ ] **Step 3: Verify Docker build**

Run: `docker build -t matlab-mcp-test .`
Expected: Build succeeds

- [ ] **Step 4: Verify package build**

Run: `python -m build && twine check dist/*`
Expected: Build succeeds, twine check passes

"""File management MCP tool implementations.

Provides:
- upload_data_impl   — upload a file to the session temp directory
- delete_file_impl   — delete a file from the session temp directory
- list_files_impl    — list files in the session temp directory
- read_script_impl   — read a .m script from the session temp directory
- read_image_impl    — read an image file and return a FastMCP Image object
- read_data_impl     — read a data file (.mat, .csv, .json, etc.)
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, List, Union

from fastmcp.utilities.types import Image

logger = logging.getLogger(__name__)

# Default max upload size in MB
_DEFAULT_MAX_SIZE_MB = 100


async def upload_data_impl(
    filename: str,
    content_base64: str,
    session_temp_dir: str,
    security: Any,
    max_size_mb: int = _DEFAULT_MAX_SIZE_MB,
) -> dict:
    """Upload a file to the session's temporary directory.

    Parameters
    ----------
    filename:
        Target filename (basename only; no path separators allowed).
    content_base64:
        Base64-encoded file content.
    session_temp_dir:
        Path to the session's temporary directory.
    security:
        A :class:`~matlab_mcp.security.validator.SecurityValidator` instance.
    max_size_mb:
        Maximum allowed file size in megabytes.

    Returns
    -------
    dict
        Result dict with ``status``, ``filename``, ``path``, and ``size_bytes``.
    """
    # Validate filename
    try:
        safe_name = security.sanitize_filename(filename)
    except ValueError as exc:
        return {
            "status": "error",
            "message": f"Invalid filename: {exc}",
        }

    # Decode base64 content
    try:
        data = base64.b64decode(content_base64)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to decode base64 content: {exc}",
        }

    # Check file size
    max_bytes = max_size_mb * 1024 * 1024
    if len(data) > max_bytes:
        return {
            "status": "error",
            "message": (
                f"File size {len(data)} bytes exceeds maximum of "
                f"{max_size_mb} MB ({max_bytes} bytes)"
            ),
        }

    # Write file
    td = Path(session_temp_dir)
    td.mkdir(parents=True, exist_ok=True)
    target = td / safe_name

    try:
        target.write_bytes(data)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to write file: {exc}",
        }

    return {
        "status": "ok",
        "filename": safe_name,
        "path": str(target),
        "size_bytes": len(data),
    }


async def delete_file_impl(
    filename: str,
    session_temp_dir: str,
    security: Any,
) -> dict:
    """Delete a file from the session's temporary directory.

    Parameters
    ----------
    filename:
        Filename to delete (basename only).
    session_temp_dir:
        Path to the session's temporary directory.
    security:
        A :class:`~matlab_mcp.security.validator.SecurityValidator` instance.

    Returns
    -------
    dict
        Result dict with ``status`` and ``filename``.
    """
    # Validate filename
    try:
        safe_name = security.sanitize_filename(filename)
    except ValueError as exc:
        return {
            "status": "error",
            "message": f"Invalid filename: {exc}",
        }

    target = Path(session_temp_dir) / safe_name

    if not target.exists():
        return {
            "status": "error",
            "filename": safe_name,
            "message": f"File not found: {safe_name}",
        }

    try:
        target.unlink()
    except Exception as exc:
        return {
            "status": "error",
            "filename": safe_name,
            "message": f"Failed to delete file: {exc}",
        }

    return {
        "status": "ok",
        "filename": safe_name,
        "message": f"File '{safe_name}' deleted",
    }


async def list_files_impl(
    session_temp_dir: str,
) -> dict:
    """List files in the session's temporary directory.

    Parameters
    ----------
    session_temp_dir:
        Path to the session's temporary directory.

    Returns
    -------
    dict
        Dict with a ``files`` list, each entry containing ``name``, ``size``,
        and ``path``.
    """
    td = Path(session_temp_dir)

    if not td.exists():
        return {"files": [], "count": 0}

    files: List[dict] = []
    try:
        for entry in sorted(td.iterdir()):
            if entry.is_file():
                try:
                    size = entry.stat().st_size
                except Exception:
                    size = -1
                files.append({
                    "name": entry.name,
                    "size": size,
                    "path": str(entry),
                })
    except Exception as exc:
        logger.warning("Failed to list files in %s: %s", session_temp_dir, exc)
        return {"files": [], "count": 0, "error": str(exc)}

    return {"files": files, "count": len(files)}


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
        Filename to read (basename only; no path separators allowed).
    session_temp_dir:
        Path to the session's temporary directory.
    security:
        A :class:`~matlab_mcp.security.validator.SecurityValidator` instance.
    max_inline_text_length:
        Maximum number of characters to return inline; content beyond this
        limit is truncated.

    Returns
    -------
    dict
        Result dict with ``status``, ``filename``, ``content``, and optionally
        ``message`` (when truncated or on error).
    """
    # Validate filename
    try:
        safe_name = security.sanitize_filename(filename)
    except ValueError as exc:
        return {"status": "error", "message": f"Invalid filename: {exc}"}

    # Enforce .m extension
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
        Filename to read (basename only; no path separators allowed).
    session_temp_dir:
        Path to the session's temporary directory.
    security:
        A :class:`~matlab_mcp.security.validator.SecurityValidator` instance.
    max_size_mb:
        Maximum allowed file size in megabytes.

    Returns
    -------
    Image | dict
        A FastMCP :class:`Image` on success, or an error dict on failure.
    """
    try:
        safe_name = security.sanitize_filename(filename)
    except ValueError as exc:
        return {"status": "error", "message": f"Invalid filename: {exc}"}

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
        Filename to read (basename only; no path separators allowed).
    format:
        Either ``"summary"`` (human-readable overview) or ``"raw"``
        (full content, base64 for binary files).
    session_temp_dir:
        Path to the session's temporary directory.
    security:
        A :class:`~matlab_mcp.security.validator.SecurityValidator` instance.
    max_size_mb:
        Maximum allowed file size in megabytes.
    max_inline_text_length:
        Maximum number of characters to return inline for text files;
        content beyond this limit is truncated.
    executor:
        An optional MATLAB executor (used for ``.mat`` summary via ``whos``).
    session_id:
        Session identifier passed to the executor.

    Returns
    -------
    dict
        Result dict with ``status``, ``filename``, ``content``, and optionally
        ``encoding``, ``size_bytes``, or ``message``.
    """
    try:
        safe_name = security.sanitize_filename(filename)
    except ValueError as exc:
        return {"status": "error", "message": f"Invalid filename: {exc}"}

    target = Path(session_temp_dir) / safe_name
    if not target.exists():
        return {"status": "error", "message": f"File not found: {safe_name}"}

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

    # .mat files — summary uses MATLAB whos, raw returns base64
    if ext == ".mat":
        if format == "summary" and executor is not None:
            mat_path = str(target).replace("'", "''")
            code = (
                f"s = whos('-file', '{mat_path}');\n"
                f"for i = 1:length(s)\n"
                f"    fprintf('%s  %s  %s\\n', s(i).name, "
                f"mat2str(s(i).size), s(i).class);\n"
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

    # .xlsx — always base64 (binary format)
    if ext == ".xlsx":
        data = target.read_bytes()
        return {
            "status": "ok",
            "filename": safe_name,
            "content": base64.b64encode(data).decode("ascii"),
            "encoding": "base64",
            "size_bytes": len(data),
        }

    # Text files (.csv, .txt, .json, .yaml, .yml, .xml)
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

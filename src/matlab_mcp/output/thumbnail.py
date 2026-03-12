"""Thumbnail generation for MATLAB figure images.

Provides ``generate_thumbnail`` which resizes an image using Pillow and
returns a base64-encoded PNG string suitable for embedding in MCP responses.
"""
from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def generate_thumbnail(
    image_path: str,
    max_width: int = 400,
) -> Optional[str]:
    """Generate a base64-encoded PNG thumbnail from *image_path*.

    Resizes the image to at most *max_width* pixels wide while preserving the
    aspect ratio.  Returns ``None`` if the image cannot be read or resized.

    Parameters
    ----------
    image_path:
        Absolute path to the source image file (PNG, JPG, etc.).
    max_width:
        Maximum width in pixels for the thumbnail.  Defaults to 400.

    Returns
    -------
    Optional[str]
        Base64-encoded PNG string, or ``None`` on failure.
    """
    try:
        from PIL import Image  # type: ignore[import]
    except ImportError:
        logger.warning("Pillow is not installed; thumbnail generation disabled")
        return None

    path = Path(image_path)
    if not path.exists():
        logger.debug("Image path does not exist: %s", image_path)
        return None

    try:
        with Image.open(path) as img:
            # Convert to RGB if necessary (handles RGBA, palette modes, etc.)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            width, height = img.size
            if width > max_width:
                ratio = max_width / width
                new_height = max(1, int(height * ratio))
                img = img.resize((max_width, new_height), Image.LANCZOS)

            # Encode to PNG in memory
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            return base64.b64encode(buf.read()).decode("ascii")

    except Exception as exc:
        logger.warning("Failed to generate thumbnail for %s: %s", image_path, exc)
        return None

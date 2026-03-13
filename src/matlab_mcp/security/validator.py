"""Security validator for MATLAB code and filenames.

Provides:
- ``BlockedFunctionError`` — raised when blocked MATLAB code is detected.
- ``SecurityValidator``   — checks code and sanitizes filenames.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class BlockedFunctionError(Exception):
    """Raised when MATLAB code contains a blocked function or construct."""


class SecurityValidator:
    """Validates MATLAB code and filenames against a security policy.

    Parameters
    ----------
    security_config:
        ``SecurityConfig`` instance with ``blocked_functions_enabled`` and
        ``blocked_functions`` attributes.
    """

    def __init__(self, security_config: Any, collector: Any = None) -> None:
        self._config = security_config
        self._collector = collector

    # ------------------------------------------------------------------
    # Code checking
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_string_literals(code: str) -> str:
        """Remove MATLAB string literals and comments to avoid false positives.

        Processing order per line:
        1. Remove double-quoted strings "..."
        2. Remove single-quoted strings '...' (MATLAB char arrays)
           - A quote preceded by [a-zA-Z0-9_)] is a transpose operator, not a string.
        3. Remove MATLAB comments (% to end of line)

        Note: This is a best-effort heuristic; it handles the common cases
        tested without a full MATLAB parser.
        """
        processed_lines = []
        for line in code.splitlines():
            # Remove double-quoted strings "..."
            line = re.sub(r'"[^"\n]*"', '""', line)
            # Remove single-quoted strings '...' (MATLAB char arrays)
            # A ' preceded by an identifier char or ) is a transpose, skip it.
            line = re.sub(r"(?<![a-zA-Z0-9_\)\]])'[^'\n]*'", "''", line)
            # Remove MATLAB line comments: % and everything after
            # But only if % is not inside a string we just cleared.
            # Since strings are blanked out, a bare % is definitely a comment.
            comment_match = re.search(r'%', line)
            if comment_match:
                line = line[:comment_match.start()]
            processed_lines.append(line)
        return "\n".join(processed_lines)

    def check_code(self, code: str) -> None:
        """Scan *code* for blocked functions/constructs.

        Parameters
        ----------
        code:
            MATLAB source code to check.

        Raises
        ------
        BlockedFunctionError
            If a blocked construct is found (and blocking is enabled).
        """
        if not self._config.blocked_functions_enabled:
            logger.debug("Security check skipped (blocked_functions disabled)")
            return

        # Strip string literals to avoid false positives
        sanitized = self._strip_string_literals(code)

        for func in self._config.blocked_functions:
            if func == "!":
                # Shell escape: lines starting with ! (after optional whitespace)
                for line in sanitized.splitlines():
                    if line.lstrip().startswith("!"):
                        logger.warning("BLOCKED: shell escape '!' in code: %s", repr(code[:120]))
                        if self._collector:
                            self._collector.record_event("blocked_function", {"function": "!"})
                        raise BlockedFunctionError(
                            f"Shell escape '!' is not allowed"
                        )
            else:
                # Match function name as a whole word followed by optional
                # whitespace and an opening parenthesis, OR just the name
                # as a standalone command (no parens required for e.g. `system cmd`)
                pattern = rf"\b{re.escape(func)}\s*\("
                if re.search(pattern, sanitized):
                    logger.warning("BLOCKED: function '%s' in code: %s", func, repr(code[:120]))
                    if self._collector:
                        self._collector.record_event("blocked_function", {"function": func})
                    raise BlockedFunctionError(
                        f"Function '{func}' is not allowed"
                    )

    # ------------------------------------------------------------------
    # Filename sanitization
    # ------------------------------------------------------------------

    _SAFE_FILENAME_RE = re.compile(r'^[a-zA-Z0-9._-]+$')

    def sanitize_filename(self, filename: str) -> str:
        """Validate and return *filename* if safe.

        Parameters
        ----------
        filename:
            Proposed filename (basename only, no directory separators).

        Returns
        -------
        str
            The filename unchanged if it passes validation.

        Raises
        ------
        ValueError
            If the filename is empty, contains path traversal (``..``),
            or contains characters outside ``[a-zA-Z0-9._-]``.
        """
        if not filename:
            raise ValueError("Filename must not be empty")

        if ".." in filename:
            raise ValueError(f"Path traversal not allowed in filename: {filename!r}")

        if not self._SAFE_FILENAME_RE.match(filename):
            raise ValueError(
                f"Filename contains invalid characters: {filename!r}. "
                "Only [a-zA-Z0-9._-] are allowed."
            )

        return filename

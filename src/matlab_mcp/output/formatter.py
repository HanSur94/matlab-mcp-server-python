"""Output formatter for MATLAB MCP Server.

Provides ``ResultFormatter`` which builds structured MCP response dicts from
raw execution results, handling text truncation/saving, variable summarisation,
figure attachment, and file listings.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ResultFormatter:
    """Formats MATLAB execution results for MCP responses.

    Parameters
    ----------
    config:
        The full ``AppConfig`` instance.  Uses ``config.output``.
    """

    def __init__(self, config: Any) -> None:
        self._config = config
        self._output_cfg = config.output

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def format_text(
        self,
        text: str,
        save_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Format captured text output.

        If the text is shorter than ``max_inline_text_length`` it is returned
        inline.  Otherwise it is truncated and, if *save_dir* is given, the
        full text is saved to a file.

        Parameters
        ----------
        text:
            Raw text captured from MATLAB stdout.
        save_dir:
            Directory path to save the full text to when truncated.

        Returns
        -------
        dict
            Keys: ``inline`` (str), ``truncated`` (bool),
            ``saved_path`` (Optional[str]).
        """
        max_len = self._output_cfg.max_inline_text_length

        if len(text) <= max_len:
            return {
                "inline": text,
                "truncated": False,
                "saved_path": None,
            }

        # Truncate and optionally save
        inline = text[:max_len]
        saved_path: Optional[str] = None

        if save_dir is not None:
            try:
                td = Path(save_dir)
                td.mkdir(parents=True, exist_ok=True)
                ts = int(time.time() * 1000)
                out_file = td / f"output_{ts}.txt"
                out_file.write_text(text, encoding="utf-8")
                saved_path = str(out_file)
                logger.debug("Saved truncated output to %s", saved_path)
            except Exception as exc:
                logger.warning("Failed to save output text: %s", exc)

        return {
            "inline": inline,
            "truncated": True,
            "saved_path": saved_path,
        }

    def format_variables(self, variables: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Summarise workspace variables.

        Parameters
        ----------
        variables:
            Dict mapping variable name to value.

        Returns
        -------
        list of dict
            Each entry has ``name``, ``type``, ``size``, ``value`` keys.
            Large values are represented by their type/size only.
        """
        result: List[Dict[str, Any]] = []
        large_threshold = self._output_cfg.large_result_threshold

        for name, value in variables.items():
            entry: Dict[str, Any] = {"name": name}
            entry["type"] = type(value).__name__

            # Determine size
            if hasattr(value, "__len__"):
                size = len(value)
                entry["size"] = size
            elif hasattr(value, "shape"):
                entry["size"] = list(value.shape)
                size = 1
                for dim in value.shape:
                    size *= dim
            else:
                entry["size"] = 1
                size = 1

            # Only include value for small scalars/items
            if size <= large_threshold:
                try:
                    # Attempt JSON serialisation to ensure it's representable
                    json.dumps(value)
                    entry["value"] = value
                except (TypeError, ValueError):
                    entry["value"] = str(value)
            else:
                entry["value"] = f"<{type(value).__name__} with {size} elements>"

            result.append(entry)

        return result

    def build_success_response(
        self,
        job_id: str,
        text: str,
        variables: Dict[str, Any],
        figures: List[Any],
        files: List[str],
        warnings: List[str],
        execution_time: Optional[float],
        save_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a structured success response dict.

        Parameters
        ----------
        job_id:
            The job identifier.
        text:
            Captured stdout text.
        variables:
            Workspace variable dict.
        figures:
            List of figure objects/dicts.
        files:
            List of file paths written during execution.
        warnings:
            List of warning strings.
        execution_time:
            Elapsed execution time in seconds (or None).
        save_dir:
            Directory to save large text output.

        Returns
        -------
        dict
            Structured response with ``status``, ``job_id``, ``output``,
            ``variables``, ``figures``, ``files``, ``warnings``,
            ``execution_time`` keys.
        """
        formatted_text = self.format_text(text, save_dir=save_dir)
        formatted_vars = self.format_variables(variables)

        return {
            "status": "completed",
            "job_id": job_id,
            "output": formatted_text,
            "variables": formatted_vars,
            "figures": figures,
            "files": files,
            "warnings": warnings,
            "execution_time": execution_time,
        }

    def build_error_response(
        self,
        job_id: str,
        error_type: str,
        message: str,
        execution_time: Optional[float],
        matlab_id: Optional[str] = None,
        stack_trace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a structured error response dict.

        Parameters
        ----------
        job_id:
            The job identifier.
        error_type:
            Type name of the error (e.g. ``"MatlabExecutionError"``).
        message:
            Human-readable error message.
        execution_time:
            Elapsed execution time in seconds (or None).
        matlab_id:
            Optional MATLAB error identifier string.
        stack_trace:
            Optional stack trace string.

        Returns
        -------
        dict
            Structured error response with ``status``, ``job_id``, ``error``,
            and ``execution_time`` keys.
        """
        return {
            "status": "failed",
            "job_id": job_id,
            "error": {
                "type": error_type,
                "message": message,
                "matlab_id": matlab_id,
                "stack_trace": stack_trace,
            },
            "execution_time": execution_time,
        }

"""Mock MATLAB engine for CI testing without a real MATLAB installation.

Simulates the matlab.engine Python API behaviour:
  - MockWorkspace  — dict-like variable storage
  - MockFuture     — wraps concurrent.futures.Future, mirrors matlab.engine future
  - MockMatlabEngine — minimal engine implementation
  - start_matlab() — factory function mirroring matlab.engine.start_matlab()
  - MatlabExecutionError — exception class

Simulated MATLAB behaviours
---------------------------
error('msg')        → raises MatlabExecutionError
clear all           → clears workspace
disp('msg')         → appends to captured output
pause(N)            → sleeps for N seconds
x = 42;             → assigns variable 'x' = 42 in workspace
background=True     → returns MockFuture
"""
from __future__ import annotations

import re
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Optional


class MatlabExecutionError(Exception):
    """Raised when MATLAB code signals an error."""


class MockWorkspace:
    """Dict-like object representing the MATLAB workspace."""

    def __init__(self) -> None:
        self._vars: dict[str, Any] = {}

    # Attribute-style access (mirrors matlab.engine workspace)
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._vars[name]
        except KeyError:
            raise AttributeError(f"MATLAB workspace has no variable '{name}'") from None

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self._vars[name] = value

    def __delattr__(self, name: str) -> None:
        if name.startswith("_"):
            super().__delattr__(name)
        else:
            self._vars.pop(name, None)

    # Dict-style access
    def __getitem__(self, key: str) -> Any:
        return self._vars[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._vars[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._vars

    def __len__(self) -> int:
        return len(self._vars)

    def keys(self):
        return self._vars.keys()

    def values(self):
        return self._vars.values()

    def items(self):
        return self._vars.items()

    def clear(self) -> None:
        self._vars.clear()

    def __repr__(self) -> str:  # pragma: no cover
        return f"MockWorkspace({self._vars!r})"


class MockFuture:
    """Wraps a concurrent.futures.Future to mimic matlab.engine's future API.

    The callable is run in a background thread; result() blocks until done.
    """

    def __init__(self, future: Future) -> None:
        self._future = future

    def result(self, timeout: Optional[float] = None) -> Any:
        """Block and return the result (raises on exception or cancellation)."""
        # Let concurrent.futures handle CancelledError and TimeoutError natively
        return self._future.result(timeout=timeout)

    def cancel(self) -> bool:
        return self._future.cancel()

    def done(self) -> bool:
        return self._future.done()

    def running(self) -> bool:
        return self._future.running()


# Thread pool shared across all engine instances for background execution
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="matlab-mock")


class MockMatlabEngine:
    """Simulated MATLAB engine.

    Only the subset of the matlab.engine API needed for MCP server testing is
    implemented.  Unrecognised MATLAB code patterns are silently ignored.
    """

    def __init__(self) -> None:
        self.workspace = MockWorkspace()
        self._alive: bool = True
        self._last_output: str = ""
        self._paths: list[str] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_alive(self) -> bool:
        return self._alive

    @property
    def last_output(self) -> str:
        return self._last_output

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def eval(
        self,
        code: str,
        nargout: int = 0,
        background: bool = False,
    ) -> Any:
        """Evaluate MATLAB code string.

        Parameters
        ----------
        code:       MATLAB code to run
        nargout:    number of return values expected (ignored in mock)
        background: if True return a MockFuture; the code runs in a thread
        """
        if not self._alive:
            raise MatlabExecutionError("Engine is not alive")

        if background:
            fut = _executor.submit(self._execute, code)
            return MockFuture(fut)
        return self._execute(code)

    def addpath(self, path: str) -> None:
        """Add a path to the MATLAB search path."""
        if path not in self._paths:
            self._paths.append(path)

    def restoredefaultpath(self) -> None:
        """Restore the default MATLAB path (clears custom paths)."""
        self._paths.clear()

    def quit(self) -> None:
        """Terminate the engine."""
        self._alive = False

    # ------------------------------------------------------------------
    # Internal execution
    # ------------------------------------------------------------------

    def _execute(self, code: str) -> None:
        """Parse and simulate a limited set of MATLAB code patterns."""
        output_parts: list[str] = []

        for raw_line in code.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("%"):
                continue

            # error('message') or error("message")
            m = re.match(r"^error\s*\(\s*['\"](.+)['\"]\s*\)\s*;?$", line)
            if m:
                raise MatlabExecutionError(m.group(1))

            # clear all / clear all; / clear (any variant)
            if re.match(r"^clear\s+all\s*;?$", line) or re.match(
                r"^clear\s+all\s+clear\s+global", line
            ):
                self.workspace.clear()
                continue

            # disp('message') or disp("message")
            m = re.match(r"^disp\s*\(\s*['\"](.*)['\"]\s*\)\s*;?$", line)
            if m:
                output_parts.append(m.group(1))
                continue

            # pause(N)
            m = re.match(r"^pause\s*\(\s*([0-9]*\.?[0-9]+)\s*\)\s*;?$", line)
            if m:
                time.sleep(float(m.group(1)))
                continue

            # x = <number>; (simple numeric assignment)
            m = re.match(
                r"^([a-zA-Z_]\w*)\s*=\s*([+-]?[0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?)\s*;?$",
                line,
            )
            if m:
                varname, val_str = m.group(1), m.group(2)
                try:
                    val: Any = int(val_str) if "." not in val_str and "e" not in val_str.lower() else float(val_str)
                except ValueError:
                    val = val_str
                self.workspace[varname] = val
                continue

            # x = 'string'; (simple string assignment)
            m = re.match(r"^([a-zA-Z_]\w*)\s*=\s*'(.*)'\s*;?$", line)
            if m:
                self.workspace[m.group(1)] = m.group(2)
                continue

            # Unrecognised lines are silently ignored (realistic: MATLAB
            # functions we haven't modelled won't raise in the mock)

        self._last_output = "\n".join(output_parts)


def start_matlab() -> MockMatlabEngine:
    """Factory function mirroring matlab.engine.start_matlab()."""
    return MockMatlabEngine()

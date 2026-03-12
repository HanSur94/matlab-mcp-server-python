"""Tests for the MATLAB engine mock."""
from __future__ import annotations

import time

import pytest

from tests.mocks.matlab_engine_mock import (
    MatlabExecutionError,
    MockFuture,
    MockMatlabEngine,
    MockWorkspace,
    start_matlab,
)


# ---------------------------------------------------------------------------
# MockWorkspace
# ---------------------------------------------------------------------------


class TestMockWorkspace:
    def test_set_and_get_attr(self):
        ws = MockWorkspace()
        ws.x = 10
        assert ws.x == 10

    def test_set_and_get_item(self):
        ws = MockWorkspace()
        ws["y"] = 20
        assert ws["y"] == 20

    def test_attr_and_item_are_same_store(self):
        ws = MockWorkspace()
        ws.z = 30
        assert ws["z"] == 30
        ws["w"] = 40
        assert ws.w == 40

    def test_missing_attr_raises(self):
        ws = MockWorkspace()
        with pytest.raises(AttributeError):
            _ = ws.nonexistent

    def test_contains(self):
        ws = MockWorkspace()
        ws.a = 1
        assert "a" in ws
        assert "b" not in ws

    def test_len(self):
        ws = MockWorkspace()
        ws.p = 1
        ws.q = 2
        assert len(ws) == 2

    def test_clear(self):
        ws = MockWorkspace()
        ws.x = 1
        ws.y = 2
        ws.clear()
        assert len(ws) == 0

    def test_keys_values_items(self):
        ws = MockWorkspace()
        ws.x = 1
        ws.y = 2
        assert set(ws.keys()) == {"x", "y"}
        assert set(ws.values()) == {1, 2}
        assert ("x", 1) in ws.items()


# ---------------------------------------------------------------------------
# MockMatlabEngine — basic lifecycle
# ---------------------------------------------------------------------------


class TestMockMatlabEngineLifecycle:
    def test_start_matlab_returns_engine(self):
        engine = start_matlab()
        assert isinstance(engine, MockMatlabEngine)

    def test_engine_alive_initially(self):
        engine = start_matlab()
        assert engine.is_alive is True

    def test_quit_marks_engine_dead(self):
        engine = start_matlab()
        engine.quit()
        assert engine.is_alive is False

    def test_eval_on_dead_engine_raises(self):
        engine = start_matlab()
        engine.quit()
        with pytest.raises(MatlabExecutionError):
            engine.eval("x = 1;")

    def test_addpath(self):
        engine = start_matlab()
        engine.addpath("/some/path")
        assert "/some/path" in engine._paths

    def test_addpath_deduplication(self):
        engine = start_matlab()
        engine.addpath("/some/path")
        engine.addpath("/some/path")
        assert engine._paths.count("/some/path") == 1

    def test_restoredefaultpath(self):
        engine = start_matlab()
        engine.addpath("/path/a")
        engine.addpath("/path/b")
        engine.restoredefaultpath()
        assert engine._paths == []


# ---------------------------------------------------------------------------
# eval — MATLAB code simulation
# ---------------------------------------------------------------------------


class TestEvalError:
    def test_error_call_raises(self):
        engine = start_matlab()
        with pytest.raises(MatlabExecutionError, match="something went wrong"):
            engine.eval("error('something went wrong');")

    def test_error_double_quote(self):
        engine = start_matlab()
        with pytest.raises(MatlabExecutionError, match="oops"):
            engine.eval('error("oops");')


class TestEvalClearAll:
    def test_clear_all_clears_workspace(self):
        engine = start_matlab()
        engine.workspace["x"] = 100
        engine.workspace["y"] = 200
        engine.eval("clear all;")
        assert len(engine.workspace) == 0

    def test_clear_all_no_semicolon(self):
        engine = start_matlab()
        engine.workspace["a"] = 1
        engine.eval("clear all")
        assert len(engine.workspace) == 0


class TestEvalDisp:
    def test_disp_captures_output(self):
        engine = start_matlab()
        engine.eval("disp('hello world');")
        assert engine.last_output == "hello world"

    def test_disp_multiple_lines(self):
        engine = start_matlab()
        engine.eval("disp('line1');\ndisp('line2');")
        assert "line1" in engine.last_output
        assert "line2" in engine.last_output

    def test_disp_empty_string(self):
        engine = start_matlab()
        engine.eval("disp('');")
        assert engine.last_output == ""


class TestEvalAssignment:
    def test_integer_assignment(self):
        engine = start_matlab()
        engine.eval("x = 42;")
        assert engine.workspace["x"] == 42
        assert isinstance(engine.workspace["x"], int)

    def test_float_assignment(self):
        engine = start_matlab()
        engine.eval("pi_approx = 3.14;")
        assert abs(engine.workspace["pi_approx"] - 3.14) < 1e-10

    def test_string_assignment(self):
        engine = start_matlab()
        engine.eval("name = 'MATLAB';")
        assert engine.workspace["name"] == "MATLAB"

    def test_negative_number_assignment(self):
        engine = start_matlab()
        engine.eval("neg = -7;")
        assert engine.workspace["neg"] == -7


class TestEvalPause:
    def test_pause_sleeps(self):
        engine = start_matlab()
        start = time.monotonic()
        engine.eval("pause(0.1);")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.08  # allow some slack


# ---------------------------------------------------------------------------
# Background execution (MockFuture)
# ---------------------------------------------------------------------------


class TestBackgroundExecution:
    def test_background_returns_future(self):
        engine = start_matlab()
        fut = engine.eval("x = 1;", background=True)
        assert isinstance(fut, MockFuture)

    def test_future_result_blocks(self):
        engine = start_matlab()
        fut = engine.eval("x = 99;", background=True)
        fut.result(timeout=5)
        assert engine.workspace["x"] == 99

    def test_future_done_after_result(self):
        engine = start_matlab()
        fut = engine.eval("y = 7;", background=True)
        fut.result(timeout=5)
        assert fut.done() is True

    def test_background_error_propagated_on_result(self):
        engine = start_matlab()
        fut = engine.eval("error('bg error');", background=True)
        with pytest.raises(MatlabExecutionError, match="bg error"):
            fut.result(timeout=5)

    def test_background_pause_completes(self):
        engine = start_matlab()
        start = time.monotonic()
        fut = engine.eval("pause(0.1);", background=True)
        fut.result(timeout=5)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.08

    def test_future_cancel_method_exists(self):
        import concurrent.futures

        engine = start_matlab()
        # Cancellation may not succeed once the future is running, but the
        # API must exist and return a bool without raising.
        fut = engine.eval("pause(0.05);", background=True)
        cancelled = fut.cancel()  # returns bool — don't assert specific value
        assert isinstance(cancelled, bool)
        # Clean up: either the future was cancelled (CancelledError) or
        # it already completed/is running (returns normally).
        try:
            fut.result(timeout=5)
        except concurrent.futures.CancelledError:
            pass  # expected when cancel() succeeded


# ---------------------------------------------------------------------------
# MatlabExecutionError
# ---------------------------------------------------------------------------


class TestMatlabExecutionError:
    def test_is_exception(self):
        err = MatlabExecutionError("test error")
        assert isinstance(err, Exception)

    def test_message_preserved(self):
        err = MatlabExecutionError("specific message")
        assert str(err) == "specific message"

    def test_can_be_caught_as_base_exception(self):
        with pytest.raises(Exception):
            raise MatlabExecutionError("caught as Exception")

"""Unit tests for HITL gate logic (src/matlab_mcp/hitl/gate.py)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from fastmcp.server.context import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)

from matlab_mcp.config import HITLConfig
from matlab_mcp.hitl.gate import (
    DENIED,
    HumanApproval,
    _detect_protected_function,
    _request_approval,
    request_execute_approval,
    request_file_approval,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(elicit_return) -> MagicMock:
    """Return a mock ctx whose .elicit() coroutine returns elicit_return."""
    ctx = MagicMock()
    ctx.elicit = AsyncMock(return_value=elicit_return)
    return ctx


def _accepted(approved: bool) -> MagicMock:
    """Return a mock AcceptedElicitation with data.approved set."""
    obj = MagicMock(spec=AcceptedElicitation)
    obj.data = HumanApproval(approved=approved)
    return obj


def _declined() -> MagicMock:
    return MagicMock(spec=DeclinedElicitation)


def _cancelled() -> MagicMock:
    return MagicMock(spec=CancelledElicitation)


# ---------------------------------------------------------------------------
# TestDisabledDefault
# ---------------------------------------------------------------------------


class TestDisabledDefault:
    """Gate functions return None (no-op) when HITL is disabled."""

    async def test_execute_approval_disabled_by_default(self):
        cfg = HITLConfig()  # enabled=False
        ctx = MagicMock()
        result = await request_execute_approval("x = 1", "sess1", ctx, cfg)
        assert result is None

    async def test_file_approval_disabled_by_default(self):
        cfg = HITLConfig()  # enabled=False
        ctx = MagicMock()
        result = await request_file_approval("upload", "data.mat", "sess1", ctx, cfg)
        assert result is None

    async def test_execute_approval_does_not_call_elicit_when_disabled(self):
        cfg = HITLConfig()
        ctx = _make_ctx(_accepted(True))
        await request_execute_approval("delete(x)", "sess1", ctx, cfg)
        ctx.elicit.assert_not_called()

    async def test_file_approval_does_not_call_elicit_when_disabled(self):
        cfg = HITLConfig()
        ctx = _make_ctx(_accepted(True))
        await request_file_approval("upload", "data.mat", "sess1", ctx, cfg)
        ctx.elicit.assert_not_called()


# ---------------------------------------------------------------------------
# TestProtectedFunctions
# ---------------------------------------------------------------------------


class TestProtectedFunctions:
    """_detect_protected_function and protected-function gate behavior."""

    def test_detects_exact_function_call(self):
        assert _detect_protected_function("delete(x)", ["delete"]) == "delete"

    def test_returns_none_when_no_match(self):
        assert _detect_protected_function("x = 1", ["delete"]) is None

    def test_no_substring_match(self):
        """'delete' must not match 'my_deleter('."""
        assert _detect_protected_function("my_deleter(x)", ["delete"]) is None

    def test_detects_first_match_in_order(self):
        code = "rmdir(path); delete(f)"
        result = _detect_protected_function(code, ["delete", "rmdir"])
        # delete appears second in protected list but rmdir in code first—
        # function iterates protected list order, so 'delete' found first
        assert result == "delete"

    def test_detects_rmdir_in_code(self):
        assert _detect_protected_function("rmdir(path)", ["delete", "rmdir"]) == "rmdir"

    def test_ignores_function_in_string_not_checked_by_gate(self):
        # The gate does not strip strings (that's the security validator's job)
        # but it should still work with raw code
        code = "delete(myfile)"
        assert _detect_protected_function(code, ["delete"]) == "delete"

    async def test_execute_approval_calls_elicit_for_protected_function(self):
        cfg = HITLConfig(enabled=True, protected_functions=["delete"])
        ctx = _make_ctx(_accepted(True))
        result = await request_execute_approval("delete(x)", "sess1", ctx, cfg)
        ctx.elicit.assert_called_once()
        assert result is None  # approved

    async def test_execute_approval_returns_denied_when_declined(self):
        cfg = HITLConfig(enabled=True, protected_functions=["delete"])
        ctx = _make_ctx(_declined())
        result = await request_execute_approval("delete(x)", "sess1", ctx, cfg)
        assert result == DENIED

    async def test_execute_approval_no_prompt_for_non_protected_code(self):
        cfg = HITLConfig(enabled=True, protected_functions=["delete"])
        ctx = _make_ctx(_accepted(True))
        result = await request_execute_approval("x = 1 + 2", "sess1", ctx, cfg)
        ctx.elicit.assert_not_called()
        assert result is None


# ---------------------------------------------------------------------------
# TestAllExecuteGate
# ---------------------------------------------------------------------------


class TestAllExecuteGate:
    """all_execute=True prompts for every execute_code call."""

    async def test_prompts_for_any_code_when_all_execute_true(self):
        cfg = HITLConfig(enabled=True, all_execute=True)
        ctx = _make_ctx(_accepted(True))
        result = await request_execute_approval("x = 1", "sess1", ctx, cfg)
        ctx.elicit.assert_called_once()
        assert result is None

    async def test_returns_none_when_approved(self):
        cfg = HITLConfig(enabled=True, all_execute=True)
        ctx = _make_ctx(_accepted(True))
        result = await request_execute_approval("x = 1 + 2", "sess1", ctx, cfg)
        assert result is None

    async def test_returns_denied_when_declined(self):
        cfg = HITLConfig(enabled=True, all_execute=True)
        ctx = _make_ctx(_declined())
        result = await request_execute_approval("x = 1", "sess1", ctx, cfg)
        assert result == DENIED

    async def test_all_execute_takes_priority_over_protected_functions(self):
        """all_execute path is checked first; protected_functions not separately evaluated."""
        cfg = HITLConfig(enabled=True, all_execute=True, protected_functions=["delete"])
        ctx = _make_ctx(_accepted(True))
        await request_execute_approval("delete(x)", "sess1", ctx, cfg)
        # Only one elicit call (from all_execute), not two
        assert ctx.elicit.call_count == 1


# ---------------------------------------------------------------------------
# TestFileOpsGate
# ---------------------------------------------------------------------------


class TestFileOpsGate:
    """request_file_approval gate for upload/delete operations."""

    async def test_calls_elicit_for_upload_when_protect_file_ops_true(self):
        cfg = HITLConfig(enabled=True, protect_file_ops=True)
        ctx = _make_ctx(_accepted(True))
        result = await request_file_approval("upload", "data.mat", "sess1", ctx, cfg)
        ctx.elicit.assert_called_once()
        assert result is None

    async def test_returns_none_when_protect_file_ops_false(self):
        cfg = HITLConfig(enabled=True, protect_file_ops=False)
        ctx = _make_ctx(_accepted(True))
        result = await request_file_approval("upload", "data.mat", "sess1", ctx, cfg)
        ctx.elicit.assert_not_called()
        assert result is None

    async def test_returns_denied_when_file_op_declined(self):
        cfg = HITLConfig(enabled=True, protect_file_ops=True)
        ctx = _make_ctx(_declined())
        result = await request_file_approval("delete", "old.mat", "sess1", ctx, cfg)
        assert result == DENIED

    async def test_delete_operation_also_prompts(self):
        cfg = HITLConfig(enabled=True, protect_file_ops=True)
        ctx = _make_ctx(_accepted(True))
        result = await request_file_approval("delete", "old.mat", "sess1", ctx, cfg)
        ctx.elicit.assert_called_once()
        assert result is None

    async def test_no_prompt_when_disabled_even_if_protect_file_ops_true(self):
        cfg = HITLConfig(enabled=False, protect_file_ops=True)
        ctx = _make_ctx(_accepted(True))
        result = await request_file_approval("upload", "data.mat", "sess1", ctx, cfg)
        ctx.elicit.assert_not_called()
        assert result is None


# ---------------------------------------------------------------------------
# TestElicitCall
# ---------------------------------------------------------------------------


class TestElicitCall:
    """_request_approval handles AcceptedElicitation, DeclinedElicitation, CancelledElicitation."""

    async def test_returns_true_when_accepted_with_approved_true(self):
        ctx = _make_ctx(_accepted(True))
        result = await _request_approval(ctx, "Approve?")
        assert result is True

    async def test_returns_false_when_accepted_with_approved_false(self):
        ctx = _make_ctx(_accepted(False))
        result = await _request_approval(ctx, "Approve?")
        assert result is False

    async def test_returns_false_when_declined(self):
        ctx = _make_ctx(_declined())
        result = await _request_approval(ctx, "Approve?")
        assert result is False

    async def test_returns_false_when_cancelled(self):
        ctx = _make_ctx(_cancelled())
        result = await _request_approval(ctx, "Approve?")
        assert result is False

"""Tests for tools/admin.py — get_pool_status_impl."""
from __future__ import annotations


class TestGetPoolStatusImpl:
    async def test_returns_pool_status_dict(self):
        """get_pool_status_impl delegates to pool.get_status() and returns the result."""
        from matlab_mcp.tools.admin import get_pool_status_impl

        class MockPool:
            def get_status(self):
                return {"total": 2, "available": 1, "busy": 1, "max": 4}

        result = await get_pool_status_impl(MockPool())
        assert result == {"total": 2, "available": 1, "busy": 1, "max": 4}

    async def test_returns_empty_status(self):
        """get_pool_status_impl should work with an empty status dict."""
        from matlab_mcp.tools.admin import get_pool_status_impl

        class MockPool:
            def get_status(self):
                return {}

        result = await get_pool_status_impl(MockPool())
        assert result == {}

    async def test_returns_arbitrary_keys(self):
        """get_pool_status_impl passes through whatever pool.get_status() returns."""
        from matlab_mcp.tools.admin import get_pool_status_impl

        class MockPool:
            def get_status(self):
                return {"total": 10, "available": 5, "busy": 5, "max": 20, "extra": "data"}

        result = await get_pool_status_impl(MockPool())
        assert result["total"] == 10
        assert result["extra"] == "data"

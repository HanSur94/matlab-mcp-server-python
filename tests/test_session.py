"""Tests for the session manager."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from matlab_mcp.session.manager import Session, SessionManager


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session_manager(tmp_path):
    """A SessionManager backed by a tmp directory with tight limits."""
    from matlab_mcp.config import AppConfig, ExecutionConfig, SessionsConfig

    cfg = AppConfig()
    cfg.sessions = SessionsConfig(max_sessions=5, session_timeout=3600)
    cfg.execution = ExecutionConfig(temp_dir=str(tmp_path / "temp"))
    return SessionManager(cfg)


@pytest.fixture
def tight_session_manager(tmp_path):
    """A SessionManager with max_sessions=2."""
    from matlab_mcp.config import AppConfig, ExecutionConfig, SessionsConfig

    cfg = AppConfig()
    cfg.sessions = SessionsConfig(max_sessions=2, session_timeout=3600)
    cfg.execution = ExecutionConfig(temp_dir=str(tmp_path / "temp"))
    return SessionManager(cfg)


# ---------------------------------------------------------------------------
# Session dataclass tests
# ---------------------------------------------------------------------------

class TestSessionDataclass:
    def test_session_has_session_id(self, tmp_path):
        s = Session(session_id="s1", temp_dir=str(tmp_path))
        assert s.session_id == "s1"

    def test_session_has_temp_dir(self, tmp_path):
        s = Session(session_id="s1", temp_dir=str(tmp_path))
        assert s.temp_dir == str(tmp_path)

    def test_created_at_set(self, tmp_path):
        before = time.time()
        s = Session(session_id="s1", temp_dir=str(tmp_path))
        after = time.time()
        assert before <= s.created_at <= after

    def test_last_active_set(self, tmp_path):
        before = time.time()
        s = Session(session_id="s1", temp_dir=str(tmp_path))
        after = time.time()
        assert before <= s.last_active <= after

    def test_touch_updates_last_active(self, tmp_path):
        s = Session(session_id="s1", temp_dir=str(tmp_path))
        original = s.last_active
        time.sleep(0.02)
        s.touch()
        assert s.last_active > original

    def test_idle_seconds_is_small_for_new_session(self, tmp_path):
        s = Session(session_id="s1", temp_dir=str(tmp_path))
        assert s.idle_seconds < 1.0

    def test_idle_seconds_increases_over_time(self, tmp_path):
        s = Session(session_id="s1", temp_dir=str(tmp_path))
        time.sleep(0.05)
        assert s.idle_seconds >= 0.04


# ---------------------------------------------------------------------------
# SessionManager.create_session
# ---------------------------------------------------------------------------

class TestCreateSession:
    def test_create_returns_session(self, session_manager):
        s = session_manager.create_session()
        assert isinstance(s, Session)

    def test_create_assigns_unique_id(self, session_manager):
        s1 = session_manager.create_session()
        s2 = session_manager.create_session()
        assert s1.session_id != s2.session_id

    def test_create_makes_temp_dir(self, session_manager):
        s = session_manager.create_session()
        assert Path(s.temp_dir).exists()

    def test_create_increments_count(self, session_manager):
        assert session_manager.session_count == 0
        session_manager.create_session()
        assert session_manager.session_count == 1

    def test_create_max_sessions_enforced(self, tight_session_manager):
        tight_session_manager.create_session()
        tight_session_manager.create_session()
        with pytest.raises(RuntimeError, match="Maximum number of sessions"):
            tight_session_manager.create_session()


# ---------------------------------------------------------------------------
# SessionManager.get_session
# ---------------------------------------------------------------------------

class TestGetSession:
    def test_get_existing_session(self, session_manager):
        s = session_manager.create_session()
        retrieved = session_manager.get_session(s.session_id)
        assert retrieved is s

    def test_get_nonexistent_returns_none(self, session_manager):
        assert session_manager.get_session("nonexistent") is None


# ---------------------------------------------------------------------------
# SessionManager.get_or_create_default
# ---------------------------------------------------------------------------

class TestGetOrCreateDefault:
    def test_creates_default_session(self, session_manager):
        s = session_manager.get_or_create_default()
        assert s is not None
        assert s.session_id == "default"

    def test_returns_same_default_session(self, session_manager):
        s1 = session_manager.get_or_create_default()
        s2 = session_manager.get_or_create_default()
        assert s1 is s2

    def test_default_temp_dir_created(self, session_manager):
        s = session_manager.get_or_create_default()
        assert Path(s.temp_dir).exists()

    def test_default_session_is_retrievable(self, session_manager):
        s = session_manager.get_or_create_default()
        retrieved = session_manager.get_session("default")
        assert retrieved is s


# ---------------------------------------------------------------------------
# SessionManager.destroy_session
# ---------------------------------------------------------------------------

class TestDestroySession:
    def test_destroy_removes_session(self, session_manager):
        s = session_manager.create_session()
        session_manager.destroy_session(s.session_id)
        assert session_manager.get_session(s.session_id) is None

    def test_destroy_removes_temp_dir(self, session_manager):
        s = session_manager.create_session()
        temp_path = Path(s.temp_dir)
        assert temp_path.exists()
        session_manager.destroy_session(s.session_id)
        assert not temp_path.exists()

    def test_destroy_returns_true_on_success(self, session_manager):
        s = session_manager.create_session()
        assert session_manager.destroy_session(s.session_id) is True

    def test_destroy_returns_false_for_unknown(self, session_manager):
        assert session_manager.destroy_session("nonexistent") is False

    def test_destroy_decrements_count(self, session_manager):
        s = session_manager.create_session()
        assert session_manager.session_count == 1
        session_manager.destroy_session(s.session_id)
        assert session_manager.session_count == 0

    def test_destroy_idempotent_for_missing_temp_dir(self, session_manager):
        """Destroying a session whose temp dir was already deleted should not raise."""
        s = session_manager.create_session()
        import shutil
        shutil.rmtree(s.temp_dir)
        # Should not raise
        result = session_manager.destroy_session(s.session_id)
        assert result is True


# ---------------------------------------------------------------------------
# SessionManager.cleanup_expired
# ---------------------------------------------------------------------------

class TestCleanupExpired:
    def test_cleanup_removes_idle_sessions(self, tmp_path):
        """Sessions beyond the timeout should be removed."""
        from matlab_mcp.config import AppConfig, ExecutionConfig, SessionsConfig
        cfg = AppConfig()
        cfg.sessions = SessionsConfig(max_sessions=10, session_timeout=1)
        cfg.execution = ExecutionConfig(temp_dir=str(tmp_path / "temp"))
        mgr = SessionManager(cfg)

        s = mgr.create_session()
        # Backdate last_active
        s.last_active = time.time() - 2
        removed = mgr.cleanup_expired()
        assert removed == 1
        assert mgr.get_session(s.session_id) is None

    def test_cleanup_keeps_recent_sessions(self, session_manager):
        """Sessions active within the timeout should NOT be removed."""
        s = session_manager.create_session()
        removed = session_manager.cleanup_expired()
        assert removed == 0
        assert session_manager.get_session(s.session_id) is not None

    def test_cleanup_skips_sessions_with_active_jobs(self, tmp_path):
        """Sessions with active jobs should be preserved even if idle."""
        from matlab_mcp.config import AppConfig, ExecutionConfig, SessionsConfig
        cfg = AppConfig()
        cfg.sessions = SessionsConfig(max_sessions=10, session_timeout=1)
        cfg.execution = ExecutionConfig(temp_dir=str(tmp_path / "temp"))
        mgr = SessionManager(cfg)

        s = mgr.create_session()
        s.last_active = time.time() - 2

        # Simulate active jobs for this session
        def has_active_jobs(sid: str) -> bool:
            return sid == s.session_id

        removed = mgr.cleanup_expired(has_active_jobs_fn=has_active_jobs)
        assert removed == 0
        assert mgr.get_session(s.session_id) is not None

    def test_cleanup_removes_only_eligible_sessions(self, tmp_path):
        """Only expired sessions without active jobs should be removed."""
        from matlab_mcp.config import AppConfig, ExecutionConfig, SessionsConfig
        cfg = AppConfig()
        cfg.sessions = SessionsConfig(max_sessions=10, session_timeout=1)
        cfg.execution = ExecutionConfig(temp_dir=str(tmp_path / "temp"))
        mgr = SessionManager(cfg)

        s_old = mgr.create_session()
        s_old.last_active = time.time() - 2

        s_new = mgr.create_session()
        # s_new is still recent

        removed = mgr.cleanup_expired()
        assert removed == 1
        assert mgr.get_session(s_old.session_id) is None
        assert mgr.get_session(s_new.session_id) is not None

    def test_cleanup_returns_count(self, tmp_path):
        from matlab_mcp.config import AppConfig, ExecutionConfig, SessionsConfig
        cfg = AppConfig()
        cfg.sessions = SessionsConfig(max_sessions=10, session_timeout=1)
        cfg.execution = ExecutionConfig(temp_dir=str(tmp_path / "temp"))
        mgr = SessionManager(cfg)

        for _ in range(3):
            s = mgr.create_session()
            s.last_active = time.time() - 2

        assert mgr.cleanup_expired() == 3


class TestSessionManagerDefaults:
    def test_default_temp_dir_is_cross_platform(self):
        import tempfile as _tempfile
        mgr = SessionManager(config=None)
        expected = str(Path(_tempfile.gettempdir()) / "matlab_mcp")
        assert str(mgr._base_temp) == expected


class TestSessionMonitoringEvents:
    def test_create_session_records_event(self):
        from unittest.mock import MagicMock
        from matlab_mcp.session.manager import SessionManager
        from matlab_mcp.config import load_config
        collector = MagicMock()
        manager = SessionManager(load_config(None), collector=collector)
        manager.create_session()
        collector.record_event.assert_called_once()
        assert collector.record_event.call_args[0][0] == "session_created"

    def test_get_or_create_default_records_event_only_once(self):
        from unittest.mock import MagicMock
        from matlab_mcp.session.manager import SessionManager
        from matlab_mcp.config import load_config
        collector = MagicMock()
        manager = SessionManager(load_config(None), collector=collector)
        manager.get_or_create_default()
        manager.get_or_create_default()
        assert collector.record_event.call_count == 1

    def test_no_collector_does_not_crash(self):
        from matlab_mcp.session.manager import SessionManager
        from matlab_mcp.config import load_config
        manager = SessionManager(load_config(None))
        session = manager.create_session()
        assert session is not None

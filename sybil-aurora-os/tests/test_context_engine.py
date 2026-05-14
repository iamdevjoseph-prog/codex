"""
Tests for context-engine skill.

Filesystem backend tests always run.
Redis backend tests run only when a Redis server is reachable at
REDIS_URL (or redis://localhost:6379 by default) and the redis package
is importable — otherwise they are skipped cleanly.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.skill_loader import register_all_as_python_packages
register_all_as_python_packages()

# Force a fresh module load so _backend is None on each test run
import importlib


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fs_engine(tmp_path: Path):
    """Return a fresh _FilesystemBackend pointed at tmp_path."""
    from core.skills.context_engine.main import _FilesystemBackend
    return _FilesystemBackend(tmp_path)


def _run_with_fs(tmp_path: Path, params: dict) -> dict:
    """Invoke context-engine with a filesystem backend in tmp_path."""
    from core.skills.context_engine.main import _FilesystemBackend
    backend = _FilesystemBackend(tmp_path)
    with patch("core.skills.context_engine.main._get_backend", return_value=backend):
        from core.skills.context_engine.main import invoke
        return invoke(params)


def _redis_available() -> bool:
    try:
        import redis as _r
        r = _r.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
        r.ping()
        return True
    except Exception:
        return False


requires_redis = pytest.mark.skipif(
    not _redis_available(),
    reason="Redis not available",
)


# ---------------------------------------------------------------------------
# Filesystem backend — unit tests
# ---------------------------------------------------------------------------

class TestFilesystemBackend:
    def test_store_and_retrieve(self, tmp_path):
        b = _fs_engine(tmp_path)
        b.store("sess", "k1", {"x": 1})
        result = b.retrieve("sess", "k1")
        assert result["success"] is True
        assert result["data"]["value"] == {"x": 1}
        assert result["backend"] == "filesystem"

    def test_retrieve_missing_key(self, tmp_path):
        b = _fs_engine(tmp_path)
        result = b.retrieve("sess", "missing")
        assert result["success"] is False
        assert "missing" in result["error"]

    def test_store_creates_session_dir(self, tmp_path):
        b = _fs_engine(tmp_path)
        b.store("new-session", "key", "val")
        assert (tmp_path / "new-session").is_dir()

    def test_store_record_has_stored_at(self, tmp_path):
        b = _fs_engine(tmp_path)
        before = int(time.time())
        r = b.store("s", "k", "v")
        assert r["data"]["stored_at"] >= before

    def test_search_finds_matching_records(self, tmp_path):
        b = _fs_engine(tmp_path)
        b.store("s", "deal1", {"address": "123 Main St Austin"})
        b.store("s", "deal2", {"address": "456 Oak Ave Dallas"})
        result = b.search("s", "Austin", 5)
        assert result["success"] is True
        assert len(result["matches"]) == 1
        assert result["matches"][0]["value"]["address"] == "123 Main St Austin"

    def test_search_no_match(self, tmp_path):
        b = _fs_engine(tmp_path)
        b.store("s", "x", {"data": "nothing relevant"})
        result = b.search("s", "quantum banana", 5)
        assert result["matches"] == []

    def test_search_respects_top_k(self, tmp_path):
        b = _fs_engine(tmp_path)
        for i in range(10):
            b.store("s", f"key{i}", {"tag": "common"})
        result = b.search("s", "common", 3)
        assert len(result["matches"]) <= 3

    def test_summarize_counts_records(self, tmp_path):
        b = _fs_engine(tmp_path)
        b.store("s", "a", 1)
        b.store("s", "b", 2)
        b.store("s", "c", 3)
        result = b.summarize("s")
        assert result["data"]["total_records"] == 3
        assert set(result["data"]["keys"]) == {"a", "b", "c"}

    def test_summarize_empty_session(self, tmp_path):
        b = _fs_engine(tmp_path)
        result = b.summarize("empty-session")
        assert result["data"]["total_records"] == 0

    def test_clear_removes_all_keys(self, tmp_path):
        b = _fs_engine(tmp_path)
        b.store("s", "a", 1)
        b.store("s", "b", 2)
        clear_result = b.clear("s")
        assert clear_result["data"]["cleared"] == 2
        summary = b.summarize("s")
        assert summary["data"]["total_records"] == 0

    def test_clear_empty_session(self, tmp_path):
        b = _fs_engine(tmp_path)
        result = b.clear("empty")
        assert result["data"]["cleared"] == 0

    def test_sessions_are_isolated(self, tmp_path):
        b = _fs_engine(tmp_path)
        b.store("sess-a", "key", "value-a")
        b.store("sess-b", "key", "value-b")
        r_a = b.retrieve("sess-a", "key")
        r_b = b.retrieve("sess-b", "key")
        assert r_a["data"]["value"] == "value-a"
        assert r_b["data"]["value"] == "value-b"

    def test_overwrite_existing_key(self, tmp_path):
        b = _fs_engine(tmp_path)
        b.store("s", "k", "first")
        b.store("s", "k", "second")
        result = b.retrieve("s", "k")
        assert result["data"]["value"] == "second"


# ---------------------------------------------------------------------------
# invoke() interface (filesystem backend)
# ---------------------------------------------------------------------------

class TestInvokeInterface:
    def test_store_returns_success_status(self, tmp_path):
        r = _run_with_fs(tmp_path, {"operation": "store", "session_id": "s", "key": "k", "value": 42})
        assert r["status"] == "success"
        assert r["skill"] == "context-engine"

    def test_retrieve_returns_stored_value(self, tmp_path):
        _run_with_fs(tmp_path, {"operation": "store", "session_id": "s", "key": "deal", "value": {"noi": 280_000}})
        r = _run_with_fs(tmp_path, {"operation": "retrieve", "session_id": "s", "key": "deal"})
        assert r["status"] == "success"
        assert r["data"]["value"]["noi"] == 280_000

    def test_search_operation(self, tmp_path):
        _run_with_fs(tmp_path, {"operation": "store", "session_id": "s", "key": "x", "value": "Austin real estate"})
        r = _run_with_fs(tmp_path, {"operation": "search", "session_id": "s", "query": "Austin"})
        assert r["status"] == "success"
        assert len(r["matches"]) == 1

    def test_summarize_operation(self, tmp_path):
        _run_with_fs(tmp_path, {"operation": "store", "session_id": "s", "key": "a", "value": 1})
        r = _run_with_fs(tmp_path, {"operation": "summarize", "session_id": "s"})
        assert r["data"]["total_records"] == 1

    def test_clear_operation(self, tmp_path):
        _run_with_fs(tmp_path, {"operation": "store", "session_id": "s", "key": "a", "value": 1})
        r = _run_with_fs(tmp_path, {"operation": "clear", "session_id": "s"})
        assert r["data"]["cleared"] == 1

    def test_unknown_operation(self, tmp_path):
        r = _run_with_fs(tmp_path, {"operation": "fly", "session_id": "s"})
        assert r["status"] == "success"
        assert r["success"] is False
        assert "Unknown operation" in r["error"]

    def test_default_session_id(self, tmp_path):
        r = _run_with_fs(tmp_path, {"operation": "store", "key": "k", "value": "v"})
        assert r["status"] == "success"

    def test_backend_key_present(self, tmp_path):
        r = _run_with_fs(tmp_path, {"operation": "store", "session_id": "s", "key": "k", "value": "v"})
        assert r["backend"] == "filesystem"


# ---------------------------------------------------------------------------
# Backend resolution
# ---------------------------------------------------------------------------

class TestBackendResolution:
    def test_resolves_filesystem_when_no_redis_url(self, tmp_path, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("CONTEXT_STORE_DIR", str(tmp_path))
        from core.skills.context_engine.main import _FilesystemBackend, _resolve_backend
        b = _resolve_backend()
        assert isinstance(b, _FilesystemBackend)

    def test_resolves_filesystem_when_redis_unreachable(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:19999")  # nothing listens here
        monkeypatch.setenv("CONTEXT_STORE_DIR", str(tmp_path))
        from core.skills.context_engine.main import _FilesystemBackend, _resolve_backend
        b = _resolve_backend()
        assert isinstance(b, _FilesystemBackend)

    def test_resolves_filesystem_when_redis_package_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("CONTEXT_STORE_DIR", str(tmp_path))
        with patch.dict("sys.modules", {"redis": None}):
            from core.skills.context_engine.main import _FilesystemBackend, _resolve_backend
            b = _resolve_backend()
        assert isinstance(b, _FilesystemBackend)


# ---------------------------------------------------------------------------
# Redis backend (skipped when Redis unavailable)
# ---------------------------------------------------------------------------

class TestRedisBackend:
    @requires_redis
    def test_store_and_retrieve(self):
        import redis as _r
        from core.skills.context_engine.main import _RedisBackend
        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        b = _RedisBackend(url, ttl=60)
        sid = f"test-{int(time.time())}"
        b.store(sid, "k", {"val": 99})
        r = b.retrieve(sid, "k")
        assert r["success"] is True
        assert r["data"]["value"] == {"val": 99}
        assert r["backend"] == "redis"
        b.clear(sid)

    @requires_redis
    def test_retrieve_missing_key(self):
        from core.skills.context_engine.main import _RedisBackend
        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        b = _RedisBackend(url, ttl=60)
        sid = f"test-{int(time.time())}"
        r = b.retrieve(sid, "nonexistent")
        assert r["success"] is False
        b.clear(sid)

    @requires_redis
    def test_search(self):
        from core.skills.context_engine.main import _RedisBackend
        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        b = _RedisBackend(url, ttl=60)
        sid = f"test-{int(time.time())}"
        b.store(sid, "d1", {"city": "Austin"})
        b.store(sid, "d2", {"city": "Dallas"})
        r = b.search(sid, "Austin", 5)
        assert r["success"] is True
        assert len(r["matches"]) == 1
        b.clear(sid)

    @requires_redis
    def test_summarize(self):
        from core.skills.context_engine.main import _RedisBackend
        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        b = _RedisBackend(url, ttl=60)
        sid = f"test-{int(time.time())}"
        b.store(sid, "a", 1)
        b.store(sid, "b", 2)
        r = b.summarize(sid)
        assert r["data"]["total_records"] == 2
        b.clear(sid)

    @requires_redis
    def test_clear(self):
        from core.skills.context_engine.main import _RedisBackend
        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        b = _RedisBackend(url, ttl=60)
        sid = f"test-{int(time.time())}"
        b.store(sid, "x", 1)
        r = b.clear(sid)
        assert r["data"]["cleared"] == 1
        assert r["backend"] == "redis"

    @requires_redis
    def test_ttl_set_on_store(self):
        import redis as _r
        from core.skills.context_engine.main import _RedisBackend
        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        b = _RedisBackend(url, ttl=300)
        sid = f"test-ttl-{int(time.time())}"
        b.store(sid, "k", "v")
        ttl = b._client.ttl(b._rkey(sid))
        assert 0 < ttl <= 300
        b.clear(sid)

    @requires_redis
    def test_sessions_isolated(self):
        from core.skills.context_engine.main import _RedisBackend
        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        b = _RedisBackend(url, ttl=60)
        ts = int(time.time())
        b.store(f"sess-a-{ts}", "k", "alpha")
        b.store(f"sess-b-{ts}", "k", "beta")
        r_a = b.retrieve(f"sess-a-{ts}", "k")
        r_b = b.retrieve(f"sess-b-{ts}", "k")
        assert r_a["data"]["value"] == "alpha"
        assert r_b["data"]["value"] == "beta"
        b.clear(f"sess-a-{ts}")
        b.clear(f"sess-b-{ts}")

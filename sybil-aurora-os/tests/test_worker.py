"""
Tests for aurora/services/worker.py

All tests run without a live Redis server by patching _get_redis.
The Worker class itself is exercised by injecting a mock Redis client
directly into _execute_job and the queue-drain loop.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from aurora.services.worker import (
    Worker,
    _execute_job,
    _result_key,
    _redis_from_url,
    RESULT_PREFIX,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_redis() -> MagicMock:
    """Return a MagicMock that behaves like a redis.Redis client."""
    rc = MagicMock()
    rc.get.return_value = None
    rc.brpop.return_value = None
    return rc


def _fake_skill_run(name, params):
    return {"status": "success", "data": {"skill": name, "params": params}}


# ---------------------------------------------------------------------------
# _result_key
# ---------------------------------------------------------------------------

class TestResultKey:
    def test_prefix(self):
        key = _result_key("abc")
        assert key.startswith(RESULT_PREFIX)

    def test_contains_job_id(self):
        assert "job-123" in _result_key("job-123")


# ---------------------------------------------------------------------------
# _execute_job
# ---------------------------------------------------------------------------

class TestExecuteJob:
    def test_success_stores_result(self):
        rc = _mock_redis()
        with patch("aurora.services.worker._skill_run", side_effect=_fake_skill_run):
            _execute_job({"job_id": "j1", "skill": "seo-engine", "input": {"topic": "test"}}, rc)
        rc.set.assert_called_once()
        key, value = rc.set.call_args[0]
        assert key == _result_key("j1")
        stored = json.loads(value)
        assert stored["status"] == "success"
        assert stored["job_id"] == "j1"
        assert "result" in stored

    def test_success_record_has_timestamps(self):
        rc = _mock_redis()
        before = int(time.time())
        with patch("aurora.services.worker._skill_run", side_effect=_fake_skill_run):
            _execute_job({"job_id": "j2", "skill": "seo-engine", "input": {}}, rc)
        stored = json.loads(rc.set.call_args[0][1])
        assert stored["started_at"] >= before
        assert stored["finished_at"] >= stored["started_at"]

    def test_missing_skill_field_writes_error(self):
        rc = _mock_redis()
        _execute_job({"job_id": "j3", "input": {}}, rc)
        stored = json.loads(rc.set.call_args[0][1])
        assert stored["status"] == "error"
        assert stored["error"] is not None

    def test_invalid_input_type_writes_error(self):
        rc = _mock_redis()
        _execute_job({"job_id": "j4", "skill": "seo-engine", "input": "not-a-dict"}, rc)
        stored = json.loads(rc.set.call_args[0][1])
        assert stored["status"] == "error"

    def test_unknown_skill_writes_error(self):
        rc = _mock_redis()
        with patch("aurora.services.worker._skill_run", side_effect=ImportError("not found")):
            _execute_job({"job_id": "j5", "skill": "no-such-skill", "input": {}}, rc)
        stored = json.loads(rc.set.call_args[0][1])
        assert stored["status"] == "error"
        assert "not found" in stored["error"]

    def test_skill_exception_writes_error(self):
        rc = _mock_redis()
        with patch("aurora.services.worker._skill_run", side_effect=RuntimeError("boom")):
            _execute_job({"job_id": "j6", "skill": "seo-engine", "input": {}}, rc)
        stored = json.loads(rc.set.call_args[0][1])
        assert stored["status"] == "error"
        assert "boom" in stored["error"]

    def test_result_ttl_set(self):
        rc = _mock_redis()
        with patch("aurora.services.worker._skill_run", side_effect=_fake_skill_run):
            _execute_job({"job_id": "j7", "skill": "seo-engine", "input": {}}, rc)
        _, kwargs = rc.set.call_args
        assert "ex" in kwargs
        assert kwargs["ex"] > 0

    def test_notify_publishes_event(self):
        rc = _mock_redis()
        with patch("aurora.services.worker._skill_run", side_effect=_fake_skill_run):
            _execute_job({"job_id": "j8", "skill": "seo-engine", "input": {}, "notify": True}, rc)
        rc.publish.assert_called_once()
        channel, msg = rc.publish.call_args[0]
        assert "j8" in channel
        assert "j8" in json.loads(msg)["job_id"]

    def test_no_notify_no_publish(self):
        rc = _mock_redis()
        with patch("aurora.services.worker._skill_run", side_effect=_fake_skill_run):
            _execute_job({"job_id": "j9", "skill": "seo-engine", "input": {}}, rc)
        rc.publish.assert_not_called()

    def test_auto_generates_job_id_when_missing(self):
        rc = _mock_redis()
        with patch("aurora.services.worker._skill_run", side_effect=_fake_skill_run):
            _execute_job({"skill": "seo-engine", "input": {}}, rc)
        stored = json.loads(rc.set.call_args[0][1])
        assert stored["job_id"]  # auto-generated UUID

    def test_error_field_none_on_success(self):
        rc = _mock_redis()
        with patch("aurora.services.worker._skill_run", side_effect=_fake_skill_run):
            _execute_job({"job_id": "j10", "skill": "seo-engine", "input": {}}, rc)
        stored = json.loads(rc.set.call_args[0][1])
        assert stored["error"] is None


# ---------------------------------------------------------------------------
# Worker class — lifecycle
# ---------------------------------------------------------------------------

class TestWorkerLifecycle:
    def test_start_spawns_threads(self):
        stop = threading.Event()
        stop.set()  # prevent loops from actually blocking
        w = Worker(concurrency=2)
        with patch("aurora.services.worker._get_redis", return_value=_mock_redis()):
            w.start()
        # Threads are daemon and may exit immediately since stop is set
        assert len(w._threads) == 2

    def test_stop_clears_threads(self):
        w = Worker(concurrency=1)
        rc = _mock_redis()
        rc.brpop.return_value = None
        with patch("aurora.services.worker._get_redis", return_value=rc):
            w.start()
            w.stop(timeout=2)
        assert not w._threads

    def test_is_running_false_before_start(self):
        w = Worker(concurrency=1)
        assert not w.is_running


# ---------------------------------------------------------------------------
# Worker.enqueue / get_result / wait_for_result
# ---------------------------------------------------------------------------

class TestWorkerAPI:
    def test_enqueue_pushes_to_queue(self):
        rc = _mock_redis()
        with patch("aurora.services.worker._redis_from_url", return_value=rc):
            jid = Worker.enqueue("seo-engine", {"topic": "test"})
        assert isinstance(jid, str)
        assert len(jid) == 36  # UUID

    def test_enqueue_uses_provided_job_id(self):
        rc = _mock_redis()
        with patch("aurora.services.worker._redis_from_url", return_value=rc):
            jid = Worker.enqueue("seo-engine", {}, job_id="custom-id-123")
        assert jid == "custom-id-123"
        pushed = json.loads(rc.lpush.call_args[0][1])
        assert pushed["job_id"] == "custom-id-123"

    def test_get_result_returns_none_when_missing(self):
        rc = _mock_redis()
        rc.get.return_value = None
        with patch("aurora.services.worker._redis_from_url", return_value=rc):
            result = Worker.get_result("nonexistent-id")
        assert result is None

    def test_get_result_parses_stored_json(self):
        rc = _mock_redis()
        stored = {"job_id": "x", "status": "success", "result": {}, "error": None,
                  "started_at": 1, "finished_at": 2}
        rc.get.return_value = json.dumps(stored)
        with patch("aurora.services.worker._redis_from_url", return_value=rc):
            result = Worker.get_result("x")
        assert result["status"] == "success"
        assert result["job_id"] == "x"

    def test_wait_for_result_returns_on_first_hit(self):
        rc = _mock_redis()
        stored = {"job_id": "y", "status": "success", "result": {}, "error": None,
                  "started_at": 1, "finished_at": 1}
        rc.get.return_value = json.dumps(stored)
        with patch("aurora.services.worker._redis_from_url", return_value=rc):
            result = Worker.wait_for_result("y", timeout=5)
        assert result is not None
        assert result["job_id"] == "y"

    def test_wait_for_result_returns_none_on_timeout(self):
        rc = _mock_redis()
        rc.get.return_value = None  # never available
        with patch("aurora.services.worker._redis_from_url", return_value=rc):
            result = Worker.wait_for_result("z", timeout=0.1, poll_interval=0.05)
        assert result is None


# ---------------------------------------------------------------------------
# Integration: full enqueue → execute → get_result cycle (no real Redis)
# ---------------------------------------------------------------------------

class TestIntegrationCycle:
    def test_execute_job_result_round_trip(self):
        """Simulate the full cycle: build job dict → execute → verify result shape."""
        store: dict = {}

        rc = MagicMock()
        rc.set.side_effect = lambda k, v, ex=None: store.__setitem__(k, v)
        rc.get.side_effect = lambda k: store.get(k)

        with patch("aurora.services.worker._skill_run", side_effect=_fake_skill_run):
            _execute_job({"job_id": "integ-1", "skill": "seo-engine", "input": {"topic": "CRE"}}, rc)

        raw = store.get(_result_key("integ-1"))
        assert raw is not None
        result = json.loads(raw)
        assert result["status"] == "success"
        assert result["result"]["data"]["skill"] == "seo-engine"

    def test_error_result_has_full_schema(self):
        """Error records must carry all schema fields even on failure."""
        rc = _mock_redis()
        with patch("aurora.services.worker._skill_run", side_effect=ValueError("bad")):
            _execute_job({"job_id": "integ-2", "skill": "seo-engine", "input": {}}, rc)
        stored = json.loads(rc.set.call_args[0][1])
        for field in ("job_id", "status", "result", "error", "started_at", "finished_at"):
            assert field in stored, f"missing field: {field}"

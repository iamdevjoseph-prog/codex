"""
Tests for aurora/services/app.py — the FastAPI layer.

Coverage:
  - /health (no auth required)
  - /execute — pipeline runs, response shape, auth enforcement
  - /execute/stream — SSE events, content-type, event sequence
  - /debug — returns staged trace
  - /skills/{name}/invoke — real skill dispatch, 404 for unknown
  - /context/{session_id} — context retrieval
  - Auth: 401 when SYBIL_API_KEY set and key wrong/missing;
          open when SYBIL_API_KEY not set
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))

# Import the app — Orchestrator is instantiated at module level so patch before import
# by using the already-imported module.
from aurora.services.app import app, _orchestrator

client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_api_key_env(monkeypatch):
    """Default: no API key set so all tests run open unless they explicitly set one."""
    monkeypatch.delenv("SYBIL_API_KEY", raising=False)


def _mock_run_result(approved: bool = True) -> dict:
    return {
        "intent": {"agent": "deal-analysis-agent", "skills": [], "classifier": "keyword"},
        "results": [],
        "agent": "deal-analysis-agent",
        "quality_score": 0.85,
        "approved": approved,
        "message": "Intelligent routing active",
    }


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_200(self):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_body(self):
        resp = client.get("/health")
        body = resp.json()
        assert body["status"] == "ok"
        assert body["system"] == "sybil-aurora-os"
        assert "version" in body

    def test_health_requires_no_auth(self, monkeypatch):
        monkeypatch.setenv("SYBIL_API_KEY", "secret")
        # health should still work with no key
        resp = client.get("/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------

class TestAuth:
    def test_no_env_key_allows_any_request(self):
        """When SYBIL_API_KEY is unset, all requests pass through."""
        resp = client.post("/execute", json={"input": "test"})
        assert resp.status_code != 401

    def test_correct_key_allowed(self, monkeypatch):
        monkeypatch.setenv("SYBIL_API_KEY", "my-secret")
        resp = client.post(
            "/execute",
            json={"input": "test"},
            headers={"X-API-Key": "my-secret"},
        )
        assert resp.status_code != 401

    def test_wrong_key_returns_401(self, monkeypatch):
        monkeypatch.setenv("SYBIL_API_KEY", "my-secret")
        resp = client.post(
            "/execute",
            json={"input": "test"},
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401

    def test_missing_key_returns_401(self, monkeypatch):
        monkeypatch.setenv("SYBIL_API_KEY", "my-secret")
        resp = client.post("/execute", json={"input": "test"})
        assert resp.status_code == 401

    def test_401_detail_message(self, monkeypatch):
        monkeypatch.setenv("SYBIL_API_KEY", "secret")
        resp = client.post("/execute", json={"input": "x"}, headers={"X-API-Key": "bad"})
        assert "Invalid" in resp.json()["detail"] or "missing" in resp.json()["detail"].lower()

    def test_debug_endpoint_also_protected(self, monkeypatch):
        monkeypatch.setenv("SYBIL_API_KEY", "secret")
        resp = client.post("/debug", json={"input": "x"})
        assert resp.status_code == 401

    def test_skill_endpoint_also_protected(self, monkeypatch):
        monkeypatch.setenv("SYBIL_API_KEY", "secret")
        resp = client.post("/skills/seo-engine/invoke", json={"params": {}})
        assert resp.status_code == 401

    def test_context_endpoint_also_protected(self, monkeypatch):
        monkeypatch.setenv("SYBIL_API_KEY", "secret")
        resp = client.get("/context/session-1")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /execute
# ---------------------------------------------------------------------------

class TestExecute:
    def test_returns_200(self):
        with patch.object(_orchestrator, "run", return_value=_mock_run_result()):
            resp = client.post("/execute", json={"input": "analyze this deal"})
        assert resp.status_code == 200

    def test_response_shape(self):
        with patch.object(_orchestrator, "run", return_value=_mock_run_result()):
            resp = client.post("/execute", json={"input": "analyze"})
        body = resp.json()
        for key in ("request_id", "status", "result", "execution_time"):
            assert key in body, f"missing key: {key}"

    def test_status_success_when_approved(self):
        with patch.object(_orchestrator, "run", return_value=_mock_run_result(approved=True)):
            resp = client.post("/execute", json={"input": "x"})
        assert resp.json()["status"] == "success"

    def test_status_degraded_when_not_approved(self):
        with patch.object(_orchestrator, "run", return_value=_mock_run_result(approved=False)):
            resp = client.post("/execute", json={"input": "x"})
        assert resp.json()["status"] == "degraded"

    def test_request_id_is_uuid_format(self):
        import uuid
        with patch.object(_orchestrator, "run", return_value=_mock_run_result()):
            resp = client.post("/execute", json={"input": "x"})
        rid = resp.json()["request_id"]
        uuid.UUID(rid)  # raises ValueError if not a valid UUID

    def test_execution_time_is_float(self):
        with patch.object(_orchestrator, "run", return_value=_mock_run_result()):
            resp = client.post("/execute", json={"input": "x"})
        assert isinstance(resp.json()["execution_time"], float)

    def test_orchestrator_error_returns_500(self):
        with patch.object(_orchestrator, "run", side_effect=RuntimeError("boom")):
            resp = client.post("/execute", json={"input": "x"})
        assert resp.status_code == 500

    def test_context_and_metadata_forwarded(self):
        captured = {}

        def fake_run(user_input, context=None, metadata=None):
            captured["context"] = context
            captured["metadata"] = metadata
            return _mock_run_result()

        with patch.object(_orchestrator, "run", side_effect=fake_run):
            client.post("/execute", json={
                "input": "x",
                "context": {"key": "val"},
                "metadata": {"session_id": "s1"},
            })
        assert captured["context"] == {"key": "val"}
        assert captured["metadata"] == {"session_id": "s1"}

    def test_real_pipeline_no_api_key(self):
        """Without ANTHROPIC_API_KEY the orchestrator degrades gracefully."""
        resp = client.post("/execute", json={"input": "create a marketing plan"})
        assert resp.status_code == 200
        assert resp.json()["status"] in ("success", "degraded")


# ---------------------------------------------------------------------------
# /execute/stream
# ---------------------------------------------------------------------------

class TestExecuteStream:
    def _stream_events(self, input_text: str, gen_override=None) -> list[dict]:
        if gen_override is not None:
            with patch.object(_orchestrator, "stream", return_value=iter(gen_override)):
                resp = client.post("/execute/stream", json={"input": input_text})
        else:
            resp = client.post("/execute/stream", json={"input": input_text})
        assert resp.status_code == 200
        events = []
        for line in resp.text.splitlines():
            line = line.strip()
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        return events

    def test_content_type_is_event_stream(self):
        stages = [{"event": "done", "data": {"approved": True, "quality_score": 0.9}}]
        with patch.object(_orchestrator, "stream", return_value=iter(stages)):
            resp = client.post("/execute/stream", json={"input": "x"})
        assert "text/event-stream" in resp.headers["content-type"]

    def test_events_are_valid_json(self):
        stages = [
            {"event": "intent", "data": {"agent": "deal-analysis-agent"}},
            {"event": "done", "data": {"approved": True, "quality_score": 0.8}},
        ]
        events = self._stream_events("x", gen_override=stages)
        assert len(events) == 2

    def test_event_sequence_includes_intent_and_done(self):
        stages = [
            {"event": "intent", "data": {"agent": "deal-analysis-agent"}},
            {"event": "security", "data": {"passed": True}},
            {"event": "quality", "data": {"approved": True, "quality_score": 0.85}},
            {"event": "done", "data": {"approved": True, "quality_score": 0.85}},
        ]
        events = self._stream_events("x", gen_override=stages)
        event_types = [e["event"] for e in events]
        assert "intent" in event_types
        assert "done" in event_types

    def test_skill_events_per_skill(self):
        stages = [
            {"event": "intent", "data": {}},
            {"event": "skill", "data": {"skill": "seo-engine", "status": "success"}},
            {"event": "skill", "data": {"skill": "ads-engine", "status": "success"}},
            {"event": "done", "data": {"approved": True, "quality_score": 0.8}},
        ]
        events = self._stream_events("x", gen_override=stages)
        skill_events = [e for e in events if e["event"] == "skill"]
        assert len(skill_events) == 2

    def test_stream_error_emits_error_event(self):
        def boom():
            yield {"event": "intent", "data": {}}
            raise RuntimeError("pipeline exploded")

        with patch.object(_orchestrator, "stream", return_value=boom()):
            resp = client.post("/execute/stream", json={"input": "x"})
        assert resp.status_code == 200
        lines = [l for l in resp.text.splitlines() if l.startswith("data: ")]
        last_event = json.loads(lines[-1][6:])
        assert last_event["event"] == "error"

    def test_real_stream_no_api_key(self):
        """End-to-end: stream completes and includes a done event."""
        resp = client.post("/execute/stream", json={"input": "analyze this deal"})
        assert resp.status_code == 200
        lines = [l.strip() for l in resp.text.splitlines() if l.strip().startswith("data: ")]
        assert len(lines) >= 1
        event_types = [json.loads(l[6:])["event"] for l in lines]
        assert "done" in event_types or "error" in event_types


# ---------------------------------------------------------------------------
# /debug
# ---------------------------------------------------------------------------

class TestDebug:
    def test_returns_200(self):
        with patch.object(_orchestrator, "debug", return_value={"stages": [], "approved": True}):
            resp = client.post("/debug", json={"input": "x"})
        assert resp.status_code == 200

    def test_response_has_request_id_and_trace(self):
        with patch.object(_orchestrator, "debug", return_value={"stages": []}):
            resp = client.post("/debug", json={"input": "x"})
        body = resp.json()
        assert "request_id" in body
        assert "trace" in body

    def test_debug_error_returns_500(self):
        with patch.object(_orchestrator, "debug", side_effect=RuntimeError("fail")):
            resp = client.post("/debug", json={"input": "x"})
        assert resp.status_code == 500

    def test_real_debug_pipeline(self):
        resp = client.post("/debug", json={"input": "analyze deal"})
        assert resp.status_code == 200
        assert "stages" in resp.json()["trace"]


# ---------------------------------------------------------------------------
# /skills/{name}/invoke
# ---------------------------------------------------------------------------

class TestSkillInvoke:
    def test_known_skill_returns_200(self):
        resp = client.post("/skills/seo-engine/invoke", json={"params": {"topic": "real estate"}})
        assert resp.status_code == 200

    def test_known_skill_returns_success_status(self):
        resp = client.post("/skills/seo-engine/invoke", json={"params": {"topic": "multifamily"}})
        assert resp.json()["status"] == "success"

    def test_unknown_skill_returns_404(self):
        resp = client.post("/skills/nonexistent-skill/invoke", json={"params": {}})
        assert resp.status_code == 404

    def test_ads_engine_invokable(self):
        resp = client.post("/skills/ads-engine/invoke", json={
            "params": {"product": "real estate", "platform": "meta", "task": "creative_generation"},
        })
        assert resp.status_code == 200
        assert "headline" in resp.json()["data"]

    def test_skill_params_forwarded(self):
        resp = client.post("/skills/sales-agent/invoke", json={
            "params": {"offer": "multifamily fund", "task": "cold_outreach"},
        })
        assert resp.status_code == 200

    def test_hyphenated_skill_name_works(self):
        resp = client.post("/skills/quality-control/invoke", json={
            "params": {"output": {"recommendation": "buy"}, "criteria": ["structured"]},
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /context/{session_id}
# ---------------------------------------------------------------------------

class TestContext:
    def test_returns_200(self):
        resp = client.get("/context/test-session-abc")
        assert resp.status_code == 200

    def test_response_has_session_id(self):
        resp = client.get("/context/my-session")
        assert resp.json()["session_id"] == "my-session"

    def test_response_is_dict(self):
        resp = client.get("/context/s")
        assert isinstance(resp.json(), dict)


# ---------------------------------------------------------------------------
# Orchestrator.stream() generator (unit tests independent of HTTP layer)
# ---------------------------------------------------------------------------

class TestOrchestratorStream:
    def test_stream_yields_intent_event(self):
        _orchestrator._client = None  # force keyword fallback
        events = list(_orchestrator.stream("analyze this deal"))
        types = [e["event"] for e in events]
        assert "intent" in types

    def test_stream_yields_done_event(self):
        _orchestrator._client = None
        events = list(_orchestrator.stream("investor report"))
        types = [e["event"] for e in events]
        assert "done" in types

    def test_stream_yields_security_and_quality(self):
        _orchestrator._client = None
        events = list(_orchestrator.stream("marketing campaign"))
        types = [e["event"] for e in events]
        assert "security" in types
        assert "quality" in types

    def test_stream_done_has_quality_score(self):
        _orchestrator._client = None
        events = list(_orchestrator.stream("x"))
        done = next(e for e in events if e["event"] == "done")
        assert "quality_score" in done["data"]
        assert "approved" in done["data"]

    def test_stream_request_id_in_done(self):
        _orchestrator._client = None
        events = list(_orchestrator.stream("x", request_id="req-123"))
        done = next(e for e in events if e["event"] == "done")
        assert done["data"]["request_id"] == "req-123"

    def test_stream_intent_first_done_last(self):
        _orchestrator._client = None
        events = list(_orchestrator.stream("analyze deal"))
        assert events[0]["event"] == "intent"
        assert events[-1]["event"] == "done"

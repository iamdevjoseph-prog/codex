"""
test_orchestrator — Tests for the Orchestrator class.

Claude API calls are always mocked so these tests run without an API key.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from sybil.orchestrator.main import Orchestrator


def _mock_client(intent_payload: dict) -> MagicMock:
    """Build a mock Anthropic client that returns the given intent JSON."""
    content = MagicMock()
    content.text = json.dumps(intent_payload)
    response = MagicMock()
    response.content = [content]
    client = MagicMock()
    client.messages.create.return_value = response
    return client


# ── Basic run contract ────────────────────────────────────────────────────────

def test_orchestrator_runs():
    """run() must return a dict with an 'intent' key regardless of API availability."""
    o = Orchestrator()
    o._client = None  # force keyword fallback — no API call
    result = o.run("Create a marketing plan")
    assert "intent" in result


def test_orchestrator_run_returns_results_list():
    o = Orchestrator()
    o._client = None
    result = o.run("seo campaign for listing")
    assert "results" in result
    assert isinstance(result["results"], list)


def test_orchestrator_run_returns_agent():
    o = Orchestrator()
    o._client = None
    result = o.run("analyze this deal")
    assert "agent" in result


def test_orchestrator_run_has_quality_score():
    o = Orchestrator()
    o._client = None
    result = o.run("investor report for fund")
    assert "quality_score" in result
    assert 0.0 <= result["quality_score"] <= 1.0


# ── Claude classification ─────────────────────────────────────────────────────

def test_orchestrator_uses_claude_when_client_set():
    o = Orchestrator()
    o._client = _mock_client({
        "intent": "marketing campaign",
        "agent": "marketing-agent",
        "skills": ["seo-engine", "ads-engine"],
    })
    result = o.run("Create a full marketing campaign for our listing")
    assert result["intent"]["agent"] == "marketing-agent"
    assert result["intent"]["classifier"] == "claude"


def test_orchestrator_executes_skills_from_claude_intent():
    o = Orchestrator()
    o._client = _mock_client({
        "intent": "SEO plan",
        "agent": "marketing-agent",
        "skills": ["seo-engine"],
    })
    result = o.run("Optimise our listing for search")
    skill_names = [r["skill"] for r in result["results"]]
    assert "seo-engine" in skill_names


def test_orchestrator_falls_back_on_bad_json():
    o = Orchestrator()
    bad_content = MagicMock()
    bad_content.text = "not json {{"
    bad_response = MagicMock()
    bad_response.content = [bad_content]
    client = MagicMock()
    client.messages.create.return_value = bad_response
    o._client = client

    result = o.run("Create a marketing plan")
    # Should still return a valid result via fallback
    assert "intent" in result


def test_orchestrator_sanitises_unknown_agent_from_claude():
    o = Orchestrator()
    o._client = _mock_client({
        "intent": "test",
        "agent": "made-up-agent",   # not in the whitelist
        "skills": [],
    })
    result = o.run("Do something")
    assert result["intent"]["agent"] == "deal-analysis-agent"  # default


# ── Skill execution ───────────────────────────────────────────────────────────

def test_execute_skill_returns_dict():
    o = Orchestrator()
    result = o._execute_skill("seo-engine", {"topic": "real estate", "keywords": ["investing"]})
    assert isinstance(result, dict)
    assert result["status"] == "success"


def test_execute_skill_missing_skill_returns_not_implemented():
    o = Orchestrator()
    result = o._execute_skill("nonexistent-skill", {"input": "test"})
    assert result["status"] == "not_implemented"
    assert "nonexistent-skill" in result["skill"]


# ── Keyword fallback ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("user_input,expected_agent", [
    ("analyze this real estate deal",        "deal-analysis-agent"),
    ("generate investor report",             "investor-report-agent"),
    ("create seo and ads for the listing",   "marketing-agent"),
])
def test_keyword_fallback_routing(user_input, expected_agent):
    o = Orchestrator()
    o._client = None
    intent = o._parse_intent(user_input)
    assert intent["agent"] == expected_agent
    assert intent["classifier"] == "keyword"


# ── debug() ───────────────────────────────────────────────────────────────────

def test_debug_returns_stages():
    o = Orchestrator()
    result = o.debug("analyze deal", metadata={"session_id": "test-dbg"})
    assert "stages" in result
    assert len(result["stages"]) >= 3


def test_debug_stage_shape():
    o = Orchestrator()
    result = o.debug("analyze deal", metadata={"session_id": "test-dbg-2"})
    for stage in result["stages"]:
        assert "stage" in stage
        assert "elapsed_ms" in stage
        assert "input" in stage
        assert "output" in stage

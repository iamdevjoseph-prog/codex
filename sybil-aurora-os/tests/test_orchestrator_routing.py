"""
test_orchestrator_routing — Verify intent classification routes to correct agents.

Tests cover both the keyword fallback and the Claude-classification path
(Claude path is tested with a mocked Anthropic client so no API key required).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ── Keyword classifier ────────────────────────────────────────────────────────

from sybil.orchestrator.orchestrator import _classify_with_keywords, _parse_intent


@pytest.mark.parametrize("intent,expected_agents", [
    ("analyze this real estate deal",                   ["deal-analysis-agent"]),
    ("underwrite the property at 123 Main",             ["deal-analysis-agent"]),
    ("generate investor report for the fund",           ["investor-report-agent"]),
    ("create a marketing campaign for this listing",    ["marketing-agent"]),
    ("seo optimize the property listing",               ["marketing-agent"]),
    ("run ads for our new multifamily offering",        ["marketing-agent"]),
    ("full pipeline: deal, report, and marketing",      ["deal-analysis-agent", "investor-report-agent", "marketing-agent"]),
    ("something completely unrelated",                  ["deal-analysis-agent"]),  # default
])
def test_keyword_routing(intent, expected_agents):
    result = _classify_with_keywords(intent)
    assert result["agents"] == expected_agents, f"Intent '{intent}' → {result['agents']}, expected {expected_agents}"
    assert result["classifier"] == "keyword"


@pytest.mark.parametrize("intent,expected_type", [
    ("analyze deal",       "deal_analysis"),
    ("investor report",    "investor_report"),
    ("seo campaign",       "marketing"),
])
def test_keyword_classifier_intent_type(intent, expected_type):
    result = _classify_with_keywords(intent)
    assert result["intent_type"] == expected_type


def test_keyword_classifier_always_returns_agents():
    result = _classify_with_keywords("")
    assert len(result["agents"]) >= 1


def test_keyword_classifier_confidence_is_float():
    result = _classify_with_keywords("analyze deal")
    assert isinstance(result["confidence"], float)
    assert 0.0 <= result["confidence"] <= 1.0


# ── Claude classifier (mocked) ────────────────────────────────────────────────

def _make_mock_response(payload: dict) -> MagicMock:
    content_block = MagicMock()
    content_block.text = json.dumps(payload)
    response = MagicMock()
    response.content = [content_block]
    return response


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"})
@patch("sybil.orchestrator.orchestrator.anthropic", create=True)
def test_claude_classifier_routes_deal_intent(mock_anthropic_module):
    client = MagicMock()
    mock_anthropic_module.Anthropic.return_value = client
    client.messages.create.return_value = _make_mock_response({
        "intent_type": "deal_analysis",
        "agents": ["deal-analysis-agent"],
        "skills": ["entrepreneur", "visualization"],
        "confidence": 0.97,
    })

    from sybil.orchestrator.orchestrator import _classify_with_claude
    result = _classify_with_claude("analyze and underwrite this commercial property")

    assert result["agents"] == ["deal-analysis-agent"]
    assert "entrepreneur" in result["skills"]
    assert result["classifier"] == "claude"
    assert result["confidence"] == 0.97


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"})
@patch("sybil.orchestrator.orchestrator.anthropic", create=True)
def test_claude_classifier_sanitises_unknown_agents(mock_anthropic_module):
    client = MagicMock()
    mock_anthropic_module.Anthropic.return_value = client
    client.messages.create.return_value = _make_mock_response({
        "intent_type": "general",
        "agents": ["fake-agent", "deal-analysis-agent"],
        "skills": ["unknown-skill", "entrepreneur"],
        "confidence": 0.8,
    })

    from sybil.orchestrator.orchestrator import _classify_with_claude
    result = _classify_with_claude("do something")

    assert "fake-agent" not in result["agents"]
    assert "deal-analysis-agent" in result["agents"]
    assert "unknown-skill" not in result["skills"]
    assert "entrepreneur" in result["skills"]


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"})
@patch("sybil.orchestrator.orchestrator.anthropic", create=True)
def test_claude_classifier_fallback_on_json_error(mock_anthropic_module):
    """If Claude returns malformed JSON, _parse_intent falls back to keywords."""
    client = MagicMock()
    mock_anthropic_module.Anthropic.return_value = client
    content_block = MagicMock()
    content_block.text = "not valid json {{"
    client.messages.create.return_value.content = [content_block]

    result = _parse_intent("analyze this deal", "sess-1")
    assert result["classifier"] == "keyword"
    assert len(result["agents"]) >= 1


@patch.dict("os.environ", {}, clear=True)
def test_parse_intent_uses_keywords_without_api_key():
    result = _parse_intent("analyze deal", "sess-1")
    assert result["classifier"] == "keyword"


# ── Full orchestrator run (agents mocked) ─────────────────────────────────────

@patch("sybil.orchestrator.orchestrator._invoke_agent")
@patch.dict("os.environ", {}, clear=True)
def test_orchestrator_run_invokes_correct_agent(mock_invoke):
    from sybil.orchestrator.orchestrator import run

    mock_invoke.return_value = {"status": "ok", "agent": "deal-analysis-agent"}

    result = run({"intent": "analyze this property deal", "payload": {}, "session_id": "test"})

    invoked = [call.args[0] for call in mock_invoke.call_args_list]
    assert "deal-analysis-agent" in invoked


@patch("sybil.orchestrator.orchestrator._invoke_agent")
@patch.dict("os.environ", {}, clear=True)
def test_orchestrator_run_returns_required_keys(mock_invoke):
    from sybil.orchestrator.orchestrator import run

    mock_invoke.return_value = {"status": "ok", "recommendation": "Proceed", "action": "Deploy"}

    result = run({"intent": "analyze deal", "payload": {}})

    assert "orchestrator" in result
    assert "agents_invoked" in result
    assert "quality_score" in result
    assert "approved" in result
    assert "elapsed_ms" in result


@patch("sybil.orchestrator.orchestrator._invoke_agent")
@patch.dict("os.environ", {}, clear=True)
def test_orchestrator_run_marketing_intent(mock_invoke):
    from sybil.orchestrator.orchestrator import run

    mock_invoke.return_value = {"status": "ok", "seo": {}, "ads": {}, "action": "Launch campaign"}

    result = run({"intent": "create seo and ads campaign for listing", "payload": {}})

    invoked = [call.args[0] for call in mock_invoke.call_args_list]
    assert "marketing-agent" in invoked

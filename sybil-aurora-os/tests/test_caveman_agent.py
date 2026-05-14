"""
Tests for caveman-agent — the base agentic execution loop.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.skills.caveman_agent.main import run, invoke, _keyword_decide, _summarise


# ---------------------------------------------------------------------------
# Contract shape
# ---------------------------------------------------------------------------

class TestContract:
    def test_returns_dict(self):
        result = run({"task": "analyze a deal"})
        assert isinstance(result, dict)

    def test_top_level_keys(self):
        result = run({"task": "test"})
        for key in ("status", "data", "meta"):
            assert key in result

    def test_status_success(self):
        assert run({"task": "anything"})["status"] == "success"

    def test_data_keys(self):
        data = run({"task": "test"})["data"]
        for key in ("task", "tool_calls", "iterations", "quality_score", "approved"):
            assert key in data

    def test_meta_keys(self):
        meta = run({"task": "test"})["meta"]
        assert meta["skill"] == "caveman-agent"
        assert "task" in meta
        assert "tools_available" in meta

    def test_invoke_alias(self):
        assert invoke is run

    def test_empty_task(self):
        result = run({})
        assert result["status"] == "success"

    def test_quality_score_is_float(self):
        result = run({"task": "analyze"})
        assert isinstance(result["data"]["quality_score"], float)

    def test_approved_is_bool(self):
        result = run({"task": "analyze"})
        assert isinstance(result["data"]["approved"], bool)


# ---------------------------------------------------------------------------
# Iteration control
# ---------------------------------------------------------------------------

class TestIterations:
    def test_respects_max_iterations(self):
        result = run({"task": "run forever", "max_iterations": 2})
        assert result["data"]["iterations"] <= 2

    def test_max_iterations_capped_at_10(self):
        result = run({"task": "x", "max_iterations": 100})
        assert result["meta"]["max_iterations"] == 10

    def test_single_iteration(self):
        result = run({"task": "quick task", "max_iterations": 1})
        assert result["data"]["iterations"] == 1

    def test_zero_tools_still_runs(self):
        result = run({"task": "x", "tools": [], "max_iterations": 1})
        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# Tool selection
# ---------------------------------------------------------------------------

class TestToolSelection:
    def test_tool_calls_in_output(self):
        result = run({"task": "analyze a real estate deal", "max_iterations": 2})
        assert isinstance(result["data"]["tool_calls"], list)

    def test_tool_calls_have_required_keys(self):
        result = run({"task": "analyze", "max_iterations": 1})
        for call in result["data"]["tool_calls"]:
            assert "tool" in call
            assert "iteration" in call
            assert "status" in call

    def test_custom_tools_available(self):
        result = run({"task": "test", "tools": ["custom-tool"], "max_iterations": 1})
        assert "custom-tool" in result["meta"]["tools_available"]

    def test_done_signal_stops_loop(self):
        def fake_decide(task, available, history, step):
            return {"tool": "__done__", "input": {}, "reasoning": "done"}
        with patch("core.skills.caveman_agent.main._decide", side_effect=fake_decide):
            result = run({"task": "x", "max_iterations": 5})
        # Loop stopped on first iteration (done signal at step 0)
        assert result["data"]["iterations"] == 1
        assert result["data"]["tool_calls"] == []

    def test_error_stops_loop(self):
        calls = []
        def fake_decide(task, available, history, step):
            return {"tool": "entrepreneur", "input": {}, "reasoning": ""}
        def fake_skill_run(name, params):
            calls.append(name)
            if name == "entrepreneur":
                return {"status": "error", "message": "boom"}
            return {"status": "success", "quality_score": 0.8, "approved": True}
        with patch("core.skills.caveman_agent.main._decide", side_effect=fake_decide):
            with patch("core.skills.caveman_agent.main._skill_run", side_effect=fake_skill_run):
                result = run({"task": "x", "max_iterations": 5})
        # Only one entrepreneur call — loop stops on error
        assert calls.count("entrepreneur") == 1


# ---------------------------------------------------------------------------
# _keyword_decide fallback
# ---------------------------------------------------------------------------

class TestKeywordDecide:
    def test_deal_task_picks_entrepreneur(self):
        decision = _keyword_decide("analyze this real estate deal", ["entrepreneur", "seo-engine"], [], 0)
        assert decision["tool"] == "entrepreneur"

    def test_seo_task_picks_seo_engine(self):
        decision = _keyword_decide("optimize seo for listing", ["seo-engine", "ads-engine"], [], 0)
        assert decision["tool"] == "seo-engine"

    def test_ads_task_picks_ads_engine(self):
        decision = _keyword_decide("create an ad campaign", ["ads-engine", "seo-engine"], [], 0)
        assert decision["tool"] == "ads-engine"

    def test_all_used_returns_done(self):
        history = [{"tool": "entrepreneur"}, {"tool": "seo-engine"}]
        decision = _keyword_decide("x", ["entrepreneur", "seo-engine"], history, 0)
        assert decision["tool"] == "__done__"

    def test_does_not_repeat_used_tools(self):
        history = [{"tool": "entrepreneur"}]
        decision = _keyword_decide("analyze deal", ["entrepreneur", "seo-engine"], history, 1)
        assert decision["tool"] != "entrepreneur"

    def test_sequential_fallback_for_unknown_task(self):
        decision = _keyword_decide("do something unknown", ["entrepreneur", "visualization"], [], 0)
        assert decision["tool"] in ("entrepreneur", "visualization")


# ---------------------------------------------------------------------------
# _summarise helper
# ---------------------------------------------------------------------------

class TestSummarise:
    def test_dict_with_status(self):
        s = _summarise({"status": "success", "data": {"a": 1}})
        assert "status=success" in s

    def test_dict_shows_keys(self):
        s = _summarise({"status": "ok", "data": {"x": 1, "y": 2}})
        assert "keys=" in s

    def test_non_dict_truncated(self):
        long_str = "x" * 200
        s = _summarise(long_str)
        assert len(s) <= 120

    def test_empty_dict(self):
        s = _summarise({})
        assert isinstance(s, str)


# ---------------------------------------------------------------------------
# Real tool execution (no mock)
# ---------------------------------------------------------------------------

class TestRealExecution:
    def test_deal_analysis_task_runs(self):
        result = run({
            "task": "analyze this real estate deal",
            "tools": ["entrepreneur"],
            "max_iterations": 2,
        })
        assert result["status"] == "success"
        assert result["data"]["iterations"] >= 1

    def test_seo_task_runs(self):
        result = run({
            "task": "optimize seo for a multifamily listing",
            "tools": ["seo-engine"],
            "max_iterations": 2,
        })
        assert result["status"] == "success"

    def test_context_injected_into_tool(self):
        captured = {}
        original_skill_run = __import__("core.skill_loader", fromlist=["run"]).run

        def tracking_run(name, params):
            if name not in ("quality-control", "anthropic-core"):
                captured["params"] = params
            return original_skill_run(name, params)

        with patch("core.skills.caveman_agent.main._skill_run", side_effect=tracking_run):
            run({
                "task": "test",
                "context": {"deal_id": "abc123"},
                "max_iterations": 1,
            })
        if captured:
            assert "deal_id" in captured.get("params", {})

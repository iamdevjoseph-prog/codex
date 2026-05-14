"""
Tests for callstack-agents — multi-agent orchestration skill.

Coverage:
  - Contract shape (status/results/execution_trace/elapsed_ms/skill)
  - sequential, parallel, dag execution modes
  - DAG topological ordering and dependency enforcement
  - DAG parallel wave execution (independent nodes run concurrently)
  - Agent resolution: sybil.agents.* → skill_loader → not_implemented stub
  - Skills used as DAG nodes (seo-engine, ads-engine)
  - Error isolation: one failing node doesn't abort the whole run
  - prior_results threading in sequential mode
  - Empty agent list
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.skills.callstack_agents.main import invoke, run, _invoke_agent, _run_dag, _run_sequential, _run_parallel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spec(name: str, input: dict | None = None, depends_on: list[str] | None = None) -> dict:
    s: dict = {"name": name}
    if input:
        s["input"] = input
    if depends_on:
        s["depends_on"] = depends_on
    return s


# ---------------------------------------------------------------------------
# Contract shape
# ---------------------------------------------------------------------------

class TestContract:
    def test_returns_dict(self):
        result = invoke({"agents": [], "execution_mode": "sequential"})
        assert isinstance(result, dict)

    def test_top_level_keys(self):
        result = invoke({"agents": []})
        for key in ("status", "results", "execution_trace", "elapsed_ms", "skill"):
            assert key in result, f"missing key: {key}"

    def test_status_success(self):
        result = invoke({"agents": []})
        assert result["status"] == "success"

    def test_skill_marker(self):
        result = invoke({"agents": []})
        assert result["skill"] == "callstack-agents"

    def test_elapsed_ms_is_non_negative_int(self):
        result = invoke({"agents": []})
        assert isinstance(result["elapsed_ms"], int)
        assert result["elapsed_ms"] >= 0

    def test_run_alias(self):
        assert run is invoke

    def test_empty_agents_returns_empty_results(self):
        result = invoke({"agents": []})
        assert result["results"] == {}
        assert result["execution_trace"] == []


# ---------------------------------------------------------------------------
# Real agent resolution — deal-analysis-agent
# ---------------------------------------------------------------------------

class TestRealAgentResolution:
    def test_deal_analysis_agent_resolves(self):
        result = invoke({"agents": [_spec("deal-analysis-agent", {"deal": {}})], "execution_mode": "sequential"})
        assert result["status"] == "success"
        agent_result = result["results"]["deal-analysis-agent"]
        assert isinstance(agent_result, dict)
        assert agent_result.get("agent") == "deal-analysis-agent"

    def test_marketing_agent_resolves(self):
        result = invoke({
            "agents": [_spec("marketing-agent", {"listing": {}, "budget": 0})],
            "execution_mode": "sequential",
        })
        assert result["results"]["marketing-agent"]["agent"] == "marketing-agent"

    def test_investor_report_agent_resolves(self):
        result = invoke({
            "agents": [_spec("investor-report-agent", {"portfolio": [], "fund_name": "F", "period": "Q1"})],
            "execution_mode": "sequential",
        })
        assert result["results"]["investor-report-agent"]["agent"] == "investor-report-agent"

    def test_unknown_agent_returns_not_implemented(self):
        result = invoke({"agents": [_spec("nonexistent-agent")], "execution_mode": "sequential"})
        assert result["status"] == "success"  # outer run never fails
        stub = result["results"]["nonexistent-agent"]
        assert stub["status"] == "not_implemented"

    def test_unknown_agent_doesnt_abort_run(self):
        agents = [_spec("nonexistent-agent"), _spec("deal-analysis-agent", {"deal": {}})]
        result = invoke({"agents": agents, "execution_mode": "sequential"})
        assert result["status"] == "success"
        assert "deal-analysis-agent" in result["results"]


# ---------------------------------------------------------------------------
# Skill-as-node resolution
# ---------------------------------------------------------------------------

class TestSkillAsNode:
    def test_seo_engine_as_node(self):
        result = invoke({
            "agents": [_spec("seo-engine", {"topic": "multifamily", "keywords": ["cap rate"]})],
            "execution_mode": "sequential",
        })
        assert result["status"] == "success"
        node_result = result["results"]["seo-engine"]
        assert node_result.get("status") == "success"

    def test_ads_engine_as_node(self):
        result = invoke({
            "agents": [_spec("ads-engine", {"product": "real estate fund", "platform": "meta"})],
            "execution_mode": "sequential",
        })
        node_result = result["results"]["ads-engine"]
        assert node_result.get("status") == "success"

    def test_skill_node_output_in_execution_trace(self):
        result = invoke({
            "agents": [_spec("seo-engine", {"topic": "real estate"})],
            "execution_mode": "sequential",
        })
        trace = result["execution_trace"]
        assert any(t["agent"] == "seo-engine" for t in trace)


# ---------------------------------------------------------------------------
# Sequential mode
# ---------------------------------------------------------------------------

class TestSequentialMode:
    def test_sequential_runs_in_order(self):
        order = []
        original_invoke = _invoke_agent

        def tracked_invoke(spec, prior):
            order.append(spec["name"])
            return {"status": "ok"}

        agents = [_spec("a"), _spec("b"), _spec("c")]
        with patch("core.skills.callstack_agents.main._invoke_agent", side_effect=tracked_invoke):
            _run_sequential(agents)

        assert order == ["a", "b", "c"]

    def test_sequential_passes_prior_results(self):
        captured = {}

        def tracking_invoke(spec, prior):
            captured[spec["name"]] = dict(prior)
            return {"status": "ok", "value": spec["name"]}

        agents = [_spec("first"), _spec("second")]
        with patch("core.skills.callstack_agents.main._invoke_agent", side_effect=tracking_invoke):
            _run_sequential(agents)

        # second agent should see first agent's output in prior_results
        assert "first" in captured["second"]

    def test_sequential_trace_has_elapsed_ms(self):
        result = invoke({"agents": [_spec("deal-analysis-agent", {"deal": {}})], "execution_mode": "sequential"})
        trace = result["execution_trace"]
        assert len(trace) == 1
        assert "elapsed_ms" in trace[0]
        assert trace[0]["elapsed_ms"] >= 0


# ---------------------------------------------------------------------------
# Parallel mode
# ---------------------------------------------------------------------------

class TestParallelMode:
    def test_parallel_runs_all_agents(self):
        result = invoke({
            "agents": [
                _spec("deal-analysis-agent", {"deal": {}}),
                _spec("marketing-agent", {"listing": {}, "budget": 0}),
            ],
            "execution_mode": "parallel",
        })
        assert "deal-analysis-agent" in result["results"]
        assert "marketing-agent" in result["results"]

    def test_parallel_failure_isolated(self):
        """A failing agent shouldn't prevent others from completing."""
        def mock_invoke(spec, prior):
            if spec["name"] == "bad-agent":
                raise RuntimeError("injected failure")
            return {"status": "ok"}

        agents = [_spec("bad-agent"), _spec("good-agent")]
        with patch("core.skills.callstack_agents.main._invoke_agent", side_effect=mock_invoke):
            results, trace = _run_parallel(agents)

        assert results["bad-agent"]["status"] == "error"
        assert results["good-agent"]["status"] == "ok"

    def test_parallel_always_populates_results(self):
        """results[name] must be set even when the agent throws."""
        def mock_invoke(spec, prior):
            raise ValueError("boom")

        agents = [_spec("failing-agent")]
        with patch("core.skills.callstack_agents.main._invoke_agent", side_effect=mock_invoke):
            results, _ = _run_parallel(agents)

        assert "failing-agent" in results
        assert results["failing-agent"]["status"] == "error"

    def test_parallel_outer_status_still_success_on_inner_failure(self):
        def mock_invoke(spec, prior):
            raise RuntimeError("oops")

        with patch("core.skills.callstack_agents.main._invoke_agent", side_effect=mock_invoke):
            result = invoke({"agents": [_spec("x")], "execution_mode": "parallel"})

        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# DAG mode
# ---------------------------------------------------------------------------

class TestDagMode:
    def test_dag_respects_depends_on(self):
        order = []

        def mock_invoke(spec, prior):
            order.append(spec["name"])
            return {"status": "ok"}

        agents = [
            _spec("root"),
            _spec("child", depends_on=["root"]),
            _spec("leaf", depends_on=["child"]),
        ]
        with patch("core.skills.callstack_agents.main._invoke_agent", side_effect=mock_invoke):
            _run_dag(agents)

        assert order.index("root") < order.index("child") < order.index("leaf")

    def test_dag_independent_nodes_all_complete(self):
        agents = [
            _spec("deal-analysis-agent", {"deal": {}}),
            _spec("marketing-agent", {"listing": {}, "budget": 0}),
        ]
        result = invoke({"agents": agents, "execution_mode": "dag"})
        assert "deal-analysis-agent" in result["results"]
        assert "marketing-agent" in result["results"]

    def test_dag_passes_dependency_output_to_dependents(self):
        received = {}

        def mock_invoke(spec, prior):
            received[spec["name"]] = dict(prior)
            return {"status": "ok", "out": spec["name"]}

        agents = [
            _spec("producer"),
            _spec("consumer", depends_on=["producer"]),
        ]
        with patch("core.skills.callstack_agents.main._invoke_agent", side_effect=mock_invoke):
            _run_dag(agents)

        assert "producer" in received["consumer"]

    def test_dag_wave_parallelism(self):
        """Two independent nodes should run concurrently, not sequentially."""
        start_times = {}
        barrier = threading.Barrier(2, timeout=3)

        def mock_invoke(spec, prior):
            start_times[spec["name"]] = time.monotonic()
            if spec["name"] in ("a", "b"):
                barrier.wait()  # both must reach here simultaneously
            return {"status": "ok"}

        agents = [_spec("a"), _spec("b"), _spec("c", depends_on=["a", "b"])]
        with patch("core.skills.callstack_agents.main._invoke_agent", side_effect=mock_invoke):
            results, _ = _run_dag(agents)

        # barrier.wait() would TimeoutError if they ran sequentially
        assert "a" in results
        assert "b" in results
        assert "c" in results

    def test_dag_default_mode(self):
        result = invoke({"agents": [_spec("deal-analysis-agent", {"deal": {}})]})
        assert result["status"] == "success"
        assert "deal-analysis-agent" in result["results"]

    def test_dag_broken_cycle_terminates(self):
        """Circular dependency should not loop forever."""
        agents = [
            _spec("x", depends_on=["y"]),
            _spec("y", depends_on=["x"]),
        ]
        result = invoke({"agents": agents, "execution_mode": "dag"})
        assert result["status"] == "success"
        assert result["results"] == {}  # nothing could execute


# ---------------------------------------------------------------------------
# _invoke_agent resolution logic
# ---------------------------------------------------------------------------

class TestInvokeAgentResolution:
    def test_resolves_real_agent(self):
        result = _invoke_agent({"name": "deal-analysis-agent", "input": {"deal": {}}}, {})
        assert result.get("agent") == "deal-analysis-agent"

    def test_falls_back_to_skill_loader(self):
        result = _invoke_agent({"name": "seo-engine", "input": {"topic": "real estate"}}, {})
        assert result.get("status") == "success"

    def test_returns_not_implemented_for_unknown(self):
        result = _invoke_agent({"name": "totally-unknown-xyz"}, {})
        assert result["status"] == "not_implemented"

    def test_agent_error_returns_error_status(self):
        mock_module = MagicMock()
        mock_module.run.side_effect = RuntimeError("agent blew up")
        with patch("importlib.import_module", return_value=mock_module):
            result = _invoke_agent({"name": "boom-agent"}, {})
        assert result["status"] == "error"
        assert "agent blew up" in result["error"]

    def test_prior_results_injected_into_input(self):
        captured = {}

        def fake_run(inp):
            captured.update(inp)
            return {"status": "ok"}

        mock_module = MagicMock()
        mock_module.run.side_effect = fake_run
        with patch("importlib.import_module", return_value=mock_module):
            _invoke_agent({"name": "any-agent", "input": {"x": 1}}, {"prev": "output"})

        assert captured.get("prior_results") == {"prev": "output"}
        assert captured.get("x") == 1

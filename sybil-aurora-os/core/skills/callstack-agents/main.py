"""
callstack-agents — Multi-agent orchestration: spawn, coordinate, and collect results.
"""

from __future__ import annotations

import importlib
import time
from collections import defaultdict
from typing import Any

SKILL_NAME = "callstack-agents"


def invoke(params: dict[str, Any]) -> dict[str, Any]:
    agents = params["agents"]
    execution_mode = params.get("execution_mode", "dag")
    task = params["task"]

    start = time.monotonic()
    trace: list[dict] = []
    results: dict[str, Any] = {}

    if execution_mode == "sequential":
        results, trace = _run_sequential(agents, results)
    elif execution_mode == "parallel":
        results, trace = _run_parallel(agents, results)
    else:
        results, trace = _run_dag(agents, results)

    return {
        "results": results,
        "execution_trace": trace,
        "elapsed_ms": int((time.monotonic() - start) * 1000),
        "skill": SKILL_NAME,
    }


def _run_sequential(agents: list[dict], results: dict) -> tuple[dict, list]:
    trace = []
    for agent_spec in agents:
        name = agent_spec["name"]
        t0 = time.monotonic()
        result = _invoke_agent(agent_spec, results)
        elapsed = int((time.monotonic() - t0) * 1000)
        results[name] = result
        trace.append({"agent": name, "elapsed_ms": elapsed, "status": "ok"})
    return results, trace


def _run_parallel(agents: list[dict], results: dict) -> tuple[dict, list]:
    import concurrent.futures
    trace = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(_invoke_agent, spec, {}): spec["name"] for spec in agents}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
                trace.append({"agent": name, "status": "ok"})
            except Exception as e:
                trace.append({"agent": name, "status": "error", "error": str(e)})
    return results, trace


def _run_dag(agents: list[dict], results: dict) -> tuple[dict, list]:
    # Topological execution respecting depends_on
    deps = {a["name"]: set(a.get("depends_on", [])) for a in agents}
    spec_map = {a["name"]: a for a in agents}
    trace = []
    completed: set[str] = set()

    while len(completed) < len(agents):
        ready = [name for name, d in deps.items() if name not in completed and d.issubset(completed)]
        if not ready:
            break
        for name in ready:
            t0 = time.monotonic()
            result = _invoke_agent(spec_map[name], results)
            elapsed = int((time.monotonic() - t0) * 1000)
            results[name] = result
            completed.add(name)
            trace.append({"agent": name, "elapsed_ms": elapsed, "status": "ok"})

    return results, trace


def _invoke_agent(agent_spec: dict, prior_results: dict) -> Any:
    name = agent_spec["name"]
    agent_input = {**agent_spec.get("input", {}), "prior_results": prior_results}

    # Dynamic agent resolution: look for agent module in sybil/agents/
    try:
        module = importlib.import_module(f"sybil.agents.{name.replace('-', '_')}")
        return module.run(agent_input)
    except ModuleNotFoundError:
        return {"status": "not_implemented", "agent": name, "input": agent_input}

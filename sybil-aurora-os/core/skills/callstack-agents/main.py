"""
callstack-agents — Multi-agent orchestration: spawn, coordinate, and collect results.

Execution modes:
  dag        — topological sort; each wave of independent nodes runs concurrently
  sequential — one agent at a time, each receives prior outputs as context
  parallel   — all agents fire simultaneously, no dependency ordering

Agent resolution order per node:
  1. sybil.agents.<name>  — real agents (deal-analysis-agent, etc.)
  2. skill_loader.run()   — any skill as a DAG node (seo-engine, ads-engine, etc.)
  3. not_implemented stub — graceful fallback so the outer run still returns success
"""

from __future__ import annotations

import concurrent.futures
import importlib
import sys
import time
from pathlib import Path
from typing import Any

# Guarantee sybil.agents.* is importable regardless of cwd
_ROOT = Path(__file__).parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Lazy import of skill_loader to avoid circular dependency at module level
def _skill_run(name: str, payload: dict) -> dict:
    from core.skill_loader import run as _sr
    return _sr(name, payload)


SKILL_NAME = "callstack-agents"


def invoke(params: dict[str, Any]) -> dict[str, Any]:
    agents = params.get("agents", [])
    execution_mode = params.get("execution_mode", "dag")

    start = time.monotonic()

    if execution_mode == "sequential":
        results, trace = _run_sequential(agents)
    elif execution_mode == "parallel":
        results, trace = _run_parallel(agents)
    else:
        results, trace = _run_dag(agents)

    return {
        "status": "success",
        "results": results,
        "execution_trace": trace,
        "elapsed_ms": int((time.monotonic() - start) * 1000),
        "skill": SKILL_NAME,
    }


run = invoke


def _run_sequential(agents: list[dict]) -> tuple[dict, list]:
    trace = []
    results: dict[str, Any] = {}
    for agent_spec in agents:
        name = agent_spec["name"]
        t0 = time.monotonic()
        result = _invoke_agent(agent_spec, results)
        elapsed = int((time.monotonic() - t0) * 1000)
        results[name] = result
        status = result.get("status", "ok") if isinstance(result, dict) else "ok"
        trace.append({"agent": name, "elapsed_ms": elapsed, "status": status})
    return results, trace


def _run_parallel(agents: list[dict]) -> tuple[dict, list]:
    trace = []
    results: dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(_invoke_agent, spec, {}): spec["name"] for spec in agents}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                results[name] = result
                status = result.get("status", "ok") if isinstance(result, dict) else "ok"
                trace.append({"agent": name, "status": status})
            except Exception as exc:
                results[name] = {"status": "error", "agent": name, "error": str(exc)}
                trace.append({"agent": name, "status": "error", "error": str(exc)})
    return results, trace


def _run_dag(agents: list[dict]) -> tuple[dict, list]:
    """
    Topological execution. Within each wave (set of nodes whose deps are all
    satisfied), nodes run concurrently via a thread pool.
    """
    deps = {a["name"]: set(a.get("depends_on", [])) for a in agents}
    spec_map = {a["name"]: a for a in agents}
    trace = []
    results: dict[str, Any] = {}
    completed: set[str] = set()

    while len(completed) < len(agents):
        ready = [name for name, d in deps.items() if name not in completed and d.issubset(completed)]
        if not ready:
            break  # circular dependency or all remaining blocked

        # Snapshot of prior results for this wave (all nodes in the wave share same view)
        prior_snapshot = dict(results)

        if len(ready) == 1:
            name = ready[0]
            t0 = time.monotonic()
            result = _invoke_agent(spec_map[name], prior_snapshot)
            elapsed = int((time.monotonic() - t0) * 1000)
            results[name] = result
            completed.add(name)
            status = result.get("status", "ok") if isinstance(result, dict) else "ok"
            trace.append({"agent": name, "elapsed_ms": elapsed, "status": status})
        else:
            # Run the whole wave in parallel
            with concurrent.futures.ThreadPoolExecutor() as executor:
                wave_futures = {
                    executor.submit(_invoke_agent, spec_map[n], prior_snapshot): n
                    for n in ready
                }
                for future in concurrent.futures.as_completed(wave_futures):
                    name = wave_futures[future]
                    t_done = 0
                    try:
                        result = future.result()
                        results[name] = result
                        status = result.get("status", "ok") if isinstance(result, dict) else "ok"
                        trace.append({"agent": name, "status": status})
                    except Exception as exc:
                        results[name] = {"status": "error", "agent": name, "error": str(exc)}
                        trace.append({"agent": name, "status": "error", "error": str(exc)})
                    completed.add(name)

    return results, trace


def _invoke_agent(agent_spec: dict, prior_results: dict) -> Any:
    """
    Resolve and call a node by name.

    Resolution order:
      1. sybil.agents.<name>  — real multi-skill agents
      2. skill_loader         — individual skills used as DAG nodes
      3. not_implemented stub — unknown name, don't crash the outer run
    """
    name = agent_spec["name"]
    agent_input = {**agent_spec.get("input", {}), "prior_results": prior_results}

    # 1. Try real agent
    try:
        module = importlib.import_module(f"sybil.agents.{name.replace('-', '_')}")
        return module.run(agent_input)
    except ImportError:
        pass
    except Exception as exc:
        return {"status": "error", "agent": name, "error": str(exc)}

    # 2. Try skill_loader (e.g. "seo-engine", "ads-engine" used as nodes)
    try:
        return _skill_run(name, agent_input)
    except (ImportError, AttributeError):
        pass
    except Exception as exc:
        return {"status": "error", "agent": name, "error": str(exc)}

    # 3. Graceful stub
    return {"status": "not_implemented", "agent": name}

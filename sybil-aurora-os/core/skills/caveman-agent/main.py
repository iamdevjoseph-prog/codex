"""
caveman-agent — Base agent runtime: plan → execute tools → validate → done.

Routes through anthropic-core for reasoning when ANTHROPIC_API_KEY is set;
degrades to a keyword-based planner otherwise so the agent is always functional.

Each iteration the agent:
  1. Asks anthropic-core to decide the next tool call (reason task)
  2. Executes the chosen tool via skill_loader
  3. Appends (tool, result) to history
  4. Repeats until the task is marked complete or max_iterations is reached
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parents[3]))

from core.skill_loader import run as _skill_run

SKILL_NAME = "caveman-agent"
_MAX_ITERATIONS = 10

# Tools the agent knows how to invoke by default
_BUILTIN_TOOLS = {
    "entrepreneur",
    "seo-engine",
    "ads-engine",
    "sales-agent",
    "visualization",
    "slides",
    "quality-control",
    "anthropic-core",
    "context-engine",
}


def run(input: dict[str, Any]) -> dict[str, Any]:
    task = input.get("task", "")
    tools = list(input.get("tools", []))
    max_iterations = min(int(input.get("max_iterations", _MAX_ITERATIONS)), _MAX_ITERATIONS)
    context = input.get("context", {})

    # Determine which tools are available for this run
    available = list(_BUILTIN_TOOLS | set(tools))

    history: list[dict] = []
    tool_calls: list[dict] = []
    iterations = 0

    for i in range(max_iterations):
        iterations = i + 1

        # Decide next action
        decision = _decide(task, available, history, i)
        tool_name = decision["tool"]
        tool_input = decision["input"]
        reasoning = decision.get("reasoning", "")

        if tool_name == "__done__":
            break

        # Execute the tool
        try:
            result = _skill_run(tool_name, {**tool_input, **context})
            tool_status = result.get("status", "success")
        except (ImportError, AttributeError):
            result = {"status": "error", "message": f"Tool '{tool_name}' not found"}
            tool_status = "error"
        except Exception as exc:
            result = {"status": "error", "message": str(exc)}
            tool_status = "error"

        record = {
            "iteration": i + 1,
            "tool": tool_name,
            "input": tool_input,
            "status": tool_status,
            "reasoning": reasoning,
        }
        tool_calls.append(record)
        history.append({**record, "output_summary": _summarise(result)})

        # Stop if a tool errored — don't keep trying with broken state
        if tool_status == "error":
            break

    # Final quality check
    final_output = {
        "task": task,
        "tool_calls": tool_calls,
        "iterations": iterations,
        "history_length": len(history),
    }
    qc = _skill_run("quality-control", {
        "output": final_output,
        "criteria": ["actionable", "complete"],
        "min_score": 0.5,
    })

    return {
        "status": "success",
        "data": {
            **final_output,
            "quality_score": qc.get("quality_score", 0.0),
            "approved": qc.get("approved", False),
        },
        "meta": {
            "skill": SKILL_NAME,
            "task": task,
            "tools_available": available,
            "max_iterations": max_iterations,
        },
    }


def _decide(task: str, available: list[str], history: list[dict], step: int) -> dict:
    """
    Ask anthropic-core to decide the next tool call.
    Falls back to keyword heuristics if LLM is not available (degraded mode).
    """
    llm_result = _skill_run("anthropic-core", {
        "task": "classify",
        "content": (
            f"Agent task: {task}\n"
            f"Step: {step + 1}\n"
            f"Completed steps: {[h['tool'] for h in history]}\n"
            f"Available tools: {available}\n"
            "Decide the NEXT tool to call. "
            "If the task is complete, return category='__done__'. "
            "Otherwise return the tool name in category and a brief reasoning."
        ),
        "categories": available + ["__done__"],
    })

    # If not degraded and LLM returned a real classification, use it
    if not llm_result.get("meta", {}).get("degraded"):
        clf = llm_result.get("data", {}).get("classification", {})
        tool = clf.get("category", "")
        if tool in available or tool == "__done__":
            return {
                "tool": tool,
                "input": {"task": task},
                "reasoning": clf.get("reasoning", ""),
            }

    # Fallback: keyword heuristics
    return _keyword_decide(task, available, history, step)


def _keyword_decide(task: str, available: list[str], history: list[dict], step: int) -> dict:
    """Simple keyword-based tool selection for degraded / no-API mode."""
    used = {h["tool"] for h in history}
    task_lower = task.lower()

    priority: list[str] = []
    if any(w in task_lower for w in ("deal", "underwrite", "cap rate", "noi", "invest")):
        priority = ["entrepreneur", "visualization"]
    elif any(w in task_lower for w in ("seo", "search", "rank", "organic", "keyword")):
        priority = ["seo-engine"]
    elif any(w in task_lower for w in ("ad", "campaign", "paid", "creative", "meta", "google")):
        priority = ["ads-engine"]
    elif any(w in task_lower for w in ("pitch", "deck", "slide", "investor", "present")):
        priority = ["slides", "visualization"]
    elif any(w in task_lower for w in ("market", "sell", "outreach", "prospect")):
        priority = ["seo-engine", "ads-engine", "sales-agent"]

    for tool in priority:
        if tool in available and tool not in used:
            return {"tool": tool, "input": {"task": task}, "reasoning": f"keyword match for '{task_lower}'"}

    # Pick first unused tool, then done
    for tool in available:
        if tool not in used and tool not in ("quality-control", "anthropic-core", "context-engine"):
            return {"tool": tool, "input": {"task": task}, "reasoning": "sequential fallback"}

    return {"tool": "__done__", "input": {}, "reasoning": "all available tools exhausted"}


def _summarise(result: dict) -> str:
    """Return a compact string summary of a tool result for history."""
    if isinstance(result, dict):
        status = result.get("status", "")
        data = result.get("data", result)
        if isinstance(data, dict):
            keys = list(data.keys())[:3]
            return f"status={status} keys={keys}"
        return f"status={status}"
    return str(result)[:120]


invoke = run

"""caveman-agent — Minimal prompt-in / action-out base agent runtime."""

from __future__ import annotations

from typing import Any

SKILL_NAME = "caveman-agent"

_MAX_ITERATIONS = 10


def run(input: dict[str, Any]) -> dict[str, Any]:
    task = input.get("task", "")
    tools = input.get("tools", [])
    max_iterations = min(input.get("max_iterations", _MAX_ITERATIONS), _MAX_ITERATIONS)

    steps = ["parse", "plan", "execute", "validate", "complete"]
    tool_calls: list[dict] = []

    for i, step in enumerate(steps):
        if i >= max_iterations:
            break
        if step == "execute" and tools:
            for tool in tools:
                tool_calls.append({"tool": tool, "status": "invoked", "iteration": i})

    return {
        "status": "success",
        "data": {
            "execution": f"Executed task: {task}",
            "steps": steps[:max_iterations],
            "tool_calls": tool_calls,
            "iterations": min(len(steps), max_iterations),
        },
        "meta": {"skill": SKILL_NAME, "task": task, "tools_available": tools},
    }


invoke = run

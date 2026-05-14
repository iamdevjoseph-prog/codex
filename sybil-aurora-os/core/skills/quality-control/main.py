"""
quality-control — Stop Slop. Enforces output quality, actionability, and production standards.
"""

from __future__ import annotations

import json
from typing import Any

SKILL_NAME = "quality-control"

_SLOP_SIGNALS = [
    "certainly!", "of course!", "absolutely!", "great question",
    "as an ai", "i cannot", "i'm just an ai", "i don't have feelings",
    "i hope this helps", "let me know if you need anything else",
    "in conclusion,", "to summarize,", "in summary,",
]

_CRITERIA_CHECKS = {
    "actionable": _check_actionable,
    "structured": _check_structured,
    "concise": _check_concise,
    "accurate": _check_accurate,
    "complete": _check_complete,
    "production_ready": _check_production_ready,
}


def invoke(params: dict[str, Any]) -> dict[str, Any]:
    output = params["output"]
    criteria = params["criteria"]
    min_score = params.get("min_score", 0.85)

    issues: list[str] = []
    recommendations: list[str] = []
    scores: list[float] = []

    # Always check for slop signals
    slop_issues = _check_slop(output)
    issues += slop_issues
    if slop_issues:
        recommendations.append("Remove filler language and hedging phrases.")

    for criterion in criteria:
        checker = _CRITERIA_CHECKS.get(criterion)
        if checker:
            criterion_issues, criterion_score = checker(output)
            issues += criterion_issues
            scores.append(criterion_score)
            if criterion_issues:
                recommendations.append(f"Improve '{criterion}': {criterion_issues[0]}")

    quality_score = (sum(scores) / len(scores)) if scores else (1.0 if not issues else 0.5)
    quality_score = round(max(0.0, quality_score - len(slop_issues) * 0.1), 2)
    approved = quality_score >= min_score and not slop_issues

    return {
        "approved": approved,
        "quality_score": quality_score,
        "issues": issues,
        "recommendations": recommendations,
        "output": output,
        "skill": SKILL_NAME,
    }


def _check_slop(output: dict) -> list[str]:
    text = json.dumps(output).lower()
    return [f"Slop signal detected: '{s}'" for s in _SLOP_SIGNALS if s in text]


def _check_actionable(output: dict) -> tuple[list[str], float]:
    text = json.dumps(output)
    action_verbs = ["implement", "deploy", "configure", "run", "execute", "create", "update", "delete", "use", "set"]
    if any(v in text.lower() for v in action_verbs):
        return [], 1.0
    return ["Output lacks actionable directives."], 0.4


def _check_structured(output: dict) -> tuple[list[str], float]:
    if isinstance(output, dict) and len(output) > 1:
        return [], 1.0
    return ["Output is not sufficiently structured."], 0.5


def _check_concise(output: dict) -> tuple[list[str], float]:
    text = json.dumps(output)
    if len(text) > 50_000:
        return ["Output is excessively verbose."], 0.6
    return [], 1.0


def _check_accurate(output: dict) -> tuple[list[str], float]:
    # Placeholder — integrate with trailofbits-security for deep accuracy checks
    return [], 1.0


def _check_complete(output: dict) -> tuple[list[str], float]:
    if not output:
        return ["Output is empty."], 0.0
    return [], 1.0


def _check_production_ready(output: dict) -> tuple[list[str], float]:
    text = json.dumps(output)
    non_prod_signals = ["todo", "fixme", "placeholder", "hardcoded", "example.com", "localhost"]
    found = [s for s in non_prod_signals if s in text.lower()]
    if found:
        return [f"Non-production signals found: {found}"], 0.5
    return [], 1.0

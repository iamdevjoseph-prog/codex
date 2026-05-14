"""
Sybil Orchestrator — Parses user intent, routes to agents, chains skills,
applies security and quality gates, returns final output.

Pipeline:
  User Intent → Agent Selection → Skill Invocation → Security → Quality → Output
"""

from __future__ import annotations

import importlib
import json
import time
from typing import Any

from core.skills.trailofbits_security.main import invoke as security_check
from core.skills.quality_control.main import invoke as quality_gate
from core.skills.context_engine.main import invoke as context_engine
from core.skills.anthropic_core.main import invoke as reasoning

ORCHESTRATOR_VERSION = "2.0.0"

_INTENT_AGENT_MAP = {
    "deal": ["deal-analysis-agent"],
    "underwrite": ["deal-analysis-agent"],
    "analyze": ["deal-analysis-agent"],
    "report": ["investor-report-agent"],
    "investor": ["investor-report-agent"],
    "fund": ["investor-report-agent"],
    "market": ["marketing-agent"],
    "listing": ["marketing-agent"],
    "seo": ["marketing-agent"],
    "ads": ["marketing-agent"],
    "full": ["deal-analysis-agent", "investor-report-agent", "marketing-agent"],
}


def run(user_input: dict[str, Any]) -> dict[str, Any]:
    """
    Entry point. user_input must contain:
      - intent: str (natural language or keyword)
      - payload: dict (domain data)
      - session_id: str (optional, for context persistence)
    """
    session_id = user_input.get("session_id", "default")
    intent_raw = user_input.get("intent", "")
    payload = user_input.get("payload", {})
    start = time.monotonic()

    # Step 1: Parse intent via reasoning
    intent_analysis = _parse_intent(intent_raw, session_id)
    agents = intent_analysis["agents"]

    # Step 2: Store context
    context_engine({"operation": "store", "key": "last_intent", "value": intent_analysis, "session_id": session_id})

    # Step 3: Execute agents
    agent_results = {}
    for agent_name in agents:
        agent_results[agent_name] = _invoke_agent(agent_name, payload)

    # Step 4: Aggregate
    aggregated = _aggregate(agent_results, intent_analysis)

    # Step 5: Security gate
    sec = security_check({
        "payload": aggregated,
        "checks": ["hallucination", "pii", "data_integrity"],
        "strict": False,
    })

    if not sec["passed"]:
        aggregated = sec["sanitized_payload"]
        aggregated["_security_warnings"] = sec["violations"]

    # Step 6: Quality gate
    qc = quality_gate({
        "output": aggregated,
        "criteria": ["actionable", "structured", "complete", "production_ready"],
        "min_score": 0.75,
    })

    # Step 7: Store result in context
    context_engine({"operation": "store", "key": "last_output", "value": qc["output"], "session_id": session_id})

    return {
        "orchestrator": ORCHESTRATOR_VERSION,
        "session_id": session_id,
        "intent": intent_raw,
        "agents_invoked": agents,
        "output": qc["output"],
        "quality_score": qc["quality_score"],
        "approved": qc["approved"],
        "elapsed_ms": int((time.monotonic() - start) * 1000),
    }


def _parse_intent(intent_raw: str, session_id: str) -> dict:
    intent_lower = intent_raw.lower()

    matched_agents: list[str] = []
    for keyword, agents in _INTENT_AGENT_MAP.items():
        if keyword in intent_lower:
            for a in agents:
                if a not in matched_agents:
                    matched_agents.append(a)

    if not matched_agents:
        matched_agents = ["deal-analysis-agent"]

    return {"raw": intent_raw, "agents": matched_agents}


def _invoke_agent(agent_name: str, payload: dict) -> dict:
    module_name = agent_name.replace("-", "_")
    try:
        module = importlib.import_module(f"sybil.agents.{module_name}")
        return module.run(payload)
    except ModuleNotFoundError:
        return {"agent": agent_name, "status": "not_implemented"}
    except Exception as e:
        return {"agent": agent_name, "status": "error", "error": str(e)}


def _aggregate(results: dict[str, dict], intent: dict) -> dict:
    return {
        "intent": intent["raw"],
        "agents": intent["agents"],
        "results": results,
        "summary": {name: r.get("status", "unknown") for name, r in results.items()},
    }

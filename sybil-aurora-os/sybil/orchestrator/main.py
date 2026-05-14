"""
Orchestrator class — wraps the functional pipeline with a stateful interface,
debug tracing, and per-stage timing for the FastAPI layer.
"""

from __future__ import annotations

import importlib
import time
from typing import Any

import sybil.orchestrator.orchestrator as _pipeline
from core.skills.trailofbits_security.main import invoke as security_check
from core.skills.quality_control.main import invoke as quality_gate
from core.skills.context_engine.main import invoke as context_engine

ORCHESTRATOR_VERSION = "2.0.0"


class Orchestrator:
    """
    Stateful orchestration interface for the FastAPI layer.

    run()   → production path, returns final approved output
    debug() → same pipeline but returns every stage's I/O and timing
    """

    def run(
        self,
        user_input: str,
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session_id = (metadata or {}).get("session_id", "default")
        return _pipeline.run({
            "intent": user_input,
            "payload": context or {},
            "session_id": session_id,
        })

    def debug(
        self,
        user_input: str,
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session_id = (metadata or {}).get("session_id", "default")
        payload = context or {}
        stages: list[dict] = []

        # Stage 1: Intent parsing
        t0 = time.monotonic()
        intent_analysis = _pipeline._parse_intent(user_input, session_id)
        stages.append(_stage("intent_parsing", t0, {"raw": user_input}, intent_analysis))

        # Stage 2: Context store
        t0 = time.monotonic()
        ctx_result = context_engine({
            "operation": "store",
            "key": "debug_intent",
            "value": intent_analysis,
            "session_id": session_id,
        })
        stages.append(_stage("context_store", t0, intent_analysis, ctx_result))

        # Stage 3: Agent execution (one trace entry per agent)
        agent_results: dict[str, Any] = {}
        for agent_name in intent_analysis["agents"]:
            t0 = time.monotonic()
            result = _pipeline._invoke_agent(agent_name, payload)
            agent_results[agent_name] = result
            stages.append(_stage(f"agent:{agent_name}", t0, {"payload_keys": list(payload.keys())}, result))

        # Stage 4: Aggregation
        t0 = time.monotonic()
        aggregated = _pipeline._aggregate(agent_results, intent_analysis)
        stages.append(_stage("aggregation", t0, {"agent_count": len(agent_results)}, aggregated))

        # Stage 5: Security gate
        t0 = time.monotonic()
        sec = security_check({
            "payload": aggregated,
            "checks": ["hallucination", "pii", "data_integrity"],
            "strict": False,
        })
        stages.append(_stage("security_gate", t0, aggregated, sec))

        if not sec["passed"]:
            aggregated = sec["sanitized_payload"]
            aggregated["_security_warnings"] = sec["violations"]

        # Stage 6: Quality gate
        t0 = time.monotonic()
        qc = quality_gate({
            "output": aggregated,
            "criteria": ["actionable", "structured", "complete", "production_ready"],
            "min_score": 0.75,
        })
        stages.append(_stage("quality_gate", t0, aggregated, qc))

        return {
            "orchestrator": ORCHESTRATOR_VERSION,
            "session_id": session_id,
            "intent": user_input,
            "agents_invoked": intent_analysis["agents"],
            "approved": qc["approved"],
            "quality_score": qc["quality_score"],
            "stages": stages,
            "final_output": qc["output"],
        }


def _stage(name: str, t0: float, input_summary: Any, output: Any) -> dict:
    return {
        "stage": name,
        "elapsed_ms": int((time.monotonic() - t0) * 1000),
        "input": input_summary,
        "output": output,
    }

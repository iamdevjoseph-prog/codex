"""
Orchestrator — intelligent intent classification via Claude, direct skill
execution, security + quality gates, and full debug tracing.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from anthropic import Anthropic

import sybil.orchestrator.orchestrator as _pipeline
from core.skill_loader import run as _skill_run, register_all_as_python_packages

register_all_as_python_packages()

ORCHESTRATOR_VERSION = "2.0.0"

_CLASSIFY_PROMPT = """\
Classify the user intent and select the agent and skills needed to fulfill it.

Available agents: deal-analysis-agent, investor-report-agent, marketing-agent
Available skills: entrepreneur, visualization, slides, seo-engine, ads-engine,
  sales-agent, anthropic-core, context-engine, callstack-agents, caveman-agent,
  ui-ux, video, image, ios-testing, quality-control, trailofbits-security

Return ONLY valid JSON — no explanation, no markdown:
{{
  "intent": "short description of what the user wants",
  "agent": "the single best agent name",
  "skills": ["skill1", "skill2"]
}}

User input:
{user_input}"""


class Orchestrator:
    """
    Stateful orchestration interface for the FastAPI layer.

    run()   → production path: classify → execute skills → security → quality → output
    debug() → same pipeline with per-stage I/O and timing
    """

    def __init__(self) -> None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        self._client = Anthropic(api_key=api_key) if api_key else None

    # ── Public interface ──────────────────────────────────────────────────────

    def run(
        self,
        user_input: str,
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        intent = self._parse_intent(user_input)

        results = []
        for skill in intent.get("skills", []):
            result = self._execute_skill(skill, {"input": user_input, **(context or {})})
            results.append({"skill": skill, "output": result})

        output = {
            "intent": intent,
            "results": results,
            "agent": intent.get("agent"),
            "message": "Intelligent routing active",
        }

        # Security gate
        sec = _skill_run("trailofbits-security", {
            "payload": output,
            "checks": ["hallucination", "pii", "data_integrity"],
            "strict": False,
        })
        if not sec["passed"]:
            output["_security_warnings"] = sec["violations"]
            output = sec["sanitized_payload"]

        # Quality gate
        qc = _skill_run("quality-control", {
            "output": output,
            "criteria": ["structured", "complete"],
            "min_score": 0.6,
        })

        return {
            "intent": intent,
            "results": results,
            "agent": intent.get("agent"),
            "quality_score": qc["quality_score"],
            "approved": qc["approved"],
            "message": "Intelligent routing active",
        }

    def debug(
        self,
        user_input: str,
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session_id = (metadata or {}).get("session_id", "default")
        payload = context or {}
        stages: list[dict] = []

        t0 = time.monotonic()
        intent_analysis = _pipeline._parse_intent(user_input, session_id)
        stages.append(_stage("intent_parsing", t0, {"raw": user_input}, intent_analysis))

        t0 = time.monotonic()
        ctx_result = _skill_run("context-engine", {
            "operation": "store", "key": "debug_intent",
            "value": intent_analysis, "session_id": session_id,
        })
        stages.append(_stage("context_store", t0, intent_analysis, ctx_result))

        agent_results: dict[str, Any] = {}
        for agent_name in intent_analysis["agents"]:
            t0 = time.monotonic()
            result = _pipeline._invoke_agent(agent_name, payload)
            agent_results[agent_name] = result
            stages.append(_stage(f"agent:{agent_name}", t0, {"payload_keys": list(payload.keys())}, result))

        t0 = time.monotonic()
        aggregated = _pipeline._aggregate(agent_results, intent_analysis)
        stages.append(_stage("aggregation", t0, {"agent_count": len(agent_results)}, aggregated))

        t0 = time.monotonic()
        sec = _skill_run("trailofbits-security", {
            "payload": aggregated,
            "checks": ["hallucination", "pii", "data_integrity"],
            "strict": False,
        })
        stages.append(_stage("security_gate", t0, aggregated, sec))

        if not sec["passed"]:
            aggregated = sec["sanitized_payload"]
            aggregated["_security_warnings"] = sec["violations"]

        t0 = time.monotonic()
        qc = _skill_run("quality-control", {
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

    # ── Internal methods ──────────────────────────────────────────────────────

    def _parse_intent(self, user_input: str) -> dict[str, Any]:
        """
        Classify intent with Claude when available; fall back to the keyword
        classifier in orchestrator.py when ANTHROPIC_API_KEY is not set or
        the API call fails.
        """
        if self._client is not None:
            try:
                return self._classify_with_claude(user_input)
            except Exception:
                pass

        # Keyword fallback
        kw = _pipeline._classify_with_keywords(user_input)
        return {
            "intent": kw["raw"],
            "agent": kw["agents"][0] if kw["agents"] else "deal-analysis-agent",
            "skills": kw.get("skills", []),
            "classifier": "keyword",
        }

    def _classify_with_claude(self, user_input: str) -> dict[str, Any]:
        response = self._client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": _CLASSIFY_PROMPT.format(user_input=user_input),
            }],
        )

        text = response.content[0].text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            text = "\n".join(text.splitlines()[1:])
        if text.endswith("```"):
            text = text[: text.rfind("```")]

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"intent": "unknown", "agent": "deal-analysis-agent", "skills": [], "raw": text}

        # Whitelist agents and skills
        valid_agents = {"deal-analysis-agent", "investor-report-agent", "marketing-agent"}
        agent = parsed.get("agent", "deal-analysis-agent")
        if agent not in valid_agents:
            agent = "deal-analysis-agent"

        return {
            "intent": parsed.get("intent", user_input),
            "agent": agent,
            "skills": parsed.get("skills", []),
            "classifier": "claude",
        }

    def _execute_skill(self, skill_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a skill by name. Uses skill_loader to handle hyphenated
        directory names (e.g. 'seo-engine' → core/skills/seo-engine/main.py).
        Falls back gracefully if the skill doesn't exist.
        """
        try:
            return _skill_run(skill_name, payload)
        except (ImportError, AttributeError) as e:
            return {"status": "not_implemented", "skill": skill_name, "error": str(e)}


def _stage(name: str, t0: float, input_summary: Any, output: Any) -> dict:
    return {
        "stage": name,
        "elapsed_ms": int((time.monotonic() - t0) * 1000),
        "input": input_summary,
        "output": output,
    }

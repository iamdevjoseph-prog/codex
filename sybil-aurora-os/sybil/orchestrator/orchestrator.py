"""
Sybil Orchestrator — Parses user intent, routes to agents, chains skills,
applies security and quality gates, returns final output.

Pipeline:
  User Intent → Agent Selection → Skill Invocation → Security → Quality → Output
"""

from __future__ import annotations

import importlib
import json
import os
import time
from typing import Any

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

from core.skill_loader import run as _skill_run

def security_check(params):  return _skill_run("trailofbits-security", params)
def quality_gate(params):     return _skill_run("quality-control", params)
def context_engine(params):   return _skill_run("context-engine", params)

ORCHESTRATOR_VERSION = "2.0.0"

_ALL_AGENTS = ["deal-analysis-agent", "investor-report-agent", "marketing-agent"]

_ALL_SKILLS = [
    "entrepreneur", "visualization", "slides",
    "seo-engine", "ads-engine", "sales-agent",
    "anthropic-core", "trailofbits-security", "quality-control",
    "context-engine", "callstack-agents", "caveman-agent",
    "ui-ux", "video", "image", "ios-testing",
]

# Keyword fallback used when ANTHROPIC_API_KEY is absent or Claude call fails
_KEYWORD_AGENT_MAP: dict[str, list[str]] = {
    "deal": ["deal-analysis-agent"],
    "underwrite": ["deal-analysis-agent"],
    "analyze": ["deal-analysis-agent"],
    "report": ["investor-report-agent"],
    "investor": ["investor-report-agent"],
    "fund": ["investor-report-agent"],
    "portfolio": ["investor-report-agent"],
    "market": ["marketing-agent"],
    "listing": ["marketing-agent"],
    "seo": ["marketing-agent"],
    "ads": ["marketing-agent"],
    "campaign": ["marketing-agent"],
    "full": _ALL_AGENTS,
}

_KEYWORD_SKILL_MAP: dict[str, list[str]] = {
    "deal": ["entrepreneur", "visualization"],
    "underwrite": ["entrepreneur", "visualization"],
    "report": ["slides", "visualization"],
    "investor": ["slides", "visualization"],
    "market": ["seo-engine", "ads-engine"],
    "seo": ["seo-engine"],
    "ads": ["ads-engine"],
    "sell": ["sales-agent"],
    "full": ["entrepreneur", "visualization", "slides", "seo-engine", "ads-engine"],
}

_CLASSIFY_PROMPT = """\
You are an AI orchestration router. Given a user intent, select the most appropriate agents and skills.

Available agents: {agents}
Available skills: {skills}

User intent: "{intent}"

Rules:
- Select only agents relevant to the intent; typically 1-2 agents
- Select only skills those agents will need; typically 2-4 skills
- If the intent is unclear, default to deal-analysis-agent + entrepreneur + visualization
- Respond ONLY with valid JSON, no explanation

Required JSON format:
{{
  "intent_type": "deal_analysis | investor_report | marketing | general",
  "agents": ["agent-name"],
  "skills": ["skill-name"],
  "confidence": 0.0
}}"""


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
    """
    Classify intent using Claude when ANTHROPIC_API_KEY is available,
    falling back to keyword matching if the key is absent or the call fails.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _classify_with_claude(intent_raw)
        except Exception:
            pass  # fall through to keyword matching

    return _classify_with_keywords(intent_raw)


def _classify_with_claude(intent_raw: str) -> dict:
    if anthropic is None:
        raise ImportError("anthropic package not installed")

    client = anthropic.Anthropic()
    prompt = _CLASSIFY_PROMPT.format(
        agents=", ".join(_ALL_AGENTS),
        skills=", ".join(_ALL_SKILLS),
        intent=intent_raw,
    )
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:])
    if raw.endswith("```"):
        raw = raw[: raw.rfind("```")]

    parsed = json.loads(raw)

    # Sanitise: only allow known agents and skills
    agents = [a for a in parsed.get("agents", []) if a in _ALL_AGENTS] or ["deal-analysis-agent"]
    skills = [s for s in parsed.get("skills", []) if s in _ALL_SKILLS]

    return {
        "raw": intent_raw,
        "intent_type": parsed.get("intent_type", "general"),
        "agents": agents,
        "skills": skills,
        "confidence": float(parsed.get("confidence", 0.9)),
        "classifier": "claude",
    }


def _classify_with_keywords(intent_raw: str) -> dict:
    intent_lower = intent_raw.lower()

    agents: list[str] = []
    skills: list[str] = []

    for keyword, kw_agents in _KEYWORD_AGENT_MAP.items():
        if keyword in intent_lower:
            for a in kw_agents:
                if a not in agents:
                    agents.append(a)

    for keyword, kw_skills in _KEYWORD_SKILL_MAP.items():
        if keyword in intent_lower:
            for s in kw_skills:
                if s not in skills:
                    skills.append(s)

    if not agents:
        agents = ["deal-analysis-agent"]

    return {
        "raw": intent_raw,
        "intent_type": _infer_intent_type(agents),
        "agents": agents,
        "skills": skills,
        "confidence": 0.7,
        "classifier": "keyword",
    }


def _infer_intent_type(agents: list[str]) -> str:
    if agents == ["deal-analysis-agent"]:
        return "deal_analysis"
    if agents == ["investor-report-agent"]:
        return "investor_report"
    if agents == ["marketing-agent"]:
        return "marketing"
    return "general"


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

"""
Sybil–Aurora OS — FastAPI entry point.

Request → FastAPI → Orchestrator → Agents → Skills → QC → Response
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel

from sybil.orchestrator.main import Orchestrator

app = FastAPI(
    title="Sybil-Aurora OS API",
    description="AI-native operating system for orchestration, agents, and skills.",
    version="2.0.0",
)

_orchestrator = Orchestrator()


# ── Models ────────────────────────────────────────────────────────────────────

class TaskRequest(BaseModel):
    input: str
    context: dict[str, Any] = {}
    metadata: dict[str, Any] = {}


class TaskResponse(BaseModel):
    request_id: str
    status: str
    result: dict[str, Any]
    execution_time: float


class SkillRequest(BaseModel):
    params: dict[str, Any]


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "system": "sybil-aurora-os", "version": "2.0.0"}


# ── Core execution ────────────────────────────────────────────────────────────

@app.post("/execute", response_model=TaskResponse)
def execute_task(request: TaskRequest) -> TaskResponse:
    """
    Full production pipeline:
    intent → agent selection → skill chain → security gate → quality gate → output
    """
    request_id = str(uuid.uuid4())
    t0 = time.time()

    try:
        result = _orchestrator.run(
            user_input=request.input,
            context=request.context,
            metadata=request.metadata,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return TaskResponse(
        request_id=request_id,
        status="success" if result.get("approved") else "degraded",
        result=result,
        execution_time=round(time.time() - t0, 3),
    )


# ── Debug ─────────────────────────────────────────────────────────────────────

@app.post("/debug")
def debug_task(request: TaskRequest) -> dict:
    """
    Same pipeline as /execute but returns the full stage-by-stage trace:
    input, output, and elapsed_ms for every step.
    """
    try:
        trace = _orchestrator.debug(
            user_input=request.input,
            context=request.context,
            metadata=request.metadata,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"request_id": str(uuid.uuid4()), "trace": trace}


# ── Direct skill invocation ───────────────────────────────────────────────────

_SKILL_REGISTRY: dict[str, Any] = {}


def _load_skill(name: str):
    """Lazy-loads a skill's invoke function by name."""
    if name in _SKILL_REGISTRY:
        return _SKILL_REGISTRY[name]

    module_name = name.replace("-", "_")
    try:
        module = __import__(f"core.skills.{module_name}.main", fromlist=["invoke"])
        fn = module.invoke
        _SKILL_REGISTRY[name] = fn
        return fn
    except (ModuleNotFoundError, AttributeError):
        return None


@app.post("/skills/{skill_name}/invoke")
def invoke_skill(
    skill_name: str = Path(description="Skill name, e.g. entrepreneur"),
    request: SkillRequest = ...,
) -> dict:
    """
    Invoke any registered skill directly. Useful for testing individual skills
    or composing custom pipelines outside the orchestrator.
    """
    invoke = _load_skill(skill_name)
    if invoke is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    try:
        result = invoke(request.params)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return result


# ── Context ───────────────────────────────────────────────────────────────────

@app.get("/context/{session_id}")
def get_context(session_id: str = Path(description="Session ID")) -> dict:
    """Returns a summary of all stored context for a session."""
    from core.skills.context_engine.main import invoke as context_engine

    result = context_engine({"operation": "summarize", "session_id": session_id})
    return {"session_id": session_id, **result}

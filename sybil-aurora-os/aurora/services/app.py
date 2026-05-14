"""
Sybil–Aurora OS — FastAPI entry point.

Request → FastAPI → Orchestrator → Agents → Skills → QC → Response

Auth:
  All endpoints except /health require X-API-Key header when SYBIL_API_KEY
  env var is set. If SYBIL_API_KEY is unset the server runs open (dev mode).

Streaming:
  POST /execute/stream returns text/event-stream SSE. Each pipeline stage
  emits a "data: <json>\n\n" event so clients get incremental updates.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Generator

from fastapi import Depends, FastAPI, HTTPException, Path as FPath, Security, status
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parents[2]))

from core.skill_loader import run as _skill_run, register_all_as_python_packages
from sybil.orchestrator.main import Orchestrator

register_all_as_python_packages()

app = FastAPI(
    title="Sybil-Aurora OS API",
    description="AI-native operating system for orchestration, agents, and skills.",
    version="2.0.0",
)

_orchestrator = Orchestrator()

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _require_api_key(api_key: str | None = Security(_API_KEY_HEADER)) -> None:
    expected = os.getenv("SYBIL_API_KEY")
    if expected and api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Health (no auth — used by load balancers / uptime monitors)
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "system": "sybil-aurora-os", "version": "2.0.0"}


# ---------------------------------------------------------------------------
# Core execution
# ---------------------------------------------------------------------------

@app.post("/execute", response_model=TaskResponse)
def execute_task(
    request: TaskRequest,
    _: None = Depends(_require_api_key),
) -> TaskResponse:
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return TaskResponse(
        request_id=request_id,
        status="success" if result.get("approved") else "degraded",
        result=result,
        execution_time=round(time.time() - t0, 3),
    )


# ---------------------------------------------------------------------------
# Streaming execution
# ---------------------------------------------------------------------------

@app.post("/execute/stream")
def execute_stream(
    request: TaskRequest,
    _: None = Depends(_require_api_key),
) -> StreamingResponse:
    """
    Same pipeline as /execute but delivered as Server-Sent Events.

    Each SSE event is a JSON object with an "event" discriminator:
      intent    — classification result
      skill     — one skill completed (per skill in the plan)
      security  — security gate result
      quality   — quality gate result
      done      — final aggregated output (mirrors /execute response body)
      error     — pipeline error (stream ends after this)

    Clients should handle each event type independently and treat "done" as
    the terminal event.
    """
    request_id = str(uuid.uuid4())

    def generate() -> Generator[str, None, None]:
        try:
            for stage in _orchestrator.stream(
                user_input=request.input,
                context=request.context,
                metadata=request.metadata,
                request_id=request_id,
            ):
                yield f"data: {json.dumps(stage)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'event': 'error', 'data': {'message': str(exc)}})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------

@app.post("/debug")
def debug_task(
    request: TaskRequest,
    _: None = Depends(_require_api_key),
) -> dict:
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"request_id": str(uuid.uuid4()), "trace": trace}


# ---------------------------------------------------------------------------
# Direct skill invocation
# ---------------------------------------------------------------------------

@app.post("/skills/{skill_name}/invoke")
def invoke_skill(
    skill_name: str = FPath(description="Skill name, e.g. seo-engine"),
    request: SkillRequest = ...,
    _: None = Depends(_require_api_key),
) -> dict:
    """
    Invoke any registered skill directly. Useful for testing individual skills
    or composing custom pipelines outside the orchestrator.
    """
    try:
        result = _skill_run(skill_name, request.params)
    except ImportError:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return result


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

@app.get("/context/{session_id}")
def get_context(
    session_id: str = FPath(description="Session ID"),
    _: None = Depends(_require_api_key),
) -> dict:
    """Returns a summary of all stored context for a session."""
    result = _skill_run("context-engine", {"operation": "summarize", "session_id": session_id})
    return {"session_id": session_id, **result}

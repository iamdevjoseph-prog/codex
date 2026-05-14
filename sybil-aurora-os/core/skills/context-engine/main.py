"""
context-engine — Structured memory, retrieval, and context persistence across tasks.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

SKILL_NAME = "context-engine"

_STORE_DIR = Path(os.environ.get("CONTEXT_STORE_DIR", "/tmp/sybil-context"))


def invoke(params: dict[str, Any]) -> dict[str, Any]:
    operation = params["operation"]
    session_id = params.get("session_id", "default")

    dispatch = {
        "store": _store,
        "retrieve": _retrieve,
        "search": _search,
        "summarize": _summarize,
        "clear": _clear,
    }

    handler = dispatch.get(operation)
    if not handler:
        return {"success": False, "error": f"Unknown operation: {operation}", "skill": SKILL_NAME}

    result = handler(params, session_id)
    result["status"] = "success"
    result["skill"] = SKILL_NAME
    return result


run = invoke


def _session_path(session_id: str) -> Path:
    path = _STORE_DIR / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _store(params: dict, session_id: str) -> dict:
    key = params["key"]
    value = params["value"]
    record = {"key": key, "value": value, "stored_at": int(time.time())}
    (_session_path(session_id) / f"{key}.json").write_text(json.dumps(record))
    return {"success": True, "data": record}


def _retrieve(params: dict, session_id: str) -> dict:
    key = params["key"]
    path = _session_path(session_id) / f"{key}.json"
    if not path.exists():
        return {"success": False, "data": None, "error": f"Key '{key}' not found"}
    return {"success": True, "data": json.loads(path.read_text())}


def _search(params: dict, session_id: str) -> dict:
    query = params.get("query", "").lower()
    top_k = params.get("top_k", 5)
    session_dir = _session_path(session_id)
    matches = []
    for f in session_dir.glob("*.json"):
        record = json.loads(f.read_text())
        content = json.dumps(record).lower()
        if query in content:
            matches.append(record)
    return {"success": True, "matches": matches[:top_k]}


def _summarize(params: dict, session_id: str) -> dict:
    session_dir = _session_path(session_id)
    all_records = [json.loads(f.read_text()) for f in session_dir.glob("*.json")]
    return {"success": True, "data": {"total_records": len(all_records), "keys": [r["key"] for r in all_records]}}


def _clear(params: dict, session_id: str) -> dict:
    session_dir = _session_path(session_id)
    count = 0
    for f in session_dir.glob("*.json"):
        f.unlink()
        count += 1
    return {"success": True, "data": {"cleared": count}}

"""
context-engine — Structured memory, retrieval, and context persistence.

Backend selection (automatic):
  Redis    — when REDIS_URL is set and the redis package is importable.
             Records are stored as session-scoped Redis hashes with a
             configurable TTL (default 86400s / 24 h).
  Filesystem — fallback when Redis is unavailable.
             Records are written as JSON files under CONTEXT_STORE_DIR
             (default /tmp/sybil-context).

All operations accept the same input dict and return the same output shape
regardless of which backend is active. Callers never need to know.
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

SKILL_NAME = "context-engine"

_DEFAULT_TTL = int(os.environ.get("CONTEXT_TTL", 86400))
_REDIS_KEY_PREFIX = "sybil"

# ---------------------------------------------------------------------------
# Backend interface
# ---------------------------------------------------------------------------

class _Backend(ABC):
    @abstractmethod
    def store(self, session_id: str, key: str, value: Any) -> dict:
        ...

    @abstractmethod
    def retrieve(self, session_id: str, key: str) -> dict:
        ...

    @abstractmethod
    def search(self, session_id: str, query: str, top_k: int) -> dict:
        ...

    @abstractmethod
    def summarize(self, session_id: str) -> dict:
        ...

    @abstractmethod
    def clear(self, session_id: str) -> dict:
        ...


# ---------------------------------------------------------------------------
# Redis backend
# ---------------------------------------------------------------------------

class _RedisBackend(_Backend):
    def __init__(self, url: str, ttl: int = _DEFAULT_TTL) -> None:
        import redis as _redis
        self._client = _redis.Redis.from_url(url, decode_responses=True)
        self._ttl = ttl

    def _rkey(self, session_id: str) -> str:
        return f"{_REDIS_KEY_PREFIX}:{session_id}"

    def store(self, session_id: str, key: str, value: Any) -> dict:
        record = {"key": key, "value": value, "stored_at": int(time.time())}
        rkey = self._rkey(session_id)
        self._client.hset(rkey, key, json.dumps(record))
        self._client.expire(rkey, self._ttl)
        return {"success": True, "data": record, "backend": "redis"}

    def retrieve(self, session_id: str, key: str) -> dict:
        raw = self._client.hget(self._rkey(session_id), key)
        if raw is None:
            return {"success": False, "data": None, "error": f"Key '{key}' not found", "backend": "redis"}
        return {"success": True, "data": json.loads(raw), "backend": "redis"}

    def search(self, session_id: str, query: str, top_k: int) -> dict:
        all_raw = self._client.hgetall(self._rkey(session_id))
        q = query.lower()
        matches = []
        for raw in all_raw.values():
            record = json.loads(raw)
            if q in json.dumps(record).lower():
                matches.append(record)
        return {"success": True, "matches": matches[:top_k], "backend": "redis"}

    def summarize(self, session_id: str) -> dict:
        all_raw = self._client.hgetall(self._rkey(session_id))
        records = [json.loads(v) for v in all_raw.values()]
        return {
            "success": True,
            "data": {"total_records": len(records), "keys": [r["key"] for r in records]},
            "backend": "redis",
        }

    def clear(self, session_id: str) -> dict:
        count = self._client.hlen(self._rkey(session_id))
        self._client.delete(self._rkey(session_id))
        return {"success": True, "data": {"cleared": count}, "backend": "redis"}


# ---------------------------------------------------------------------------
# Filesystem backend
# ---------------------------------------------------------------------------

class _FilesystemBackend(_Backend):
    def __init__(self, store_dir: str | Path) -> None:
        self._root = Path(store_dir)

    def _session_path(self, session_id: str) -> Path:
        path = self._root / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def store(self, session_id: str, key: str, value: Any) -> dict:
        record = {"key": key, "value": value, "stored_at": int(time.time())}
        (self._session_path(session_id) / f"{key}.json").write_text(json.dumps(record))
        return {"success": True, "data": record, "backend": "filesystem"}

    def retrieve(self, session_id: str, key: str) -> dict:
        path = self._session_path(session_id) / f"{key}.json"
        if not path.exists():
            return {"success": False, "data": None, "error": f"Key '{key}' not found", "backend": "filesystem"}
        return {"success": True, "data": json.loads(path.read_text()), "backend": "filesystem"}

    def search(self, session_id: str, query: str, top_k: int) -> dict:
        q = query.lower()
        matches = []
        for f in self._session_path(session_id).glob("*.json"):
            record = json.loads(f.read_text())
            if q in json.dumps(record).lower():
                matches.append(record)
        return {"success": True, "matches": matches[:top_k], "backend": "filesystem"}

    def summarize(self, session_id: str) -> dict:
        records = [json.loads(f.read_text()) for f in self._session_path(session_id).glob("*.json")]
        return {
            "success": True,
            "data": {"total_records": len(records), "keys": [r["key"] for r in records]},
            "backend": "filesystem",
        }

    def clear(self, session_id: str) -> dict:
        count = 0
        for f in self._session_path(session_id).glob("*.json"):
            f.unlink()
            count += 1
        return {"success": True, "data": {"cleared": count}, "backend": "filesystem"}


# ---------------------------------------------------------------------------
# Backend resolution — called once at module level, cached
# ---------------------------------------------------------------------------

def _resolve_backend() -> _Backend:
    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        try:
            backend = _RedisBackend(redis_url)
            # Verify connectivity — raises on failure
            backend._client.ping()
            return backend
        except Exception:
            pass  # fall through to filesystem

    store_dir = os.environ.get("CONTEXT_STORE_DIR", "/tmp/sybil-context")
    return _FilesystemBackend(store_dir)


_backend: _Backend | None = None


def _get_backend() -> _Backend:
    global _backend
    if _backend is None:
        _backend = _resolve_backend()
    return _backend


# ---------------------------------------------------------------------------
# Public skill interface
# ---------------------------------------------------------------------------

def invoke(params: dict[str, Any]) -> dict[str, Any]:
    operation = params.get("operation", "store")
    session_id = params.get("session_id", "default")

    backend = _get_backend()

    if operation == "store":
        result = backend.store(session_id, params["key"], params["value"])
    elif operation == "retrieve":
        result = backend.retrieve(session_id, params["key"])
    elif operation == "search":
        result = backend.search(session_id, params.get("query", ""), params.get("top_k", 5))
    elif operation == "summarize":
        result = backend.summarize(session_id)
    elif operation == "clear":
        result = backend.clear(session_id)
    else:
        return {"status": "success", "success": False, "error": f"Unknown operation: {operation}", "skill": SKILL_NAME}

    result["status"] = "success"
    result["skill"] = SKILL_NAME
    return result


run = invoke

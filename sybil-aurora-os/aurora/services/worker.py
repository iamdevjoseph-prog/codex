"""
Aurora Worker — Async skill execution via Redis job queue.

Job lifecycle:
  1. Caller pushes a JSON job to list  sybil:jobs:pending
  2. Worker pops, executes the skill, writes result to hash sybil:jobs:results
  3. Result TTL defaults to 3600s; caller polls or uses Pub/Sub notify

Job schema (JSON):
  {
    "job_id":   "<uuid>",           # required
    "skill":    "<skill-name>",     # required
    "input":    {...},              # required, forwarded to skill
    "timeout":  30,                 # optional, seconds (default 30)
    "notify":   true|false          # optional, publish result event
  }

Result schema stored at sybil:jobs:results:<job_id>:
  {
    "job_id":     "<uuid>",
    "status":     "success" | "error",
    "result":     {...},
    "error":      "<message>" | null,
    "started_at": <epoch>,
    "finished_at":<epoch>
  }

Environment variables:
  REDIS_URL          — Redis connection (default redis://localhost:6379)
  WORKER_CONCURRENCY — parallel workers (default 4)
  WORKER_QUEUE       — queue list name   (default sybil:jobs:pending)
  JOB_RESULT_TTL     — result expiry s   (default 3600)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parents[2]))

from core.skill_loader import run as _skill_run, register_all_as_python_packages

register_all_as_python_packages()

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REDIS_URL       = os.environ.get("REDIS_URL", "redis://localhost:6379")
QUEUE_KEY       = os.environ.get("WORKER_QUEUE", "sybil:jobs:pending")
RESULT_PREFIX   = "sybil:jobs:results"
RESULT_TTL      = int(os.environ.get("JOB_RESULT_TTL", 3600))
CONCURRENCY     = int(os.environ.get("WORKER_CONCURRENCY", 4))
BLOCK_TIMEOUT   = 2   # seconds to block on BRPOP before looping (allows clean shutdown)

# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

def _redis_from_url(url: str):
    """Return a connected Redis client for *url* (lazily imported)."""
    import redis as _r
    return _r.Redis.from_url(url, decode_responses=True)


def _get_redis():
    """Return a Redis client for the default REDIS_URL."""
    return _redis_from_url(REDIS_URL)


def _result_key(job_id: str) -> str:
    return f"{RESULT_PREFIX}:{job_id}"


# ---------------------------------------------------------------------------
# Job execution
# ---------------------------------------------------------------------------

def _execute_job(job: dict[str, Any], redis_client) -> None:
    """Run one job synchronously and write the result to Redis."""
    job_id   = job.get("job_id", str(uuid.uuid4()))
    skill    = job.get("skill", "")
    inp      = job.get("input", {})
    notify   = bool(job.get("notify", False))
    started  = int(time.time())

    log.info("job=%s skill=%s starting", job_id, skill)

    try:
        if not skill:
            raise ValueError("Missing required field 'skill'")
        if not isinstance(inp, dict):
            raise ValueError("Field 'input' must be a JSON object")
        result_payload = _skill_run(skill, inp)
        record = {
            "job_id":      job_id,
            "status":      "success",
            "result":      result_payload,
            "error":       None,
            "started_at":  started,
            "finished_at": int(time.time()),
        }
    except ImportError as exc:
        record = {
            "job_id":      job_id,
            "status":      "error",
            "result":      {},
            "error":       f"Skill '{skill}' not found: {exc}",
            "started_at":  started,
            "finished_at": int(time.time()),
        }
    except Exception as exc:
        record = {
            "job_id":      job_id,
            "status":      "error",
            "result":      {},
            "error":       str(exc),
            "started_at":  started,
            "finished_at": int(time.time()),
        }

    rkey = _result_key(job_id)
    redis_client.set(rkey, json.dumps(record), ex=RESULT_TTL)

    if notify:
        redis_client.publish(f"sybil:jobs:done:{job_id}", json.dumps({"job_id": job_id, "status": record["status"]}))

    log.info("job=%s skill=%s status=%s elapsed=%ds",
             job_id, skill, record["status"],
             record["finished_at"] - record["started_at"])


def _worker_loop(stop_event: threading.Event) -> None:
    """
    Blocking worker loop: BRPOP a job from the queue, execute it.
    Runs until stop_event is set.
    """
    rc = _get_redis()
    log.info("worker loop started queue=%s", QUEUE_KEY)

    while not stop_event.is_set():
        item = rc.brpop(QUEUE_KEY, timeout=BLOCK_TIMEOUT)
        if item is None:
            continue  # timeout — check stop_event and loop

        _, raw = item
        try:
            job = json.loads(raw)
        except json.JSONDecodeError as exc:
            log.error("bad job JSON: %s — %s", raw[:120], exc)
            continue

        try:
            _execute_job(job, rc)
        except Exception as exc:
            log.exception("unhandled error in job execution: %s", exc)


# ---------------------------------------------------------------------------
# Public API — used by tests and potential programmatic callers
# ---------------------------------------------------------------------------

class Worker:
    """
    Manages a pool of worker threads draining the Redis job queue.

    Usage:
        w = Worker()
        w.start()
        # ... submit jobs via enqueue() ...
        w.stop()
    """

    def __init__(
        self,
        concurrency: int = CONCURRENCY,
        queue_key: str = QUEUE_KEY,
        redis_url: str = REDIS_URL,
    ) -> None:
        self._concurrency = concurrency
        self._queue_key   = queue_key
        self._redis_url   = redis_url
        self._stop        = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        self._stop.clear()
        for i in range(self._concurrency):
            t = threading.Thread(
                target=_worker_loop,
                args=(self._stop,),
                name=f"aurora-worker-{i}",
                daemon=True,
            )
            t.start()
            self._threads.append(t)
        log.info("worker pool started threads=%d queue=%s", self._concurrency, self._queue_key)

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=timeout)
        self._threads.clear()
        log.info("worker pool stopped")

    @property
    def is_running(self) -> bool:
        return any(t.is_alive() for t in self._threads)

    @staticmethod
    def enqueue(skill: str, inp: dict[str, Any], *, notify: bool = False,
                job_id: str | None = None, redis_url: str = REDIS_URL) -> str:
        """
        Push a job onto the queue. Returns the job_id.
        Importable standalone so callers don't need to instantiate Worker.
        """
        rc = _redis_from_url(redis_url)
        jid = job_id or str(uuid.uuid4())
        payload = {"job_id": jid, "skill": skill, "input": inp, "notify": notify}
        rc.lpush(QUEUE_KEY, json.dumps(payload))
        return jid

    @staticmethod
    def get_result(job_id: str, redis_url: str = REDIS_URL) -> dict[str, Any] | None:
        """
        Retrieve job result from Redis. Returns None if not yet available.
        """
        rc = _redis_from_url(redis_url)
        raw = rc.get(_result_key(job_id))
        if raw is None:
            return None
        return json.loads(raw)

    @staticmethod
    def wait_for_result(job_id: str, timeout: float = 30.0,
                        poll_interval: float = 0.1,
                        redis_url: str = REDIS_URL) -> dict[str, Any] | None:
        """
        Poll until the result is available or timeout expires.
        Returns the result dict, or None on timeout.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = Worker.get_result(job_id, redis_url=redis_url)
            if result is not None:
                return result
            time.sleep(poll_interval)
        return None


# ---------------------------------------------------------------------------
# __main__ entry point — used by docker-compose `command`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "info").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    log.info("Aurora worker starting concurrency=%d queue=%s", CONCURRENCY, QUEUE_KEY)

    worker = Worker(concurrency=CONCURRENCY)
    worker.start()

    try:
        # Keep the main thread alive; threads are daemon so Ctrl-C exits cleanly
        while worker.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("shutdown signal received")
    finally:
        worker.stop()
        log.info("worker shutdown complete")

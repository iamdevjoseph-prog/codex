"""
trailofbits-security — Validation, hallucination detection, secure execution patterns.
"""

from __future__ import annotations

import json
import re
from typing import Any

SKILL_NAME = "trailofbits-security"

_INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"disregard (all|your) (previous|prior|above)",
    r"you are now",
    r"system prompt",
    r"<script",
    r"DROP TABLE",
    r"--\s*$",
]

_PII_PATTERNS = [
    r"\b\d{3}-\d{2}-\d{4}\b",          # SSN
    r"\b\d{16}\b",                       # Credit card
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email
]


def invoke(params: dict[str, Any]) -> dict[str, Any]:
    payload = params["payload"]
    checks = params["checks"]
    schema_ref = params.get("schema_ref")
    strict = params.get("strict", True)

    violations: list[dict] = []
    payload_str = json.dumps(payload)

    if "injection" in checks:
        violations += _check_injection(payload_str)

    if "pii" in checks:
        violations += _check_pii(payload_str)

    if "schema" in checks and schema_ref:
        violations += _check_schema(payload, schema_ref)

    if "hallucination" in checks:
        violations += _check_hallucination(payload)

    if "data_integrity" in checks:
        violations += _check_data_integrity(payload)

    risk_score = min(len(violations) * 0.2, 1.0)
    passed = len(violations) == 0 if strict else risk_score < 0.5

    return {
        "status": "success",
        "passed": passed,
        "violations": violations,
        "sanitized_payload": _sanitize(payload) if not passed else payload,
        "risk_score": round(risk_score, 2),
        "skill": SKILL_NAME,
    }


run = invoke


def _check_injection(text: str) -> list[dict]:
    found = []
    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            found.append({"type": "injection", "pattern": pattern})
    return found


def _check_pii(text: str) -> list[dict]:
    found = []
    for pattern in _PII_PATTERNS:
        if re.search(pattern, text):
            found.append({"type": "pii", "pattern": pattern})
    return found


def _check_schema(payload: dict, schema_ref: dict) -> list[dict]:
    violations = []
    for required_field in schema_ref.get("required", []):
        if required_field not in payload:
            violations.append({"type": "schema", "message": f"Missing required field: {required_field}"})
    return violations


def _check_hallucination(payload: dict) -> list[dict]:
    violations = []
    text = json.dumps(payload).lower()
    hallucination_signals = ["i made up", "i invented", "fictional", "as an ai i cannot verify"]
    for signal in hallucination_signals:
        if signal in text:
            violations.append({"type": "hallucination", "signal": signal})
    return violations


def _check_data_integrity(payload: dict) -> list[dict]:
    violations = []
    text = json.dumps(payload)
    if len(text) > 500_000:
        violations.append({"type": "data_integrity", "message": "Payload exceeds size limit"})
    return violations


def _sanitize(payload: dict) -> dict:
    sanitized = json.dumps(payload)
    for pattern in _PII_PATTERNS:
        sanitized = re.sub(pattern, "[REDACTED]", sanitized)
    return json.loads(sanitized)

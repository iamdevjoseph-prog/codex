#!/usr/bin/env python
"""
CLI bridge: reads {"skill": name, "input": {...}} JSON from stdin,
invokes the named Sybil-Aurora skill, and writes result JSON to stdout.

This is the subprocess boundary between the Rust Codex CLI and the
Python skill layer. The Rust python_bridge module spawns this script.

Exit codes:
  0  skill ran (result JSON on stdout; status may be "error" at the skill level)
  1  skill not found or invocation error
  2  invalid JSON input or missing required keys
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure the sybil-aurora-os root is importable regardless of cwd
sys.path.insert(0, str(Path(__file__).parent))

from skill_loader import run as _skill_run, register_all_as_python_packages

register_all_as_python_packages()


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        _error_exit(f"Invalid JSON input: {exc}", code=2)

    skill = payload.get("skill", "")
    if not skill:
        _error_exit("Missing required key 'skill'", code=2)

    input_data = payload.get("input", {})
    if not isinstance(input_data, dict):
        _error_exit("'input' must be a JSON object", code=2)

    try:
        result = _skill_run(skill, input_data)
    except ImportError:
        _error_exit(f"Skill '{skill}' not found", code=1)
    except Exception as exc:
        _error_exit(str(exc), code=1)

    json.dump(result, sys.stdout)
    sys.stdout.flush()


def _error_exit(message: str, code: int) -> None:
    json.dump({"status": "error", "message": message}, sys.stdout)
    sys.stdout.flush()
    sys.exit(code)


if __name__ == "__main__":
    main()

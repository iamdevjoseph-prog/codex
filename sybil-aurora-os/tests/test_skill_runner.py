"""
Tests for core/skill_runner.py — the subprocess boundary used by the Rust bridge.

Runs the script as a real subprocess to verify stdin/stdout/exit-code contract.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

RUNNER = str(Path(__file__).parents[1] / "core" / "skill_runner.py")


def _run(stdin_text: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, RUNNER],
        input=stdin_text,
        capture_output=True,
        text=True,
    )


def _run_json(payload: dict) -> subprocess.CompletedProcess:
    return _run(json.dumps(payload))


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_seo_engine_exits_zero(self):
        r = _run_json({"skill": "seo-engine", "input": {"topic": "real estate", "keywords": ["cap rate"]}})
        assert r.returncode == 0

    def test_seo_engine_stdout_is_valid_json(self):
        r = _run_json({"skill": "seo-engine", "input": {"topic": "multifamily"}})
        result = json.loads(r.stdout)
        assert isinstance(result, dict)

    def test_seo_engine_returns_success_status(self):
        r = _run_json({"skill": "seo-engine", "input": {"topic": "multifamily"}})
        result = json.loads(r.stdout)
        assert result["status"] == "success"

    def test_ads_engine_returns_headline(self):
        r = _run_json({
            "skill": "ads-engine",
            "input": {"product": "fund", "platform": "meta", "task": "creative_generation"},
        })
        result = json.loads(r.stdout)
        assert result["status"] == "success"
        assert "headline" in result["data"]

    def test_sales_agent_cold_outreach(self):
        r = _run_json({
            "skill": "sales-agent",
            "input": {"offer": "real estate fund", "task": "cold_outreach"},
        })
        result = json.loads(r.stdout)
        assert result["status"] == "success"
        assert "script" in result["data"]

    def test_quality_control_skill(self):
        r = _run_json({
            "skill": "quality-control",
            "input": {"output": {"recommendation": "buy"}, "criteria": ["structured"]},
        })
        result = json.loads(r.stdout)
        assert result["status"] == "success"

    def test_empty_input_defaults_gracefully(self):
        r = _run_json({"skill": "seo-engine", "input": {}})
        assert r.returncode == 0
        result = json.loads(r.stdout)
        assert result["status"] == "success"

    def test_anthropic_core_degrades_without_api_key(self):
        r = _run_json({"skill": "anthropic-core", "input": {"task": "chat", "prompt": "hello"}})
        assert r.returncode == 0
        result = json.loads(r.stdout)
        assert result["status"] == "success"

    def test_output_has_no_trailing_content_after_json(self):
        r = _run_json({"skill": "seo-engine", "input": {}})
        # stdout should be parseable as a complete JSON object with nothing extra
        result = json.loads(r.stdout)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Unknown skill
# ---------------------------------------------------------------------------

class TestUnknownSkill:
    def test_exit_code_is_1(self):
        r = _run_json({"skill": "nonexistent-xyz", "input": {}})
        assert r.returncode == 1

    def test_stdout_is_error_json(self):
        r = _run_json({"skill": "nonexistent-xyz", "input": {}})
        result = json.loads(r.stdout)
        assert result["status"] == "error"
        assert "nonexistent-xyz" in result["message"]


# ---------------------------------------------------------------------------
# Bad input
# ---------------------------------------------------------------------------

class TestBadInput:
    def test_invalid_json_exit_code_2(self):
        r = _run("this is not json")
        assert r.returncode == 2

    def test_invalid_json_stdout_is_error(self):
        r = _run("not json {")
        result = json.loads(r.stdout)
        assert result["status"] == "error"

    def test_missing_skill_key_exit_code_2(self):
        r = _run_json({"input": {"topic": "x"}})  # no "skill" key
        assert r.returncode == 2

    def test_missing_skill_key_error_message(self):
        r = _run_json({"input": {}})
        result = json.loads(r.stdout)
        assert result["status"] == "error"
        assert "skill" in result["message"]

    def test_input_not_a_dict_exit_code_2(self):
        r = _run_json({"skill": "seo-engine", "input": "not a dict"})
        assert r.returncode == 2

    def test_empty_stdin_exit_code_2(self):
        r = _run("")
        assert r.returncode == 2


# ---------------------------------------------------------------------------
# All known skills are invocable
# ---------------------------------------------------------------------------

KNOWN_SKILLS = [
    ("seo-engine",    {"topic": "real estate"}),
    ("ads-engine",    {"product": "fund", "platform": "meta"}),
    ("sales-agent",   {"offer": "fund", "task": "cold_outreach"}),
    ("entrepreneur",  {"task": "deal_analysis", "data": {}}),
    ("visualization", {"chart_type": "bar", "data": {"Q1": 100}, "title": "NOI"}),
    ("slides",        {"deck_type": "investor_deck", "content": {}}),
    ("quality-control", {"output": {"x": 1}, "criteria": ["structured"]}),
]


@pytest.mark.parametrize("skill,inp", KNOWN_SKILLS)
def test_known_skill_exits_zero(skill: str, inp: dict):
    r = _run_json({"skill": skill, "input": inp})
    assert r.returncode == 0, f"{skill} exited {r.returncode}: {r.stderr}"
    result = json.loads(r.stdout)
    assert result["status"] == "success", f"{skill} returned status={result['status']!r}"

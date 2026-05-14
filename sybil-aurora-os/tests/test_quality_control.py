"""
test_quality_control — Verify the Stop Slop gate catches low-quality output
and approves production-grade output.
"""

from __future__ import annotations

import pytest

from core.skills.quality_control.main import run as qc


# ── Stop Slop detection ───────────────────────────────────────────────────────

@pytest.mark.parametrize("slop_phrase", [
    "certainly!",
    "of course!",
    "great question",
    "as an ai",
    "i hope this helps",
    "let me know if you need anything else",
    "in conclusion,",
    "i'm just an ai",
])
def test_stop_slop_blocks_filler_phrases(slop_phrase):
    payload = {"message": f"{slop_phrase} here is your analysis."}
    result = qc({"output": payload, "criteria": ["actionable"]})
    assert not result["approved"], f"Slop phrase '{slop_phrase}' was not caught"
    assert result["quality_score"] < 1.0
    assert any("Slop" in issue for issue in result["issues"])


def test_stop_slop_returns_issues_list(slop_payload):
    result = qc({"output": slop_payload, "criteria": ["actionable", "structured"]})
    assert isinstance(result["issues"], list)
    assert len(result["issues"]) > 0


def test_stop_slop_provides_recommendations(slop_payload):
    result = qc({"output": slop_payload, "criteria": ["actionable"]})
    assert len(result["recommendations"]) > 0


# ── Approval on clean output ──────────────────────────────────────────────────

def test_clean_output_approved(clean_payload):
    result = qc({
        "output": clean_payload,
        "criteria": ["actionable", "structured", "complete"],
        "min_score": 0.7,
    })
    assert result["approved"]
    assert result["quality_score"] >= 0.7


def test_clean_output_has_no_slop_issues(clean_payload):
    result = qc({"output": clean_payload, "criteria": ["actionable"]})
    slop_issues = [i for i in result["issues"] if "Slop" in i]
    assert slop_issues == []


# ── Criteria checks ───────────────────────────────────────────────────────────

def test_empty_output_fails_complete_check():
    result = qc({"output": {}, "criteria": ["complete"]})
    assert not result["approved"]
    assert result["quality_score"] == 0.0


def test_non_production_signals_detected():
    payload = {"code": "TODO: fix this", "url": "localhost:3000"}
    result = qc({"output": payload, "criteria": ["production_ready"]})
    assert not result["approved"]
    prod_issues = [i for i in result["issues"] if "production" in i.lower() or "Non-production" in i]
    assert len(prod_issues) > 0


def test_verbose_output_penalises_concise_score():
    large_payload = {"data": "x" * 60_000}
    result = qc({"output": large_payload, "criteria": ["concise"]})
    assert result["quality_score"] < 1.0


def test_min_score_threshold_respected():
    # Single-key dict: scores 0.5 on "structured" (not sufficiently structured)
    payload = {"note": "some data here"}
    high_bar = qc({"output": payload, "criteria": ["structured"], "min_score": 0.9})
    low_bar  = qc({"output": payload, "criteria": ["structured"], "min_score": 0.1})
    assert not high_bar["approved"]
    assert low_bar["approved"]


def test_output_key_always_present(clean_payload):
    result = qc({"output": clean_payload, "criteria": ["actionable"]})
    assert "output" in result


def test_quality_score_is_normalised(clean_payload):
    result = qc({"output": clean_payload, "criteria": ["actionable", "structured", "complete"]})
    assert 0.0 <= result["quality_score"] <= 1.0

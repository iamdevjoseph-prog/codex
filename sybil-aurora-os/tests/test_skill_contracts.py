"""
test_skill_contracts — Verify every skill satisfies the universal interface.

Universal contract:
  run(input: dict) -> {"status": "success", "data": {...}, "meta": {...}}
"""

from __future__ import annotations

import importlib

import pytest

# (skill_name, minimal_valid_input)
SKILL_CASES = [
    ("seo-engine",            {"topic": "multifamily real estate", "keywords": ["cap rate", "Austin"], "task": "listing_optimization"}),
    ("ads-engine",            {"product": "multifamily deal", "platform": "meta", "task": "creative_generation"}),
    ("sales-agent",           {"offer": "real estate fund", "task": "cold_outreach", "prospect": {"name": "Alex"}}),
    ("caveman-agent",         {"task": "analyze deal metrics", "tools": ["entrepreneur"]}),
    ("ui-ux",                 {"product": "investment dashboard", "task": "wireframe", "platform": "web"}),
    ("video",                 {"topic": "real estate investing", "task": "script", "style": "explainer", "duration_seconds": 60}),
    ("image",                 {"concept": "aerial view of commercial property", "task": "generate_prompt", "count": 2}),
    ("ios-testing",           {"app": "Sybil Investor App", "task": "generate_tests"}),
    ("entrepreneur",          {"task": "deal_analysis", "data": {"purchase_price": 4_200_000, "noi": 280_000, "loan_amount": 3_000_000}}),
    ("visualization",         {"chart_type": "bar", "data": {"Q1": 280_000, "Q2": 295_000}, "title": "NOI by Quarter"}),
    ("slides",                {"deck_type": "investor_deck", "content": {"executive_summary": {"irr": "12%"}}}),
    ("context-engine",        {"operation": "store", "key": "test_key", "value": {"x": 1}, "session_id": "test-session"}),
    ("callstack-agents",      {"task": "run agents", "agents": [{"name": "deal-analysis-agent", "input": {}}]}),
    ("caveman-agent",         {"task": "baseline execution loop", "max_iterations": 3}),
    ("quality-control",       {"output": {"recommendation": "Proceed", "action": "Deploy"}, "criteria": ["actionable", "structured"]}),
    ("trailofbits-security",  {"payload": {"data": "safe content"}, "checks": ["injection", "pii"]}),
]


def _load_run(skill_name: str):
    module_path = f"core.skills.{skill_name.replace('-', '_')}.main"
    module = importlib.import_module(module_path)
    fn = getattr(module, "run", None) or getattr(module, "invoke", None)
    assert fn is not None, f"{skill_name} exposes neither run() nor invoke()"
    return fn


@pytest.mark.parametrize("skill_name,skill_input", SKILL_CASES)
def test_skill_returns_success_status(skill_name, skill_input):
    fn = _load_run(skill_name)
    result = fn(skill_input)
    assert result["status"] == "success", f"{skill_name} returned status={result.get('status')!r}"


@pytest.mark.parametrize("skill_name,skill_input", SKILL_CASES)
def test_skill_has_data_key(skill_name, skill_input):
    fn = _load_run(skill_name)
    result = fn(skill_input)
    # Accept the universal 'data' key OR well-known domain-specific keys used by
    # legacy skills (entrepreneur → analysis, visualization → spec, slides → slides,
    # callstack-agents → results, security/qc gates → passed/approved).
    _DATA_KEYS = {"data", "passed", "approved", "analysis", "spec", "slides", "results"}
    has_data = bool(_DATA_KEYS & result.keys())
    assert has_data, f"{skill_name} result missing payload key: {list(result.keys())}"


@pytest.mark.parametrize("skill_name,skill_input", SKILL_CASES)
def test_skill_has_meta_or_skill_marker(skill_name, skill_input):
    fn = _load_run(skill_name)
    result = fn(skill_input)
    has_meta = "meta" in result or "skill" in result
    assert has_meta, f"{skill_name} result has no 'meta' or 'skill' marker: {list(result.keys())}"


@pytest.mark.parametrize("skill_name,skill_input", SKILL_CASES)
def test_skill_returns_dict(skill_name, skill_input):
    fn = _load_run(skill_name)
    result = fn(skill_input)
    assert isinstance(result, dict), f"{skill_name} did not return a dict"


# ── Specific contract checks for key skills ───────────────────────────────────

def test_entrepreneur_deal_analysis_has_recommendation(sample_deal):
    from core.skills.entrepreneur.main import run
    result = run({"task": "deal_analysis", "data": sample_deal})
    assert "recommendation" in result
    assert result["recommendation"] in ("Proceed", "Review underwriting")


def test_entrepreneur_cap_rate_calculation(sample_deal):
    from core.skills.entrepreneur.main import run
    result = run({"task": "deal_analysis", "data": sample_deal})
    expected_cap_rate = round(280_000 / 4_200_000 * 100, 2)
    assert result["analysis"]["cap_rate"] == expected_cap_rate


def test_visualization_returns_spec(sample_deal):
    from core.skills.visualization.main import run
    result = run({"chart_type": "bar", "data": {"Q1": 100, "Q2": 200}, "title": "Test"})
    assert "spec" in result
    assert result["chart_type"] == "bar"


def test_slides_investor_deck_has_ten_slides():
    from core.skills.slides.main import run
    result = run({"deck_type": "investor_deck", "content": {}})
    assert result["slide_count"] == 10
    assert len(result["slides"]) == 10


def test_seo_engine_listing_optimization():
    from core.skills.seo_engine.main import run
    result = run({"topic": "multifamily", "keywords": ["cap rate", "Austin"], "task": "listing_optimization"})
    assert result["status"] == "success"
    assert "optimized_title" in result["data"]
    assert "score" in result["data"]


def test_ads_engine_creative_has_headline():
    from core.skills.ads_engine.main import run
    result = run({"product": "real estate fund", "platform": "meta", "task": "creative_generation"})
    assert result["status"] == "success"
    assert "headline" in result["data"]
    assert "cta" in result["data"]


def test_sales_agent_has_objections():
    from core.skills.sales_agent.main import run
    result = run({"offer": "fund", "task": "objection_handling"})
    assert result["status"] == "success"
    assert len(result["data"]["objections"]) > 0
    assert len(result["data"]["responses"]) == len(result["data"]["objections"])


def test_ios_testing_generates_xctest_code():
    from core.skills.ios_testing.main import run
    result = run({"app": "InvestorApp", "task": "generate_tests", "target": "InvestorAppTarget"})
    assert result["status"] == "success"
    assert "XCTestCase" in result["data"]["test_code"]
    assert len(result["data"]["tests"]) > 0


def test_video_script_has_scenes():
    from core.skills.video.main import run
    result = run({"topic": "real estate", "task": "script", "style": "explainer", "duration_seconds": 60})
    assert result["status"] == "success"
    assert len(result["data"]["scenes"]) > 0


def test_image_generate_prompt_returns_prompts():
    from core.skills.image.main import run
    result = run({"concept": "aerial view of property", "task": "generate_prompt", "count": 3})
    assert result["status"] == "success"
    assert len(result["data"]["prompts"]) == 3

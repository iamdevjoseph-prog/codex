"""
test_skills — Smoke tests for individual skill invocations via their run() interface.
"""

from __future__ import annotations

from core.skills.seo_engine.main import run as seo_run
from core.skills.ads_engine.main import run as ads_run
from core.skills.sales_agent.main import run as sales_run
from core.skills.entrepreneur.main import run as entrepreneur_run
from core.skills.visualization.main import run as viz_run
from core.skills.slides.main import run as slides_run


# ── seo-engine ────────────────────────────────────────────────────────────────

def test_seo_skill():
    result = seo_run({"topic": "real estate", "keywords": ["investing"]})
    assert result["status"] == "success"
    assert "article" in result["data"]


def test_seo_skill_keyword_research():
    result = seo_run({"topic": "multifamily", "market": "Austin", "task": "keyword_research"})
    assert result["status"] == "success"
    assert "primary_keywords" in result["data"]


def test_seo_skill_meta_generation():
    result = seo_run({"topic": "commercial real estate", "keywords": ["cap rate"], "task": "meta_generation"})
    assert result["status"] == "success"
    assert "title_tag" in result["data"]


# ── ads-engine ────────────────────────────────────────────────────────────────

def test_ads_skill_creative():
    result = ads_run({"product": "multifamily fund", "platform": "meta", "task": "creative_generation"})
    assert result["status"] == "success"
    assert "headline" in result["data"]
    assert "cta" in result["data"]


def test_ads_skill_budget_allocation():
    result = ads_run({"product": "fund", "task": "budget_allocation", "budget": 10_000,
                      "platforms": ["meta", "google", "linkedin"]})
    assert result["status"] == "success"
    assert "allocation" in result["data"]
    total = sum(result["data"]["allocation"].values())
    assert abs(total - 10_000) < 1


# ── sales-agent ───────────────────────────────────────────────────────────────

def test_sales_skill_cold_outreach():
    result = sales_run({"offer": "real estate fund", "task": "cold_outreach",
                        "prospect": {"name": "Alex"}, "channel": "email"})
    assert result["status"] == "success"
    assert "script" in result["data"]
    assert "subject_line" in result["data"]


def test_sales_skill_email_sequence():
    result = sales_run({"offer": "fund", "task": "email_sequence", "prospect": {"name": "Sam"}})
    assert result["status"] == "success"
    assert len(result["data"]["sequence"]) == 3


# ── entrepreneur ──────────────────────────────────────────────────────────────

def test_entrepreneur_deal_analysis():
    result = entrepreneur_run({
        "task": "deal_analysis",
        "data": {"purchase_price": 4_200_000, "noi": 280_000, "loan_amount": 3_000_000},
    })
    assert result["status"] == "success"
    assert "recommendation" in result
    assert result["analysis"]["cap_rate"] == round(280_000 / 4_200_000 * 100, 2)


# ── visualization ─────────────────────────────────────────────────────────────

def test_visualization_bar_chart():
    result = viz_run({"chart_type": "bar", "data": {"Q1": 100, "Q2": 200}, "title": "NOI"})
    assert result["status"] == "success"
    assert "spec" in result


def test_visualization_waterfall():
    result = viz_run({"chart_type": "waterfall", "data": {"Rev": 500, "OpEx": -200, "NOI": 300}, "title": "Waterfall"})
    assert result["status"] == "success"


# ── slides ────────────────────────────────────────────────────────────────────

def test_slides_investor_deck():
    result = slides_run({"deck_type": "investor_deck", "content": {"executive_summary": {"irr": "12%"}}})
    assert result["status"] == "success"
    assert result["slide_count"] == 10


def test_slides_markdown_format():
    result = slides_run({"deck_type": "report", "content": {"overview": "Fund summary"}, "format": "markdown"})
    assert result["status"] == "success"
    assert isinstance(result["slides"][0], str)
    assert "---" in result["slides"][0]

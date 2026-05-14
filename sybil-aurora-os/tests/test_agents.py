"""
Tests for agent-level skill chaining:
  - marketing-agent uses seo-engine, ads-engine, sales-agent via skill_loader
  - deal-analysis-agent chains entrepreneur → visualization → security → quality-control
  - investor-report-agent chains entrepreneur → slides → visualization → quality-control
  - Full real-estate intelligence pipeline across all three agents
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from sybil.agents.marketing_agent import run as marketing_run
from sybil.agents.deal_analysis_agent import run as deal_run
from sybil.agents.investor_report_agent import run as investor_run


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def listing():
    return {
        "address": "123 Main St, Austin TX",
        "type": "multifamily",
        "bedrooms": 24,
        "cap_rate": "6.8",
        "highlights": "Fully occupied, below-market rents, value-add upside",
        "market": "Austin TX",
    }


@pytest.fixture
def deal():
    return {
        "address": "123 Main St, Austin TX",
        "purchase_price": 3_200_000,
        "noi": 218_000,
        "loan_amount": 2_240_000,
        "hold_period": "5yr",
    }


@pytest.fixture
def portfolio():
    return [
        {"name": "Austin MF", "asset_type": "multifamily", "cost_basis": 3_200_000, "current_value": 3_800_000, "noi": 218_000, "return_pct": 18.75},
        {"name": "Dallas Office", "asset_type": "office", "cost_basis": 5_000_000, "current_value": 5_600_000, "noi": 340_000, "return_pct": 12.0},
    ]


# ---------------------------------------------------------------------------
# marketing-agent
# ---------------------------------------------------------------------------

class TestMarketingAgent:
    def test_returns_dict(self, listing):
        result = marketing_run({"listing": listing, "budget": 50_000})
        assert isinstance(result, dict)

    def test_top_level_keys(self, listing):
        result = marketing_run({"listing": listing, "budget": 50_000})
        for key in ("agent", "status", "listing", "seo", "ads", "outreach", "total_budget"):
            assert key in result, f"missing key: {key}"

    def test_agent_identity(self, listing):
        result = marketing_run({"listing": listing, "budget": 50_000})
        assert result["agent"] == "marketing-agent"

    def test_status_ok(self, listing):
        result = marketing_run({"listing": listing, "budget": 50_000})
        assert result["status"] == "ok"

    def test_seo_comes_from_real_skill(self, listing):
        result = marketing_run({"listing": listing, "budget": 50_000})
        seo = result["seo"]
        # seo-engine listing_optimization returns these keys
        assert "optimized_title" in seo
        assert "target_keywords" in seo
        assert "score" in seo

    def test_ads_per_platform(self, listing):
        result = marketing_run({"listing": listing, "budget": 60_000, "platforms": ["meta", "google"]})
        ads = result["ads"]
        assert "meta" in ads
        assert "google" in ads

    def test_ads_from_real_skill(self, listing):
        result = marketing_run({"listing": listing, "budget": 30_000, "platforms": ["meta"]})
        ad = result["ads"]["meta"]
        # ads-engine creative_generation returns these keys
        assert "headline" in ad
        assert "cta" in ad
        assert "estimated_roas" in ad

    def test_outreach_from_real_skill(self, listing):
        result = marketing_run({"listing": listing, "budget": 0})
        outreach = result["outreach"]
        # sales-agent cold_outreach returns these keys
        assert "script" in outreach
        assert "subject_line" in outreach
        assert "cta" in outreach

    def test_quality_gate_applied(self, listing):
        result = marketing_run({"listing": listing, "budget": 50_000})
        assert "quality_score" in result
        assert "approved" in result
        assert isinstance(result["quality_score"], float)

    def test_budget_split_across_platforms(self, listing):
        result = marketing_run({"listing": listing, "budget": 40_000, "platforms": ["meta", "google"]})
        assert result["total_budget"] == 40_000
        # Both platforms should have gotten a budget allocation
        for platform_ad in result["ads"].values():
            assert isinstance(platform_ad, dict)

    def test_empty_listing_doesnt_crash(self):
        result = marketing_run({"listing": {}, "budget": 0})
        assert result["agent"] == "marketing-agent"
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# deal-analysis-agent
# ---------------------------------------------------------------------------

class TestDealAnalysisAgent:
    def test_returns_dict(self, deal):
        result = deal_run({"deal": deal})
        assert isinstance(result, dict)

    def test_agent_identity(self, deal):
        result = deal_run({"deal": deal})
        assert result["agent"] == "deal-analysis-agent"

    def test_status_ok(self, deal):
        result = deal_run({"deal": deal})
        assert result["status"] == "ok"

    def test_underwriting_present(self, deal):
        result = deal_run({"deal": deal})
        assert "underwriting" in result
        uw = result["underwriting"]
        assert "analysis" in uw
        assert "cap_rate" in uw["analysis"]

    def test_chart_present(self, deal):
        result = deal_run({"deal": deal})
        assert "chart" in result

    def test_risk_score_present(self, deal):
        result = deal_run({"deal": deal})
        assert "risk_score" in result
        assert 0.0 <= result["risk_score"] <= 1.0

    def test_quality_score_present(self, deal):
        result = deal_run({"deal": deal})
        assert "quality_score" in result
        assert isinstance(result["quality_score"], float)

    def test_cap_rate_computed(self, deal):
        result = deal_run({"deal": deal})
        cap_rate = result["underwriting"]["analysis"]["cap_rate"]
        expected = round(218_000 / 3_200_000 * 100, 2)
        assert abs(cap_rate - expected) < 0.01

    def test_empty_deal_doesnt_crash(self):
        result = deal_run({"deal": {}})
        assert isinstance(result, dict)
        assert "agent" in result


# ---------------------------------------------------------------------------
# investor-report-agent
# ---------------------------------------------------------------------------

class TestInvestorReportAgent:
    def test_returns_dict(self, portfolio):
        result = investor_run({"portfolio": portfolio, "fund_name": "Sybil Capital Fund I", "period": "Q1 2026"})
        assert isinstance(result, dict)

    def test_agent_identity(self, portfolio):
        result = investor_run({"portfolio": portfolio, "fund_name": "Sybil Capital Fund I", "period": "Q1 2026"})
        assert result["agent"] == "investor-report-agent"

    def test_status_ok(self, portfolio):
        result = investor_run({"portfolio": portfolio, "fund_name": "SCF-I", "period": "Q1 2026"})
        assert result["status"] == "ok"

    def test_slides_generated(self, portfolio):
        result = investor_run({"portfolio": portfolio, "fund_name": "SCF-I", "period": "Q1 2026"})
        assert "slides" in result
        assert result["slide_count"] > 0

    def test_charts_generated(self, portfolio):
        result = investor_run({"portfolio": portfolio, "fund_name": "SCF-I", "period": "Q1 2026"})
        charts = result["charts"]
        assert "returns" in charts
        assert "allocation" in charts
        assert "waterfall" in charts

    def test_metrics_aggregated(self, portfolio):
        result = investor_run({"portfolio": portfolio, "fund_name": "SCF-I", "period": "Q1 2026"})
        metrics = result["metrics"]
        assert metrics["deal_count"] == 2
        assert metrics["aum"] == 3_800_000 + 5_600_000

    def test_quality_gate_applied(self, portfolio):
        result = investor_run({"portfolio": portfolio, "fund_name": "SCF-I", "period": "Q1 2026"})
        assert "quality_score" in result
        assert "approved" in result

    def test_empty_portfolio(self):
        result = investor_run({"portfolio": [], "fund_name": "Empty Fund", "period": "Q1 2026"})
        assert result["status"] == "ok"
        assert result["metrics"]["aum"] == 0


# ---------------------------------------------------------------------------
# Full pipeline: all three agents chained
# ---------------------------------------------------------------------------

class TestFullRealEstatePipeline:
    def test_full_pipeline_runs(self, deal, listing, portfolio):
        """End-to-end: underwrite → market → report."""
        deal_result = deal_run({"deal": deal})
        assert deal_result["status"] == "ok"

        marketing_result = marketing_run({"listing": listing, "budget": 50_000})
        assert marketing_result["status"] == "ok"

        investor_result = investor_run({
            "portfolio": portfolio,
            "fund_name": "Sybil Capital Fund I",
            "period": "Q1 2026",
        })
        assert investor_result["status"] == "ok"

        # Validate chained outputs are coherent
        assert deal_result["agent"] == "deal-analysis-agent"
        assert marketing_result["agent"] == "marketing-agent"
        assert investor_result["agent"] == "investor-report-agent"

    def test_pipeline_quality_all_scored(self, deal, listing, portfolio):
        """All agents must return quality scores from the quality-control gate."""
        for result in [
            deal_run({"deal": deal}),
            marketing_run({"listing": listing, "budget": 10_000}),
            investor_run({"portfolio": portfolio, "fund_name": "F", "period": "Q1"}),
        ]:
            assert "quality_score" in result, f"missing quality_score in {result.get('agent')}"
            assert isinstance(result["quality_score"], float)

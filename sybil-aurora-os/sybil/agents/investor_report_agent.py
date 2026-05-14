"""
investor-report-agent — Generates investor-grade reports and decks from deal data.

Skills used: entrepreneur, slides, visualization, quality-control
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parents[2]))

from core.skills.entrepreneur.main import invoke as entrepreneur
from core.skills.slides.main import invoke as slides
from core.skills.visualization.main import invoke as visualization
from core.skills.quality_control.main import invoke as quality_control

AGENT_NAME = "investor-report-agent"


def run(params: dict[str, Any]) -> dict[str, Any]:
    portfolio = params.get("portfolio", [])
    fund_name = params.get("fund_name", "Fund")
    period = params.get("period", "Q1 2026")
    brand = params.get("brand", {})

    # Step 1: Aggregate metrics across portfolio
    portfolio_metrics = _aggregate_portfolio(portfolio)

    # Step 2: Build financial charts
    charts = {
        "returns": visualization({
            "chart_type": "line",
            "data": portfolio_metrics.get("returns_by_period", {}),
            "title": f"{fund_name} — Returns {period}",
        })["spec"],
        "allocation": visualization({
            "chart_type": "pie",
            "data": portfolio_metrics.get("allocation", {}),
            "title": "Portfolio Allocation",
        })["spec"],
        "waterfall": visualization({
            "chart_type": "waterfall",
            "data": portfolio_metrics.get("cash_flow", {}),
            "title": "Cash Flow Waterfall",
        })["spec"],
    }

    # Step 3: Build investor deck
    deck_content = {
        "executive_summary": {
            "fund": fund_name,
            "period": period,
            "aum": portfolio_metrics.get("aum"),
            "irr": portfolio_metrics.get("irr"),
        },
        "financials": {**portfolio_metrics, "charts": charts},
        "traction": {"deals_closed": len(portfolio), "total_deployed": portfolio_metrics.get("deployed")},
    }

    deck = slides({"deck_type": "investor_deck", "content": deck_content, "brand": brand})

    output = {
        "agent": AGENT_NAME,
        "status": "ok",
        "fund": fund_name,
        "period": period,
        "slides": deck["slides"],
        "slide_count": deck["slide_count"],
        "charts": charts,
        "metrics": portfolio_metrics,
    }

    # Step 4: Quality gate
    qc = quality_control({
        "output": output,
        "criteria": ["structured", "complete", "production_ready"],
        "domain": "investor_relations",
    })
    output["quality_score"] = qc["quality_score"]
    output["approved"] = qc["approved"]

    return output


def _aggregate_portfolio(portfolio: list[dict]) -> dict:
    if not portfolio:
        return {"aum": 0, "irr": 0, "deployed": 0, "returns_by_period": {}, "allocation": {}, "cash_flow": {}}

    total_value = sum(d.get("current_value", 0) for d in portfolio)
    total_cost = sum(d.get("cost_basis", 0) for d in portfolio)
    irr = round((total_value - total_cost) / total_cost * 100, 2) if total_cost else 0

    return {
        "aum": total_value,
        "deployed": total_cost,
        "irr": irr,
        "deal_count": len(portfolio),
        "returns_by_period": {d.get("name", f"deal_{i}"): d.get("return_pct", 0) for i, d in enumerate(portfolio)},
        "allocation": {d.get("asset_type", "unknown"): d.get("current_value", 0) for d in portfolio},
        "cash_flow": {d.get("name", f"deal_{i}"): d.get("noi", 0) for i, d in enumerate(portfolio)},
    }

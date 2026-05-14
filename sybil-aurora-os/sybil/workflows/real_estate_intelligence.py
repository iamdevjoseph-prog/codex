"""
real-estate-intelligence workflow — End-to-end pipeline for a single deal:
  deal analysis → investor report → marketing campaign

Demonstrates full skill chaining: entrepreneur → visualization → slides
  → seo-engine → ads-engine → trailofbits-security → quality-control
"""

from __future__ import annotations

from typing import Any

from sybil.orchestrator.orchestrator import run as orchestrate


def execute(deal: dict[str, Any], fund_config: dict[str, Any]) -> dict[str, Any]:
    """
    Runs the full real estate intelligence pipeline for a single deal.

    Args:
        deal: Property data (address, purchase_price, noi, loan_amount, etc.)
        fund_config: Fund metadata (name, brand, portfolio, budget, platforms)

    Returns:
        Structured output with underwriting, investor report, and marketing campaign.
    """
    session_id = f"rei-{deal.get('id', 'deal')}"

    # Phase 1: Deal underwriting
    underwriting = orchestrate({
        "intent": "analyze and underwrite deal",
        "payload": {"deal": deal, "constraints": fund_config.get("constraints", {})},
        "session_id": session_id,
    })

    if not underwriting["approved"]:
        return {
            "workflow": "real-estate-intelligence",
            "status": "halted",
            "phase": "underwriting",
            "reason": "quality_gate_failed",
            "details": underwriting,
        }

    # Phase 2: Investor report
    portfolio = fund_config.get("portfolio", []) + [deal]
    report = orchestrate({
        "intent": "generate investor report for fund",
        "payload": {
            "portfolio": portfolio,
            "fund_name": fund_config.get("name", "Fund"),
            "period": fund_config.get("period", "Q1 2026"),
            "brand": fund_config.get("brand", {}),
        },
        "session_id": session_id,
    })

    # Phase 3: Marketing campaign
    marketing = orchestrate({
        "intent": "market listing with seo and ads",
        "payload": {
            "listing": deal,
            "budget": fund_config.get("marketing_budget", 5000),
            "platforms": fund_config.get("platforms", ["meta", "google"]),
            "objectives": ["leads"],
        },
        "session_id": session_id,
    })

    return {
        "workflow": "real-estate-intelligence",
        "status": "complete",
        "session_id": session_id,
        "deal": deal.get("address"),
        "phases": {
            "underwriting": underwriting,
            "investor_report": report,
            "marketing": marketing,
        },
        "quality_scores": {
            "underwriting": underwriting.get("quality_score"),
            "investor_report": report.get("quality_score"),
            "marketing": marketing.get("quality_score"),
        },
    }


if __name__ == "__main__":
    import json

    sample_deal = {
        "id": "deal-001",
        "address": "1234 Commerce Blvd, Austin TX",
        "type": "multifamily",
        "bedrooms": 24,
        "purchase_price": 4_200_000,
        "noi": 280_000,
        "loan_amount": 3_000_000,
        "cap_rate": "6.7",
        "hold_period": "5yr",
        "highlights": "Stabilized asset, 95% occupied, below-market rents",
    }

    sample_fund = {
        "name": "Aurora Capital Fund I",
        "period": "Q2 2026",
        "marketing_budget": 8000,
        "platforms": ["meta", "linkedin"],
        "brand": {"primary_color": "#1a1a2e"},
        "constraints": {"irr_target": "12%"},
        "portfolio": [],
    }

    result = execute(sample_deal, sample_fund)
    print(json.dumps(result, indent=2, default=str))

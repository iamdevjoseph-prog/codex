"""
marketing-agent — Drives organic and paid marketing for listings and campaigns.

Skills used: seo-engine, ads-engine, sales-agent, quality-control
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parents[2]))

from core.skills.quality_control.main import invoke as quality_control

AGENT_NAME = "marketing-agent"


def run(params: dict[str, Any]) -> dict[str, Any]:
    listing = params.get("listing", {})
    budget = params.get("budget", 0)
    platforms = params.get("platforms", ["meta", "google"])
    objectives = params.get("objectives", ["leads"])

    # SEO: listing optimization
    seo_output = _run_seo(listing)

    # Ads: paid creatives per platform
    ad_outputs = {}
    per_platform_budget = budget / len(platforms) if platforms else 0
    for platform in platforms:
        ad_outputs[platform] = _run_ads(listing, per_platform_budget, platform, objectives[0])

    # Sales: outreach copy
    outreach = _run_sales(listing)

    output = {
        "agent": AGENT_NAME,
        "status": "ok",
        "listing": listing.get("address", "unknown"),
        "seo": seo_output,
        "ads": ad_outputs,
        "outreach": outreach,
        "total_budget": budget,
    }

    qc = quality_control({
        "output": output,
        "criteria": ["actionable", "structured", "complete"],
        "domain": "marketing",
    })
    output["quality_score"] = qc["quality_score"]
    output["approved"] = qc["approved"]

    return output


def _run_seo(listing: dict) -> dict:
    address = listing.get("address", "")
    property_type = listing.get("type", "property")
    keywords = [f"{property_type} for sale", address, f"invest in {property_type}"]
    return {
        "optimized_title": f"{listing.get('bedrooms', '')}BR {property_type} | {address}",
        "meta_description": f"Premium {property_type} at {address}. {listing.get('highlights', '')}",
        "target_keywords": keywords,
        "score": 0.82,
        "recommendations": ["Add neighborhood keywords", "Include cap rate in title for investor searches"],
        "skill": "seo-engine",
    }


def _run_ads(listing: dict, budget: float, platform: str, objective: str) -> dict:
    return {
        "platform": platform,
        "objective": objective,
        "budget": budget,
        "headline": f"Invest in {listing.get('type', 'Property')} — {listing.get('cap_rate', '')}% Cap Rate",
        "body": f"Located at {listing.get('address', '')}. Strong cash flow, institutional quality.",
        "cta": "Request Full Underwriting",
        "targeting": {"interests": ["real estate investing", "commercial real estate"], "income": "100k+"},
        "estimated_roas": 3.2,
        "skill": "ads-engine",
    }


def _run_sales(listing: dict) -> dict:
    return {
        "subject_line": f"Deal: {listing.get('address', 'Off-market opportunity')}",
        "copy": (
            f"Hi [Name],\n\n"
            f"We have an off-market {listing.get('type', 'property')} at {listing.get('address', '')} "
            f"with a {listing.get('cap_rate', '')}% cap rate and strong fundamentals.\n\n"
            f"I'd like to walk you through the numbers. Are you available this week?\n\n"
            f"Best,"
        ),
        "call_to_action": "Reply to schedule a call",
        "channel": "email",
        "skill": "sales-agent",
    }

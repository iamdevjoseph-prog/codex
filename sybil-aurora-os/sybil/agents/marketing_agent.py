"""
marketing-agent — Drives organic and paid marketing for listings and campaigns.

Skills used: seo-engine, ads-engine, sales-agent, quality-control
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parents[2]))

from core.skill_loader import run as _skill_run
from core.skills.quality_control.main import invoke as quality_control

AGENT_NAME = "marketing-agent"


def run(params: dict[str, Any]) -> dict[str, Any]:
    listing = params.get("listing", {})
    budget = params.get("budget", 0)
    platforms = params.get("platforms", ["meta", "google"])
    objectives = params.get("objectives", ["leads"])

    seo_output = _run_seo(listing)

    ad_outputs: dict[str, Any] = {}
    per_platform_budget = budget / len(platforms) if platforms else 0
    for platform in platforms:
        ad_outputs[platform] = _run_ads(listing, per_platform_budget, platform, objectives[0])

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
    cap_rate = listing.get("cap_rate", "")
    keywords = [
        f"{property_type} for sale",
        address,
        f"invest in {property_type}",
        *([] if not cap_rate else [f"{property_type} {cap_rate}% cap rate"]),
    ]
    result = _skill_run("seo-engine", {
        "task": "listing_optimization",
        "topic": f"{property_type} at {address}",
        "keywords": keywords,
        "url": listing.get("url", ""),
        "market": listing.get("market", address),
    })
    return result.get("data", result)


def _run_ads(listing: dict, budget: float, platform: str, objective: str) -> dict:
    address = listing.get("address", "")
    property_type = listing.get("type", "property")
    product = f"{property_type} at {address}" if address else property_type
    result = _skill_run("ads-engine", {
        "task": "creative_generation",
        "product": product,
        "platform": platform,
        "objective": objective,
        "budget": budget,
    })
    return result.get("data", result)


def _run_sales(listing: dict) -> dict:
    address = listing.get("address", "off-market opportunity")
    property_type = listing.get("type", "property")
    cap_rate = listing.get("cap_rate", "")
    offer = f"{property_type} at {address}" + (f" ({cap_rate}% cap rate)" if cap_rate else "")
    result = _skill_run("sales-agent", {
        "task": "cold_outreach",
        "offer": offer,
        "channel": "email",
        "tone": "consultative",
    })
    return result.get("data", result)

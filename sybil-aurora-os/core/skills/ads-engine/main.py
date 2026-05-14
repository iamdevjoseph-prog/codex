"""ads-engine — Paid acquisition, ad creatives, targeting, ROAS optimisation."""

from __future__ import annotations

from typing import Any

SKILL_NAME = "ads-engine"


def run(input: dict[str, Any]) -> dict[str, Any]:
    product = input.get("product", "offer")
    platform = input.get("platform", "meta")
    objective = input.get("objective", "leads")
    budget = input.get("budget", 1000.0)
    task = input.get("task", "creative_generation")

    if task == "audience_targeting":
        data = _audience_targeting(product, platform, objective)
    elif task == "budget_allocation":
        data = _budget_allocation(budget, input.get("platforms", ["meta", "google"]))
    elif task == "copy_variants":
        data = _copy_variants(product)
    else:
        data = _creative_generation(product, platform, objective)

    return {"status": "success", "data": data, "meta": {"skill": SKILL_NAME, "platform": platform}}


def _creative_generation(product: str, platform: str, objective: str) -> dict:
    headlines = [
        f"Get the best {product} today",
        f"Why {product} is the smartest move right now",
        f"Unlock returns with {product}",
    ]
    return {
        "headline": headlines[0],
        "primary_text": f"This {product} will change how you think about capital allocation. Institutional-quality underwriting, transparent data.",
        "cta": {"leads": "Request Analysis", "conversions": "Invest Now", "awareness": "Learn More"}.get(objective, "Learn More"),
        "variants": headlines,
        "estimated_ctr": 0.024,
        "estimated_roas": 3.2,
        "platform": platform,
    }


def _audience_targeting(product: str, platform: str, objective: str) -> dict:
    return {
        "platform": platform,
        "interests": ["real estate investing", "commercial real estate", "alternative investments", "REITs"],
        "demographics": {"age_min": 28, "age_max": 65, "income": "100k+"},
        "behaviors": ["frequent_traveler", "small_business_owner"],
        "lookalike_source": "existing_investors",
        "estimated_reach": 420_000,
    }


def _budget_allocation(total: float, platforms: list[str]) -> dict:
    weights = {"meta": 0.40, "google": 0.35, "linkedin": 0.20, "tiktok": 0.05}
    active = {p: weights.get(p, 1 / len(platforms)) for p in platforms}
    total_weight = sum(active.values())
    return {
        "total_budget": total,
        "allocation": {p: round(total * w / total_weight, 2) for p, w in active.items()},
        "recommendation": "Front-load Meta for lead gen; use Google for high-intent search capture.",
    }


def _copy_variants(product: str) -> dict:
    return {
        "variants": [
            {"tone": "direct", "copy": f"Serious about {product}? Let's talk numbers."},
            {"tone": "consultative", "copy": f"Most investors overlook {product}. Here's the data you need."},
            {"tone": "urgency", "copy": f"Off-market {product} — this window closes Friday."},
        ]
    }


invoke = run

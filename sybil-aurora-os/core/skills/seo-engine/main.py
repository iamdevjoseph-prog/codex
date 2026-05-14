"""seo-engine — Organic growth, keyword strategy, listing optimization."""

from __future__ import annotations

from typing import Any

SKILL_NAME = "seo-engine"


def run(input: dict[str, Any]) -> dict[str, Any]:
    topic = input.get("topic", "")
    keywords = input.get("keywords", [])
    url = input.get("url", "")
    market = input.get("market", "")
    task = input.get("task", "listing_optimization")

    if task == "keyword_research":
        data = _keyword_research(topic, market)
    elif task == "meta_generation":
        data = _meta_generation(topic, keywords, url)
    elif task == "content_brief":
        data = _content_brief(topic, keywords)
    else:
        data = _listing_optimization(topic, keywords, url)

    return {"status": "success", "data": data, "meta": {"skill": SKILL_NAME, "task": task}}


def _listing_optimization(topic: str, keywords: list, url: str) -> dict:
    primary = keywords[0] if keywords else topic
    return {
        "optimized_title": f"{primary} | {topic}" if topic else primary,
        "meta_description": f"Discover {topic} with insights on {', '.join(keywords[:3])}. Expert analysis and actionable data.",
        "target_keywords": keywords or [topic],
        "score": 0.82,
        "recommendations": [
            "Add neighbourhood/market keywords for local SEO",
            "Include cap rate or yield figures for investor searches",
            "Use structured data (Schema.org RealEstateListing) on listing pages",
        ],
    }


def _keyword_research(topic: str, market: str) -> dict:
    base = topic.lower()
    return {
        "primary_keywords": [base, f"{base} investment", f"{base} for sale"],
        "long_tail": [f"best {base} in {market}", f"how to invest in {base}", f"{base} cap rate {market}"],
        "negative_keywords": ["free", "DIY"],
        "estimated_monthly_volume": {"primary": 4400, "long_tail": 880},
    }


def _meta_generation(topic: str, keywords: list, url: str) -> dict:
    kw = keywords[0] if keywords else topic
    return {
        "title_tag": f"{kw} — {topic} | Sybil Capital",
        "meta_description": f"Premium {topic.lower()} opportunities. Data-driven underwriting, institutional quality. {kw}.",
        "og_title": f"Invest in {topic}",
        "canonical_url": url,
    }


def _content_brief(topic: str, keywords: list) -> dict:
    return {
        "h1": f"The Complete Guide to {topic}",
        "sections": [f"What is {topic}?", "Market Analysis", "Investment Criteria", "Case Studies", "How to Get Started"],
        "target_keywords": keywords,
        "word_count_target": 2000,
        "internal_links": 3,
    }


# Backward-compat alias used by orchestrator's _load_skill()
invoke = run

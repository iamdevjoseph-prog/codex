"""
slides — Investor decks, pitch decks, structured slide generation.
"""

from __future__ import annotations

from typing import Any

SKILL_NAME = "slides"

_INVESTOR_DECK_TEMPLATE = [
    "cover",
    "executive_summary",
    "problem",
    "solution",
    "market_opportunity",
    "business_model",
    "traction",
    "financials",
    "team",
    "ask",
]


def invoke(params: dict[str, Any]) -> dict[str, Any]:
    deck_type = params.get("deck_type", "investor_deck")
    content = params.get("content", {})
    brand = params.get("brand", {})
    fmt = params.get("format", "json")

    builder = _BUILDERS.get(deck_type, _generic_deck)
    slides = builder(content, brand)

    if fmt == "markdown":
        slides = _to_markdown(slides)

    return {"status": "success", "slides": slides, "deck_type": deck_type, "slide_count": len(slides), "skill": SKILL_NAME}


def _investor_deck(content: dict, brand: dict) -> list[dict]:
    slides = []
    for slide_type in _INVESTOR_DECK_TEMPLATE:
        slide_data = content.get(slide_type, {})
        slides.append({
            "type": slide_type,
            "title": slide_type.replace("_", " ").title(),
            "content": slide_data,
            "brand": brand,
        })
    return slides


def _generic_deck(content: dict, brand: dict) -> list[dict]:
    slides = []
    for key, value in content.items():
        slides.append({
            "type": "content",
            "title": key.replace("_", " ").title(),
            "content": value,
            "brand": brand,
        })
    return slides


def _to_markdown(slides: list[dict]) -> list[str]:
    output = []
    for slide in slides:
        output.append(f"## {slide['title']}\n\n{slide['content']}\n\n---")
    return output


_BUILDERS = {
    "investor_deck": _investor_deck,
    "pitch_deck": _investor_deck,
    "report": _generic_deck,
    "executive_summary": _generic_deck,
}

run = invoke

"""image — Image generation prompts, editing specs, asset pipelines."""

from __future__ import annotations

from typing import Any

SKILL_NAME = "image"

_STYLE_MODIFIERS = {
    "modern": "clean, high contrast, minimal, professional photography",
    "luxury": "premium, gold accents, dark background, editorial photography",
    "data": "infographic, data visualization, clean sans-serif typography",
    "aerial": "drone photography, bird's-eye view, high resolution, golden hour",
}


def run(input: dict[str, Any]) -> dict[str, Any]:
    concept = input.get("concept", "visual")
    task = input.get("task", "generate_prompt")
    style = input.get("style", "modern")
    dimensions = input.get("dimensions", {"width": 1024, "height": 1024})
    count = input.get("count", 1)

    if task == "batch_pipeline":
        data = _batch_pipeline(concept, style, dimensions, count)
    elif task == "edit_spec":
        data = _edit_spec(concept, input.get("edits", []))
    elif task == "asset_variants":
        data = _asset_variants(concept, style)
    else:
        data = _generate_prompt(concept, style, dimensions, count)

    return {"status": "success", "data": data, "meta": {"skill": SKILL_NAME, "task": task}}


def _generate_prompt(concept: str, style: str, dimensions: dict, count: int) -> dict:
    modifier = _STYLE_MODIFIERS.get(style, _STYLE_MODIFIERS["modern"])
    base_prompt = f"{concept}, {modifier}, 4K, photorealistic"
    return {
        "prompt": f"Generate image of {concept}",
        "full_prompt": base_prompt,
        "negative_prompt": "blurry, low quality, watermark, text overlay, distorted",
        "style": style,
        "dimensions": dimensions,
        "count": count,
        "prompts": [f"{base_prompt}, variation {i + 1}" for i in range(count)],
    }


def _batch_pipeline(concept: str, style: str, dimensions: dict, count: int) -> dict:
    modifier = _STYLE_MODIFIERS.get(style, _STYLE_MODIFIERS["modern"])
    return {
        "pipeline": "batch",
        "jobs": [
            {"id": i, "prompt": f"{concept}, {modifier}", "dimensions": dimensions, "status": "queued"}
            for i in range(count)
        ],
        "estimated_seconds": count * 12,
    }


def _edit_spec(concept: str, edits: list) -> dict:
    return {
        "source": concept,
        "edits": edits or ["background_removal", "color_grade", "resize"],
        "output_format": "png",
        "preserve_alpha": True,
    }


def _asset_variants(concept: str, style: str) -> dict:
    modifier = _STYLE_MODIFIERS.get(style, _STYLE_MODIFIERS["modern"])
    return {
        "variants": [
            {"name": "hero", "dimensions": {"width": 1920, "height": 1080}, "prompt": f"{concept}, {modifier}, wide"},
            {"name": "square", "dimensions": {"width": 1080, "height": 1080}, "prompt": f"{concept}, {modifier}, centered"},
            {"name": "story", "dimensions": {"width": 1080, "height": 1920}, "prompt": f"{concept}, {modifier}, vertical"},
            {"name": "thumbnail", "dimensions": {"width": 400, "height": 300}, "prompt": f"{concept}, {modifier}, compact"},
        ]
    }


invoke = run

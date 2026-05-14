"""video — Programmatic video scripts, scene graphs, render specs."""

from __future__ import annotations

from typing import Any

SKILL_NAME = "video"

_SCENE_TEMPLATES = {
    "explainer": ["hook", "problem", "solution", "how_it_works", "social_proof", "cta"],
    "promo": ["hook", "benefit_1", "benefit_2", "benefit_3", "offer", "cta"],
    "documentary": ["intro", "context", "story_arc", "evidence", "conclusion"],
    "ad": ["hook", "problem", "solution", "cta"],
}


def run(input: dict[str, Any]) -> dict[str, Any]:
    topic = input.get("topic", "content")
    task = input.get("task", "script")
    duration = input.get("duration_seconds", 60)
    style = input.get("style", "explainer")
    aspect_ratio = input.get("aspect_ratio", "16:9")

    scene_names = _SCENE_TEMPLATES.get(style, _SCENE_TEMPLATES["explainer"])
    seconds_per_scene = duration // len(scene_names)

    if task == "storyboard":
        data = _storyboard(topic, scene_names, seconds_per_scene)
    elif task == "render_spec":
        data = _render_spec(duration, aspect_ratio, style)
    elif task == "scene_graph":
        data = _scene_graph(topic, scene_names, seconds_per_scene)
    else:
        data = _script(topic, scene_names, seconds_per_scene, style)

    return {"status": "success", "data": data, "meta": {"skill": SKILL_NAME, "style": style, "duration_seconds": duration}}


def _script(topic: str, scenes: list[str], secs: int, style: str) -> dict:
    scene_scripts = {
        "hook": f"Did you know most investors miss the single biggest driver of returns in {topic}?",
        "problem": f"The challenge with {topic} is that the data is fragmented and the analysis takes weeks.",
        "solution": f"Sybil-Aurora OS analyzes {topic} in seconds — cap rate, LTV, cash flow, risk score, all in one place.",
        "how_it_works": "You submit the deal. Our agents underwrite it, generate the investor report, and launch the marketing campaign. Automatically.",
        "social_proof": "Over 120 deals analyzed. $340M in capital allocated. Zero manual spreadsheets.",
        "cta": "Request your free deal analysis at sybil-aurora.io",
    }
    return {
        "script": f"Video script about {topic}",
        "scenes": [{"name": s, "duration_seconds": secs, "copy": scene_scripts.get(s, f"[{s} segment about {topic}]")} for s in scenes],
        "total_duration": secs * len(scenes),
        "style": style,
    }


def _storyboard(topic: str, scenes: list[str], secs: int) -> dict:
    return {
        "frames": [
            {"scene": s, "duration": secs, "visual": f"[{s.replace('_', ' ').title()} visual for {topic}]", "voiceover": True}
            for s in scenes
        ]
    }


def _render_spec(duration: int, aspect_ratio: str, style: str) -> dict:
    res = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
    w, h = res.get(aspect_ratio, (1920, 1080))
    return {"width": w, "height": h, "fps": 30, "duration_seconds": duration, "codec": "h264", "bitrate": "8M", "format": "mp4"}


def _scene_graph(topic: str, scenes: list[str], secs: int) -> dict:
    return {
        "nodes": [{"id": i, "type": s, "duration": secs} for i, s in enumerate(scenes)],
        "edges": [{"from": i, "to": i + 1} for i in range(len(scenes) - 1)],
        "topic": topic,
    }


invoke = run

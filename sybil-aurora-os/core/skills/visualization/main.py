"""
visualization — Financial charts, dashboards, D3/Vega-Lite specs.
"""

from __future__ import annotations

from typing import Any

SKILL_NAME = "visualization"

_THEMES = {
    "dark": {"background": "#1a1a2e", "foreground": "#e0e0e0", "accent": "#16213e"},
    "light": {"background": "#ffffff", "foreground": "#333333", "accent": "#f0f0f0"},
    "minimal": {"background": "transparent", "foreground": "#111111", "accent": "#eeeeee"},
}


def invoke(params: dict[str, Any]) -> dict[str, Any]:
    chart_type = params["chart_type"]
    data = params["data"]
    title = params.get("title", "")
    fmt = params.get("format", "json")
    theme = _THEMES.get(params.get("theme", "dark"), _THEMES["dark"])

    builder = _CHART_BUILDERS.get(chart_type, _default_spec)
    spec = builder(data, title, theme)

    if fmt == "vega":
        spec = _wrap_vega_lite(spec, chart_type, data, title, theme)

    return {"status": "success", "spec": spec, "chart_type": chart_type, "title": title, "skill": SKILL_NAME}


def _bar_spec(data: dict, title: str, theme: dict) -> dict:
    return {
        "status": "success",
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": title,
        "mark": "bar",
        "data": {"values": _normalize(data)},
        "encoding": {
            "x": {"field": "label", "type": "ordinal"},
            "y": {"field": "value", "type": "quantitative"},
            "color": {"value": "#4a90d9"},
        },
        "background": theme["background"],
    }


def _line_spec(data: dict, title: str, theme: dict) -> dict:
    return {
        "status": "success",
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": title,
        "mark": {"type": "line", "point": True},
        "data": {"values": _normalize(data)},
        "encoding": {
            "x": {"field": "label", "type": "ordinal"},
            "y": {"field": "value", "type": "quantitative"},
        },
        "background": theme["background"],
    }


def _waterfall_spec(data: dict, title: str, theme: dict) -> dict:
    values = _normalize(data)
    running = 0
    waterfall_data = []
    for item in values:
        start = running
        running += item["value"]
        waterfall_data.append({**item, "start": start, "end": running})

    return {"type": "waterfall", "title": title, "data": waterfall_data, "background": theme["background"]}


def _default_spec(data: dict, title: str, theme: dict) -> dict:
    return {"type": "raw", "title": title, "data": data}


def _normalize(data: dict) -> list[dict]:
    if isinstance(data, list):
        return data
    return [{"label": k, "value": v} for k, v in data.items()]


def _wrap_vega_lite(spec: dict, chart_type: str, data: dict, title: str, theme: dict) -> dict:
    return spec


_CHART_BUILDERS = {
    "bar": _bar_spec,
    "line": _line_spec,
    "waterfall": _waterfall_spec,
    "pie": _default_spec,
    "scatter": _default_spec,
    "heatmap": _default_spec,
    "candlestick": _default_spec,
}

run = invoke

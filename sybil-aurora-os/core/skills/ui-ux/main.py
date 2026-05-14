"""ui-ux — Interface design, user flows, component specs."""

from __future__ import annotations

from typing import Any

SKILL_NAME = "ui-ux"

_PLATFORM_COMPONENTS = {
    "web": ["navbar", "sidebar", "cards", "charts", "data-table", "modal", "toast"],
    "ios": ["UINavigationController", "UITableView", "UICollectionView", "UITabBar", "SwiftUI.List"],
    "android": ["Toolbar", "RecyclerView", "BottomNavigationView", "FloatingActionButton"],
    "desktop": ["MenuBar", "Toolbar", "SplitPane", "DataGrid", "StatusBar"],
}


def run(input: dict[str, Any]) -> dict[str, Any]:
    product = input.get("product", "app")
    task = input.get("task", "wireframe")
    platform = input.get("platform", "web")
    style = input.get("style", "minimal")
    context = input.get("context", {})

    if task == "flow":
        data = _user_flow(product, platform, context)
    elif task == "component_spec":
        data = _component_spec(product, platform, style)
    elif task == "design_system":
        data = _design_system(style)
    elif task == "accessibility_audit":
        data = _accessibility_audit(context)
    else:
        data = _wireframe(product, platform, style)

    return {"status": "success", "data": data, "meta": {"skill": SKILL_NAME, "platform": platform, "task": task}}


def _wireframe(product: str, platform: str, style: str) -> dict:
    return {
        "layout": "dashboard" if "dashboard" in product.lower() else "standard",
        "components": _PLATFORM_COMPONENTS.get(platform, _PLATFORM_COMPONENTS["web"])[:5],
        "description": f"Modern {style} UI for {product}",
        "grid": "12-column" if platform == "web" else "native",
        "spacing_unit": 8,
    }


def _user_flow(product: str, platform: str, context: dict) -> dict:
    return {
        "flow_name": f"{product} Core Flow",
        "steps": [
            {"id": 1, "screen": "Onboarding", "action": "Sign in / Register"},
            {"id": 2, "screen": "Dashboard", "action": "View portfolio summary"},
            {"id": 3, "screen": "Deal Detail", "action": "Review underwriting"},
            {"id": 4, "screen": "Invest", "action": "Confirm allocation"},
            {"id": 5, "screen": "Confirmation", "action": "View receipt + next steps"},
        ],
        "platform": platform,
        "entry_point": "Onboarding",
        "exit_point": "Confirmation",
    }


def _component_spec(product: str, platform: str, style: str) -> dict:
    return {
        "components": [
            {"name": "DealCard", "type": "card", "props": ["title", "cap_rate", "location", "status"]},
            {"name": "MetricsBar", "type": "stat-row", "props": ["irr", "ltv", "noi", "hold_period"]},
            {"name": "AllocationChart", "type": "pie-chart", "props": ["data", "colors", "legend"]},
        ],
        "design_tokens": {"primary": "#4a90d9", "surface": "#1a1a2e", "text": "#e0e0e0"},
        "platform": platform,
    }


def _design_system(style: str) -> dict:
    systems = {
        "minimal": {"typography": "Inter", "radius": 4, "shadow": "none", "density": "comfortable"},
        "material": {"typography": "Roboto", "radius": 8, "shadow": "md", "density": "standard"},
        "cupertino": {"typography": "SF Pro", "radius": 12, "shadow": "sm", "density": "spacious"},
    }
    return systems.get(style, systems["minimal"])


def _accessibility_audit(context: dict) -> dict:
    return {
        "wcag_level": "AA",
        "checks": ["color_contrast", "keyboard_nav", "screen_reader", "focus_indicators", "alt_text"],
        "issues": [],
        "score": 0.94,
    }


invoke = run

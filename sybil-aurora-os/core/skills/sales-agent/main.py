"""sales-agent — Conversion scripts, sequences, objection handling."""

from __future__ import annotations

from typing import Any

SKILL_NAME = "sales-agent"

_OBJECTIONS = {
    "price": ("Too expensive", "The ROI outpaces the cost within 12 months — let me walk you through the numbers."),
    "time": ("Need more time to decide", "Totally fair. Let's schedule 20 minutes so you have everything you need to decide confidently."),
    "trust": ("Not sure I trust this", "Fair — here are three investors who ran the same numbers and closed. I can connect you directly."),
    "fit": ("Not sure it's right for us", "Let's pressure-test that. What would the deal need to look like to make sense for your portfolio?"),
}


def run(input: dict[str, Any]) -> dict[str, Any]:
    offer = input.get("offer", "service")
    task = input.get("task", "cold_outreach")
    prospect = input.get("prospect", {})
    tone = input.get("tone", "consultative")
    channel = input.get("channel", "email")

    if task == "objection_handling":
        data = _objection_handling(offer)
    elif task == "follow_up":
        data = _follow_up(offer, prospect, channel)
    elif task == "close_script":
        data = _close_script(offer, prospect)
    elif task == "email_sequence":
        data = _email_sequence(offer, prospect)
    else:
        data = _cold_outreach(offer, prospect, tone, channel)

    return {"status": "success", "data": data, "meta": {"skill": SKILL_NAME, "task": task, "channel": channel}}


def _cold_outreach(offer: str, prospect: dict, tone: str, channel: str) -> dict:
    name = prospect.get("name", "there")
    script = (
        f"Hi {name},\n\n"
        f"Are you currently looking to improve your exposure to {offer}? "
        f"We work with investors who want institutional-quality underwriting without the overhead.\n\n"
        f"Happy to share a quick analysis specific to your portfolio. Worth a 15-minute call?\n\nBest,"
    )
    return {
        "script": script,
        "subject_line": f"Quick question about your {offer} strategy",
        "cta": "Reply to book 15 min",
        "objections": [o for o, _ in _OBJECTIONS.values()],
        "responses": [r for _, r in _OBJECTIONS.values()],
    }


def _objection_handling(offer: str) -> dict:
    return {
        "script": f"Are you currently looking to improve your {offer}? Here's how we help...",
        "objections": [o for o, _ in _OBJECTIONS.values()],
        "responses": [r for _, r in _OBJECTIONS.values()],
        "framework": "Feel → Felt → Found",
    }


def _follow_up(offer: str, prospect: dict, channel: str) -> dict:
    name = prospect.get("name", "there")
    return {
        "script": f"Hi {name}, just circling back on the {offer} analysis I sent. Did you get a chance to look it over?",
        "subject_line": f"Re: {offer} — any questions?",
        "send_delay_days": 3,
        "max_follow_ups": 3,
    }


def _close_script(offer: str, prospect: dict) -> dict:
    return {
        "script": f"Based on everything we've discussed, the {offer} makes sense for your criteria. Ready to move forward?",
        "next_steps": ["Execute NDA", "Share full data room", "Sign term sheet"],
        "urgency_lever": "We have one other interested party — wanted to give you first right of refusal.",
    }


def _email_sequence(offer: str, prospect: dict) -> dict:
    name = prospect.get("name", "Investor")
    return {
        "sequence": [
            {"day": 0, "subject": f"Opportunity: {offer}", "preview": f"Hi {name}, I wanted to share something specific to your portfolio..."},
            {"day": 3, "subject": f"Re: {offer} — quick follow-up", "preview": "Did you get a chance to review the analysis?"},
            {"day": 7, "subject": f"Final note on {offer}", "preview": "I'll keep this brief — are you open to a 10-minute call?"},
        ]
    }


invoke = run

"""
deal-analysis-agent — Underwrites real estate and capital allocation deals.

Skills used: entrepreneur, visualization, trailofbits-security, quality-control
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parents[2]))

from core.skills.entrepreneur.main import invoke as entrepreneur
from core.skills.visualization.main import invoke as visualization
from core.skills.trailofbits_security.main import invoke as security
from core.skills.quality_control.main import invoke as quality_control

AGENT_NAME = "deal-analysis-agent"


def run(params: dict[str, Any]) -> dict[str, Any]:
    deal = params.get("deal", {})
    constraints = params.get("constraints", {})

    # Step 1: Business logic — underwriting
    analysis = entrepreneur({
        "task": "deal_analysis",
        "data": deal,
        "constraints": constraints,
    })

    # Step 2: Financial visualization
    chart = visualization({
        "chart_type": "bar",
        "data": analysis.get("metrics", {}),
        "title": f"Deal Analysis — {deal.get('address', 'Property')}",
        "theme": "dark",
    })

    # Step 3: Security validation
    validation = security({
        "payload": analysis,
        "checks": ["hallucination", "data_integrity", "schema"],
        "schema_ref": {"required": ["analysis", "recommendation", "metrics", "risks"]},
        "strict": True,
    })

    if not validation["passed"]:
        return {
            "agent": AGENT_NAME,
            "status": "blocked",
            "reason": "security_validation_failed",
            "violations": validation["violations"],
        }

    output = {
        "agent": AGENT_NAME,
        "status": "ok",
        "deal": deal.get("address", "unknown"),
        "underwriting": analysis,
        "chart": chart["spec"],
        "risk_score": validation["risk_score"],
    }

    # Step 4: Quality gate
    qc = quality_control({
        "output": output,
        "criteria": ["actionable", "structured", "complete", "production_ready"],
        "domain": "real_estate",
        "min_score": 0.8,
    })

    output["quality_score"] = qc["quality_score"]
    output["approved"] = qc["approved"]

    if not qc["approved"]:
        output["quality_issues"] = qc["issues"]

    return output

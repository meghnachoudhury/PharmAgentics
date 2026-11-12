"""Forecast-Explanation lane: the API scaffold (core-007 User Story 8; owners Alvin and Sienna).

The lane is reserved: roles CA (analyst view) and BM (leadership view) exist in roles.json, and the UI
has a Forecast section. When the lane's engine lands, add its routes here, following the Briefing
routes in app.py: the server decides the view from the role, leadership responses carry no evidence or
trace, and every number is a claim with evidence (shared Principle I). Set lanes.forecast.available to
true in roles.json when it is ready.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from . import rbac

router = APIRouter(prefix="/api/forecast", tags=["forecast"])


@router.get("/status")
def status(response: Response, p: rbac.Principal = Depends(rbac.require_user)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    role = p.role("forecast")
    return {
        "lane": "forecast", "available": rbac.lane_available("forecast"),
        "role": role.name if role else None, "persona": role.persona if role else None,
        "label": role.label if role else None, "views": list(role.views) if role else [],
        "planned": {
            "analyst": "Forecast against actual by territory and week, the drivers of the gap with evidence, "
                       "and what to revise (Commercial Analytics Analyst, CA).",
            "leadership": "An executive summary of the forecast gap and dynamic projections, with no evidence "
                          "or trace (Brand Manager, BM).",
        },
    }

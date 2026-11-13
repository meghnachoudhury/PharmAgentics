"""Forecast-Explanation lane: the API (core-007 User Story 8; owners Alvin and Sienna).

Who may do what (the personas do not assume the Brand Manager operates the agent):

- The Commercial Analyst (CA) runs the agent, reads the full run (seven stages, report, evidence), may
  preview the leadership view, and submits a run for approval.
- The Brand Manager (BM) cannot run or submit. BM reads the leadership view (an executive summary with no evidence
  or trace) of submitted runs and approves, rejects or returns them, with a note for a rejection or a return.
- Nothing is approved by the system. A run is ``not_submitted`` until the CA submits it.

The engine and model are fixed by the server (FEAGENT_MODE, default "stub", which uses no language model); a caller
cannot choose them. Set lanes.forecast.available to true in roles.json when the UI is ready to open the Forecast
section; these routes work for the Forecast roles regardless of that flag.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool

from . import forecast_store, rbac, service, store, views
from .schemas import ForecastReview, ForecastRunRequest

log = logging.getLogger("pharmagentics.forecast")
router = APIRouter(prefix="/api/forecast", tags=["forecast"])

ENGINE_DIR = Path(__file__).resolve().parents[3] / "agents" / "forecast-explanation"
MODES = {"stub", "auto", "ollama"}  # stub: no language model; ollama: a local model; auto: local model, else stub
Forecast = Depends(rbac.require_forecast)


def engine_mode() -> str:
    mode = os.environ.get("FEAGENT_MODE", "stub")
    return mode if mode in MODES else "stub"


def _pipeline():
    if not ENGINE_DIR.is_dir():
        raise HTTPException(status_code=503, detail="The Forecast engine is not installed on this server.")
    if str(ENGINE_DIR) not in sys.path:
        sys.path.insert(0, str(ENGINE_DIR))
    from feagent import pipeline

    return pipeline


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/status")
def status(response: Response, p: rbac.Principal = Depends(rbac.require_user)) -> dict:
    _no_store(response)
    role = p.role("forecast")
    return {
        "lane": "forecast", "available": rbac.lane_available("forecast"), "engine": engine_mode(),
        "role": role.name if role else None, "persona": role.persona if role else None,
        "label": role.label if role else None, "views": list(role.views) if role else [],
        "actions": list(role.actions) if role else [],
        "planned": {
            "analyst": "Forecast against actual by territory and week, the drivers of the gap with evidence, "
                       "and what to revise (Commercial Analyst, CA).",
            "leadership": "An executive summary of the forecast gap and dynamic projections, with no evidence "
                          "or trace (Brand Manager, BM).",
        },
    }


@router.get("/cases")
def cases(response: Response, who=Forecast) -> dict:
    """The three ready-made cards: the request body to POST to /api/forecast/runs for each."""
    _no_store(response)
    rbac.allow(who[1], "run")
    out = []
    for case in _pipeline().FORECAST_LANE_CASES:
        req = case["request"]
        out.append({
            "case_id": case["case_id"], "tag": case["tag"], "label": case["label"],
            "request": {"territory_id": req["territory_id"], "week_start": req["week_start"],
                        "window_weeks": req.get("window_weeks", 1)},
        })
    return {"lane": "forecast", "cases": out}


@router.get("/context")
async def context(response: Response, who=Forecast) -> dict:
    """The governed scope choices for a manual Forecast run."""
    _no_store(response)
    rbac.allow(who[1], "run")
    try:
        release = await run_in_threadpool(service.release_context)
    except service.MissingDatabase as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # The Briefing release lists the eight territories; Forecast also runs the national total, first.
    return {"territory_ids": ["NATIONAL", *release.territory_ids], "available_weeks": [d.isoformat() for d in release.available_weeks],
            "latest_week": release.latest_week.isoformat(), "metric": "TRx", "brand": "BXA Cardiovela"}


def _who(p: rbac.Principal, role: rbac.Role) -> dict:
    return {"user": rbac.pseudonym(p.sub), "role": role.name, "persona": role.persona}


def _record(run_id: str) -> dict:
    record = forecast_store.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No such Forecast run.")
    return record


def _visible(role: rbac.Role, record: dict) -> bool:
    """The CA sees every run. A reader without the run action sees only what has been submitted."""
    return "run" in role.actions or record["review_status"] != forecast_store.NOT_SUBMITTED


@router.post("/runs")
async def run(payload: ForecastRunRequest, response: Response, who=Forecast) -> dict:
    _no_store(response)
    p, role = who
    rbac.allow(role, "run")
    view = rbac.view_for(role, payload.view)
    pipeline = _pipeline()
    request = {"territory_id": payload.territory_id, "week_start": payload.week_start.isoformat(),
               "window_weeks": payload.window_weeks}
    body = {
        "request_id": f"fcst_{payload.territory_id}_{payload.week_start.isoformat()}_{payload.window_weeks}w",
        "source": "manual", "brand": "BXA Cardiovela", "metric": "TRx", **request,
    }
    try:
        result = await run_in_threadpool(pipeline.run_forecast_pipeline, body, engine_mode())
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        log.exception("forecast run failed")
        raise HTTPException(status_code=500, detail="The Forecast run failed.") from None
    record = forecast_store.save(request, result, by=rbac.pseudonym(p.sub))
    store.record_event("forecast_run", **_who(p, role), forecast_run_id=record["run_id"], view=view)
    return views.forecast_record(record, view)


@router.get("/runs")
def list_runs(response: Response, status: str | None = None, who=Forecast) -> dict:
    _no_store(response)
    _p, role = who
    rbac.allow(role, "read")
    rows = [views.forecast_summary(r) for r in forecast_store.all_runs() if _visible(role, r)]
    if status:
        rows = [r for r in rows if r["review_status"] == status]
    return {"lane": "forecast", "runs": rows}


@router.get("/runs/{run_id}")
def open_run(run_id: str, response: Response, view: str | None = None, who=Forecast) -> dict:
    _no_store(response)
    p, role = who
    rbac.allow(role, "read")
    record = _record(run_id)
    if not _visible(role, record):
        raise HTTPException(status_code=404, detail="No such Forecast run.")
    chosen = rbac.view_for(role, view)
    store.record_event("forecast_opened", **_who(p, role), forecast_run_id=run_id, view=chosen)
    return views.forecast_record(record, chosen)


@router.post("/runs/{run_id}/submit")
def submit(run_id: str, response: Response, who=Forecast) -> dict:
    """The CA sends a run to the Brand Manager for approval."""
    _no_store(response)
    p, role = who
    rbac.allow(role, "run")
    _record(run_id)
    try:
        record = forecast_store.submit(run_id, rbac.pseudonym(p.sub), role.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store.record_event("forecast_submitted", **_who(p, role), forecast_run_id=run_id)
    return views.forecast_record(record, rbac.view_for(role, None))


@router.post("/runs/{run_id}/review")
def review(run_id: str, decision: ForecastReview, response: Response, who=Forecast) -> dict:
    """The Brand Manager approves, rejects or returns a submitted run."""
    _no_store(response)
    p, role = who
    rbac.allow(role, "review")
    _record(run_id)
    if decision.decision in ("rejected", "returned") and not decision.note:
        word = "rejection" if decision.decision == "rejected" else "return"
        raise HTTPException(status_code=422, detail=f"A {word} needs a note.")
    try:
        record = forecast_store.review(run_id, decision.decision, decision.note, rbac.pseudonym(p.sub), role.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store.record_event("forecast_reviewed", **_who(p, role), forecast_run_id=run_id, decision=decision.decision, note=decision.note)
    return views.forecast_record(record, rbac.view_for(role, None))

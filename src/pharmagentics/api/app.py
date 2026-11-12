"""HTTP API for PharmAgentics Briefing, with role-based views (core-007).

Run locally with stand-in identities:
  PHARMAGENTICS_AUTH=dev uv run uvicorn pharmagentics.api.app:app --reload
With Keycloak: see deploy/README.md (docker compose).

Set PHARMAGENTICS_STATIC_DIR to a built frontend (vite build output) to serve the
UI from the same origin as the API; the container image does this (core-007 FR-017).

Every data route needs a signed-in user with a Briefing role. The server decides the view:
the Commercial Analyst (P1) gets the analyst view and may preview the leadership view; the
Brand Director (P3) gets only the leadership view, only of briefs the analyst approved.
"""
from __future__ import annotations

import hmac
import logging
import os
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import auth, jobs, rbac, service, store, views
from .schemas import (AgentJobRequest, BriefingQuery, InsightMark, ReleaseContext, ReviewRequest, WorkerPoll,
                      WorkerResult)

logger = logging.getLogger(__name__)

DEFAULT_ORIGINS = (
    "http://localhost:5500,http://127.0.0.1:5500,"
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:8443,http://127.0.0.1:8443"
)
origins = [s.strip() for s in os.environ.get(
    "PHARMAGENTICS_ALLOWED_ORIGINS", DEFAULT_ORIGINS
).split(",") if s.strip()]

_secret = os.environ.get("PHARMAGENTICS_SESSION_SECRET")
if not _secret:
    if os.environ.get("K_SERVICE"):
        raise RuntimeError("PHARMAGENTICS_SESSION_SECRET must be set on Cloud Run.")
    _secret = secrets.token_urlsafe(32)  # local only: sessions end when the process restarts

app = FastAPI(
    title="PharmAgentics — Briefing API",
    version="0.2.0",
    description="Briefing API over the governed scripted baseline, with role-based views (core-007).",
)
app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_credentials=False,
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
)
app.add_middleware(
    SessionMiddleware, secret_key=_secret, session_cookie="pa_session", max_age=8 * 3600,
    same_site="lax", https_only=bool(os.environ.get("K_SERVICE") or os.environ.get("PHARMAGENTICS_SECURE_COOKIES")),
)
app.include_router(auth.router)

Briefing = Depends(rbac.require_briefing)


def _no_store(response: Response) -> None:
    # Briefs are per-user, role-shaped responses: never cache them in a browser or proxy.
    response.headers["Cache-Control"] = "no-store"


def _who(p: rbac.Principal, role: rbac.Role) -> dict:
    return {"user": rbac.pseudonym(p.sub), "role": role.name, "persona": role.persona}


@app.get("/api/health")
def health() -> dict:
    return {"service": "pharmagentics_briefing_api", "database_ready": service.DB.is_file()}


@app.get("/api/me")
def me(response: Response, p: rbac.Principal = Depends(rbac.require_user)) -> dict:
    """Who is signed in and what they may open (FR-008). Only the user's own details."""
    _no_store(response)
    lanes = {r.lane: {"role": r.name, "persona": r.persona, "label": r.label, "views": list(r.views),
                      "actions": list(r.actions), "available": rbac.lane_available(r.lane)} for r in p.lanes}
    return {"name": p.name, "auth_mode": auth.mode(), "lanes": lanes}


@app.get("/api/briefing/context", response_model=ReleaseContext)
async def context(who=Briefing) -> ReleaseContext:
    try:
        return await run_in_threadpool(service.release_context)
    except service.MissingDatabase as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Cannot read synthetic data release")
        raise HTTPException(status_code=500, detail="Could not read data release") from exc


@app.post("/api/briefing/triage")
async def briefing_triage(payload: BriefingQuery, response: Response, who=Briefing) -> dict:
    """Stages 1 to 3 and the code triage plan the analyst reviews before investigation (brief-002 US8)."""
    p, role = who
    rbac.allow(role, "run")
    _no_store(response)
    started = time.perf_counter()
    try:
        plan = await run_in_threadpool(service.run_triage, payload)
    except service.MissingDatabase as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (service.OutsideRelease, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Triage failed")
        raise HTTPException(status_code=500, detail="Triage failed. Check server logs.") from exc
    store.record_event("triaged", **_who(p, role), plan_id=plan["plan_id"], cards=len(plan["stories"]),
                       latency_ms=round((time.perf_counter() - started) * 1000), state=plan["state"])
    return plan


@app.post("/api/briefing/query")
async def briefing_query(payload: BriefingQuery, response: Response, who=Briefing) -> dict:
    p, role = who
    rbac.allow(role, "run")
    _no_store(response)
    started = time.perf_counter()
    try:
        result = await run_in_threadpool(service.run_briefing, payload)
    except service.MissingDatabase as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except service.StalePlan as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (service.OutsideRelease, service.BadDecision) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Briefing request failed")
        raise HTTPException(status_code=500, detail="Briefing execution failed. Check server logs.") from exc
    latency_ms = round((time.perf_counter() - started) * 1000)
    record = store.save_brief(result.model_dump(mode="json"), by=rbac.pseudonym(p.sub))
    store.record_event("requested", **_who(p, role), brief_id=record["brief_id"], latency_ms=latency_ms,
                       engine=result.engine, system=result.system, data_version=result.data_version,
                       week_start=str(result.week_start), territory_id=result.territory_id,
                       triage_default=(result.triage or {}).get("default"))
    return views.analyst(record)


@app.get("/api/briefing/published")
async def published(response: Response, who=Briefing) -> list[dict]:
    """Analyst-approved briefs on the current data version (FR-009), as leadership summaries' headers."""
    _p, role = who
    rbac.allow(role, "read")
    _no_store(response)
    version = await run_in_threadpool(service.current_data_version)
    return [{k: views.leadership(r)[k] for k in ("brief_id", "week_start", "territory_id", "engine", "reviewed_at", "abstained")}
            for r in store.approved(version)]


@app.get("/api/briefing/{brief_id}")
async def open_brief(brief_id: str, response: Response, view: str | None = Query(default=None), who=Briefing) -> dict:
    p, role = who
    rbac.allow(role, "read")
    _no_store(response)
    chosen = rbac.view_for(role, view)
    record = store.get_brief(brief_id)
    # A leader sees only approved briefs; anything else is "not found", so its existence is not disclosed.
    if record is None or ("review" not in role.actions and record["review_status"] != "approved"):
        raise HTTPException(status_code=404, detail="No such briefing.")
    store.record_event("opened", **_who(p, role), brief_id=brief_id, view=chosen)
    return views.analyst(record) if chosen == rbac.ANALYST else views.leadership(record)


@app.post("/api/briefing/{brief_id}/review")
async def review(brief_id: str, decision: ReviewRequest, response: Response, who=Briefing) -> dict:
    p, role = who
    rbac.allow(role, "review")
    _no_store(response)
    if decision.decision == "rejected" and not decision.reason:
        raise HTTPException(status_code=422, detail="A rejection needs a reason.")
    try:
        record = store.set_review(brief_id, decision.decision, decision.reason, by=rbac.pseudonym(p.sub))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="No such briefing.") from exc
    store.record_event("reviewed", **_who(p, role), brief_id=brief_id, decision=decision.decision, reason=decision.reason)
    return views.analyst(record)


@app.post("/api/uat/insight", status_code=204)
async def insight(mark: InsightMark, who=Briefing) -> Response:
    p, role = who
    rbac.view_for(role, mark.view)
    store.record_event("insight", **_who(p, role), brief_id=mark.brief_id, view=mark.view)
    return Response(status_code=204)


# --- Agent jobs, run by the owner's local worker (core-007 FR-028; brief-002 Phase B) -----------------

def _job_view(job: dict) -> dict:
    out = {k: job[k] for k in ("id", "kind", "status", "created_at", "started_at", "finished_at", "error")}
    if job["status"] == "done" and job["kind"] == "triage":
        out["result"] = job["result"]
    elif job["status"] == "done" and job["kind"] == "brief":
        record = store.get_brief(job["result"]["brief_id"])
        out["result"] = views.analyst(record) if record else None
    return out


@app.get("/api/agent/status")
def agent_status(response: Response, who=Briefing) -> dict:
    _no_store(response)
    return {**jobs.status(), "configured": bool(os.environ.get("PHARMAGENTICS_WORKER_TOKEN"))}


@app.post("/api/agent/jobs")
async def agent_submit(req: AgentJobRequest, response: Response, who=Briefing) -> dict:
    p, role = who
    rbac.allow(role, "run")
    _no_store(response)
    try:
        await run_in_threadpool(service._check_scope, req.query)
    except service.OutsideRelease as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = {"query": req.query.model_dump(mode="json"), "question": service.normalize_question(req.query)}
    if req.kind == "brief":
        plan_job = jobs.get(req.triage_job or "")
        if plan_job is None or plan_job["kind"] != "triage" or plan_job["status"] != "done":
            raise HTTPException(status_code=400, detail="A brief job needs a finished triage job.")
        plan = plan_job["result"]
        if req.decision is None or req.decision.plan_id != plan["plan_id"]:
            raise HTTPException(status_code=409, detail="The decision is not for that triage plan; review it again.")
        allowed = {c["id"] for c in plan["stories"] if c["proposed"] == "investigate"}
        if (bad := [s for s in req.decision.stories if s not in allowed]):
            raise HTTPException(status_code=400, detail=f"Not a story this plan proposes: {', '.join(bad)}")
        payload.update(plan=plan, decision=req.decision.model_dump(), triage_job=plan_job["id"])
    job = jobs.submit(req.kind, payload, by=rbac.pseudonym(p.sub))
    store.record_event("agent_job", **_who(p, role), job_id=job["id"], job_kind=req.kind)
    return _job_view(job)


@app.get("/api/agent/jobs/{job_id}")
def agent_job(job_id: str, response: Response, who=Briefing) -> dict:
    _p, role = who
    rbac.allow(role, "run")
    _no_store(response)
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such job.")
    return _job_view(job)


def _worker(authorization: str | None = Header(default=None)) -> None:
    token = os.environ.get("PHARMAGENTICS_WORKER_TOKEN")
    if not token:
        raise HTTPException(status_code=503, detail="Agent jobs are not configured on this server.")
    given = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(given.encode(), token.encode()):
        raise HTTPException(status_code=401, detail="Worker token required.")


@app.post("/api/worker/next", dependencies=[Depends(_worker)])
def worker_next(poll: WorkerPoll) -> Response:
    job = jobs.next_job(poll.model)
    if job is None:
        return Response(status_code=204)
    return JSONResponse({"id": job["id"], "kind": job["kind"], "payload": job["payload"]})


@app.post("/api/worker/jobs/{job_id}", dependencies=[Depends(_worker)])
async def worker_result(job_id: str, posted: WorkerResult) -> dict:
    job = jobs.get(job_id)
    if job is None or job["status"] != "running":
        raise HTTPException(status_code=404, detail="No running job with that ID.")
    if not posted.ok:
        jobs.complete(job_id, False, None, posted.error)
        return {"status": "failed"}
    query = BriefingQuery.model_validate(job["payload"]["query"])
    try:
        if job["kind"] == "triage":
            plan = posted.result or {}
            if plan.get("state") != "OUT_OF_SCOPE":
                service._traceable(plan.get("claims", []), plan.get("evidence", []))
            plan.update(brand_id=query.brand_id, territory_id=query.territory_id, week_start=query.week_start.isoformat())
            jobs.complete(job_id, True, plan, None)
        else:
            result = await run_in_threadpool(service.accept_agent_brief, query, posted.result or {})
            record = store.save_brief(result.model_dump(mode="json"), by=job["by"])
            jobs.complete(job_id, True, {"brief_id": record["brief_id"]}, None)
            store.record_event("requested", user=job["by"], role="briefing-analyst", persona="P1",
                               brief_id=record["brief_id"], engine="agent", system=result.system,
                               data_version=result.data_version, week_start=str(result.week_start),
                               territory_id=result.territory_id, triage_default=(result.triage or {}).get("default"),
                               agent_seconds=((posted.result or {}).get("envelope") or {}).get("trajectory", {}).get("seconds"))
    except Exception as exc:  # noqa: BLE001 - an untraceable or malformed result fails the job, visibly
        logger.warning("Agent result refused: %s", exc)
        jobs.complete(job_id, False, None, f"The agent's result did not pass the traceability check: {exc}")
        return {"status": "failed"}
    return {"status": "done"}


# Same-origin UI (core-007 FR-017). Mounted last so every /api and /auth route above wins.
_static = os.environ.get("PHARMAGENTICS_STATIC_DIR")
if _static and Path(_static).is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="ui")

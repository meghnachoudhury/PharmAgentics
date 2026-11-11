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

import logging
import os
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import auth, rbac, service, store, views
from .schemas import BriefingQuery, InsightMark, ReleaseContext, ReviewRequest

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
    except service.OutsideRelease as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Briefing request failed")
        raise HTTPException(status_code=500, detail="Briefing execution failed. Check server logs.") from exc
    latency_ms = round((time.perf_counter() - started) * 1000)
    record = store.save_brief(result.model_dump(mode="json"), by=rbac.pseudonym(p.sub))
    store.record_event("requested", **_who(p, role), brief_id=record["brief_id"], latency_ms=latency_ms,
                       engine=result.engine, system=result.system, data_version=result.data_version,
                       week_start=str(result.week_start), territory_id=result.territory_id)
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


# Same-origin UI (core-007 FR-017). Mounted last so every /api and /auth route above wins.
_static = os.environ.get("PHARMAGENTICS_STATIC_DIR")
if _static and Path(_static).is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="ui")

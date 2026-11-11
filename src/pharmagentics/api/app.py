"""Local/development HTTP API for PharmAgentics Briefing.

Run:
  uv run uvicorn pharmagentics.api.app:app --reload

Set PHARMAGENTICS_STATIC_DIR to a built frontend (vite build output) to serve the
UI from the same origin as the API; the container image does this (core-007).

CORS is a *browser policy*, not authentication. This demo is not a public,
production-ready service. Keep it local or on a restricted development tunnel.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import service
from .schemas import BriefingQuery, BriefingResult, ReleaseContext

logger = logging.getLogger(__name__)

DEFAULT_ORIGINS = (
    "http://localhost:5500,http://127.0.0.1:5500,"
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:8443,http://127.0.0.1:8443"
)
origins = [s.strip() for s in os.environ.get(
    "PHARMAGENTICS_ALLOWED_ORIGINS", DEFAULT_ORIGINS
).split(",") if s.strip()]

app = FastAPI(
    title="PharmAgentics — Briefing Integration API",
    version="0.1.0",
    description="Development-only API over the governed Briefing scripted baseline.",
)
app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_credentials=False,
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
)


@app.get("/api/health")
def health() -> dict:
    return {"service": "pharmagentics_briefing_api", "database_ready": service.DB.is_file()}


@app.get("/api/briefing/context", response_model=ReleaseContext)
async def context() -> ReleaseContext:
    try:
        return await run_in_threadpool(service.release_context)
    except service.MissingDatabase as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Cannot read synthetic data release")
        raise HTTPException(status_code=500, detail="Could not read data release") from exc


@app.post("/api/briefing/query", response_model=BriefingResult)
async def briefing_query(payload: BriefingQuery, response: Response) -> BriefingResult:
    # Prevent intermediaries from caching unpublished synthetic draft briefings.
    response.headers["Cache-Control"] = "no-store"
    try:
        return await run_in_threadpool(service.run_briefing, payload)
    except service.MissingDatabase as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except service.OutsideRelease as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Briefing request failed")
        raise HTTPException(status_code=500, detail="Briefing execution failed. Check server logs.") from exc


# Same-origin UI (core-007 FR-017). Mounted last so every /api route above wins.
_static = os.environ.get("PHARMAGENTICS_STATIC_DIR")
if _static and Path(_static).is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="ui")

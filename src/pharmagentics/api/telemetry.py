"""Evaluation telemetry for the hosted app: the golden-set scores of each system, read from telemetry.json.

The cloud image holds no MLflow store and no eval/ code, so `eval/harness/telemetry_export.py` writes the snapshot
locally before a deploy. Run-level scores only. A user sees the runs of their own lanes plus the cross-lane runs.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response

from . import rbac

FILE = Path(__file__).with_name("telemetry.json")
router = APIRouter(prefix="/api", tags=["telemetry"])
EMPTY = {"exported": None, "note": "No telemetry exported yet.", "latest": [], "runs": []}


def snapshot() -> dict:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(EMPTY)


def for_lanes(snap: dict, lanes: set[str]) -> dict:
    keep = lambda r: r.get("lane") in lanes or r.get("lane") == "all"  # noqa: E731
    return {**snap, "latest": [r for r in snap.get("latest", []) if keep(r)],
            "runs": [r for r in snap.get("runs", []) if keep(r)]}


@router.get("/telemetry")
def telemetry(response: Response, p: rbac.Principal = Depends(rbac.require_user)) -> dict:
    if not p.lanes:
        raise HTTPException(status_code=403, detail="Your account has no PharmAgentics role.")
    response.headers["Cache-Control"] = "no-store"
    return for_lanes(snapshot(), {r.lane for r in p.lanes})

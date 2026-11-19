"""Data classification per tab and view (core-009), version 1: labels only.

The levels, the level of each tab or view, and each role's clearance live in classification.json, so they change
without code. Nothing here refuses access: core-007 (roles.json, rbac.py) still decides what a role can open.
Enforcement is core-009 User Story 2, for Meghna: `allowed()` is the check it would use.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from . import rbac

FILE = Path(__file__).with_name("classification.json")
router = APIRouter(prefix="/api", tags=["classification"])


def check(c: dict) -> None:
    """A malformed edit must fail the tests, not a participant."""
    ids = [lv["id"] for lv in c["levels"]]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError("classification.json: level ids must be unique and non-empty")
    for key, level in {**c["tabs"], **c["clearance"]}.items():
        if level not in ids:
            raise ValueError(f"classification.json: {key} has unknown level {level!r}")
    missing = sorted(set(rbac.roles()) - set(c["clearance"]))
    if missing:
        raise ValueError(f"classification.json: no clearance for role(s) {', '.join(missing)}")


@lru_cache(maxsize=1)
def config() -> dict:
    c = json.loads(FILE.read_text(encoding="utf-8"))
    check(c)
    return c


def rank(level: str) -> int:
    return [lv["id"] for lv in config()["levels"]].index(level)


def allowed(role: rbac.Role, tab: str) -> bool:
    """Whether a role's clearance reaches a tab's level. Not called anywhere yet (core-009 FR-005)."""
    c = config()
    return rank(c["clearance"][role.name]) >= rank(c["tabs"][tab])


@router.get("/classification")
def classification(request: Request, response: Response, p: rbac.Principal = Depends(rbac.require_user)) -> dict:
    if not p.lanes:
        raise HTTPException(status_code=403, detail="Your account has no PharmAgentics role.")
    response.headers["Cache-Control"] = "no-store"
    c = config()
    return {"version": c["version"], "levels": c["levels"], "tabs": c["tabs"],
            "clearance": {r.lane: c["clearance"][r.name] for r in p.lanes}}

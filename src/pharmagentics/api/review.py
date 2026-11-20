"""The Feedback review list (core-008 FR-021; Session 2026-11-20).

`python -m eval improve` writes proposals (lessons and draft cases) to `review/proposals/<id>.json` in the state
store. The tester admin, and nobody else, reads them here and approves or rejects each one; any other login gets
404, so the list's existence is not disclosed. No new role or persona: the project keeps four Briefing personas,
three Forecast personas and one tester admin. Decisions are not UAT events. Approval only queues a proposal:
`python -m eval promote` writes it, and a pull request merges it.
"""
from __future__ import annotations

import json
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from . import rbac, store

router = APIRouter(prefix="/api/review", tags=["review"])
PROPOSALS = "review/proposals/"
PROPOSAL_ID = re.compile(r"^p-[0-9a-f]{12}$")


class Decision(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=500)


def tester(p: rbac.Principal = Depends(rbac.require_user)) -> rbac.Principal:
    if not p.is_tester:
        raise HTTPException(status_code=404, detail="Not found.")
    return p


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/proposals")
def proposals(response: Response, p: rbac.Principal = Depends(tester)) -> list[dict]:
    _no_store(response)
    docs = [json.loads(store.backend().read(k) or "{}") for k in store.backend().keys(PROPOSALS)]
    order = {"proposed": 0, "approved": 1, "rejected": 2, "promoted": 3}
    return sorted((d for d in docs if d), key=lambda d: (order.get(d.get("status"), 9), not d.get("confident"),
                                                         d.get("created_at") or ""))


@router.post("/proposals/{proposal_id}")
def decide(proposal_id: str, body: Decision, response: Response, p: rbac.Principal = Depends(tester)) -> dict:
    _no_store(response)
    if not PROPOSAL_ID.match(proposal_id):
        raise HTTPException(status_code=404, detail="No such proposal.")
    key = f"{PROPOSALS}{proposal_id}.json"
    doc = json.loads(store.backend().read(key) or "null")
    if doc is None:
        raise HTTPException(status_code=404, detail="No such proposal.")
    if doc.get("status") not in ("proposed", "approved", "rejected"):
        raise HTTPException(status_code=409, detail=f"This proposal is already {doc.get('status')}.")
    doc.update(status="approved" if body.decision == "approve" else "rejected", decided_by=p.name or p.sub,
               decided_at=store.now(), note=body.note)
    store.backend().write(key, json.dumps(doc, indent=1, default=str))
    return doc

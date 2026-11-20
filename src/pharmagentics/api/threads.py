"""Threads of follow-ups on a brief (brief-006 slice 3; ADR 0002).

One thread per analyst per brief, kept in the state store at `threads/<brief_id>/<owner>.json`, where `<owner>` is
a short hash of the analyst's subject, so no name sits in a key. A thread is never part of the approved brief:
leaders cannot reach any of these routes (404, so a thread's existence is not disclosed). Unsaved threads untouched
for 30 days are deleted when threads are opened (and once per process). Saved threads are kept, can be opened
read-only by any Briefing analyst through their share path, and feed the feedback review list (core-008).
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timedelta, timezone

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from pharmagentics.tools import followup

from . import agent_host, rbac, store

router = APIRouter(prefix="/api/briefing/{brief_id}/thread", tags=["threads"])
MAX_TURNS = 20  # FR-008
KEEP_DAYS = 30
_purged = False


class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    section: str | None = Field(default=None, pattern=r"^\d(\.\d+)?$")
    engine: Literal["scripted", "agent"] = "scripted"  # agent: Claude Haiku in the app (slice 4, core-007 FR-032)


def _agent_answer(result: dict, question: str, section: str | None) -> dict:
    """One Haiku turn (brief-006 slice 4); only when the app runs the agent itself."""
    spec = agent_host.model()
    if not spec:
        raise HTTPException(status_code=409, detail="The agent is not available here; ask the scripted engine.")
    if str(agent_host.AGENTS_DIR) not in sys.path:
        sys.path.insert(0, str(agent_host.AGENTS_DIR))
    from briefing_agent import followup as agent_followup

    return agent_followup.answer(result, question, section, spec)


def owner_of(p: rbac.Principal) -> str:
    return hashlib.sha256(f"thread|{p.sub}".encode()).hexdigest()[:12]


def _key(brief_id: str, owner: str) -> str:
    if not brief_id.startswith("b-") or not brief_id[2:].isalnum() or not owner.isalnum():
        raise HTTPException(status_code=404, detail="No such thread.")
    return f"threads/{brief_id}/{owner}.json"


def read(brief_id: str, owner: str) -> dict | None:
    text = store.backend().read(_key(brief_id, owner))
    return json.loads(text) if text else None


def write(thread: dict) -> None:
    thread["updated_at"] = store.now()
    store.backend().write(_key(thread["brief_id"], thread["owner"]), store._dump(thread))


def purge(now: datetime | None = None) -> int:
    """Delete unsaved threads untouched for 30 days (brief-006 FR-008). Returns how many went."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=KEEP_DAYS)
    gone = 0
    for key in store.backend().keys("threads/"):
        thread = json.loads(store.backend().read(key) or "{}")
        stamp = thread.get("updated_at") or thread.get("created_at")
        if thread and not thread.get("saved") and stamp and datetime.fromisoformat(stamp) < cutoff:
            store.backend().delete(key)
            gone += 1
    return gone


def _purge_once() -> None:
    global _purged
    if not _purged:
        _purged = True
        purge()


def analyst(brief_id: str, who=Depends(rbac.require_briefing)) -> tuple[rbac.Principal, dict]:
    """Only roles that review briefs (analysts) reach threads; anyone else, and any unknown brief, gets 404."""
    p, role = who
    record = store.get_brief(brief_id)
    if "review" not in role.actions or record is None:
        raise HTTPException(status_code=404, detail="No such thread.")
    _purge_once()
    return p, record


def _public(thread: dict | None, record: dict, owner: str, mine: bool) -> dict:
    thread = thread or {"brief_id": record["brief_id"], "owner": owner, "saved": False, "turns": []}
    return {"brief_id": record["brief_id"], "owner": thread["owner"], "mine": mine, "saved": thread.get("saved", False),
            "shared_from": thread.get("shared_from"), "turns": thread.get("turns", []), "max_turns": MAX_TURNS,
            "share_path": f"/api/briefing/{record['brief_id']}/thread/shared/{thread['owner']}" if thread.get("saved") else None,
            "suggestions": followup.suggestions(record["result"].get("sections") or [])}


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("")
def my_thread(brief_id: str, response: Response, who=Depends(analyst)) -> dict:
    p, record = who
    _no_store(response)
    owner = owner_of(p)
    return _public(read(brief_id, owner), record, owner, mine=True)


@router.post("/ask")
def ask(brief_id: str, body: Ask, response: Response, who=Depends(analyst)) -> dict:
    p, record = who
    _no_store(response)
    owner = owner_of(p)
    thread = read(brief_id, owner) or {"brief_id": brief_id, "owner": owner, "saved": False, "created_at": store.now(), "turns": []}
    if len(thread["turns"]) >= MAX_TURNS:
        raise HTTPException(status_code=409, detail=f"This thread is full ({MAX_TURNS} follow-ups). Start a new thread.")
    started = time.perf_counter()
    if body.engine == "agent":
        turn = _agent_answer(record["result"], body.question, body.section)
        if turn.get("error") == "timeout":  # FR-010: shown and logged, no answer text kept
            store.record_event("follow_up", **p.tag(), brief_id=brief_id, rule="timeout", engine="agent",
                               seconds=turn["seconds"])
            raise HTTPException(status_code=504, detail=turn["answer"])
    else:
        turn = followup.answer(record["result"], body.question, body.section)
    turn.update(n=len(thread["turns"]) + 1, question=body.question, section=body.section, at=store.now(),
                seconds=round(time.perf_counter() - started, 3))
    thread["turns"].append(turn)
    write(thread)
    store.record_event("follow_up", **p.tag(), brief_id=brief_id, rule=turn["kind"], engine=turn["engine"],
                       seconds=turn["seconds"])
    return _public(thread, record, owner, mine=True)


@router.post("/save")
def save(brief_id: str, response: Response, who=Depends(analyst)) -> dict:
    p, record = who
    _no_store(response)
    owner = owner_of(p)
    thread = read(brief_id, owner)
    if not thread or not thread["turns"]:
        raise HTTPException(status_code=409, detail="Ask a follow-up before saving the thread.")
    thread["saved"] = True
    write(thread)
    return _public(thread, record, owner, mine=True)


@router.get("/shared/{owner}")
def shared(brief_id: str, owner: str, response: Response, who=Depends(analyst)) -> dict:
    p, record = who
    _no_store(response)
    thread = read(brief_id, owner)
    if not thread or not thread.get("saved"):  # only saved threads are shared
        raise HTTPException(status_code=404, detail="No such thread.")
    return _public(thread, record, owner, mine=owner == owner_of(p))


@router.post("/continue/{owner}")
def continue_thread(brief_id: str, owner: str, response: Response, who=Depends(analyst)) -> dict:
    p, record = who
    _no_store(response)
    source = read(brief_id, owner)
    if not source or not source.get("saved"):
        raise HTTPException(status_code=404, detail="No such thread.")
    mine = owner_of(p)
    thread = {"brief_id": brief_id, "owner": mine, "saved": False, "created_at": store.now(),
              "shared_from": owner, "turns": [dict(t) for t in source["turns"]][:MAX_TURNS]}
    write(thread)
    return _public(thread, record, mine, mine=True)


def turn_shown(p: rbac.Principal, brief_id: str, n: int) -> str | None:
    """The answer text of turn `n` in this person's own thread (for a vote on a follow-up, core-008)."""
    thread = read(brief_id, owner_of(p))
    turns = (thread or {}).get("turns", [])
    return turns[n - 1]["answer"] if 0 < n <= len(turns) else None

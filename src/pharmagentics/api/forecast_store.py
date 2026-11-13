"""Forecast runs and their review state as small JSON documents (forecast_runs/<id>.json), on the same two
backends as the Briefing store (a local folder, or the Cloud Storage bucket on Cloud Run).

A run starts as ``not_submitted``. The Commercial Analyst submits it (``pending_review``); the Brand
Manager approves, rejects or returns it. Nothing is ever approved by the system. Each step is kept in
``history`` with a pseudonym, never a name, so a later evaluation log can read it.
"""
from __future__ import annotations

import hashlib
import json
import re

from .store import _dump, backend, now

NOT_SUBMITTED, PENDING, APPROVED, REJECTED, RETURNED = "not_submitted", "pending_review", "approved", "rejected", "returned"
ID = re.compile(r"^f-[0-9a-f]{12}$")


def run_id(request: dict, result: dict) -> str:
    """The same request on the same data release and engine gives the same id, so a rerun keeps its review."""
    key = "|".join(str(x) for x in (request["territory_id"], request["week_start"], request["window_weeks"],
                                    result.get("dataset_release"), result["report"].get("investigator_mode")))
    return "f-" + hashlib.sha256(key.encode()).hexdigest()[:12]


def _same_answer(a: dict, b: dict) -> bool:
    def key(result: dict) -> tuple:
        r = result["report"]
        return (r["variance_trx"], r["abstained"], (r.get("verification") or {}).get("verdict"),
                tuple((d["driver"], round(d["impact_trx"], 3)) for d in r["drivers"]))
    return key(a) == key(b)


def _key(rid: str) -> str:
    if not ID.match(rid):
        raise KeyError(rid)
    return f"forecast_runs/{rid}.json"


def get(rid: str) -> dict | None:
    try:
        text = backend().read(_key(rid))
    except KeyError:
        return None
    return json.loads(text) if text else None


def _put(record: dict) -> dict:
    backend().write(_key(record["run_id"]), _dump(record))
    return record


PENDING_WRITER_SECONDS = 300  # a writer still "pending" after this long was lost (a restart); try again


def pending_writer() -> dict:
    return {"narrative": None, "report_model": "none", "writer_status": "pending", "writer_attempts": [],
            "writer_started_at": now()}


def _stale(started_at: str | None) -> bool:
    if not started_at:
        return True
    from datetime import datetime, timezone
    return (datetime.now(timezone.utc) - datetime.fromisoformat(started_at)).total_seconds() > PENDING_WRITER_SECONDS


def needs_writer(request: dict, result: dict) -> bool:
    """Whether the report writer should run for this answer. A rerun of an answer that already has prose, or that
    was correctly left without (an attribution paused), spends nothing; one that fell back is tried again, and
    one still being written is left alone."""
    existing = get(run_id(request, result))
    if existing is None or not _same_answer(existing["result"], result):
        return True
    status = existing.get("writer_status")
    if status == "pending":
        return _stale(existing.get("writer_started_at"))
    outcomes = [a.get("outcome") for a in existing.get("writer_attempts") or []]
    return status in (None, "fallback_stub") or outcomes == ["disabled"]


def set_writer(rid: str, writer: dict) -> None:
    """Store the finished prose on a run. Re-reads the run first, so a review made meanwhile is kept."""
    record = get(rid)
    if record is None:
        return
    record.update(narrative=writer["narrative"], report_model=writer["report_model"],
                  writer_status=writer["writer_status"], writer_attempts=writer["writer_attempts"])
    record.pop("writer_started_at", None)
    _put(record)


def save(request: dict, result: dict, by: str, writer: dict | None = None) -> dict:
    rid = run_id(request, result)
    existing = get(rid)
    if existing and _same_answer(existing["result"], result):
        if writer is not None:  # the answer is unchanged; keep its review state and refresh the prose
            existing.update(writer)
            return _put(existing)
        return existing
    writer = writer or {"narrative": None, "report_model": "none", "writer_status": "skipped", "writer_attempts": []}
    record = {"run_id": rid, "created_at": now(), "created_by": by, "request": request, "result": result,
              "review_status": NOT_SUBMITTED, "submitted_by": None, "submitted_at": None,
              "reviewed_by": None, "reviewed_at": None, "review_decision": None, "review_note": None, "history": [],
              **writer}
    return _put(record)


def _log(record: dict, action: str, by: str, role: str, note: str | None) -> None:
    record["history"].append({"at": now(), "by": by, "role": role, "action": action, "note": note})


def submit(rid: str, by: str, role: str) -> dict:
    record = get(rid)
    if record is None:
        raise KeyError(rid)
    if record["review_status"] not in (NOT_SUBMITTED, RETURNED):
        raise ValueError(f"A run that is {record['review_status']} cannot be submitted.")
    record.update(review_status=PENDING, submitted_by=by, submitted_at=now(), reviewed_by=None, reviewed_at=None,
                  review_decision=None, review_note=None)
    _log(record, "submitted", by, role, None)
    return _put(record)


def review(rid: str, decision: str, note: str | None, by: str, role: str) -> dict:
    record = get(rid)
    if record is None:
        raise KeyError(rid)
    if record["review_status"] != PENDING:
        raise ValueError(f"Only a submitted run can be reviewed; this one is {record['review_status']}.")
    record.update(review_status=decision, reviewed_by=by, reviewed_at=now(), review_decision=decision, review_note=note)
    _log(record, decision, by, role, note)
    return _put(record)


def all_runs() -> list[dict]:
    store = backend()
    out = []
    for key in store.keys("forecast_runs/"):
        text = store.read(key)
        if text:
            out.append(json.loads(text))
    return sorted(out, key=lambda r: r["created_at"], reverse=True)

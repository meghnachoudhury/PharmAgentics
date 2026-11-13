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


def save(request: dict, result: dict, by: str) -> dict:
    rid = run_id(request, result)
    existing = get(rid)
    if existing and _same_answer(existing["result"], result):
        return existing
    record = {"run_id": rid, "created_at": now(), "created_by": by, "request": request, "result": result,
              "review_status": NOT_SUBMITTED, "submitted_by": None, "submitted_at": None,
              "reviewed_by": None, "reviewed_at": None, "review_decision": None, "review_note": None, "history": []}
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

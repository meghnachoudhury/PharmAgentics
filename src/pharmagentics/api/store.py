"""Briefs, approvals and UAT events as small JSON files (core-007 FR-010, FR-025).

PHARMAGENTICS_STATE_DIR points at a local folder in development and at a Cloud Storage
bucket mounted into the container on Cloud Run, so approvals survive restarts with no
database. One file per brief and one file per event: no appends, which Cloud Storage
mounts handle poorly.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[3]


def state_dir() -> Path:
    return Path(os.environ.get("PHARMAGENTICS_STATE_DIR", ROOT / "local" / "state"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, path)


def brief_id(result: dict) -> str:
    """Same engine, data version, week, territory and question give the same brief, so a rerun
    keeps its review state instead of creating a duplicate."""
    key = "|".join(str(result.get(k)) for k in ("system", "data_version", "week_start", "territory_id", "question"))
    return "b-" + hashlib.sha256(key.encode()).hexdigest()[:12]


def _brief_path(bid: str) -> Path:
    if not bid.startswith("b-") or not bid[2:].isalnum():
        raise KeyError(bid)
    return state_dir() / "briefs" / f"{bid}.json"


def save_brief(result: dict, by: str) -> dict:
    bid = brief_id(result)
    existing = get_brief(bid)
    if existing and existing["result"].get("answer") == result.get("answer"):
        return existing
    record = {"brief_id": bid, "created_at": now(), "created_by": by, "result": result,
              "review_status": "pending", "reviewed_by": None, "reviewed_at": None, "review_reason": None}
    _write(_brief_path(bid), record)
    return record


def get_brief(bid: str) -> dict | None:
    try:
        path = _brief_path(bid)
    except KeyError:
        return None
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def set_review(bid: str, decision: str, reason: str | None, by: str) -> dict:
    record = get_brief(bid)
    if record is None:
        raise KeyError(bid)
    record.update(review_status=decision, reviewed_by=by, reviewed_at=now(), review_reason=reason)
    _write(_brief_path(bid), record)
    return record


def approved(data_version: str | None) -> list[dict]:
    folder = state_dir() / "briefs"
    out = []
    for path in sorted(folder.glob("b-*.json")) if folder.is_dir() else []:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["review_status"] == "approved" and record["result"].get("data_version") == data_version:
            out.append(record)
    return sorted(out, key=lambda r: (r["result"]["week_start"], r["result"]["territory_id"]), reverse=True)


def record_event(kind: str, **fields) -> None:
    """One UAT event. Never raises: a failed write is logged and the briefing is still served (FR-025)."""
    event = {"kind": kind, "ts": now(), "app_version": os.environ.get("PHARMAGENTICS_VERSION", "dev"), **fields}
    try:
        _write(state_dir() / "events" / f"{event['ts'][:10]}" / f"{event['ts'].replace(':', '')}-{uuid.uuid4().hex[:8]}.json", event)
    except OSError:
        logger.exception("UAT event not recorded: %s", kind)

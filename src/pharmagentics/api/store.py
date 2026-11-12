"""Briefs, approvals and UAT events as small JSON documents (core-007 FR-010, FR-025).

Two backends, same layout (briefs/<id>.json, events/<date>/<ts>-<id>.json):
- PHARMAGENTICS_STATE_BUCKET set: a Cloud Storage bucket (Cloud Run). Approvals survive
  restarts and redeploys with no database.
- otherwise a local folder, PHARMAGENTICS_STATE_DIR (default local/state; /state in the image).
One document per brief and per event, never appended to.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[3]


class LocalBackend:
    def __init__(self, root: Path):
        self.root = root

    def read(self, key: str) -> str | None:
        path = self.root / key
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def write(self, key: str, text: str) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{uuid.uuid4().hex[:6]}.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)

    def keys(self, prefix: str) -> list[str]:
        folder = self.root / prefix
        return sorted(p.relative_to(self.root).as_posix() for p in folder.rglob("*.json")) if folder.is_dir() else []


class BucketBackend:
    def __init__(self, bucket: str):
        from google.cloud import storage  # only needed on Cloud Run

        self.bucket = storage.Client().bucket(bucket)

    def read(self, key: str) -> str | None:
        blob = self.bucket.blob(key)
        return blob.download_as_text() if blob.exists() else None

    def write(self, key: str, text: str) -> None:
        self.bucket.blob(key).upload_from_string(text, content_type="application/json")

    def keys(self, prefix: str) -> list[str]:
        return sorted(b.name for b in self.bucket.list_blobs(prefix=prefix) if b.name.endswith(".json"))


@lru_cache(maxsize=4)
def _backend(bucket: str | None, folder: str):
    return BucketBackend(bucket) if bucket else LocalBackend(Path(folder))


def backend():
    return _backend(os.environ.get("PHARMAGENTICS_STATE_BUCKET") or None,
                    os.environ.get("PHARMAGENTICS_STATE_DIR", str(ROOT / "local" / "state")))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _dump(data: dict) -> str:
    return json.dumps(data, indent=1, default=str)


def brief_id(result: dict) -> str:
    """Same engine, data version, week, territory and question give the same brief, so a rerun
    keeps its review state instead of creating a duplicate."""
    key = "|".join(str(result.get(k)) for k in ("system", "data_version", "week_start", "territory_id", "question"))
    triage = result.get("triage") or {}
    if triage and not triage.get("default", True):  # P1 changed the plan: a different brief (brief-002 R6)
        key += "|triage:" + ",".join(triage.get("order", []))
    return "b-" + hashlib.sha256(key.encode()).hexdigest()[:12]


def _brief_key(bid: str) -> str:
    if not bid.startswith("b-") or not bid[2:].isalnum():
        raise KeyError(bid)
    return f"briefs/{bid}.json"


def save_brief(result: dict, by: str) -> dict:
    bid = brief_id(result)
    existing = get_brief(bid)
    if existing and existing["result"].get("answer") == result.get("answer"):
        missing = {k: result[k] for k in ("triage", "flow") if result.get(k) and not existing["result"].get(k)}
        if missing:  # a brief stored before brief-002 Phase A gains its flow; the review state is kept
            existing["result"].update(missing)
            backend().write(_brief_key(bid), _dump(existing))
        return existing
    record = {"brief_id": bid, "created_at": now(), "created_by": by, "result": result,
              "review_status": "pending", "reviewed_by": None, "reviewed_at": None, "review_reason": None}
    backend().write(_brief_key(bid), _dump(record))
    return record


def get_brief(bid: str) -> dict | None:
    try:
        key = _brief_key(bid)
    except KeyError:
        return None
    text = backend().read(key)
    return json.loads(text) if text else None


def set_review(bid: str, decision: str, reason: str | None, by: str) -> dict:
    record = get_brief(bid)
    if record is None:
        raise KeyError(bid)
    record.update(review_status=decision, reviewed_by=by, reviewed_at=now(), review_reason=reason)
    backend().write(_brief_key(bid), _dump(record))
    return record


def approved(data_version: str | None) -> list[dict]:
    store = backend()
    out = []
    for key in store.keys("briefs/"):
        text = store.read(key)
        record = json.loads(text) if text else None
        if record and record["review_status"] == "approved" and record["result"].get("data_version") == data_version:
            out.append(record)
    return sorted(out, key=lambda r: (r["result"]["week_start"], r["result"]["territory_id"]), reverse=True)


def record_event(kind: str, **fields) -> None:
    """One UAT event. Never raises: a failed write is logged and the briefing is still served (FR-025)."""
    event = {"kind": kind, "ts": now(), "app_version": os.environ.get("PHARMAGENTICS_VERSION", "dev"), **fields}
    key = f"events/{event['ts'][:10]}/{event['ts'].replace(':', '')}-{uuid.uuid4().hex[:8]}.json"
    try:
        backend().write(key, _dump(event))
    except Exception:  # noqa: BLE001 - any storage failure must not stop the briefing
        logger.exception("UAT event not recorded: %s", kind)

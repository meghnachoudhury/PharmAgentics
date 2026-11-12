"""Agent job queue (core-007 FR-028). The app never runs a model: a worker on the owner's PC takes jobs
outbound, runs the agent on its local model, and posts results back.

The queue lives in memory and is mirrored to the store (jobs/<id>.json), so it survives a restart; the
app runs as one Cloud Run instance, so the in-memory index is the queue. One job runs at a time (one GPU).
"""
from __future__ import annotations

import json
import threading
import time
import uuid

from . import store

STALE_SECONDS = 600      # a running job with no result after this is failed (the host went away)
OFFLINE_AFTER = 60       # no poll for this long: the agent host is offline
_lock = threading.Lock()
_jobs: dict[str, dict] = {}
_loaded = False
_host = {"last_seen": 0.0, "model": None}


def _save(job: dict) -> None:
    store.backend().write(f"jobs/{job['id']}.json", json.dumps(job, default=str))


def _load() -> None:
    global _loaded
    if _loaded:
        return
    b = store.backend()
    for key in b.keys("jobs/"):
        text = b.read(key)
        if text:
            job = json.loads(text)
            _jobs[job["id"]] = job
    _loaded = True


def reset() -> None:
    """Tests only: forget the in-memory queue."""
    global _loaded
    with _lock:
        _jobs.clear()
        _host.update(last_seen=0.0, model=None)
        _loaded = False


def submit(kind: str, payload: dict, by: str) -> dict:
    job = {"id": "j-" + uuid.uuid4().hex[:12], "kind": kind, "status": "queued", "payload": payload, "by": by,
           "created_at": store.now(), "started_at": None, "finished_at": None, "result": None, "error": None,
           "started_ts": None}
    with _lock:
        _load()
        _jobs[job["id"]] = job
        _save(job)
    return job


def get(job_id: str) -> dict | None:
    with _lock:
        _load()
        return _jobs.get(job_id)


def _expire(now: float) -> None:
    for job in _jobs.values():
        if job["status"] == "running" and job["started_ts"] and now - job["started_ts"] > STALE_SECONDS:
            job.update(status="failed", error="The agent host did not return a result in time.", finished_at=store.now())
            _save(job)


def next_job(model: str | None) -> dict | None:
    """The worker's poll: records the heartbeat, hands out the oldest queued job if none is running."""
    now = time.time()
    with _lock:
        _load()
        _host.update(last_seen=now, model=model)
        _expire(now)
        if any(j["status"] == "running" for j in _jobs.values()):
            return None
        queued = sorted((j for j in _jobs.values() if j["status"] == "queued"), key=lambda j: j["created_at"])
        if not queued:
            return None
        job = queued[0]
        job.update(status="running", started_at=store.now(), started_ts=now)
        _save(job)
        return job


def complete(job_id: str, ok: bool, result: dict | None, error: str | None) -> dict:
    with _lock:
        _load()
        job = _jobs.get(job_id)
        if job is None or job["status"] != "running":
            raise KeyError(job_id)
        job.update(status="done" if ok else "failed", result=result if ok else None,
                   error=None if ok else (error or "The agent run failed.")[:500], finished_at=store.now())
        _save(job)
        return job


def status() -> dict:
    now = time.time()
    with _lock:
        _load()
        _expire(now)
        seen = _host["last_seen"]
        return {"online": bool(seen) and now - seen < OFFLINE_AFTER,
                "last_seen_seconds": round(now - seen) if seen else None, "model": _host["model"],
                "queued": sum(j["status"] == "queued" for j in _jobs.values()),
                "running": sum(j["status"] == "running" for j in _jobs.values())}

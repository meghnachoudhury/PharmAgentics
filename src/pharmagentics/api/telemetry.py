"""Telemetry for the hosted app, as aggregates only: golden-set scores exported from MLflow, and live use.

The image holds no MLflow store, so the scores come from `telemetry/eval.json` in the state bucket (pushed by
`deploy/gcp.py telemetry`), else the copy bundled at build time. Live use is computed from the stored UAT events,
agent jobs and feedback; the test login's traffic is left out and only counted.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response

from . import cloud, feedback, jobs, rbac, store

logger = logging.getLogger(__name__)
FILE = Path(__file__).with_name("telemetry.json")
BUCKET_KEY = "telemetry/eval.json"
TTL_SECONDS = 300
EMPTY = {"exported": None, "note": "No telemetry exported yet.", "latest": [], "runs": []}
LANE_EVENTS = {
    "briefing": {"requested": "requests", "opened": "opens", "reviewed": "reviews", "insight": "insights"},
    "forecast": {"forecast_run": "requests", "forecast_opened": "opens", "forecast_reviewed": "reviews",
                 "forecast_submitted": "submissions"},
}

router = APIRouter(prefix="/api", tags=["telemetry"])
_lock = threading.Lock()
_events: dict[str, dict] = {}
_cache: dict[str, tuple[float, Any]] = {}


def _cached(name: str, build):
    hit = _cache.get(name)
    if hit and time.monotonic() - hit[0] < TTL_SECONDS:
        return hit[1]
    value = build()
    _cache[name] = (time.monotonic(), value)
    return value


def reset() -> None:
    with _lock:
        _events.clear()
        _cache.clear()


def _read_snapshot() -> dict:
    try:
        text = store.backend().read(BUCKET_KEY)
        if text:
            return json.loads(text)
    except Exception:  # noqa: BLE001 - an unreadable bucket copy falls back to the bundled one
        logger.exception("Telemetry snapshot not read from the state store")
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(EMPTY)


def snapshot() -> dict:
    return _cached("eval", _read_snapshot)


def for_lanes(snap: dict, lanes: set[str]) -> dict:
    def keep(r: dict) -> bool:
        return r.get("lane") in lanes or r.get("lane") == "all"
    return {**snap, "latest": [r for r in snap.get("latest", []) if keep(r)],
            "runs": [r for r in snap.get("runs", []) if keep(r)]}


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(q * len(ordered)) - 1)], 1)


def _week(ts: str) -> str:
    d = date.fromisoformat(ts[:10])
    return (d - timedelta(days=d.weekday())).isoformat()


def _seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


def _spread(values: list[float]) -> dict | None:
    return {"n": len(values), "p50": _percentile(values, 0.5), "p95": _percentile(values, 0.95)} if values else None


def summarize_usage(events: list[dict], job_docs: list[dict], pulses: list[dict], surveys: list[dict],
                    votes: list[dict], questionnaire: dict) -> dict:
    """Aggregate live use per lane plus platform ratings. Pure: no I/O, no per-person rows."""
    testers = {e.get("user") for e in [*events, *pulses, *surveys, *votes] if e.get("test")}

    def real(docs: list[dict], who: str = "user") -> list[dict]:
        return [d for d in docs if not d.get("test") and d.get(who) not in testers]

    kept, kept_jobs = real(events), real(job_docs, "by")
    lanes: dict[str, dict] = {}
    for lane, kinds in LANE_EVENTS.items():
        mine = [e for e in kept if e["kind"] in kinds]
        counts = Counter(kinds[e["kind"]] for e in mine)
        requests = [e for e in mine if kinds[e["kind"]] == "requests"]
        lane_votes = [v for v in real(votes) if v.get("lane") == lane]
        out = {
            **{name: counts.get(name, 0) for name in kinds.values()},
            "weekly": dict(sorted(Counter(_week(e["ts"]) for e in requests).items())),
            "decisions": dict(Counter(e.get("decision") for e in mine if kinds[e["kind"]] == "reviews")),
            "votes": {"up": sum(v["vote"] == "up" for v in lane_votes), "down": sum(v["vote"] == "down" for v in lane_votes)},
        }
        if lane == "briefing":
            out["engines"] = dict(Counter(e.get("engine") or "unknown" for e in requests))
            out["scripted_ms"] = _spread([e["latency_ms"] for e in requests if e.get("latency_ms") is not None])
            out["agent_jobs"] = dict(Counter(f"{j.get('kind', 'job')} {j['status']}" for j in kept_jobs))
            out["agent_seconds"] = _spread([s for j in kept_jobs if j["status"] == "done" and j.get("kind") != "triage"
                                            and (s := _seconds(j.get("created_at"), j.get("finished_at"))) is not None])
        lanes[lane] = out

    feedback_docs = [*pulses, *surveys, *votes]
    summary = feedback.summarize(real(pulses), real(surveys), questionnaire, real(votes))
    return {
        "since": min((e["ts"] for e in kept), default=None),
        "excluded_test_records": (len(events) - len(kept)) + (len(job_docs) - len(kept_jobs))
                                 + (len(feedback_docs) - len(real(feedback_docs))),
        "lanes": lanes,
        "sessions": summary["pulse"]["by_rating"],
        "sus": summary["survey"]["sus"],
    }


def _new_events(backend) -> list[dict]:
    with _lock:
        for key in backend.keys("events/"):
            if key not in _events and (text := backend.read(key)):
                _events[key] = json.loads(text)
        return list(_events.values())


def load_usage(backend, job_docs: list[dict] | None = None) -> dict:
    """Read every source from a state backend. Events never change once written, so the app reads each once."""
    if job_docs is None:
        job_docs = [json.loads(t) for k in backend.keys("jobs/") if (t := backend.read(k))]
    pulses, surveys = feedback.load_feedback(backend)
    return summarize_usage(_new_events(backend), job_docs, pulses, surveys, feedback.load_votes(backend),
                           feedback.questionnaire())


def _live_usage() -> dict:
    usage = load_usage(store.backend(), jobs.all_jobs())
    if cloud.configured():
        usage["cloud_seconds"] = {"used": round(cloud.seconds_used()), "limit": round(cloud.seconds_used() + cloud.seconds_left())}
    usage["computed"] = store.now()
    return usage


def _signed_in(p: rbac.Principal) -> set[str]:
    if not p.lanes:
        raise HTTPException(status_code=403, detail="Your account has no PharmAgentics role.")
    return {r.lane for r in p.lanes}


@router.get("/telemetry")
def telemetry(response: Response, p: rbac.Principal = Depends(rbac.require_user)) -> dict:
    lanes = _signed_in(p)
    response.headers["Cache-Control"] = "no-store"
    return for_lanes(snapshot(), lanes)


@router.get("/telemetry/usage")
def usage(response: Response, p: rbac.Principal = Depends(rbac.require_user)) -> dict:
    lanes = _signed_in(p)
    response.headers["Cache-Control"] = "no-store"
    live = _cached("usage", _live_usage)
    return {**live, "lanes": {k: v for k, v in live["lanes"].items() if k in lanes}}

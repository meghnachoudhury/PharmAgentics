"""Cloud agent host (core-007 FR-031): an always-available CPU host for the agent team, on demand.

When an analyst queues an agent job and no teammate's machine is hosting, the app starts a Cloud Run *job*
(`pharmagentics-agent`: Ollama with the same qwen3 model, on CPU, plus the same worker the teammates run).
The job drains the queue, then exits when idle, so it bills only while it works. Nothing leaves the project:
the model runs inside our own container, so this adds no external model provider (System S14).

Cost guard: Cloud Run's free tier is 180,000 vCPU-seconds a month. The job uses CLOUD_VCPUS cores, so the app
keeps a monthly budget of job-seconds (PHARMAGENTICS_CLOUD_MAX_SECONDS, default 80% of the free tier) and starts
no new execution once it is used. A teammate's machine, when one is online, always goes first.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone

from . import store

logger = logging.getLogger(__name__)

COOLDOWN = 240           # seconds after a start before another is considered (a cold start takes about a minute)
FAILED_COOLDOWN = 60     # after a failed start
START_OVERHEAD = 300     # job-seconds charged per start for the cold start and the idle wait before it exits
DEFAULT_MAX_SECONDS = 18_000   # 8 vCPUs x 18,000 s = 144,000 vCPU-seconds, 80% of the free tier
# Measured on Cloud Run, 2026-11-12: cold start 96 s, triage 30 s, a full brief 828 s (about 14 minutes).
DEFAULT_ETA_MINUTES = 15       # for a brief, cold start included
_lock = threading.Lock()
_state = {"last_start": 0.0, "error": None}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def configured() -> bool:
    return bool(_env("PHARMAGENTICS_CLOUD_AGENT_JOB") and _env("PHARMAGENTICS_GCP_PROJECT"))


def _month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _usage_key() -> str:
    return f"cloud/usage-{_month()}.json"


def usage() -> dict:
    import json

    text = store.backend().read(_usage_key())
    data = json.loads(text) if text else {}
    return {"starts": int(data.get("starts", 0)), "job_seconds": float(data.get("job_seconds", 0.0))}


def _write_usage(data: dict) -> None:
    import json

    store.backend().write(_usage_key(), json.dumps(data))


def seconds_used() -> float:
    u = usage()
    return u["starts"] * START_OVERHEAD + u["job_seconds"]


def seconds_left() -> float:
    return max(0.0, float(_env("PHARMAGENTICS_CLOUD_MAX_SECONDS", str(DEFAULT_MAX_SECONDS))) - seconds_used())


def record_job_seconds(seconds: float) -> None:
    """A job the cloud host finished: add its running time to this month's budget."""
    with _lock:
        u = usage()
        _write_usage({"starts": u["starts"], "job_seconds": u["job_seconds"] + max(0.0, seconds)})


def status() -> dict:
    last = _state["last_start"]
    return {"enabled": configured(), "seconds_left": round(seconds_left()) if configured() else 0,
            "starting": bool(last) and time.time() - last < COOLDOWN, "error": _state["error"],
            "eta_minutes": int(_env("PHARMAGENTICS_CLOUD_ETA_MINUTES", str(DEFAULT_ETA_MINUTES)) or 0) or None,
            "cpu": True}


def _post(url: str) -> None:
    """Start the job (Cloud Run Admin API v2, as the app's own service account). Replaceable in tests."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    response = AuthorizedSession(credentials).post(url, json={}, timeout=30)
    if response.status_code >= 300:
        raise RuntimeError(f"Cloud Run refused to start the agent job (HTTP {response.status_code}): {response.text[:200]}")


def maybe_start(queued: int, online: bool) -> bool:
    """Start the cloud host if work is waiting, nobody is hosting, the budget allows and one is not just starting.
    Returns True when it started one. Never raises: a failure is shown in the status and the job keeps waiting."""
    if not configured() or queued <= 0 or online:
        return False
    with _lock:
        now = time.time()
        cooldown = FAILED_COOLDOWN if _state["error"] else COOLDOWN
        if now - _state["last_start"] < cooldown:
            return False
        if seconds_left() <= 0:
            _state["error"] = "This month's cloud agent budget is used up; a teammate's machine can still run it."
            return False
        _state["last_start"] = now
        u = usage()
        _write_usage({"starts": u["starts"] + 1, "job_seconds": u["job_seconds"]})
    url = (f"https://run.googleapis.com/v2/projects/{_env('PHARMAGENTICS_GCP_PROJECT')}/locations/"
           f"{_env('PHARMAGENTICS_CLOUD_AGENT_REGION', 'us-central1')}/jobs/{_env('PHARMAGENTICS_CLOUD_AGENT_JOB')}:run")
    try:
        _post(url)
        _state["error"] = None
        logger.info("Started the cloud agent host")
        return True
    except Exception as exc:  # noqa: BLE001 - starting the host must never break a request
        logger.exception("Could not start the cloud agent host")
        with _lock:  # refund the start: nothing ran
            u = usage()
            _write_usage({"starts": max(0, u["starts"] - 1), "job_seconds": u["job_seconds"]})
        _state["error"] = f"The cloud host could not start: {exc}"[:240]
        return False


def reset() -> None:
    """Tests only."""
    _state.update(last_start=0.0, error=None)

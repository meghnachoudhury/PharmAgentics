"""The app's built-in agent worker (core-007 FR-032, 2026-11-19).

With `PHARMAGENTICS_AGENT_MODEL=anthropic:<model>` and `ANTHROPIC_API_KEY` set, the app runs one worker thread
that takes agent jobs from the same queue as external workers (jobs.py) and hands each result to the same
acceptance path as a posted result (app.accept_result), so the traceability check applies unchanged. The
request handlers never call the model; only this thread does. `PHARMAGENTICS_AGENT_IN_APP=0` turns it off.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Callable

from . import jobs

logger = logging.getLogger(__name__)
NAME = "builtin"
POLL_SECONDS = 2.0
HEARTBEAT_SECONDS = 20.0
AGENTS_DIR = Path(__file__).resolve().parents[3] / "agents" / "brand-briefing"

_stop = threading.Event()
_thread: threading.Thread | None = None


def model() -> str | None:
    """The Anthropic model the built-in worker uses, or None when it is not configured."""
    from pharmagentics.llm import load_env

    load_env()
    spec = os.environ.get("PHARMAGENTICS_AGENT_MODEL", "")
    if os.environ.get("PHARMAGENTICS_AGENT_IN_APP", "1") == "0" or not spec.startswith("anthropic:"):
        return None
    return spec if os.environ.get("ANTHROPIC_API_KEY") else None


def _run_job(job: dict, spec: str) -> dict:
    if str(AGENTS_DIR) not in sys.path:
        sys.path.insert(0, str(AGENTS_DIR))
    from briefing_agent.worker import run_job

    return run_job(job, spec)


def work_once(spec: str, accept: Callable[[str, bool, dict | None, str | None], dict],
              runner: Callable[[dict, str], dict] = _run_job) -> bool:
    """Take one queued job, run it, hand over the result. False when there was nothing to do."""
    job = jobs.next_job(spec, NAME)
    if job is None:
        return False
    done = threading.Event()

    def beat() -> None:  # a long run must not look like a dead host (jobs.HEARTBEAT_STALE)
        while not done.wait(HEARTBEAT_SECONDS):
            jobs.heartbeat(spec, NAME)

    threading.Thread(target=beat, daemon=True).start()
    try:
        ok, result, error = True, runner(job, spec), None
    except Exception as exc:  # noqa: BLE001 - any failure fails the job visibly, never the app
        logger.warning("Built-in agent job %s failed: %s", job["id"], traceback.format_exc(limit=3))
        ok, result, error = False, None, f"{exc.__class__.__name__}: {exc}"[:1900]
    finally:
        done.set()
    try:
        accept(job["id"], ok, result, error)
    except KeyError:
        logger.warning("Built-in agent job %s was no longer running when it finished", job["id"])
    return True


def _loop(spec: str, accept) -> None:
    logger.info("Built-in agent worker started on %s", spec)
    while not _stop.is_set():
        try:
            if not work_once(spec, accept):
                _stop.wait(POLL_SECONDS)
        except Exception:  # noqa: BLE001 - the loop must survive anything a single job does
            logger.exception("Built-in agent worker error")
            _stop.wait(POLL_SECONDS * 5)


def start(accept) -> bool:
    """Start the worker thread once, if configured. Returns whether it runs."""
    global _thread
    spec = model()
    if spec is None or (_thread is not None and _thread.is_alive()):
        return _thread is not None and _thread.is_alive()
    _stop.clear()
    _thread = threading.Thread(target=_loop, args=(spec, accept), name="agent-builtin", daemon=True)
    _thread.start()
    return True


def stop() -> None:
    _stop.set()

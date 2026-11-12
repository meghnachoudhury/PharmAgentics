"""Local agent worker (core-007 FR-028). Runs on the owner's PC next to Ollama.

It polls the app outbound (no open port, Ollama stays on localhost), takes one job at a time, runs build 3
on the local model, and posts the result. The app checks every brief's traceability before anyone sees it.

    uv run python agents/brand-briefing/run_worker.py --app https://<app-url>     # token from deploy/.env.uat
"""
from __future__ import annotations

import argparse
import os
import socket
import threading
import time
import traceback
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]


def _env_file(path: Path) -> dict[str, str]:
    out = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def run_job(job: dict, model: str | None) -> dict:
    """One job, on the local model. Returns the result the app expects."""
    import briefing_agent as agent

    payload = job["payload"]
    if job["kind"] == "triage":
        return agent.triage(payload["question"], model)
    return agent.run_with_plan(payload["question"], payload["decision"], payload["plan"], model)


def _heartbeat(app: str, headers: dict, model: str, name: str, stop: threading.Event, every: float = 20.0) -> None:
    """Tell the app this worker is alive while it runs a job (it does not poll then). Never raises."""
    with httpx.Client(timeout=20) as http:
        while not stop.wait(every):
            try:
                http.post(f"{app}/api/worker/heartbeat", json={"model": model, "worker": name}, headers=headers)
            except httpx.HTTPError:
                pass  # the app may be cold-starting; the next beat retries


def main(argv: list[str] | None = None) -> None:
    env = _env_file(ROOT / "deploy" / ".env.uat")
    ap = argparse.ArgumentParser(description="Run PharmAgentics agent jobs on this machine's local model.")
    ap.add_argument("--app", default=os.environ.get("PHARMAGENTICS_APP_URL", "http://localhost:8080"))
    ap.add_argument("--token", default=os.environ.get("PHARMAGENTICS_WORKER_TOKEN") or env.get("PHARMAGENTICS_WORKER_TOKEN"))
    ap.add_argument("--model", default=None, help="model spec; default PHARMAGENTICS_AGENT_MODEL or the local qwen3")
    ap.add_argument("--interval", type=float, default=10.0, help="seconds between polls when idle")
    ap.add_argument("--once", action="store_true", help="take at most one job, then exit")
    ap.add_argument("--idle-exit", type=float, default=0.0, metavar="SECONDS",
                    help="exit after this long with no job (the cloud host uses it so it bills only while it works)")
    ap.add_argument("--name", default=os.environ.get("PHARMAGENTICS_WORKER_NAME") or socket.gethostname()[:60],
                    help="how this machine shows in the app's host list (default: the computer name)")
    a = ap.parse_args(argv)
    if not a.token:
        raise SystemExit("No worker token: set PHARMAGENTICS_WORKER_TOKEN or run deploy/make_env.py.")
    from pharmagentics.llm import model_spec

    spec = model_spec(a.model)
    app = a.app.rstrip("/")
    headers = {"Authorization": f"Bearer {a.token}"}
    print(f"Agent worker '{a.name}': {app}, model {spec}. Polling every {a.interval:g} s; Ctrl+C to stop.", flush=True)
    backoff = a.interval
    idle_since = time.time()
    with httpx.Client(timeout=60) as http:
        while True:
            try:
                r = http.post(f"{app}/api/worker/next", json={"model": spec, "worker": a.name}, headers=headers)
                if r.status_code == 401:
                    raise SystemExit("The app refused the worker token.")
                r.raise_for_status()
                backoff = a.interval
            except httpx.HTTPError as exc:
                print(f"  app unreachable ({exc.__class__.__name__}); retrying in {backoff:g} s", flush=True)
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)
                continue
            if r.status_code == 204:
                if a.once or (a.idle_exit and time.time() - idle_since > a.idle_exit):
                    print("  no work: stopping", flush=True)
                    return
                time.sleep(a.interval)
                continue
            job = r.json()
            started = time.time()
            print(f"  job {job['id']} ({job['kind']}): {job['payload']['question']}", flush=True)
            stop = threading.Event()
            beat = threading.Thread(target=_heartbeat, args=(app, headers, spec, a.name, stop), daemon=True)
            beat.start()  # a long CPU run must not look like a dead host
            try:
                body = {"ok": True, "result": run_job(job, spec)}
            except Exception as exc:  # noqa: BLE001 - any failure is reported to the app, not swallowed
                traceback.print_exc()
                body = {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"[:1900]}
            finally:
                stop.set()
                beat.join(timeout=5)
            for attempt in range(5):
                try:
                    done = http.post(f"{app}/api/worker/jobs/{job['id']}", json=body, headers=headers)
                    print(f"  job {job['id']}: {done.json().get('status', done.status_code)} in {time.time() - started:.0f} s", flush=True)
                    break
                except httpx.HTTPError as exc:
                    print(f"  could not post the result ({exc.__class__.__name__}); retry {attempt + 1}", flush=True)
                    time.sleep(5)
            idle_since = time.time()
            if a.once:
                return

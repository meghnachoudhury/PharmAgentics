"""core-007 FR-032: the app's built-in agent worker. No model is called: the runner is simulated with the
scripted engine, as in test_jobs.py, so these tests check the plumbing and the unchanged traceability check."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents" / "brand-briefing"))

from pharmagentics.api import agent_host, cloud, jobs, service  # noqa: E402
from pharmagentics.api.app import accept_result, app  # noqa: E402

pytestmark = pytest.mark.skipif(not service.DB.is_file(), reason="Build local/pharmagentics.duckdb first")
Q = {"intent": "weekly_brief", "brand_id": "BXA", "territory_id": "MID_ATLANTIC", "week_start": "2026-07-13",
     "question": "What changed, and why?"}
SPEC = "anthropic:claude-haiku-5-5"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("PHARMAGENTICS_AUTH", "dev")
    monkeypatch.setenv("PHARMAGENTICS_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("PHARMAGENTICS_WORKER_TOKEN", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    for k in ("PHARMAGENTICS_CLOUD_AGENT_JOB", "PHARMAGENTICS_GCP_PROJECT", "PHARMAGENTICS_AGENT_IN_APP"):
        monkeypatch.delenv(k, raising=False)
    jobs.reset()
    cloud.reset()
    yield
    jobs.reset()
    cloud.reset()


def analyst() -> TestClient:
    c = TestClient(app)
    c.post("/auth/dev-login", data={"username": "dev-analyst"})
    return c


def scripted_triage(job: dict, spec: str) -> dict:
    from briefing_baseline.pipeline import triage

    return dict(triage(job["payload"]["question"]), engine="agent", manager_order=["territory:PACIFIC"], flagged=False, flags=[])


@pytest.mark.parametrize("model,key,switch,expected", [
    (SPEC, "k", None, SPEC),
    (SPEC, None, None, None),                       # no key: off
    ("ollama:qwen3:4b", "k", None, None),           # a local model runs in a worker, never in the app
    (SPEC, "k", "0", None),                         # explicitly off
])
def test_builtin_worker_runs_only_when_configured(monkeypatch, model, key, switch, expected):
    monkeypatch.setattr("pharmagentics.llm.load_env", lambda *a, **k: None)
    monkeypatch.setenv("PHARMAGENTICS_AGENT_MODEL", model)
    if key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    else:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    if switch:
        monkeypatch.setenv("PHARMAGENTICS_AGENT_IN_APP", switch)
    assert agent_host.model() == expected


def test_status_reports_the_builtin_host(monkeypatch):
    monkeypatch.setattr(agent_host, "model", lambda: SPEC)
    body = analyst().get("/api/agent/status").json()
    assert body["configured"] is True and body["builtin"] == {"model": SPEC}


def test_builtin_worker_runs_a_job_through_the_same_checks():
    a = analyst()
    job = a.post("/api/agent/jobs", json={"kind": "triage", "query": Q}).json()
    assert agent_host.work_once(SPEC, accept_result, runner=scripted_triage) is True
    shown = a.get(f"/api/agent/jobs/{job['id']}").json()
    assert shown["status"] == "done" and shown["host_kind"] == "builtin" and shown["result"]["engine"] == "agent"
    assert agent_host.work_once(SPEC, accept_result, runner=scripted_triage) is False  # nothing left


def test_a_failing_run_fails_the_job_visibly():
    a = analyst()
    job = a.post("/api/agent/jobs", json={"kind": "triage", "query": Q}).json()

    def broken(job, spec):
        raise RuntimeError("rate limited")

    agent_host.work_once(SPEC, accept_result, runner=broken)
    shown = a.get(f"/api/agent/jobs/{job['id']}").json()
    assert shown["status"] == "failed" and "rate limited" in shown["error"]


def test_an_untraceable_brief_is_refused_as_before():
    from briefing_baseline.pipeline import run_with_plan

    a = analyst()
    tjob = a.post("/api/agent/jobs", json={"kind": "triage", "query": Q}).json()
    agent_host.work_once(SPEC, accept_result, runner=scripted_triage)
    plan = a.get(f"/api/agent/jobs/{tjob['id']}").json()["result"]
    decision = {"plan_id": plan["plan_id"], "stories": ["territory:PACIFIC"]}
    bjob = a.post("/api/agent/jobs", json={"kind": "brief", "query": Q, "triage_job": tjob["id"], "decision": decision}).json()

    def invented(job, spec):
        good = run_with_plan(job["payload"]["question"], decision)
        return {**good, "envelope": {**good["envelope"], "answer": good["envelope"]["answer"] + "\nPacific fell 99.9%."}}

    agent_host.work_once(SPEC, accept_result, runner=invented)
    shown = a.get(f"/api/agent/jobs/{bjob['id']}").json()
    assert shown["status"] == "failed" and "99.9%" in shown["error"]

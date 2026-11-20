"""Telemetry: golden-set snapshot per lane, live-use aggregates, and test-login traffic left out."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from pharmagentics.api import feedback, jobs, rbac, store, telemetry
from pharmagentics.api.app import app

SNAPSHOT_FIELDS = {"run_id", "started", "minutes", "system", "model", "lane", "control", "cases", "reruns", "judge",
                   "code_version", "data_version", "metrics", "judge_metrics"}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("PHARMAGENTICS_AUTH", "dev")
    monkeypatch.setenv("PHARMAGENTICS_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("PHARMAGENTICS_STATE_BUCKET", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    telemetry.reset()
    jobs.reset()
    yield
    telemetry.reset()
    jobs.reset()


def signed_in(user: str) -> TestClient:
    c = TestClient(app)
    assert c.post("/auth/dev-login", data={"username": user}, follow_redirects=False).status_code == 303
    return c


def event(kind: str, ts: str, user: str, **fields) -> dict:
    return {"kind": kind, "ts": ts, "user": user, **fields}


def test_for_lanes_keeps_own_lane_and_cross_lane_runs():
    snap = {"latest": [{"lane": "briefing"}, {"lane": "forecast"}, {"lane": "all"}], "runs": [{"lane": "forecast"}]}
    out = telemetry.for_lanes(snap, {"briefing"})
    assert [r["lane"] for r in out["latest"]] == ["briefing", "all"] and out["runs"] == []


def test_bundled_snapshot_holds_scores_only():
    for r in json.loads(telemetry.FILE.read_text(encoding="utf-8"))["runs"]:
        assert set(r) <= SNAPSHOT_FIELDS
        assert all(isinstance(v, (int, float)) for v in {**r["metrics"], **r["judge_metrics"]}.values())


@pytest.mark.parametrize("values, q, expected", [([5], 0.5, 5), ([1, 2, 3, 4], 0.5, 2), ([1, 2, 3, 4], 0.95, 4),
                                                ([*range(1, 101)], 0.95, 95), ([], 0.5, None)])
def test_percentile_is_nearest_rank(values, q, expected):
    assert telemetry._percentile(values, q) == expected


def test_bucket_copy_wins_over_bundled_copy():
    store.backend().write(telemetry.BUCKET_KEY, json.dumps({**telemetry.EMPTY, "exported": "2026-11-20T00:00+00:00"}))
    assert telemetry.snapshot()["exported"] == "2026-11-20T00:00+00:00"


def test_usage_leaves_out_the_tester_even_where_an_event_lacks_the_flag():
    events = [
        event("requested", "2026-11-17T10:00:00+00:00", "u-p1", engine="scripted", latency_ms=1000),
        event("requested", "2026-11-18T10:00:00+00:00", "u-p1", engine="scripted", latency_ms=3000),
        event("reviewed", "2026-11-18T11:00:00+00:00", "u-p1", decision="approved"),
        event("agent_job", "2026-11-18T12:00:00+00:00", "u-test", test=True),
        event("requested", "2026-11-18T12:01:00+00:00", "u-test", engine="agent"),
        event("forecast_run", "2026-11-19T09:00:00+00:00", "u-ca"),
    ]
    job_docs = [
        {"by": "u-p1", "kind": "brief", "status": "done", "created_at": "2026-11-18T10:00:00+00:00", "finished_at": "2026-11-18T10:01:00+00:00"},
        {"by": "u-test", "kind": "brief", "status": "done", "created_at": "2026-11-18T12:00:00+00:00", "finished_at": "2026-11-18T12:30:00+00:00"},
    ]
    pulses = [{"session": "s1", "user": "u-test", "rating": "bad", "ts": "2026-11-18T12:02:00+00:00", "where": "briefing", "test": True}]
    u = telemetry.summarize_usage(events, job_docs, pulses, [], [], feedback.questionnaire())
    b = u["lanes"]["briefing"]
    assert b["requests"] == 2 and b["engines"] == {"scripted": 2}
    assert b["decisions"] == {"approved": 1}
    assert b["scripted_ms"] == {"n": 2, "p50": 1000, "p95": 3000}
    assert b["agent_jobs"] == {"brief done": 1} and b["agent_seconds"]["p50"] == 60
    assert b["weekly"] == {"2026-11-16": 2}
    assert u["lanes"]["forecast"]["requests"] == 1
    assert "participants" not in u and u["excluded_test_records"] == 4 and u["sessions"]["bad"] == 0


def test_usage_endpoint_shows_only_the_signed_in_lanes_and_no_person():
    p1 = rbac.pseudonym("dev-analyst")
    store.record_event("requested", user=p1, role="briefing-analyst", persona="P1", engine="scripted", latency_ms=800)
    store.record_event("forecast_run", user=rbac.pseudonym("dev-forecast-analyst"), role="forecast-analyst", persona="CA")
    assert signed_in("dev-tester").post("/api/feedback/pulse", json={"rating": "bad", "where": "briefing"}).status_code == 200

    director = signed_in("dev-director").get("/api/telemetry/usage")
    assert director.status_code == 200 and director.headers["cache-control"] == "no-store"
    body = director.json()
    assert set(body["lanes"]) == {"briefing"} and body["lanes"]["briefing"]["requests"] == 1
    assert body["sessions"] == {r: 0 for r in feedback.RATINGS}
    assert p1 not in json.dumps(body)

    assert set(signed_in("dev-forecast-manager").get("/api/telemetry/usage").json()["lanes"]) == {"forecast"}
    assert signed_in("dev-norole").get("/api/telemetry/usage").status_code == 403
    assert TestClient(app).get("/api/telemetry/usage").status_code == 401


def test_eval_endpoint_filters_runs_by_lane():
    store.backend().write(telemetry.BUCKET_KEY, json.dumps({**telemetry.EMPTY, "latest": [
        {"lane": "briefing", "system": "a"}, {"lane": "forecast", "system": "b"}, {"lane": "all", "system": "c"}]}))
    latest = signed_in("dev-forecast-analyst").get("/api/telemetry").json()["latest"]
    assert [r["system"] for r in latest] == ["b", "c"]

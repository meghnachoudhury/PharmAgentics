"""core-007 role-based access: the server decides every view from the signed-in role.

Uses the stand-in identities (PHARMAGENTICS_AUTH=dev). The engine is mocked except in the
last test, which runs the real scripted baseline on the New England week (user story P1-Q2).
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from pharmagentics.api import auth, rbac, service, views
from pharmagentics.api.app import app
from pharmagentics.api.schemas import BriefingResult

VALID = {"intent": "weekly_brief", "brand_id": "BXA", "territory_id": "NEW_ENGLAND",
         "week_start": "2026-05-04", "question": "Generate the weekly brand-performance briefing."}

ANSWER = """Brief for week of 2026-05-04. Data version vtest. Product: BXA. Territory questions use only cuts that pass the feed gate.
Data health: 7 of 8 territories pass the feed gate for 2026-05-04. Withheld cuts are left out of every figure below and never read as zero demand:
- New England, week of 2026-05-04: not reportable (missing keys, late delivery); 84 rows against 128 expected.
KPIs: BXA TRx averaged 3,362 a week across 6 of 8 territories (like for like), down 5.2% against the weeks before.
Story one: Pacific. BXA TRx averaged 464 a week against 674 before (down 31.2%).
Checked, in this order:
- Data artifact: ruled out. Every Pacific cut in these weeks passes the feed gate.
- Supply: supported. BXA inventory fill averaged 0.69.
Confidence: High. Leading driver: supply. Next: involve supply chain.
Considered and dropped: 6 territories moved within their normal range."""


def sample() -> BriefingResult:
    return BriefingResult.model_validate({
        "system": "briefing_scripted", "question": "Week of 2026-05-04 in New England: brief",
        "territory_id": "NEW_ENGLAND", "week_start": "2026-05-04", "answer": ANSWER,
        "claims": [{"value": "3,362", "evidence_id": "e1"}],
        "evidence": [{"id": "e1", "tool": "get_metric", "query": "select avg(trx) from reporting.v_weekly_rx_kpis",
                      "result": 3362, "data_version": "vtest"}],
        "data_version": "vtest", "abstained": False,
    })


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("PHARMAGENTICS_AUTH", "dev")
    monkeypatch.setenv("PHARMAGENTICS_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("K_SERVICE", raising=False)


def signed_in(username: str) -> TestClient:
    client = TestClient(app)
    assert client.post("/auth/dev-login", data={"username": username}, follow_redirects=False).status_code == 303
    return client


def run_brief(analyst: TestClient) -> dict:
    with patch.object(service, "run_briefing", return_value=sample()):
        response = analyst.post("/api/briefing/query", json=VALID)
    assert response.status_code == 200, response.text
    return response.json()


def leaks(body) -> list[str]:
    text = json.dumps(body).lower()
    return [k for k in ('"claims"', '"evidence"', '"answer"', '"query"', "select ", "reporting.v_", "checked, in this order")
            if k in text]


# --- sign-in ----------------------------------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("get", "/api/me"), ("get", "/api/briefing/context"), ("post", "/api/briefing/query"),
    ("get", "/api/briefing/published"), ("get", "/api/briefing/b-000000000000"),
    ("post", "/api/briefing/b-000000000000/review"), ("post", "/api/uat/insight"),
])
def test_every_data_route_needs_sign_in(method, path):
    response = getattr(TestClient(app), method)(path)
    assert response.status_code == 401


def test_health_is_open_and_holds_no_data():
    body = TestClient(app).get("/api/health").json()
    assert set(body) == {"service", "database_ready"}


def test_me_returns_only_own_role_and_views():
    body = signed_in("dev-director").get("/api/me").json()
    assert body["lanes"] == {"briefing": {"role": "briefing-director", "persona": "P3", "label": "Brand Director",
                                          "views": ["leadership"], "actions": ["read"], "available": True}}


def test_user_without_a_role_sees_no_data():
    client = signed_in("dev-norole")
    assert client.get("/api/me").json()["lanes"] == {}
    assert client.get("/api/briefing/context").status_code == 403
    assert client.get("/api/briefing/published").status_code == 403


def test_forecast_roles_are_reserved_and_do_not_cross_lanes():
    for user, persona in (("dev-forecast-analyst", "CA"), ("dev-forecast-manager", "BM")):
        client = signed_in(user)
        lanes = client.get("/api/me").json()["lanes"]
        assert list(lanes) == ["forecast"] and lanes["forecast"]["persona"] == persona
        assert lanes["forecast"]["available"] is False
        assert client.post("/api/briefing/query", json=VALID).status_code == 403


def test_dev_sign_in_is_refused_on_cloud_run(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "pharmagentics")
    with pytest.raises(RuntimeError):
        auth.mode()


def test_two_roles_in_one_lane_get_the_more_restricted_one():
    p = rbac.Principal("x", "x", ("briefing-analyst", "briefing-director", "offline_access"))
    assert p.role("briefing").name == "briefing-director"


# --- views ------------------------------------------------------------------------------------

def test_analyst_gets_full_view_and_brief_starts_pending():
    body = run_brief(signed_in("dev-analyst"))
    assert body["view"] == "analyst" and body["review_status"] == "pending"
    assert body["claims"] and body["evidence"] and body["answer"] == ANSWER


def test_director_cannot_run_review_or_open_analyst_view():
    analyst, director = signed_in("dev-analyst"), signed_in("dev-director")
    bid = run_brief(analyst)["brief_id"]
    analyst.post(f"/api/briefing/{bid}/review", json={"decision": "approved"})
    assert director.post("/api/briefing/query", json=VALID).status_code == 403
    assert director.post(f"/api/briefing/{bid}/review", json={"decision": "approved"}).status_code == 403
    assert director.get(f"/api/briefing/{bid}?view=analyst").status_code == 403


def test_director_sees_only_approved_briefs():
    analyst, director = signed_in("dev-analyst"), signed_in("dev-director")
    bid = run_brief(analyst)["brief_id"]
    with patch.object(service, "current_data_version", return_value="vtest"):
        assert director.get("/api/briefing/published").json() == []
        assert director.get(f"/api/briefing/{bid}").status_code == 404
        analyst.post(f"/api/briefing/{bid}/review", json={"decision": "rejected", "reason": "numbers look off"})
        assert director.get(f"/api/briefing/{bid}").status_code == 404
        analyst.post(f"/api/briefing/{bid}/review", json={"decision": "approved"})
        assert [b["brief_id"] for b in director.get("/api/briefing/published").json()] == [bid]
        assert director.get(f"/api/briefing/{bid}").status_code == 200
    with patch.object(service, "current_data_version", return_value="another-release"):
        assert director.get("/api/briefing/published").json() == []


def test_leadership_response_carries_no_evidence_query_or_trace():
    analyst, director = signed_in("dev-analyst"), signed_in("dev-director")
    bid = run_brief(analyst)["brief_id"]
    analyst.post(f"/api/briefing/{bid}/review", json={"decision": "approved"})
    response = director.get(f"/api/briefing/{bid}")
    body = response.json()
    assert response.headers["cache-control"] == "no-store"
    assert body["view"] == "leadership" and leaks(body) == []
    assert set(body) == set(views.LEADERSHIP_FIELDS) | {"view", "summary"}


def test_analyst_preview_matches_what_the_director_sees():
    analyst, director = signed_in("dev-analyst"), signed_in("dev-director")
    bid = run_brief(analyst)["brief_id"]
    preview = analyst.get(f"/api/briefing/{bid}?view=leadership").json()
    analyst.post(f"/api/briefing/{bid}/review", json={"decision": "approved"})
    seen = director.get(f"/api/briefing/{bid}").json()
    assert preview["summary"] == seen["summary"] and leaks(preview) == []


def test_rejection_needs_a_reason():
    analyst = signed_in("dev-analyst")
    bid = run_brief(analyst)["brief_id"]
    assert analyst.post(f"/api/briefing/{bid}/review", json={"decision": "rejected"}).status_code == 422


def test_summary_keeps_caveats_and_drops_only_check_detail():
    summary = views.executive_summary(ANSWER)
    lines = summary.splitlines()
    assert set(lines) <= set(ANSWER.splitlines())  # every number is already one of the run's claims
    assert any("New England" in l and "not reportable" in l for l in lines)
    assert any("6 of 8 territories" in l for l in lines)
    assert "Confidence: High. Leading driver: supply. Next: involve supply chain." in lines
    assert not any(l.startswith(("Checked, in this order", "- Data artifact", "- Supply", "Considered and dropped")) for l in lines)


# --- UAT events -------------------------------------------------------------------------------

def test_uat_events_are_pseudonymous(tmp_path):
    analyst = signed_in("dev-analyst")
    bid = run_brief(analyst)["brief_id"]
    analyst.post(f"/api/briefing/{bid}/review", json={"decision": "approved"})
    assert analyst.post("/api/uat/insight", json={"brief_id": bid, "view": "analyst"}).status_code == 204
    events = [json.loads(p.read_text()) for p in (tmp_path / "events").rglob("*.json")]
    assert sorted(e["kind"] for e in events) == ["insight", "requested", "reviewed"]
    text = json.dumps(events)
    assert "dev-analyst" not in text and "Dev Commercial Analyst" not in text
    assert {e["user"] for e in events} == {rbac.pseudonym("dev-analyst")}
    assert next(e for e in events if e["kind"] == "requested")["latency_ms"] >= 0


def test_director_cannot_mark_insight_on_analyst_view():
    assert signed_in("dev-director").post("/api/uat/insight", json={"brief_id": "b-x", "view": "analyst"}).status_code == 403


# --- real engine ------------------------------------------------------------------------------

@pytest.mark.skipif(not service.DB.is_file(), reason="Build local/pharmagentics.duckdb first")
def test_real_new_england_week_keeps_the_withheld_cut_for_leaders():
    """User story P1-Q2 through the real scripted baseline: leaders still learn New England is not reportable."""
    analyst, director = signed_in("dev-analyst"), signed_in("dev-director")
    brief = analyst.post("/api/briefing/query", json=VALID).json()
    analyst.post(f"/api/briefing/{brief['brief_id']}/review", json={"decision": "approved"})
    body = director.get(f"/api/briefing/{brief['brief_id']}").json()
    assert leaks(body) == []
    assert "7 of 8 territories" in body["summary"] and "not reportable" in body["summary"]
    assert set(body["summary"].splitlines()) <= set(brief["answer"].splitlines())


# --- brief-002 Phase A: triage plan review and stage flow (real engine) -----------------------------

TRIAGE_Q = {**VALID, "territory_id": "MID_ATLANTIC", "week_start": "2026-07-13"}


@pytest.mark.skipif(not service.DB.is_file(), reason="Build local/pharmagentics.duckdb first")
def test_triage_is_analyst_only_and_decisions_are_checked():
    assert TestClient(app).post("/api/briefing/triage", json=TRIAGE_Q).status_code == 401
    for user in ("dev-director", "dev-forecast-analyst", "dev-forecast-manager"):
        assert signed_in(user).post("/api/briefing/triage", json=TRIAGE_Q).status_code == 403
    analyst = signed_in("dev-analyst")
    plan = analyst.post("/api/briefing/triage", json=TRIAGE_Q).json()
    assert plan["state"] == "TRIAGE_REVIEW" and [c["id"] for c in plan["stories"]][:2] == ["territory:PACIFIC", "territory:MID_ATLANTIC"]
    stale = {**TRIAGE_Q, "triage": {"plan_id": "t-000000000000", "stories": []}}
    assert analyst.post("/api/briefing/query", json=stale).status_code == 409
    bad = {**TRIAGE_Q, "triage": {"plan_id": plan["plan_id"], "stories": ["territory:GREAT_LAKES"]}}
    response = analyst.post("/api/briefing/query", json=bad)
    assert response.status_code == 400 and "territory:GREAT_LAKES" in response.json()["detail"]


@pytest.mark.skipif(not service.DB.is_file(), reason="Build local/pharmagentics.duckdb first")
def test_flow_and_triage_record_reach_the_analyst_only():
    analyst, director = signed_in("dev-analyst"), signed_in("dev-director")
    plan = analyst.post("/api/briefing/triage", json=TRIAGE_Q).json()
    decision = {"plan_id": plan["plan_id"], "stories": ["territory:PACIFIC", "competitor:BXE"]}
    brief = analyst.post("/api/briefing/query", json={**TRIAGE_Q, "triage": decision}).json()
    assert brief["triage"]["default"] is False and "Left out of this brief by the analyst: Mid-Atlantic." in brief["answer"]
    assert brief["flow"][-1]["states"] == ["IN_REVIEW"]
    approved = analyst.post(f"/api/briefing/{brief['brief_id']}/review", json={"decision": "approved"}).json()
    assert approved["flow"][-1]["states"] == ["IN_REVIEW", "PUBLISHED"]
    seen = director.get(f"/api/briefing/{brief['brief_id']}").json()
    assert "flow" not in seen and "triage" not in seen and leaks(seen) == []
    rejected = analyst.post(f"/api/briefing/{brief['brief_id']}/review", json={"decision": "rejected", "reason": "test"}).json()
    assert rejected["flow"][-1]["states"] == ["IN_REVIEW", "RETURNED"]
    # The default plan is the same brief as running without triage (same brief_id, same text)
    default = {"plan_id": plan["plan_id"], "stories": [c["id"] for c in plan["stories"] if c["proposed"] == "investigate"]}
    a = analyst.post("/api/briefing/query", json={**TRIAGE_Q, "triage": default}).json()
    b = analyst.post("/api/briefing/query", json=TRIAGE_Q).json()
    assert a["brief_id"] == b["brief_id"] and a["answer"] == b["answer"] and a["brief_id"] != brief["brief_id"]


def test_login_shows_a_retry_page_while_keycloak_is_starting(monkeypatch):
    """core-007 SC-004: Keycloak scales to zero; an unreachable sign-in service is a retry page, never a 500."""
    monkeypatch.setenv("PHARMAGENTICS_AUTH", "oidc")
    monkeypatch.setenv("PHARMAGENTICS_OIDC_ISSUER", "http://127.0.0.1:9/realms/pharmagentics")  # nothing listens here
    monkeypatch.setenv("PHARMAGENTICS_OIDC_CLIENT_ID", "pharmagentics-app")
    monkeypatch.setenv("PHARMAGENTICS_OIDC_CLIENT_SECRET", "x")
    monkeypatch.delenv("PHARMAGENTICS_OIDC_METADATA_URL", raising=False)
    monkeypatch.setattr(auth, "_oauth", None)
    response = TestClient(app).get("/auth/login", follow_redirects=False)
    monkeypatch.setattr(auth, "_oauth", None)
    assert response.status_code == 503 and response.headers["retry-after"] == "5"
    assert "Starting the sign-in service" in response.text


@pytest.mark.skipif(not service.DB.is_file(), reason="Build local/pharmagentics.duckdb first")
def test_citations_reach_the_analyst_only():
    analyst, director = signed_in("dev-analyst"), signed_in("dev-director")
    brief = analyst.post("/api/briefing/query", json=TRIAGE_Q).json()
    assert brief["citations"] and all(brief["answer"][s["start"]:s["end"]] == brief["claims"][s["claim"]]["value"] for s in brief["citations"])
    analyst.post(f"/api/briefing/{brief['brief_id']}/review", json={"decision": "approved"})
    assert "citations" not in director.get(f"/api/briefing/{brief['brief_id']}").json()


def test_forecast_scaffold_reports_role_and_not_live():
    assert TestClient(app).get("/api/forecast/status").status_code == 401
    body = signed_in("dev-forecast-manager").get("/api/forecast/status").json()
    assert body["available"] is False and body["persona"] == "BM" and body["views"] == ["leadership"]
    assert signed_in("dev-analyst").get("/api/forecast/status").json()["role"] is None

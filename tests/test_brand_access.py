"""core-010: same persona, different account grants; real brand-specific governed evidence."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from pharmagentics.api import auth, brand_access, jobs, rbac, service, store, threads
from pharmagentics.api.app import app
from pharmagentics.api.schemas import BriefingQuery
from pharmagentics.tools import Registry

Q = {"brand_id": "BXC", "territory_id": "PACIFIC", "week_start": "2026-06-08",
     "question": "Generate the weekly brand-performance briefing."}
needs_db = pytest.mark.skipif(not service.DB.is_file(), reason="Build DuckDB first")


@pytest.fixture(autouse=True)
def environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PHARMAGENTICS_AUTH", "dev")
    monkeypatch.setenv("PHARMAGENTICS_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("PHARMAGENTICS_STATE_BUCKET", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setattr(threads, "_purged", True)
    monkeypatch.setitem(auth.DEV_USERS, "dev-bxc-only", ("BXC only", ["tester", "brand-bxc"]))
    jobs.reset()
    yield
    jobs.reset()


def signed_in(user):
    c = TestClient(app)
    assert c.post("/auth/dev-login", data={"username": user}, follow_redirects=False).status_code == 303
    return c


@pytest.fixture(scope="module")
def results():
    return {b: service.run_briefing(BriefingQuery.model_validate({**Q, "brand_id": b})).model_dump(mode="json")
            for b in ("BXA", "BXC")}


@pytest.fixture
def bxc(results):
    return store.save_brief(deepcopy(results["BXC"]), by="test-analyst")["brief_id"]


@needs_db
def test_same_role_different_account_grants_and_empty_access():
    a, b = signed_in("dev-analyst-multibrand"), signed_in("dev-analyst")
    assert a.get("/api/me").json()["lanes"] == b.get("/api/me").json()["lanes"]
    ca, cb = a.get("/api/briefing/context").json(), b.get("/api/briefing/context").json()
    assert ca["product_ids"] == ["BXA", "BXC"] and cb["product_ids"] == ["BXA"]
    assert {x["id"]: x["engines"] for x in ca["brands"]} == {"BXA": ["scripted", "agent"], "BXC": ["scripted"]}
    empty = signed_in("dev-analyst-no-brands").get("/api/briefing/context")
    assert empty.status_code == 200
    assert empty.json()["product_ids"] == empty.json()["brands"] == [] and empty.json()["brand_id"] is None


@pytest.mark.parametrize("path", ["/api/briefing/triage", "/api/briefing/query", "/api/agent/jobs"])
def test_ungranted_requests_fail_before_any_engine(path):
    b = signed_in("dev-analyst")
    payload = {"kind": "triage", "query": Q} if path.endswith("jobs") else Q
    with patch.object(service, "run_triage") as triage, patch.object(service, "run_briefing") as run, \
            patch.object(service, "_check_scope") as scope:
        assert b.post(path, json=payload).status_code == 403
        triage.assert_not_called(); run.assert_not_called(); scope.assert_not_called()
    with patch("pharmagentics.api.overview.build") as overview:
        assert b.get("/api/briefing/overview?brand_id=BXC&week=2026-06-08").status_code == 403
        overview.assert_not_called()


@needs_db
def test_real_brands_have_distinct_ids_and_replayable_primary_claims_and_charts(results):
    assert store.brief_id(results["BXA"]) != store.brief_id(results["BXC"])
    # Existing BXA URLs and approvals keep their pre-feature identity.
    r = results["BXA"]
    key = "|".join(str(r.get(k)) for k in ("system", "data_version", "week_start", "territory_id", "question"))
    assert store.brief_id(r) == "b-" + hashlib.sha256(key.encode()).hexdigest()[:12]
    reg = Registry(service.DB)
    try:
        for b, expected in (("BXA", 464), ("BXC", 626)):
            result = results[b]
            primary = [e for e in result["evidence"] if e["result"] == expected
                       and f"product_id = '{b}'" in e["query"] and "PACIFIC" in e["query"]]
            assert primary and any(c["value"] == str(expected) and c["evidence_id"] in {e["id"] for e in primary}
                                   for c in result["claims"])
            claimed = {c["evidence_id"] for c in result["claims"]}
            for e in result["evidence"]:
                if e["id"] in claimed:
                    assert float(reg.scalar(e["query"]) or 0) == pytest.approx(e["result"])
            story = next(s for s in result["sections"] if s["number"].startswith("3.") and s["title"] == "Pacific")
            assert story["chart"]["table"]["rows"][-1] == ["2026-06-08", expected]
        assert not any("product_id = 'BXA'" in e["query"] for e in results["BXC"]["evidence"])
    finally:
        reg.close()


@needs_db
def test_overview_uses_selected_brand_and_permitted_competitor_policy():
    a, b = signed_in("dev-analyst-multibrand"), signed_in("dev-analyst")
    for brand, expected in (("BXA", (464, 96, 49)), ("BXC", (626, 140, 83))):
        data = a.get(f"/api/briefing/overview?week=2026-06-08&brand_id={brand}").json()
        pacific = next(t for t in data["territories"] if t["id"] == "PACIFIC")
        point = pacific["series"][-1]
        assert (point["trx"], point["nrx"], point["nbrx"]) == expected
        assert data["product"] == brand
    # Dedicated workspace protection intentionally permits aggregate competitor market context.
    data = b.get("/api/briefing/overview?week=2026-06-08&brand_id=BXA").json()
    assert any(m["product"] == "BXC" and m["name"] == "Lipidara" for t in data["territories"] for m in t["mix"])
    assert any("group by 1, 2" in e["query"] and e["params"].get("scope") == "TRx by product" for e in data["evidence"])


@needs_db
def test_cross_brand_plan_is_rejected():
    a = signed_in("dev-analyst-multibrand")
    plans = {b: a.post("/api/briefing/triage", json={**Q, "brand_id": b}).json() for b in ("BXA", "BXC")}
    assert plans["BXA"]["plan_id"] != plans["BXC"]["plan_id"]
    wrong = {"plan_id": plans["BXA"]["plan_id"], "stories": []}
    assert a.post("/api/briefing/query", json={**Q, "triage": wrong}).status_code == 409
    plan = plans["BXC"]
    decision = {"plan_id": plan["plan_id"], "stories": [s["id"] for s in plan["stories"] if s["proposed"] == "investigate"]}
    response = a.post("/api/briefing/query", json={**Q, "triage": decision})
    assert response.status_code == 200 and response.json()["brand_id"] == "BXC"


@needs_db
def test_approval_and_leadership_access_are_also_brand_checked(bxc):
    a, da, db = signed_in("dev-analyst-multibrand"), signed_in("dev-director-multibrand"), signed_in("dev-director")
    assert da.get(f"/api/briefing/{bxc}").status_code == 404
    assert a.post(f"/api/briefing/{bxc}/review", json={"decision": "approved"}).status_code == 200
    summary = da.get(f"/api/briefing/{bxc}").json()
    assert summary["brand_id"] == "BXC" and summary["view"] == "leadership" and "626" in summary["summary"]
    assert not {"answer", "claims", "evidence", "triage", "flow"} & summary.keys()
    assert "\"query\"" not in json.dumps(summary) and "\"text_citations\"" not in json.dumps(summary)
    assert any(r["brief_id"] == bxc and r["brand_id"] == "BXC" for r in da.get("/api/briefing/published").json())
    assert db.get("/api/briefing/published").json() == []
    assert db.get(f"/api/briefing/{bxc}?brand_id=BXA").status_code == 404


@needs_db
def test_saved_brief_reviews_threads_links_and_votes_do_not_leak(bxc):
    a, b = signed_in("dev-analyst-multibrand"), signed_in("dev-analyst")
    assert a.post(f"/api/briefing/{bxc}/thread/ask", json={"question": "Restate Lipidara's bottom line"}).status_code == 200
    saved = a.post(f"/api/briefing/{bxc}/thread/save").json()
    for path in (f"/api/briefing/{bxc}", f"/api/briefing/{bxc}/thread", saved["share_path"]):
        denied = b.get(path)
        assert denied.status_code == 404 and "626" not in denied.text
    for path, payload in (
        (f"/api/briefing/{bxc}/review", {"decision": "approved"}),
        (f"/api/briefing/{bxc}/review", {"decision": "rejected"}),
        (f"/api/briefing/{bxc}/thread/ask", {"question": "Restate the bottom line"}),
        (f"/api/briefing/{bxc}/thread/save", {}),
        (f"/api/briefing/{bxc}/thread/continue/{saved['owner']}", {}),
        ("/api/feedback/vote", {"lane": "briefing", "ref": bxc, "view": "analyst", "vote": "down"}),
        ("/api/feedback/vote", {"lane": "briefing", "ref": f"{bxc}:t1", "view": "analyst", "vote": "up"}),
        ("/api/uat/insight", {"brief_id": bxc, "view": "analyst"}),
    ):
        assert b.post(path, json=payload).status_code == 404
    assert b.get(f"/api/feedback/vote?lane=briefing&ref={bxc}&view=analyst").status_code == 404
    assert store.get_brief(bxc)["review_status"] == "pending" and not store.backend().keys("feedback/response/")


@needs_db
@pytest.mark.parametrize("territory,week,reason,basis", [
    ("NEW_ENGLAND", "2026-05-04", "missing keys", "projected"),
    ("GREAT_LAKES", "2026-07-06", "duplicate keys", "estimated"),
])
def test_flagged_cuts_are_withheld_for_bxc(territory, week, reason, basis):
    a = signed_in("dev-analyst-multibrand")
    plan = a.post("/api/briefing/triage", json={**Q, "territory_id": territory, "week_start": week}).json()
    assert territory in plan["withheld"] and reason in plan["context"]
    assert not any(s["territory"] == territory for s in plan["stories"])
    result = a.post("/api/briefing/query", json={**Q, "territory_id": territory, "week_start": week}).json()
    assert basis in result["answer"] and "an assumption" in result["answer"] and reason in result["answer"]
    reg = Registry(service.DB)
    try:
        assert reg.rows(f"select trx from reporting.v_weekly_rx_kpis where product_id = 'BXC' and territory_id = '{territory}' and week_start = DATE '{week}'") == []
    finally:
        reg.close()


def test_bxc_agent_submission_is_rejected_even_with_a_grant():
    a = signed_in("dev-analyst-multibrand")
    with patch.object(service, "_check_scope") as scope:
        response = a.post("/api/agent/jobs", json={"kind": "triage", "query": Q})
        assert response.status_code == 400 and "does not support" in response.text
        scope.assert_not_called()
    assert jobs.all_jobs() == []


def test_agent_worker_and_result_admission_refuse_a_different_brand():
    import sys
    sys.path.insert(0, str(service.BRIEFING_DIR))
    from briefing_agent.worker import run_job
    from pharmagentics.api.app import accept_result

    with pytest.raises(ValueError, match="BXA only"):
        run_job({"kind": "triage", "payload": {"query": Q}}, None)
    j = jobs.submit("triage", {"query": {**Q, "brand_id": "BXA"}}, by="test")
    assert jobs.next_job(None)["id"] == j["id"]
    assert accept_result(j["id"], True, {"brand_id": "BXC", "state": "ROUTINE"}, None)["status"] == "failed"
    assert jobs.get(j["id"])["result"] is None and store.backend().keys("briefs/") == []


@needs_db
def test_bxc_agent_followup_cannot_call_the_bxa_agent(bxc):
    a = signed_in("dev-analyst-multibrand")
    with patch("pharmagentics.api.agent_host.model") as model:
        assert a.post(f"/api/briefing/{bxc}/thread/ask", json={"question": "Explain the change", "engine": "agent"}).status_code == 400
        model.assert_not_called()


@needs_db
def test_mismatched_engine_brand_is_never_saved():
    with patch("briefing_baseline.pipeline.answer", return_value={"brand_id": "BXA"}), patch.object(store, "save_brief") as save:
        assert signed_in("dev-analyst-multibrand").post("/api/briefing/query", json=Q).status_code == 500
        save.assert_not_called()


def test_tester_switch_retains_actual_grants_and_forecast_requires_bxa():
    c = signed_in("dev-bxc-only")
    assert c.get("/api/me").json()["brand_ids"] == ["BXC"]
    assert c.post("/api/me/view-as", json={"view": "leadership"}).json()["brand_ids"] == ["BXC"]
    assert c.get("/api/briefing/context").json()["product_ids"] == ["BXC"]
    for path in ("/api/forecast/context", "/api/forecast/runs", "/api/forecast/status", "/api/forecast/drivers"):
        assert c.get(path).status_code == 403
    assert c.post("/api/forecast/ask", json={"question": "What changed?"}).status_code == 403


def test_jobs_require_requester_grants_and_matching_triage_scope():
    a, b, other = signed_in("dev-analyst-multibrand"), signed_in("dev-analyst"), signed_in("dev-bxc-only")
    payload = {"query": Q, "question": "test"}
    j = jobs.submit("triage", payload, by=rbac.pseudonym("dev-analyst-multibrand"))
    assert a.get(f"/api/agent/jobs/{j['id']}").status_code == 200
    assert b.get(f"/api/agent/jobs/{j['id']}").status_code == 404  # same persona, no BXC grant
    assert other.get(f"/api/agent/jobs/{j['id']}").status_code == 404  # same grant, different requester


def test_agent_triage_cannot_be_reused_by_another_scope_or_requester():
    a, b = signed_in("dev-analyst-multibrand"), signed_in("dev-analyst")
    q = {**Q, "brand_id": "BXA"}
    j = jobs.submit("triage", {"query": q}, by=rbac.pseudonym("dev-analyst"))
    assert jobs.next_job(None)["id"] == j["id"]
    plan = {"plan_id": "t-000000000000", "stories": [], "brand_id": "BXA"}
    jobs.complete(j["id"], True, plan, None)
    req = {"kind": "brief", "query": {**q, "territory_id": "MOUNTAIN"}, "triage_job": j["id"],
           "decision": {"plan_id": plan["plan_id"], "stories": []}}
    assert b.post("/api/agent/jobs", json=req).status_code == 409
    assert a.post("/api/agent/jobs", json=req).status_code == 404  # cannot reuse another requester's plan


def test_grant_changes_take_effect_on_next_sign_in(monkeypatch):
    c = signed_in("dev-analyst-multibrand")
    monkeypatch.setitem(auth.DEV_USERS, "dev-analyst-multibrand", ("Same analyst", ["briefing-analyst", "brand-bxa"]))
    assert c.get("/api/me").json()["brand_ids"] == ["BXA", "BXC"]
    c.get("/auth/logout", follow_redirects=False)
    c.post("/auth/dev-login", data={"username": "dev-analyst-multibrand"}, follow_redirects=False)
    assert c.get("/api/me").json()["brand_ids"] == ["BXA"]


def test_missing_or_unknown_brand_grants_never_derive_access_from_role():
    class Request:
        session = {}
    req = Request()
    auth._set_user(req, "x", "x", ["briefing-analyst", "brand-bxc", "brand-all", "admin"])
    p = rbac.principal(req)
    assert p.role_names == ("briefing-analyst",) and p.brand_grants == ("brand-bxc",)
    assert brand_access.allowed_brands(p) == {"BXC"}
    assert brand_access.allowed_brands(rbac.Principal("x", "x", ("briefing-analyst",))) == set()


@needs_db
def test_feedback_review_filters_proposals_and_checks_decisions(bxc):
    ids = ["p-" + "1" * 12, "p-" + "2" * 12]
    for pid, brand in zip(ids, ("BXA", "BXC")):
        source = f"thread:{bxc}/owner" if brand == "BXC" else "legacy:test"
        store.backend().write(f"review/proposals/{pid}.json", json.dumps({"id": pid, "brand_id": brand,
                             "source": source, "kind": "case", "status": "proposed", "before": f"private {brand}"}))
    # A tester restricted to BXA still has admin status, not BXC access.
    auth.DEV_USERS["dev-test-bxa"] = ("BXA tester", ["tester", "brand-bxa"])
    try:
        c = signed_in("dev-test-bxa")
        assert [d["id"] for d in c.get("/api/review/proposals").json()] == ids[:1]
        denied = c.post(f"/api/review/proposals/{ids[1]}", json={"decision": "approve"})
        assert denied.status_code == 404 and "private BXC" not in denied.text
        store.backend().delete(f"briefs/{bxc}.json")  # retained feedback still has its declared brand
        assert [d["id"] for d in c.get("/api/review/proposals").json()] == ids[:1]
        assert len(signed_in("dev-tester").get("/api/review/proposals").json()) == 2
    finally:
        del auth.DEV_USERS["dev-test-bxa"]


@needs_db
def test_bxc_feedback_keeps_its_brand_and_never_reruns_the_bxa_agent(bxc, tmp_path):
    from eval.harness import improve

    a = signed_in("dev-analyst-multibrand")
    assert a.post("/api/feedback/vote", json={"lane": "briefing", "ref": bxc, "view": "analyst",
                  "vote": "down", "comment": "Please make the data caveat clearer."}).status_code == 200
    a.post(f"/api/briefing/{bxc}/thread/ask", json={"question": "Restate the bottom line"})
    a.post(f"/api/briefing/{bxc}/thread/save")
    with patch.object(improve, "draft_lesson") as lesson, patch.object(improve, "rerun") as rerun:
        proposals = improve.run(state_dir=tmp_path, backend=store.backend())
        lesson.assert_not_called(); rerun.assert_not_called()
    assert len(proposals) == 2
    assert all(p["brand_id"] == "BXC" and p["kind"] == "case" and not p["confident"] for p in proposals)

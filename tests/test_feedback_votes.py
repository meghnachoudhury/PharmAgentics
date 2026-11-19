"""core-008 User Stories 5 and 6: thumbs up or down on one answer, and golden-set candidates drafted from the votes.

Uses the stand-in identities (PHARMAGENTICS_AUTH=dev) and a temporary state folder. No model, no database.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from pharmagentics.api import feedback, forecast_store, rbac, store
from pharmagentics.api.app import app

Q = feedback.questionnaire()


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("PHARMAGENTICS_AUTH", "dev")
    monkeypatch.setenv("PHARMAGENTICS_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("PHARMAGENTICS_STATE_BUCKET", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)


def signed_in(user: str) -> TestClient:
    c = TestClient(app)
    assert c.post("/auth/dev-login", data={"username": user}, follow_redirects=False).status_code == 303
    return c


def stored(tmp_path: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in (tmp_path / "feedback" / "response").rglob("*.json")]


def a_brief(status: str = "pending") -> str:
    result = {"system": "briefing_scripted", "engine": "scripted", "data_version": "dv-1", "brand_id": "BXA",
              "territory_id": "GREAT_LAKES", "week_start": "2026-10-05", "question": None,
              "answer": "BXA TRx rose.\nChecked, in this order:\n- SQL detail for the analyst."}
    bid = store.save_brief(result, by="u-test")["brief_id"]
    if status != "pending":
        store.set_review(bid, status, None, by="u-test")
    return bid


def a_forecast_run(submitted: bool = False) -> str:
    request = {"territory_id": "SOUTHEAST", "week_start": "2026-08-31", "window_weeks": 4}
    result = {"dataset_release": "rel-1", "report": {"headline": "BXA missed forecast.", "investigator_mode": "scripted",
                                                     "variance_trx": -10, "abstained": False, "drivers": []}}
    record = forecast_store.save(request, result, by="u-test",
                                 writer={"narrative": {"summary": "Missed.", "analyst_notes": "check SE feed"},
                                         "report_model": "none", "writer_status": "ok", "writer_attempts": []})
    if submitted:
        forecast_store.submit(record["run_id"], by="u-test", role="forecast-analyst")
    return record["run_id"]


# --- votes ----------------------------------------------------------------------------------------

def test_analyst_votes_on_a_brief_and_reads_it_back(tmp_path):
    bid = a_brief()
    c = signed_in("dev-analyst")
    q = {"lane": "briefing", "ref": bid, "view": "analyst"}
    assert c.get("/api/feedback/vote", params=q).json()["vote"] is None
    r = c.post("/api/feedback/vote", json={**q, "vote": "down", "comment": "  The week-over-week change is wrong. "})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.json()["comment"] == "The week-over-week change is wrong."
    c.post("/api/feedback/vote", json={**q, "vote": "up"})  # changing the vote replaces it
    (doc,) = stored(tmp_path)
    assert doc["vote"] == "up" and doc["comment"] is None and doc["updates"] == 1
    assert doc["engine"] == "scripted" and doc["data_version"] == "dv-1" and doc["scope"]["territory_id"] == "GREAT_LAKES"
    assert "SQL detail" in doc["shown"]  # the analyst saw the full brief
    assert doc["user"] == rbac.pseudonym("dev-analyst") and doc["personas"] == ["P1"]
    assert "dev-analyst" not in json.dumps(doc) and "Dev Commercial" not in json.dumps(doc)
    assert c.get("/api/feedback/vote", params=q).json()["vote"] == "up"


def test_a_leader_votes_only_on_approved_briefs_and_only_the_summary_is_kept(tmp_path):
    bid = a_brief()
    c = signed_in("dev-director")
    body = {"lane": "briefing", "ref": bid, "view": "leadership", "vote": "down"}
    assert c.post("/api/feedback/vote", json=body).status_code == 404  # existence not disclosed
    assert c.get("/api/feedback/vote", params={k: body[k] for k in ("lane", "ref", "view")}).status_code == 404
    assert not stored(tmp_path)
    store.set_review(bid, "approved", None, by="u-test")
    assert c.post("/api/feedback/vote", json=body).status_code == 200
    assert c.post("/api/feedback/vote", json={**body, "view": "analyst"}).status_code == 403
    (doc,) = stored(tmp_path)
    assert "SQL detail" not in doc["shown"] and "BXA TRx rose." in doc["shown"]


def test_forecast_votes_follow_the_run_visibility(tmp_path):
    rid = a_forecast_run()
    manager = signed_in("dev-forecast-manager")
    body = {"lane": "forecast", "ref": rid, "view": "leadership", "vote": "up"}
    assert manager.post("/api/feedback/vote", json=body).status_code == 404  # not submitted yet
    assert signed_in("dev-forecast-analyst").post("/api/feedback/vote", json={**body, "view": "analyst"}).status_code == 200
    forecast_store.submit(rid, by="u-test", role="forecast-analyst")
    assert manager.post("/api/feedback/vote", json=body).status_code == 200
    docs = {d["view"]: d for d in stored(tmp_path)}
    assert "analyst_notes" not in docs["leadership"]["shown"]["narrative"]
    assert docs["analyst"]["shown"]["narrative"]["analyst_notes"] == "check SE feed"
    assert docs["analyst"]["scope"] == {"territory_id": "SOUTHEAST", "week_start": "2026-08-31", "window_weeks": 4}


def test_a_vote_in_a_lane_without_a_role_is_refused():
    bid = a_brief("approved")
    c = signed_in("dev-forecast-manager")
    assert c.post("/api/feedback/vote", json={"lane": "briefing", "ref": bid, "view": "leadership", "vote": "up"}).status_code == 403


@pytest.mark.parametrize("body", [
    {"lane": "briefing", "ref": "b-0123456789ab", "view": "analyst", "vote": "meh"},
    {"lane": "payer", "ref": "b-0123456789ab", "view": "analyst", "vote": "up"},
    {"lane": "briefing", "ref": "../../etc", "view": "analyst", "vote": "up"},
    {"lane": "briefing", "ref": "b-0123456789ab", "view": "analyst", "vote": "up", "comment": "x" * 501},
    {"lane": "briefing", "ref": "b-0123456789ab", "view": "analyst", "vote": "up", "extra": 1},
])
def test_vote_refuses_bad_input(body):
    assert signed_in("dev-analyst").post("/api/feedback/vote", json=body).status_code == 422


def test_vote_routes_refuse_signed_out_and_role_less_callers():
    q = {"lane": "briefing", "ref": "b-0123456789ab", "view": "analyst"}
    assert TestClient(app).post("/api/feedback/vote", json={**q, "vote": "up"}).status_code == 401
    assert TestClient(app).get("/api/feedback/vote", params=q).status_code == 401
    assert signed_in("dev-norole").post("/api/feedback/vote", json={**q, "vote": "up"}).status_code == 403


def test_the_report_counts_votes_and_lists_downvotes(tmp_path):
    bid = a_brief("approved")
    signed_in("dev-analyst").post("/api/feedback/vote", json={"lane": "briefing", "ref": bid, "view": "analyst", "vote": "up"})
    signed_in("dev-director").post("/api/feedback/vote", json={"lane": "briefing", "ref": bid, "view": "leadership",
                                                                "vote": "down", "comment": "Too long."})
    summary = feedback.summarize([], [], Q, feedback.load_votes(store.LocalBackend(tmp_path)))
    a = summary["answers"]
    assert (a["votes"], a["answers"], a["up"], a["down"]) == (2, 1, 1, 1)
    assert a["by"] == {"briefing · scripted · analyst": {"up": 1, "down": 0},
                       "briefing · scripted · leadership": {"up": 0, "down": 1}}
    md = feedback.to_markdown(summary, Q)
    assert "2 votes on 1 answers: 1 up, 1 down" in md and "Too long." in md


# --- golden-set candidates ------------------------------------------------------------------------

def test_candidates_draft_one_case_per_answer_and_keep_edits(tmp_path):
    from eval.harness import candidates
    bid, rid = a_brief("approved"), a_forecast_run(submitted=True)
    signed_in("dev-analyst").post("/api/feedback/vote", json={"lane": "briefing", "ref": bid, "view": "analyst", "vote": "up"})
    signed_in("dev-director").post("/api/feedback/vote", json={"lane": "briefing", "ref": bid, "view": "leadership",
                                                                "vote": "down", "comment": "Wrong territory."})
    signed_in("dev-forecast-manager").post("/api/feedback/vote", json={"lane": "forecast", "ref": rid, "view": "leadership", "vote": "up"})
    out = tmp_path / "candidates"
    written, kept, _ = candidates.run(tmp_path, out_dir=out)
    assert len(written) == 2 and not kept
    brief = yaml.safe_load((out / "briefing" / f"{bid}.yaml").read_text(encoding="utf-8"))
    assert brief["status"] == "candidate" and brief["id"] is None and brief["facts"] == [] and brief["reference_answer"] is None
    assert brief["kind"] == "investigate" and brief["votes"] == {"up": 1, "down": 1}
    assert brief["comments"][0]["comment"] == "Wrong territory." and set(brief["shown"]) == {"analyst", "leadership"}
    fc = yaml.safe_load((out / "forecast" / f"{rid}.yaml").read_text(encoding="utf-8"))
    assert fc["kind"] == "regression" and "SOUTHEAST" in fc["question"]
    (out / "briefing" / f"{bid}.yaml").write_text("edited by a person", encoding="utf-8")
    written, kept, _ = candidates.run(tmp_path, out_dir=out)
    assert not written and len(kept) == 2
    assert (out / "briefing" / f"{bid}.yaml").read_text(encoding="utf-8") == "edited by a person"
    candidates.run(tmp_path, out_dir=out, force=True)
    assert (out / "briefing" / f"{bid}.yaml").read_text(encoding="utf-8") != "edited by a person"


def test_candidates_are_not_golden_cases():
    from eval.harness import candidates
    from eval.harness.paths import GOLDEN_DIR
    assert GOLDEN_DIR not in candidates.CANDIDATES_DIR.parents and candidates.CANDIDATES_DIR != GOLDEN_DIR

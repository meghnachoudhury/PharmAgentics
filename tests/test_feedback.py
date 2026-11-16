"""core-008 UAT feedback: the session pulse, the platform questionnaire, SUS scoring and the report maths.

Uses the stand-in identities (PHARMAGENTICS_AUTH=dev) and a temporary state folder. No model, no database.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from pharmagentics.api import feedback, rbac, store
from pharmagentics.api.app import app

ALL_USERS = ("dev-analyst", "dev-director", "dev-forecast-analyst", "dev-forecast-manager")
Q = feedback.questionnaire()
SUS = Q["scoring"]["sus"]
ROUTES = [("get", "/api/feedback/status"), ("post", "/api/feedback/pulse"), ("get", "/api/feedback/questionnaire"),
          ("get", "/api/feedback/survey"), ("post", "/api/feedback/survey")]


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


def stored(tmp_path: Path, prefix: str) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in (tmp_path / prefix).rglob("*.json")]


def sus_answers(odd: int, even: int) -> dict:
    return {sid: (odd if n % 2 == 0 else even) for n, sid in enumerate(SUS)}


# --- who may use it -------------------------------------------------------------------------------

@pytest.mark.parametrize("method,path", ROUTES)
def test_signed_out_users_get_nothing(method, path):
    assert getattr(TestClient(app), method)(path).status_code == 401


@pytest.mark.parametrize("method,path", ROUTES)
def test_an_account_with_no_role_gets_nothing(method, path):
    assert getattr(signed_in("dev-norole"), method)(path).status_code == 403


@pytest.mark.parametrize("user", ALL_USERS)
def test_every_persona_can_rate_and_answer(user):
    c = signed_in(user)
    assert c.post("/api/feedback/pulse", json={"rating": "good"}).status_code == 200
    assert c.post("/api/feedback/survey", json={"version": Q["version"], "answers": {"x_best": "Clear."}}).status_code == 200


# --- the session pulse ----------------------------------------------------------------------------

def test_pulse_is_stored_without_any_personal_detail(tmp_path):
    c = signed_in("dev-analyst")
    r = c.post("/api/feedback/pulse", json={"rating": "bad", "comment": "  Slow after I clicked approve.  ", "where": "briefing", "ref": "b-0123456789ab"})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    (doc,) = stored(tmp_path, "feedback/pulse")
    assert doc["rating"] == "bad" and doc["comment"] == "Slow after I clicked approve." and doc["where"] == "briefing"
    assert doc["user"] == rbac.pseudonym("dev-analyst") and doc["personas"] == ["P1"] and doc["roles"] == ["briefing-analyst"]
    text = json.dumps(doc)
    assert "dev-analyst" not in text and "Dev Commercial" not in text  # no sign-in name, no display name


def test_the_last_rating_of_a_session_is_the_session_rating():
    c = signed_in("dev-director")
    assert c.get("/api/feedback/status").json()["pulse"] is None
    c.post("/api/feedback/pulse", json={"rating": "bad"})
    c.post("/api/feedback/pulse", json={"rating": "good", "comment": "It got better."})
    assert c.get("/api/feedback/status").json()["pulse"]["rating"] == "good"
    c.post("/auth/dev-login", data={"username": "dev-director"})  # a new sign-in is a new session
    assert c.get("/api/feedback/status").json()["pulse"] is None


@pytest.mark.parametrize("body", [
    {"rating": "great"}, {"rating": "good", "comment": "x" * 301}, {"rating": "good", "where": "mars"},
    {"rating": "good", "ref": "has spaces"}, {"rating": "good", "extra": 1}, {}, {"rating": 3},
])
def test_pulse_refuses_bad_input(body):
    assert signed_in("dev-analyst").post("/api/feedback/pulse", json=body).status_code == 422


def test_blank_comment_is_stored_as_none(tmp_path):
    signed_in("dev-analyst").post("/api/feedback/pulse", json={"rating": "fine", "comment": "   "})
    assert stored(tmp_path, "feedback/pulse")[0]["comment"] is None


def test_a_failed_save_is_reported_not_swallowed():
    class Broken:
        def write(self, key, text):
            raise OSError("bucket unreachable")

        def read(self, key):
            return None

    c = signed_in("dev-analyst")
    with patch.object(store, "backend", return_value=Broken()):
        assert c.post("/api/feedback/pulse", json={"rating": "good"}).status_code == 503
        assert c.post("/api/feedback/survey", json={"version": Q["version"], "answers": {"x_best": "ok"}}).status_code == 503
    assert c.get("/api/feedback/status").json()["pulse"] is None  # a rating that was not saved is not remembered


# --- the questionnaire ----------------------------------------------------------------------------

def test_questionnaire_is_served_without_its_editing_notes():
    body = signed_in("dev-forecast-manager").get("/api/feedback/questionnaire").json()
    assert body["version"] == Q["version"] and "_comment" not in body and len(feedback.items(body)) == 20


def test_the_shipped_questionnaire_is_valid_and_sus_is_the_standard_ten():
    feedback.check_questionnaire(Q)
    by_id = {i["id"]: i for i in feedback.items(Q)}
    assert len(SUS) == 10
    # Odd statements are worded positively, even ones negatively: the scoring below relies on that order.
    assert [bool(by_id[s].get("reverse")) for s in SUS] == [False, True] * 5


def test_check_questionnaire_rejects_a_bad_edit():
    for mutate, why in [
        (lambda q: q["sections"][0]["items"].append(dict(q["sections"][0]["items"][0])), "unique"),
        (lambda q: q["sections"][0]["items"][0].update(type="emoji"), "unknown type"),
        (lambda q: q.update(version=0), "version"),
        (lambda q: q["sections"][2]["items"][1].update(options=[]), "options"),
        (lambda q: q["scoring"]["sus"].__setitem__(0, "o_nps"), "SUS"),
    ]:
        q = deepcopy(Q)
        mutate(q)
        with pytest.raises(ValueError):
            feedback.check_questionnaire(q)


# --- SUS, by code ---------------------------------------------------------------------------------

@pytest.mark.parametrize("odd,even,expected", [(5, 1, 100.0), (3, 3, 50.0), (1, 5, 0.0), (4, 2, 75.0), (5, 5, 50.0), (2, 2, 50.0), (2, 4, 25.0)])
def test_sus_score_matches_hand_computed_values(odd, even, expected):
    assert feedback.sus_score(Q, sus_answers(odd, even)) == expected


def test_sus_needs_all_ten_statements():
    answers = sus_answers(5, 1)
    answers.pop("sus7")
    assert feedback.sus_score(Q, answers) is None


# --- submitting the questionnaire -----------------------------------------------------------------

def test_survey_is_stored_scored_and_replaced_on_resubmit(tmp_path):
    c = signed_in("dev-analyst")
    answers = {**sus_answers(5, 1), "o_nps": 9, "o_used": ["briefing", "evidence", "briefing"], "o_freq": "weekly", "x_fix": "  Faster agent runs. "}
    r = c.post("/api/feedback/survey", json={"version": Q["version"], "answers": answers})
    assert r.status_code == 200 and r.json()["answered"] == 14
    (doc,) = stored(tmp_path, "feedback/survey")
    assert doc["sus"] == 100.0 and doc["updates"] == 0 and doc["answers"]["o_used"] == ["briefing", "evidence"]
    assert doc["answers"]["x_fix"] == "Faster agent runs." and doc["personas"] == ["P1"]
    assert "dev-analyst" not in json.dumps(doc)
    c.post("/api/feedback/survey", json={"version": Q["version"], "answers": {**answers, "o_nps": 3}})
    (doc,) = stored(tmp_path, "feedback/survey")  # one document per participant
    assert doc["answers"]["o_nps"] == 3 and doc["updates"] == 1
    assert c.get("/api/feedback/status").json()["survey"] == {"submitted_at": doc["ts"], "version": Q["version"]}


def test_a_partial_survey_has_no_sus_score(tmp_path):
    signed_in("dev-director").post("/api/feedback/survey", json={"version": Q["version"], "answers": {"sus1": 4, "t_trace": 5}})
    assert stored(tmp_path, "feedback/survey")[0]["sus"] is None


def test_participants_only_ever_see_their_own_answers():
    a, d = signed_in("dev-analyst"), signed_in("dev-director")
    a.post("/api/feedback/survey", json={"version": Q["version"], "answers": {"x_best": "The citations."}})
    assert a.get("/api/feedback/survey").json()["answers"] == {"x_best": "The citations."}
    assert d.get("/api/feedback/survey").json() == {"version": None, "answers": {}, "submitted_at": None}


@pytest.mark.parametrize("answers", [
    {}, {"nope": 1}, {"sus1": 0}, {"sus1": 6}, {"sus1": "4"}, {"sus1": True}, {"sus1": 3.5}, {"o_nps": 11}, {"o_nps": -1},
    {"o_freq": "daily"}, {"o_freq": ["weekly"]}, {"o_used": "briefing"}, {"o_used": ["briefing", "telepathy"]},
    {"x_best": 5}, {"x_best": "x" * 1001},
])
def test_survey_refuses_bad_answers(answers):
    assert signed_in("dev-analyst").post("/api/feedback/survey", json={"version": Q["version"], "answers": answers}).status_code == 422


def test_survey_refuses_an_old_questionnaire_version():
    r = signed_in("dev-analyst").post("/api/feedback/survey", json={"version": Q["version"] + 1, "answers": {"sus1": 4}})
    assert r.status_code == 409 and "changed" in r.json()["detail"]


def test_blank_text_and_empty_choices_are_dropped():
    clean = feedback.validate_answers(Q, {"x_best": "   ", "o_used": [], "sus1": 4})
    assert clean == {"sus1": 4}


# --- the report -----------------------------------------------------------------------------------

def pulse(session, ts, rating, persona="P1", comment=None, where="briefing"):
    return {"session": session, "ts": ts, "rating": rating, "personas": [persona], "comment": comment, "where": where}


def survey(persona, odd, even, nps, ts="2026-11-14T10:00:00.000+00:00", **extra):
    answers = {**sus_answers(odd, even), "o_nps": nps, **extra}
    return {"ts": ts, "version": 1, "personas": [persona], "answers": answers, "sus": feedback.sus_score(Q, answers)}


def test_summary_counts_the_last_rating_of_each_session():
    pulses = [pulse("s1", "2026-11-14T09:00", "bad"), pulse("s1", "2026-11-14T09:30", "good", comment="Fixed itself."),
              pulse("s2", "2026-11-14T09:10", "fine", persona="P3"), pulse("s3", "2026-11-14T09:20", "bad", persona="P3", comment="Too slow.")]
    s = feedback.summarize(pulses, [], Q)["pulse"]
    assert s["submissions"] == 4 and s["sessions"] == 3
    assert s["by_rating"] == {"good": 1, "fine": 1, "bad": 1}
    assert s["by_role"] == {"P1": {"good": 1, "fine": 0, "bad": 0}, "P3": {"good": 0, "fine": 1, "bad": 1}}
    assert [c["comment"] for c in s["comments"]] == ["Fixed itself.", "Too slow."]


def test_summary_survey_numbers():
    surveys = [survey("P1", 5, 1, 10, x_fix="Speed."), survey("P3", 3, 3, 8, o_used=["briefing"]), survey("P1", 4, 2, 5, o_used=["briefing", "agent"])]
    out = feedback.summarize([], surveys, Q)["survey"]
    assert out["responses"] == 3 and out["sus"] == {"n": 3, "mean": 75.0, "median": 75.0, "min": 50.0, "max": 100.0}
    rows = {r["id"]: r for r in out["items"]}
    assert rows["sus1"]["mean"] == 4.0 and rows["sus1"]["counts"] == {"1": 0, "2": 0, "3": 1, "4": 1, "5": 1}
    assert rows["sus2"]["reverse"] is True
    assert (rows["o_nps"]["promoters"], rows["o_nps"]["passives"], rows["o_nps"]["detractors"], rows["o_nps"]["nps"]) == (1, 1, 1, 0)
    assert rows["o_used"]["counts"] == {"Weekly briefing": 2, "Triage review": 0, "Evidence and citations": 0, "Agent team": 1,
                                       "Leadership summaries": 0, "Forecast explanation": 0}
    assert rows["x_fix"]["answers"] == [{"role": "P1", "text": "Speed."}]


def test_markdown_report_reads_well_and_handles_no_data():
    empty = feedback.to_markdown(feedback.summarize([], [], Q), Q)
    assert "No session ratings yet." in empty and "No questionnaire responses yet." in empty
    full = feedback.to_markdown(feedback.summarize([pulse("s1", "2026-11-14T09:00", "good", comment="Nice.")], [survey("P1", 5, 1, 10)], Q), Q)
    assert "| Good | 1 |" in full and "mean 100.0" in full and "net promoter score 100" in full and "Nice." in full


def test_report_script_reads_a_state_folder(tmp_path):
    import importlib.util

    c = signed_in("dev-analyst")
    c.post("/api/feedback/pulse", json={"rating": "fine", "comment": "OK overall"})
    c.post("/api/feedback/survey", json={"version": Q["version"], "answers": {**sus_answers(4, 2), "x_best": "Evidence."}})
    spec = importlib.util.spec_from_file_location("feedback_report", Path(__file__).resolve().parents[1] / "deploy" / "feedback_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out, csv_dir = tmp_path / "report.md", tmp_path / "csv"
    assert mod.main(["--state-dir", str(tmp_path), "--out", str(out), "--csv", str(csv_dir)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "OK overall" in text and "mean 75.0" in text and "Evidence." in text
    assert (csv_dir / "pulses.csv").read_text(encoding="utf-8-sig").splitlines()[1].split(",")[3] == "fine"
    header = (csv_dir / "survey.csv").read_text(encoding="utf-8-sig").splitlines()[0].split(",")
    assert header[:5] == ["user", "ts", "version", "personas", "sus"] and "x_best" in header


def test_persona_table_follows_the_natural_order():
    pulses = [pulse("s1", "2026-11-14T09:00", "good", persona="BM"), pulse("s2", "2026-11-14T09:01", "fine", persona="P3"),
              pulse("s3", "2026-11-14T09:02", "bad", persona="CA"), pulse("s4", "2026-11-14T09:03", "good", persona="P1")]
    pulses.append({**pulse("s5", "2026-11-14T09:04", "fine"), "personas": ["P1", "CA"]})  # a mentor login holding two personas
    text = feedback.to_markdown(feedback.summarize(pulses, [], Q), Q)
    rows = [line.split("|")[1].strip() for line in text.splitlines() if line.startswith("| ") and line.split("|")[1].strip() in {"P1", "P3", "CA", "BM", "P1/CA"}]
    assert rows == ["P1", "P3", "CA", "BM", "P1/CA"]

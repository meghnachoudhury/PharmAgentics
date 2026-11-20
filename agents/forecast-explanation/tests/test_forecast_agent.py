"""The question-driven Forecast engine (fcst-001): scope, discovery, comparisons, rules policy, writer invariants,
guardrails on the investigator's tools, and the model fallback. No model and no network: the rules policy runs."""
from __future__ import annotations

import re

import pytest

from pharmagentics.tools import DEFAULT_DB, Registry

from forecast_agent import answer
from forecast_agent.engine import Case, Refused
from forecast_agent.scope import intent_of, parse_scope

pytestmark = pytest.mark.skipif(not DEFAULT_DB.is_file(), reason="DuckDB not built; run the data loader")
FIRST, LATEST = "2024-10-14", "2026-10-05"


def case(question: str) -> Case:
    reg = Registry(DEFAULT_DB)
    return Case(reg, parse_scope(question, FIRST, LATEST))


@pytest.mark.parametrize("question,intent", [
    ("Week of 2026-05-04, New England: Is the deviation reliable, or a data issue?", "reliability"),
    ("Week of 2026-08-24: Which regions or segments drive the miss?", "where"),
    ("Week of 2026-08-24: How much of the miss does each driver explain?", "attribution"),
    ("Mar to Sep 2026: What are the most plausible commercial drivers?", "drivers"),
    ("Mar to Oct 2026: Should any forecast assumptions be reviewed?", "assumptions"),
    ("Top 5 largest gaps in the last 3 months", "screen"),
    ("Week of 2026-08-24: Is the explanation auditable and reconciled?", "audit"),
])
def test_intent(question, intent):
    assert intent_of(question) == intent


def test_relative_period_counts_back_from_the_latest_week():
    s = parse_scope("Top 5 largest gaps in the last 3 months", FIRST, LATEST)
    assert s.weeks[-1] == LATEST and len(s.weeks) == 13 and s.territory == "NATIONAL"


@pytest.mark.parametrize("question", ["What is the forecast miss for Metacora?",
                                      "Should we cut the budget for the Southeast?"])
def test_out_of_scope_questions_run_nothing(question):
    out = answer(question)
    assert out["abstained"] and not out["claims"] and out["report"]["out_of_scope"]


def test_national_week_reproduces_the_story_split():
    out = answer("Week of 2026-08-24: How much of the miss does each driver explain?")
    r = out["report"]
    assert r["variance_trx"] == -1036 and r["bias_trx"] == -32
    by = {d["driver"]: d for d in r["drivers"]}
    assert by["competitor"]["impact_trx"] == -655 and by["competitor"]["confidence"] == "medium"
    assert by["promotion"]["territory"] == "SOUTHEAST" and -230 < by["promotion"]["impact_trx"] < -195
    assert r["bias_trx"] + sum(d["impact_trx"] for d in r["drivers"]) + r["residual_trx"] == pytest.approx(-1036, abs=1)
    assert r["verification"]["verdict"] == "PASS"


def test_every_digit_in_an_answer_is_a_claim_value_or_a_date():
    out = answer("Mar to Sep 2026: What are the most plausible commercial drivers?")
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b|\b\w*[A-Za-z_]\w*\d\w*\b", " ", out["answer"])  # dates and identifiers
    for c in sorted(out["claims"], key=lambda c: -len(c["value"])):
        text = text.replace(c["value"], " ")
    assert not re.findall(r"\d", text)


def test_discovery_finds_the_episodes_without_a_calendar():
    c = case("Mar to Sep 2026: What are the most plausible commercial drivers?")
    found = {(e.driver, e.territory) for e in c.discover()}
    assert {("promotion", "GREAT_LAKES"), ("promotion", "SOUTHEAST"), ("supply", "PACIFIC"), ("competitor", "ALL")} <= found


def test_a_long_period_sets_aside_provisional_weeks_instead_of_abstaining():
    out = answer("Mar to Sep 2026: What are the most plausible commercial drivers?")
    r = out["report"]
    assert not r["abstained"] and set(r["set_aside_weeks"]) == {"2026-05-04", "2026-07-06"}
    assert {d["driver"] for d in r["drivers"]} == {"promotion", "supply", "competitor"}
    assert any(d["action"] == "set_aside_weeks" and d["by"] == "code" for d in r["decisions"])


def test_a_provisional_week_is_never_attributed():
    out = answer("Week of 2026-05-04, New England: Is the deviation reliable, or a data issue?")
    assert out["abstained"] and not out["report"]["drivers"] and "provisional" in out["answer"]


def test_mid_atlantic_access_is_quantified_against_clean_controls():
    out = answer("Weeks of 2025-08-04 to 2025-10-27, Mid-Atlantic: How much can credibly be attributed to each driver?")
    access = next(d for d in out["report"]["drivers"] if d["driver"] == "access")
    assert access["impact_trx"] == -693 and len(access["controls"]) == 7


def test_an_easing_that_reverses_a_restriction_is_not_a_new_episode():
    c = case("Mar to Sep 2026: What are the most plausible commercial drivers?")
    assert not [e for e in c.discover() if e.driver == "access"]


def test_tools_refuse_what_the_rules_do_not_allow():
    c = case("Week of 2026-08-24: How much of the miss does each driver explain?")
    eps = {e.driver: e for e in c.discover()}
    se = eps["promotion"]
    with pytest.raises(Refused, match="Unknown episode"):
        c.compare("E99")
    with pytest.raises(Refused, match="at least four"):
        c.compare(se.id, ["NEW_ENGLAND", "MID_ATLANTIC", "GREAT_LAKES", "SOUTH_CENTRAL"])
    with pytest.raises(Refused, match="call compare first"):
        c.accept(se.id, "K9", "a reason in words", "agent")
    k = c.compare(se.id)
    with pytest.raises(Refused, match="digits"):
        c.accept(se.id, k.id, "it fell by 60 percent", "agent")
    c.accept(se.id, k.id, "it fell well behind clean controls", "agent")
    assert c.accepted()[0][0].id == se.id


def test_a_dropped_control_changes_the_estimate_and_is_recorded():
    c = case("Week of 2026-08-24: How much of the miss does each driver explain?")
    se = next(e for e in c.discover() if e.driver == "promotion")
    default, dropped = c.compare(se.id), c.compare(se.id, ["SOUTH_CENTRAL"])
    assert "SOUTH_CENTRAL" not in dropped.controls and round(dropped.effect) == -204 and round(default.effect) == -213


@pytest.fixture
def no_language_model(monkeypatch):
    """Reading and writing without a model server: the reader and the writer report a model error."""
    import forecast_agent.prose as prose
    import forecast_agent.reader as reader
    from forecast_agent.scope import parse_scope as rules

    monkeypatch.setattr(reader, "read_scope", lambda q, f, l, spec: (rules(q, f, l), "rules"))
    monkeypatch.setattr(prose, "write_summary", lambda w, parts, spec: (None, "model_error"))


def test_a_failed_model_falls_back_to_the_rules(monkeypatch, no_language_model):
    import forecast_agent.agent as agent

    def broken(spec):
        raise RuntimeError("no model server")

    monkeypatch.setattr(agent, "chat_client", broken)
    out = answer("Week of 2026-08-24: How much of the miss does each driver explain?", model="ollama:none",
                 investigator="model")
    assert out["trajectory"]["fallback"] and "rules fallback" in out["report"]["investigator_mode"]
    assert {d["driver"] for d in out["report"]["drivers"]} == {"competitor", "promotion"}


def test_candidates_a_model_leaves_open_are_decided_by_the_rules_and_labelled(monkeypatch, no_language_model):
    import forecast_agent.agent as agent

    class Silent:  # a model that answers without calling any tool
        def __init__(self, *a, **k):
            pass

        async def run(self, *a, **k):
            return None

    monkeypatch.setattr(agent, "Agent", Silent)
    monkeypatch.setattr(agent, "chat_client", lambda spec: None)
    monkeypatch.setattr(agent, "chat_options", lambda spec: {})
    out = answer("Week of 2026-08-24: How much of the miss does each driver explain?", model="ollama:none",
                 investigator="model")
    assert out["trajectory"]["left_undecided"] == 2 and not out["trajectory"]["fallback"]
    assert {d["by"] for d in out["report"]["decisions"]} == {"rules (agent left it undecided)"}
    assert {d["driver"] for d in out["report"]["drivers"]} == {"competitor", "promotion"}


def test_with_a_model_the_rules_still_investigate_by_default(no_language_model):
    out = answer("Week of 2026-08-24: How much of the miss does each driver explain?", model="ollama:none")
    assert out["report"]["investigator_mode"] == "rules" and out["trajectory"]["investigator"] == "rules"
    assert out["report"]["summary_by"] == "code" and out["trajectory"]["writer_status"] == "model_error"


def test_a_confirmed_scope_skips_reading(no_language_model):
    out = answer("Why did we miss?", model="ollama:none", territory="PACIFIC", weeks=["2026-06-01", "2026-06-08"],
                 intent="drivers")
    r = out["report"]
    assert r["scope_read_by"] == "confirmed" and r["intent"] == "drivers" and r["territory_id"] == "PACIFIC"


@pytest.mark.parametrize("start,end,weeks", [
    ("2026-08-24", "2026-08-24", ["2026-08-24"]),
    ("2026-05-06", "2026-05-06", ["2026-05-04"]),
    ("2026-08-01", "2026-08-31", ["2026-08-03", "2026-08-10", "2026-08-17", "2026-08-24", "2026-08-31"]),
    ("2027-01-01", "2027-02-01", []),
])
def test_the_reader_turns_calendar_dates_into_release_weeks(start, end, weeks):
    from forecast_agent.reader import _period
    assert _period(start, end, FIRST, LATEST) == weeks


def test_the_summary_check_refuses_what_a_model_must_not_write():
    from forecast_agent.prose import check
    tokens = [{"token": "{c1}", "means": "miss"}, {"token": "{c2}", "means": "residual"}]
    allowed = {"drivers": {"promotion"}, "territories": {"NATIONAL", "SOUTHEAST"}, "residual": "{c2}"}
    ok = "Cardiovela missed by {c1}, mostly from the Southeast rep coverage lapse; {c2} is not explained yet."
    assert check(ok, tokens, allowed) is None
    assert check(ok.replace("{c1}", "about 1,000"), tokens, allowed) == "digit_outside_token"
    assert check(ok + " Also {c9}.", tokens, allowed) == "unknown_token"
    assert check("Cardiovela missed by {c1} in the Southeast.", tokens, allowed) == "residual_missing"
    assert check(ok + " We should cut the budget there.", tokens, allowed) == "commercial_action"
    assert check(ok + " Supply was tight too.", tokens, allowed) == "new_driver"
    assert check(ok + " Pacific also fell.", tokens, allowed) == "new_territory"

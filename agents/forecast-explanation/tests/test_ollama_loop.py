import json

import pytest

from feagent import store
from feagent.investigator import MAX_UNUSABLE_REPLIES, run_investigation
from feagent.schema import InvestigationRequest
from feagent.shared_world import available as shared_available
from feagent.shared_world import resolve_week
from feagent.store import reset
from feagent.tools import run_tool

requires_shared = pytest.mark.skipif(
    not shared_available(),
    reason="PharmAgentics data/agent_visible not found; set PHARMAGENTICS_DATA_DIR",
)


class ScriptedClient:
    """Stands in for Ollama. A reply is a dict, a raw string, or a function of the messages so far."""

    name = "scripted"
    model = "scripted-model"

    def __init__(self, replies, available=True):
        self.replies = list(replies)
        self.calls = 0
        self.messages = []
        self._available = available

    def available(self):
        return (True, "ok") if self._available else (False, "scripted client is down")

    def complete(self, messages):
        self.calls += 1
        self.messages = list(messages)
        reply = self.replies.pop(0)
        if callable(reply):
            reply = reply(messages)
        return reply if isinstance(reply, str) else json.dumps(reply)


def tool_ids(messages, name):
    ids = []
    for message in messages:
        if message["role"] != "user":
            continue
        try:
            record = json.loads(message["content"]).get("tool_result")
        except ValueError:
            continue
        if record and record["name"] == name:
            ids.append(record["tool_id"])
    return ids


def tool(name, **arguments):
    return {"action": "tool", "name": name, "arguments": arguments}


def final(**report):
    return {"action": "final", "report": report}


def request():
    reset()
    return InvestigationRequest.from_dict(
        {
            "request_id": "req_lumina_w18",
            "source": "manual",
            "brand": "LUMINA",
            "week": 18,
            "week_ending": "2026-05-08",
            "metric": "TRx",
        }
    )


def good_run():
    def answer(messages):
        payer, competitor = tool_ids(messages, "compare_exposed_control")
        return final(
            headline="LUMINA missed forecast in week 18.",
            drivers=[
                {"driver": "payer_access", "impact_trx": -1350, "confidence": "high", "evidence_ids": [payer]},
                {"driver": "competitor_activity", "impact_trx": -650, "confidence": "high", "evidence_ids": [competitor]},
            ],
            what_to_check=[{"question": "Inspect the residual", "why": "-400 remains", "owner": "Forecasting"}],
            caveats=["scripted run"],
            abstained=False,
        )

    return [
        tool("validate_and_quantify", week=18),
        tool("list_candidate_events", week=18),
        tool("compare_exposed_control", event_id="evt_payer_001", week=18),
        tool("compare_exposed_control", event_id="evt_comp_001", week=18),
        answer,
    ]


def test_tool_with_a_stray_case_id_does_not_crash():
    record = run_tool(
        "reconcile_attribution",
        {"variance_trx": -100.0, "driver_impacts": {"a": -50.0}, "case_id": "week18"},
    )
    assert record["payload"]["residual_trx"] == -50.0


def test_scripted_model_run_is_verified_against_the_tools():
    client = ScriptedClient(good_run())
    report = run_investigation(request(), mode="ollama", client=client)
    assert report.investigator_mode == "ollama"
    assert [d.impact_trx for d in report.drivers] == [-1350, -650]
    assert report.residual_trx == -400
    assert report.verification["verdict"] == "PASS"


def test_model_calling_reconcile_does_not_crash_the_loop():
    client = ScriptedClient(
        [
            tool("validate_and_quantify", week=18),
            tool("reconcile_attribution", variance_trx=-2400, driver_impacts={"payer_access": -1350}),
            final(headline="h", drivers=[], what_to_check=[], caveats=[], abstained=False),
        ]
    )
    report = run_investigation(request(), mode="ollama", client=client)
    reconciled = [rec for rec in report.evidence if rec.name == "reconcile_attribution"]
    assert reconciled[0].payload["residual_trx"] == -1050
    assert "error" not in reconciled[0].payload


def test_reply_that_is_not_json_gets_a_second_chance():
    client = ScriptedClient(
        [
            "I believe the payer change explains it.",
            tool("validate_and_quantify", week=18),
            final(headline="h", drivers=[], what_to_check=[], caveats=[], abstained=False),
        ]
    )
    report = run_investigation(request(), mode="ollama", client=client)
    assert report.investigator_mode == "ollama"
    assert client.calls == 3
    assert any("not valid JSON" in message["content"] for message in client.messages)


def test_unknown_tool_is_reported_back_to_the_model():
    client = ScriptedClient(
        [
            tool("magic_tool", week=18),
            final(headline="h", drivers=[], what_to_check=[], caveats=[], abstained=False),
        ]
    )
    report = run_investigation(request(), mode="ollama", client=client)
    assert "Unknown tool magic_tool" in json.dumps([m["content"] for m in client.messages])
    assert report.verification["verdict"] in {"PASS", "WARN", "FAIL"}


def test_tool_that_raises_is_reported_back_not_raised():
    client = ScriptedClient(
        [
            tool("compare_exposed_control", event_id="evt_payer_001", week="eighteen"),
            final(headline="h", drivers=[], what_to_check=[], caveats=[], abstained=False),
        ]
    )
    report = run_investigation(request(), mode="ollama", client=client)
    failed = [rec for rec in report.evidence if rec.name == "compare_exposed_control"]
    assert failed and failed[0].payload["ok"] is False
    assert "TypeError" in failed[0].payload["error"]


def test_malformed_final_report_gets_a_chance_to_fix_itself():
    client = ScriptedClient(
        [
            tool("validate_and_quantify", week=18),
            final(headline="h", drivers=[{"driver": "payer_access"}], what_to_check=[], caveats=[]),
            final(headline="h", drivers=[], what_to_check=[], caveats=[], abstained=False),
        ]
    )
    report = run_investigation(request(), mode="ollama", client=client)
    assert client.calls == 3
    assert report.drivers == []


def test_model_that_never_answers_properly_is_cut_off():
    client = ScriptedClient(["nope"] * (MAX_UNUSABLE_REPLIES + 1))
    with pytest.raises(RuntimeError, match="unusable replies"):
        run_investigation(request(), mode="ollama", client=client)


def test_report_is_always_about_the_requested_week():
    client = ScriptedClient(
        [
            tool("validate_and_quantify", week=17),
            final(headline="h", drivers=[], what_to_check=[], caveats=[], abstained=False),
        ]
    )
    report = run_investigation(request(), mode="ollama", client=client)
    assert report.week == 18
    assert report.variance_trx == -2400
    assert report.verification["checks"][0]["id"] == "scope_matches_request"
    assert report.verification["checks"][0]["status"] == "pass"


def test_unrecognised_confidence_becomes_low():
    client = ScriptedClient(
        [
            tool("validate_and_quantify", week=18),
            tool("list_candidate_events", week=18),
            tool("compare_exposed_control", event_id="evt_payer_001", week=18),
            lambda messages: final(
                headline="h",
                drivers=[
                    {
                        "driver": "payer_access",
                        "impact_trx": -1350,
                        "confidence": "extremely sure",
                        "evidence_ids": tool_ids(messages, "compare_exposed_control"),
                    }
                ],
                what_to_check=[],
                caveats=[],
                abstained=False,
            ),
        ]
    )
    report = run_investigation(request(), mode="ollama", client=client)
    assert report.drivers[0].confidence == "low"


def test_auto_mode_falls_back_to_the_stub_when_ollama_is_down():
    report = run_investigation(request(), mode="auto", client=ScriptedClient([], available=False))
    assert report.investigator_mode == "stub"
    assert report.variance_trx == -2400


def test_auto_mode_falls_back_to_the_stub_when_the_model_fails():
    client = ScriptedClient(["nope"] * (MAX_UNUSABLE_REPLIES + 1))
    report = run_investigation(request(), mode="auto", client=client)
    assert report.investigator_mode == "stub"


@requires_shared
@pytest.mark.parametrize("mode", ["ollama", "auto"])
def test_provisional_actual_is_withheld_before_any_model_is_called(mode):
    reset()
    store.use_world("shared")
    store.connect()
    asked = InvestigationRequest.from_dict(
        {
            "request_id": "fcst_ne",
            "source": "manual",
            "brand": "BXA Cardiovela",
            "week_start": "2026-05-04",
            "territory_id": "NEW_ENGLAND",
            "metric": "TRx",
        }
    )
    asked.week = int(resolve_week(None, "2026-05-04")["week"])
    client = ScriptedClient([])
    report = run_investigation(asked, mode=mode, client=client)
    assert client.calls == 0
    assert report.abstained is True
    assert report.drivers == []
    assert report.investigator_mode == "gate"
    assert report.verification["verdict"] == "PASS"


def _driver_run(confidence, evidence_ids=None):
    def answer(messages):
        payer = tool_ids(messages, "compare_exposed_control")[0]
        return final(
            headline="h",
            drivers=[
                {
                    "driver": "payer_access",
                    "impact_trx": -1350,
                    "confidence": confidence,
                    "evidence_ids": [payer] if evidence_ids is None else evidence_ids,
                }
            ],
            what_to_check=[],
            caveats=[],
            abstained=False,
        )

    return [
        tool("validate_and_quantify", week=18),
        tool("list_candidate_events", week=18),
        tool("compare_exposed_control", event_id="evt_payer_001", week=18),
        answer,
    ]


def test_a_model_cannot_claim_more_confidence_than_the_evidence_supports():
    report = run_investigation(request(), mode="ollama", client=ScriptedClient(_driver_run("high")))
    driver = report.drivers[0]
    assert driver.confidence == "medium"
    assert any("model stated high; capped to medium" in r for r in driver.confidence_reasons)
    assert report.verification["verdict"] != "FAIL"


def test_a_model_may_state_less_confidence_than_the_cap():
    report = run_investigation(request(), mode="ollama", client=ScriptedClient(_driver_run("low")))
    driver = report.drivers[0]
    assert driver.confidence == "low"
    assert not any("capped" in r for r in driver.confidence_reasons)


def test_a_driver_with_no_supporting_tool_result_is_inconclusive_and_fails_verification():
    report = run_investigation(
        request(), mode="ollama", client=ScriptedClient(_driver_run("high", evidence_ids=["t_made_up"]))
    )
    assert report.drivers[0].confidence == "inconclusive"
    assert report.verification["verdict"] == "FAIL"


def test_a_bare_report_object_is_accepted_as_the_final_answer():
    bare = {"headline": "h", "drivers": [], "what_to_check": [], "caveats": [], "abstained": False}
    client = ScriptedClient([tool("validate_and_quantify", week=18), bare])
    report = run_investigation(request(), mode="ollama", client=client)
    assert client.calls == 2
    assert report.headline == "h"


def test_a_model_that_needs_ten_steps_still_finishes_under_the_default_limit():
    client = ScriptedClient(
        [tool("get_region_deltas", week=18) for _ in range(9)]
        + [final(headline="h", drivers=[], what_to_check=[], caveats=[], abstained=False)]
    )
    report = run_investigation(request(), mode="ollama", client=client)
    assert client.calls == 10
    assert report.headline == "h"


def test_the_report_keeps_the_requested_window_even_if_the_model_queries_one_week():
    asked = request()
    asked.window_weeks = 2

    def answer(messages):
        payer = tool_ids(messages, "compare_exposed_control")[0]
        return final(
            headline="h",
            drivers=[{"driver": "payer_access", "impact_trx": -2700, "confidence": "low", "evidence_ids": [payer]}],
            what_to_check=[],
            caveats=[],
            abstained=False,
        )

    client = ScriptedClient(
        [
            tool("validate_and_quantify", week=18, window_weeks=1),
            tool("list_candidate_events", week=18),
            tool("compare_exposed_control", event_id="evt_payer_001", week=18),
            answer,
        ]
    )
    report = run_investigation(asked, mode="ollama", client=client)
    assert report.window_weeks == 2
    assert report.variance_trx == -4800
    contrast = next(rec for rec in report.evidence if rec.name == "compare_exposed_control")
    assert contrast.arguments["window_weeks"] == 2
    assert report.verification["verdict"] != "FAIL"


def test_a_model_cannot_change_the_window_the_request_fixed():
    asked = request()
    asked.window_weeks = 2
    client = ScriptedClient(
        [
            tool("validate_and_quantify", week=18, window_weeks=1),
            tool("get_region_deltas", week=18, window_weeks=1),
            tool("list_candidate_events", week=18, window_weeks=1),
            tool("compare_exposed_control", event_id="evt_payer_001", week=18, window_weeks=1),
            final(headline="h", drivers=[], what_to_check=[], caveats=[], abstained=False),
        ]
    )
    report = run_investigation(asked, mode="ollama", client=client)
    windows = {rec.name: rec.arguments["window_weeks"] for rec in report.evidence if "window_weeks" in rec.arguments}
    assert set(windows.values()) == {2}
    assert set(windows) >= {"validate_and_quantify", "get_region_deltas", "list_candidate_events", "compare_exposed_control"}

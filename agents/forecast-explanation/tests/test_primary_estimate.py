import copy
import json

import pytest

from feagent import store
from feagent.investigator import run_investigation
from feagent.schema import InvestigationRequest
from feagent.shared_world import available as shared_available
from feagent.shared_world import resolve_week
from feagent.store import reset
from feagent.tools import baseline_change_estimate, compare_exposed_control, primary_estimate
from feagent.verify import verify_report

requires_shared = pytest.mark.skipif(
    not shared_available(),
    reason="PharmAgentics data/agent_visible not found; set PHARMAGENTICS_DATA_DIR",
)


def lumina_request(territory_id=None):
    reset()
    payload = {
        "request_id": "req_lumina_w18",
        "source": "manual",
        "brand": "LUMINA",
        "week": 18,
        "week_ending": "2026-05-08",
        "metric": "TRx",
    }
    if territory_id:
        payload["territory_id"] = territory_id
    return InvestigationRequest.from_dict(payload)


def failing(result):
    return {c["id"] for c in result["checks"] if c["status"] == "fail"}


def warning(result):
    return {c["id"] for c in result["checks"] if c["status"] == "warn"}


def test_the_regional_effects_add_up_to_the_total():
    reset()
    payload = compare_exposed_control("evt_payer_001", week=18, window_weeks=2)["payload"]
    by_region = payload["effect_by_exposed_region"]
    assert set(by_region) == {"Northeast", "South"}
    assert sum(by_region.values()) == pytest.approx(payload["estimated_total_trx"])
    assert payload["estimate_per_exposed_region"] == pytest.approx(payload["estimated_total_trx"] / 2)


def test_each_exposed_region_gets_its_own_effect_from_its_own_error():
    reset()
    view = compare_exposed_control("evt_payer_001", week=18)["payload"]["forecast_error_view"]
    rows = {row["region"]: row for row in view["by_region"]}
    assert rows["Northeast"]["error_trx"] == -775
    assert rows["Northeast"]["forecast_trx"] == 3000
    assert rows["Northeast"]["effect_trx"] == -675
    assert view["n_controls"] == 1


def test_the_helpers_pick_the_national_total_or_one_territorys_share():
    reset()
    payload = compare_exposed_control("evt_payer_001", week=18)["payload"]
    assert primary_estimate(payload) == -1350
    assert primary_estimate(payload, "Northeast") == -675
    assert primary_estimate(payload, "West") is None
    assert baseline_change_estimate(payload) == pytest.approx(-1350)
    assert baseline_change_estimate(payload, "Northeast") == pytest.approx(-675)


def test_an_event_without_controls_has_no_primary_estimate_and_no_cross_check():
    reset()
    store.connect().execute("UPDATE commercial_events SET control_regions = '[]' WHERE event_id = 'evt_payer_001'")
    payload = compare_exposed_control("evt_payer_001", week=18)["payload"]
    assert primary_estimate(payload) is None
    assert baseline_change_estimate(payload) is None
    assert payload["effect_by_exposed_region"] == {}


def test_a_territory_report_uses_that_territorys_effect_not_the_national_total():
    asked = lumina_request("Northeast")
    report = run_investigation(asked, mode="stub")
    assert [(d.driver, d.impact_trx) for d in report.drivers] == [("payer_access", -675)]
    assert report.verification["verdict"] == "PASS"
    forged = copy.deepcopy(report)
    forged.drivers[0].impact_trx = -1350
    forged.residual_trx = forged.variance_trx - forged.drivers[0].impact_trx
    assert "driver_evidence:payer_access" in failing(verify_report(forged, asked))


def test_estimators_that_agree_raise_no_warning():
    asked = lumina_request()
    report = run_investigation(asked, mode="stub")
    checks = {c["id"]: c["status"] for c in report.verification["checks"]}
    assert checks["estimator_agreement:payer_access"] == "pass"
    assert checks["estimator_agreement:competitor_activity"] == "pass"


def test_a_cross_check_that_disagrees_is_a_warning_and_lowers_the_cap():
    asked = lumina_request()
    report = run_investigation(asked, mode="stub")
    tampered = copy.deepcopy(report)
    payer = next(rec for rec in tampered.evidence if rec.payload.get("driver") == "payer_access")
    payer.payload["baseline_change_total_trx"] = -100.0
    result = verify_report(tampered, asked)
    assert "estimator_agreement:payer_access" in warning(result)
    assert "driver_confidence:payer_access" not in failing(result)


def test_the_method_name_says_what_the_estimate_is():
    reset()
    payload = compare_exposed_control("evt_payer_001", week=18)["payload"]
    assert payload["method"] == "forecast_error_difference_vs_named_controls"
    assert "baseline-change" in payload["assumption"]


@requires_shared
def test_the_southeast_promotion_estimators_agree_and_both_are_reported():
    reset()
    store.use_world("shared")
    store.connect()
    week = int(resolve_week(None, "2026-08-24")["week"])
    payload = compare_exposed_control("evt_promo_southeast", week)["payload"]
    assert primary_estimate(payload) == pytest.approx(-211.8, abs=0.1)
    assert baseline_change_estimate(payload) == pytest.approx(-225.0)
    assert primary_estimate(payload, "SOUTHEAST") == pytest.approx(primary_estimate(payload))
    assert primary_estimate(payload, "PACIFIC") is None


@requires_shared
def test_the_regional_effects_add_up_to_the_total_on_the_real_window():
    reset()
    store.use_world("shared")
    store.connect()
    week = int(resolve_week(None, "2025-08-04")["week"])
    payload = compare_exposed_control("evt_access_mid_atlantic", week, window_weeks=13)["payload"]
    assert sum(payload["effect_by_exposed_region"].values()) == pytest.approx(payload["estimated_total_trx"])


class ScriptedClient:
    name = "scripted"
    model = "scripted-model"

    def __init__(self, replies):
        self.replies = list(replies)

    def available(self):
        return True, "ok"

    def complete(self, messages):
        reply = self.replies.pop(0)
        reply = reply(messages) if callable(reply) else reply
        return reply if isinstance(reply, str) else json.dumps(reply)


def _tool_id(messages, name):
    for message in messages:
        if message["role"] == "user":
            try:
                record = json.loads(message["content"]).get("tool_result")
            except ValueError:
                continue
            if record and record["name"] == name:
                return record["tool_id"]


def _model_run(impact):
    return ScriptedClient(
        [
            {"action": "tool", "name": "validate_and_quantify", "arguments": {"week": 98, "territory_id": "SOUTHEAST"}},
            {"action": "tool", "name": "compare_exposed_control", "arguments": {"event_id": "evt_promo_southeast", "week": 98}},
            lambda messages: {
                "action": "final",
                "report": {
                    "headline": "h",
                    "drivers": [
                        {
                            "driver": "promotion",
                            "impact_trx": impact,
                            "confidence": "high",
                            "evidence_ids": [_tool_id(messages, "compare_exposed_control")],
                        }
                    ],
                    "what_to_check": [],
                    "caveats": [],
                    "abstained": False,
                },
            },
        ]
    )


def _southeast_request():
    reset()
    store.use_world("shared")
    store.connect()
    asked = InvestigationRequest.from_dict(
        {
            "request_id": "fcst_se",
            "source": "manual",
            "brand": "BXA Cardiovela",
            "week_start": "2026-08-24",
            "territory_id": "SOUTHEAST",
            "metric": "TRx",
        }
    )
    asked.week = int(resolve_week(None, "2026-08-24")["week"])
    return asked


@requires_shared
def test_a_model_that_quotes_the_old_baseline_figure_instead_of_the_primary_estimate_fails():
    report = run_investigation(_southeast_request(), mode="ollama", client=_model_run(-225.0))
    assert "driver_evidence:promotion" in failing(report.verification)


@requires_shared
def test_a_model_that_quotes_the_primary_estimate_passes_the_evidence_check():
    report = run_investigation(_southeast_request(), mode="ollama", client=_model_run(-211.8))
    assert "driver_evidence:promotion" not in failing(report.verification)
    assert report.drivers[0].confidence == "high"

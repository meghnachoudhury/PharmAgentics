import copy
import json

import pytest

from feagent import store
from feagent.investigator import run_investigation
from feagent.pipeline import FORECAST_LANE_CASES, run_forecast_pipeline
from feagent.schema import InvestigationRequest
from feagent.shared_world import available as shared_available
from feagent.shared_world import resolve_week
from feagent.store import reset
from feagent.tools import compare_exposed_control, list_candidate_events, validate_and_quantify
from feagent.verify import verify_report

requires_shared = pytest.mark.skipif(
    not shared_available(),
    reason="PharmAgentics data/agent_visible not found; set PHARMAGENTICS_DATA_DIR",
)


def lumina_payload(**extra):
    return {
        "request_id": "req_lumina_w18",
        "source": "manual",
        "brand": "LUMINA",
        "week": 18,
        "week_ending": "2026-05-08",
        "metric": "TRx",
        **extra,
    }


def lumina_request(**extra):
    reset()
    return InvestigationRequest.from_dict(lumina_payload(**extra))


def test_a_request_defaults_to_one_week():
    assert InvestigationRequest.from_dict(lumina_payload()).window_weeks == 1
    assert InvestigationRequest.from_dict(lumina_payload(window_weeks=None)).window_weeks == 1


def test_a_window_is_parsed_and_bounded():
    assert InvestigationRequest.from_dict(lumina_payload(window_weeks="13")).window_weeks == 13
    for bad in (0, -1, 53, "many"):
        with pytest.raises(ValueError):
            InvestigationRequest.from_dict(lumina_payload(window_weeks=bad))


def test_the_window_sums_forecast_and_actual_across_weeks():
    reset()
    q = validate_and_quantify(17, window_weeks=3)["payload"]
    assert (q["forecast"], q["actual"], q["variance_trx"]) == (36000, 31200, -4800)
    assert q["window_weeks"] == 3
    assert q["week"] == 17
    assert q["week_ending"] == "2026-05-15"


def test_one_week_is_still_the_default_window():
    reset()
    q = validate_and_quantify(18)["payload"]
    assert (q["forecast"], q["actual"], q["window_weeks"]) == (12000, 9600, 1)


def test_a_window_that_runs_past_the_data_is_an_error_not_a_partial_sum():
    reset()
    q = validate_and_quantify(23, window_weeks=3)["payload"]
    assert q["ok"] is False
    assert "2 of 3 weeks" in q["error"]


def test_candidate_events_cover_the_whole_window():
    reset()
    assert list_candidate_events(14)["payload"]["n_events"] == 0
    assert list_candidate_events(14, window_weeks=3)["payload"]["n_events"] == 2


def test_the_event_contrast_is_the_sum_of_the_weekly_contrasts():
    reset()
    payload = compare_exposed_control("evt_payer_001", week=18, window_weeks=2)["payload"]
    assert [row["did_per_exposed_region"] for row in payload["weekly_did"]] == [-675, -675]
    assert payload["baseline_change_per_exposed_region"] == -1350
    assert payload["baseline_change_total_trx"] == -2700
    assert payload["estimated_total_trx"] == -2700
    assert payload["window_weeks"] == 2
    assert {row["delta"] for row in payload["exposed_detail"]} == {-1550}


def test_with_a_flat_forecast_the_baseline_cross_check_agrees_with_the_primary_estimate():
    reset()
    payload = compare_exposed_control("evt_payer_001", week=18, window_weeks=2)["payload"]
    view = payload["forecast_error_view"]
    assert payload["baseline_change_total_trx"] == pytest.approx(payload["estimated_total_trx"])
    assert view["effect_trx"] == payload["estimated_total_trx"]
    assert view["exposed_error_trx"] == -3100
    assert view["control_error_rate_spread"] is None


def test_an_event_without_controls_has_no_forecast_error_view():
    reset()
    store.connect()
    store.connect().execute("UPDATE commercial_events SET control_regions = '[]' WHERE event_id = 'evt_payer_001'")
    payload = compare_exposed_control("evt_payer_001", week=18, window_weeks=2)["payload"]
    assert payload["forecast_error_view"] is None
    assert payload["estimated_total_trx"] is None


def test_the_stub_explains_a_two_week_window_end_to_end():
    asked = lumina_request(window_weeks=2)
    report = run_investigation(asked, mode="stub")
    impacts = {d.driver: d.impact_trx for d in report.drivers}
    assert report.window_weeks == 2
    assert report.variance_trx == -4800
    assert impacts == {"payer_access": -2700, "competitor_activity": -1300}
    assert report.residual_trx == -800
    assert "over the 2 weeks ending" in report.headline
    assert report.verification["verdict"] == "PASS"


def test_a_report_for_another_window_fails_the_scope_check():
    report = run_investigation(lumina_request(window_weeks=2), mode="stub")
    one_week = lumina_request()
    result = verify_report(report, one_week)
    assert "scope_matches_request" in {c["id"] for c in result["checks"] if c["status"] == "fail"}


def test_a_driver_citing_evidence_from_another_window_fails():
    asked = lumina_request(window_weeks=2)
    report = run_investigation(asked, mode="stub")
    forged = copy.deepcopy(report)
    for rec in forged.evidence:
        if rec.name == "compare_exposed_control":
            rec.arguments["window_weeks"] = 1
    failed = {c["id"] for c in verify_report(forged, asked)["checks"] if c["status"] == "fail"}
    assert failed >= {"driver_evidence:payer_access", "driver_evidence:competitor_activity"}


def test_the_pipeline_pins_the_window_and_says_so():
    reset()
    run = run_forecast_pipeline(lumina_payload(window_weeks=2), mode="stub")
    assert run["pin"]["window_weeks"] == 2
    assert run["stages"][2]["summary"].endswith("over 2 weeks")
    assert run["report"]["window_weeks"] == 2
    other = run_forecast_pipeline(lumina_payload(), mode="stub")
    assert other["fingerprint"] != run["fingerprint"]


def test_the_pipeline_rejects_a_window_that_runs_past_the_data():
    reset()
    with pytest.raises(ValueError, match="of 3 weeks"):
        run_forecast_pipeline(lumina_payload(week=23, window_weeks=3), mode="stub")


@requires_shared
def test_the_mid_atlantic_card_is_a_thirteen_week_window():
    card = next(c for c in FORECAST_LANE_CASES if c["case_id"].startswith("mid-atlantic"))
    assert card["request"]["window_weeks"] == 13
    reset()
    run = run_forecast_pipeline(card["request"], mode="stub")
    report = run["report"]
    assert (report["forecast_trx"], report["actual_trx"], report["variance_trx"]) == (9884, 9154, -730)
    assert report["window_weeks"] == 13
    assert "over the 13 weeks ending 2025-11-02" in report["headline"]
    assert run["stages"][2]["summary"] == "V = -730 TRx (-7.4%) over 13 weeks"


@requires_shared
def test_the_baseline_contrast_over_thirteen_weeks_matches_the_raw_csv():
    reset()
    store.use_world("shared")
    store.connect()
    week = int(resolve_week(None, "2025-08-04")["week"])
    payload = compare_exposed_control("evt_access_mid_atlantic", week, window_weeks=13)["payload"]
    assert payload["baseline_week"] == 42
    assert payload["exposed_mean_delta"] == 951
    assert payload["baseline_change_per_exposed_region"] == pytest.approx(138.714, abs=0.01)
    assert len(payload["weekly_did"]) == 13


@requires_shared
def test_the_primary_estimate_recovers_an_effect_the_baseline_contrast_cannot():
    reset()
    store.use_world("shared")
    store.connect()
    week = int(resolve_week(None, "2025-08-04")["week"])
    payload = compare_exposed_control("evt_access_mid_atlantic", week, window_weeks=13)["payload"]
    assert payload["estimated_total_trx"] == pytest.approx(-679.4, abs=0.5)
    assert payload["baseline_change_total_trx"] == pytest.approx(138.7, abs=0.1)
    view = payload["forecast_error_view"]
    assert view["exposed_error_trx"] == -730
    assert view["exposed_error_rate"] == pytest.approx(-0.0739, abs=0.0005)
    assert view["control_error_rate_mean"] == pytest.approx(-0.0051, abs=0.0005)
    assert view["control_error_rate_spread"] == pytest.approx(0.0207, abs=0.0005)
    assert view["effect_trx"] == pytest.approx(-679.4, abs=0.5)


@requires_shared
def test_the_thirteen_week_card_explains_the_miss_but_is_flagged_for_the_disagreeing_cross_check():
    card = next(c for c in FORECAST_LANE_CASES if c["case_id"].startswith("mid-atlantic"))
    reset()
    run = run_forecast_pipeline(card["request"], mode="stub")
    report = run["report"]
    (driver,) = report["drivers"]
    assert driver["impact_trx"] == pytest.approx(-679.4, abs=0.5)
    assert driver["confidence"] == "medium"
    assert abs(report["residual_trx"]) < 60
    stage = run["stages"][5]
    assert stage["status"] == "FLAG"
    assert {c["id"] for c in stage["result"]["checks"] if c["status"] == "warn"} == {
        "estimator_agreement:payer_access"
    }


@requires_shared
def test_a_provisional_week_anywhere_in_the_window_withholds_attribution():
    reset()
    store.use_world("shared")
    store.connect()
    week = int(resolve_week(None, "2026-05-04")["week"])
    payload = validate_and_quantify(week - 1, territory_id="NEW_ENGLAND", window_weeks=2)["payload"]
    assert payload["actual_is_provisional"] is True
    assert payload["provisional_weeks"] == [week]


@requires_shared
def test_the_default_for_a_card_without_a_window_is_still_one_week():
    reset()
    run = run_forecast_pipeline(
        {
            "request_id": "ma",
            "source": "manual",
            "brand": "BXA Cardiovela",
            "week_start": "2025-08-04",
            "territory_id": "MID_ATLANTIC",
            "metric": "TRx",
        },
        mode="stub",
    )
    assert run["report"]["window_weeks"] == 1
    assert run["report"]["variance_trx"] == -34
    json.dumps(run)

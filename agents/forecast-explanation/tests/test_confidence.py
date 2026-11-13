import copy

import pytest

from feagent.confidence import MIN_CONTROLS_FOR_HIGH, assess_confidence, capped
from feagent.investigator import run_investigation
from feagent.pipeline import run_forecast_pipeline
from feagent.schema import InvestigationRequest
from feagent.shared_world import available as shared_available
from feagent.store import reset
from feagent.verify import verify_report

requires_shared = pytest.mark.skipif(
    not shared_available(),
    reason="PharmAgentics data/agent_visible not found; set PHARMAGENTICS_DATA_DIR",
)


def contrast(
    effect=-225.0,
    n_controls=7,
    exposed_rate=-0.42,
    control_mean=-0.16,
    spread=0.05,
    cross=None,
    region="R0",
):
    """A compare_exposed_control payload with only the fields the confidence rule reads."""
    if n_controls == 0:
        return {"forecast_error_view": None, "estimated_total_trx": None, "effect_by_exposed_region": {}}
    return {
        "forecast_error_view": {
            "n_controls": n_controls,
            "exposed_error_rate": exposed_rate,
            "control_error_rate_mean": control_mean,
            "control_error_rate_spread": spread,
            "by_region": [{"region": region, "error_rate": exposed_rate, "effect_trx": effect}],
        },
        "estimated_total_trx": effect,
        "effect_by_exposed_region": {region: effect},
        "baseline_change_total_trx": effect if cross is None else cross,
        "baseline_change_per_exposed_region": effect if cross is None else cross,
    }


def test_a_clean_contrast_earns_high():
    assert assess_confidence(contrast(), variance_trx=-343) == ("high", [])


def test_no_control_is_inconclusive():
    level, reasons = assess_confidence(contrast(n_controls=0), variance_trx=-343)
    assert level == "inconclusive"
    assert "no control region" in reasons[0]


def test_a_single_control_caps_at_medium():
    level, reasons = assess_confidence(contrast(n_controls=1, spread=None), variance_trx=-343)
    assert level == "medium"
    assert f"at least {MIN_CONTROLS_FOR_HIGH}" in reasons[0]


def test_an_estimate_against_the_miss_is_low():
    level, reasons = assess_confidence(contrast(effect=+80.0), variance_trx=-343)
    assert level == "low"
    assert any("against the miss" in r for r in reasons)


def test_a_gap_inside_the_control_noise_is_low():
    level, reasons = assess_confidence(contrast(exposed_rate=-0.20, control_mean=-0.16), variance_trx=-343)
    assert level == "low"
    assert any("within 2x the spread" in r for r in reasons)


def test_a_gap_between_two_and_three_times_the_noise_is_medium():
    level, reasons = assess_confidence(contrast(exposed_rate=-0.28, control_mean=-0.16), variance_trx=-343)
    assert level == "medium"
    assert any("under 3x the spread" in r for r in reasons)


def test_a_cross_check_that_disagrees_caps_at_medium():
    level, reasons = assess_confidence(contrast(effect=-679.0, cross=+139.0), variance_trx=-730)
    assert level == "medium"
    assert any("cross-check" in r for r in reasons)


def test_a_cross_check_that_roughly_agrees_does_not_cap():
    assert assess_confidence(contrast(effect=-212.0, cross=-225.0), variance_trx=-343) == ("high", [])


def test_the_lowest_cap_wins_and_every_reason_is_kept():
    level, reasons = assess_confidence(
        contrast(effect=+80.0, n_controls=1, spread=None, cross=-300.0), variance_trx=-343
    )
    assert level == "low"
    assert len(reasons) == 3


def test_a_zero_variance_does_not_trip_the_direction_or_agreement_rules():
    assert assess_confidence(contrast(effect=+80.0, cross=-300.0), variance_trx=0)[0] == "high"


def test_a_territory_is_judged_on_its_own_error_rate():
    payload = contrast(exposed_rate=-0.42, control_mean=-0.16, spread=0.05)
    payload["forecast_error_view"]["by_region"] = [{"region": "SMALL", "error_rate": -0.17, "effect_trx": -10.0}]
    payload["effect_by_exposed_region"] = {"SMALL": -10.0}
    payload["baseline_change_per_exposed_region"] = -10.0
    assert assess_confidence(payload, variance_trx=-30, territory_id="NATIONAL")[0] == "high"
    level, reasons = assess_confidence(payload, variance_trx=-30, territory_id="SMALL")
    assert level == "low"
    assert any("within 2x the spread" in r for r in reasons)


def test_capped_never_raises_a_label():
    assert capped("high", "medium") == "medium"
    assert capped("low", "high") == "low"
    assert capped("inconclusive", "high") == "inconclusive"
    assert capped("not a level", "high") == "low"


def lumina():
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


def test_lumina_drivers_are_medium_because_there_is_only_one_control_region():
    asked = lumina()
    report = run_investigation(asked, mode="stub")
    assert {d.confidence for d in report.drivers} == {"medium"}
    assert all(len(d.confidence_reasons) == 1 for d in report.drivers)
    assert "only 1 control region" in report.drivers[0].confidence_reasons[0]
    assert report.verification["verdict"] == "PASS"


def test_a_report_that_claims_more_confidence_than_the_evidence_fails_verification():
    asked = lumina()
    report = run_investigation(asked, mode="stub")
    forged = copy.deepcopy(report)
    forged.drivers[0].confidence = "high"
    result = verify_report(forged, asked)
    assert result["verdict"] == "FAIL"
    assert [c["id"] for c in result["checks"] if c["status"] == "fail"] == ["driver_confidence:payer_access"]


def test_pipeline_drafting_stage_carries_the_reasons():
    reset()
    run = run_forecast_pipeline(
        {
            "request_id": "req_lumina_w18",
            "source": "manual",
            "brand": "LUMINA",
            "week": 18,
            "week_ending": "2026-05-08",
            "metric": "TRx",
        },
        mode="stub",
    )
    driver = run["stages"][4]["result"]["drivers"][0]
    assert driver["confidence"] == "medium"
    assert driver["confidence_reasons"]


def _bxa(week_start, territory_id, window_weeks=None):
    reset()
    payload = {
        "request_id": f"fcst_{territory_id}",
        "source": "manual",
        "brand": "BXA Cardiovela",
        "week_start": week_start,
        "territory_id": territory_id,
        "metric": "TRx",
    }
    if window_weeks:
        payload["window_weeks"] = window_weeks
    return run_forecast_pipeline(payload, mode="stub")["report"]


@requires_shared
@pytest.mark.parametrize("week_start,territory", [("2026-08-24", "NATIONAL"), ("2026-08-24", "SOUTHEAST")])
def test_the_well_identified_promotion_estimate_stays_high(week_start, territory):
    drivers = _bxa(week_start, territory)["drivers"]
    assert [(d["driver"], d["confidence"]) for d in drivers] == [("promotion", "high")]
    assert drivers[0]["confidence_reasons"] == []


@requires_shared
def test_the_mid_atlantic_single_week_estimate_is_low_and_says_why():
    (driver,) = _bxa("2025-08-04", "MID_ATLANTIC")["drivers"]
    assert driver["confidence"] == "low"
    assert any("within 2x the spread" in r for r in driver["confidence_reasons"])


@requires_shared
def test_the_mid_atlantic_thirteen_week_estimate_is_medium_because_the_cross_check_disagrees():
    (driver,) = _bxa("2025-08-04", "MID_ATLANTIC", window_weeks=13)["drivers"]
    assert driver["confidence"] == "medium"
    assert len(driver["confidence_reasons"]) == 1
    assert "cross-check" in driver["confidence_reasons"][0]

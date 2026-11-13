import pytest

from feagent.pipeline import run_forecast_pipeline
from feagent.shared_world import available as shared_available
from feagent.store import reset
from feagent.tools import compare_exposed_control

requires_shared = pytest.mark.skipif(
    not shared_available(),
    reason="PharmAgentics data/agent_visible not found; set PHARMAGENTICS_DATA_DIR",
)


def _contrasts(week_start, territory_id):
    reset()
    run = run_forecast_pipeline(
        {
            "request_id": f"fcst_{territory_id}_{week_start}",
            "source": "manual",
            "brand": "BXA Cardiovela",
            "week_start": week_start,
            "territory_id": territory_id,
            "metric": "TRx",
        },
        mode="stub",
    )
    return run, {
        rec["payload"]["event_id"]: rec["payload"]
        for rec in run["report"]["evidence"]
        if rec["name"] == "compare_exposed_control"
    }


def test_event_without_a_start_week_keeps_the_fixed_offset():
    payload = compare_exposed_control("evt_payer_001", week=18)["payload"]
    assert payload["baseline_rule"] == "fixed_offset"
    assert payload["baseline_week"] == 16
    assert payload["event_start_week"] is None
    assert payload["estimated_total_trx"] == -1350


def test_a_missing_baseline_week_costs_the_cross_check_not_the_estimate():
    payload = compare_exposed_control("evt_payer_001", week=1)["payload"]
    assert payload["ok"] is True
    assert payload["estimated_total_trx"] == 0
    assert payload["baseline_change_total_trx"] is None
    assert payload["weekly_did"] == []


def test_missing_forecast_or_actual_rows_are_an_error_not_a_crash():
    payload = compare_exposed_control("evt_payer_001", week=99)["payload"]
    assert payload["ok"] is False
    assert "No TRx forecast or actual" in payload["error"]


@requires_shared
def test_event_start_weeks_come_from_the_calendar():
    _, contrasts = _contrasts("2026-08-24", "NATIONAL")
    assert contrasts["evt_promo_southeast"]["event_start_week"] == 95
    assert contrasts["evt_comp_metacora"]["event_start_week"] == 73
    _, contrasts = _contrasts("2025-08-04", "MID_ATLANTIC")
    assert contrasts["evt_access_mid_atlantic"]["event_start_week"] == 43


@requires_shared
def test_the_cross_check_baseline_is_before_the_lapse_and_the_primary_estimate_is_the_forecast_error_effect():
    run, contrasts = _contrasts("2026-08-24", "SOUTHEAST")
    promo = contrasts["evt_promo_southeast"]
    assert promo["baseline_rule"] == "week_before_event_start"
    assert promo["baseline_week"] == 94
    assert promo["exposed_mean_delta"] == -245
    assert promo["control_mean_delta"] == pytest.approx(-20)
    assert promo["baseline_change_per_exposed_region"] == pytest.approx(-225)
    impacts = {d["driver"]: d["impact_trx"] for d in run["report"]["drivers"]}
    assert impacts["promotion"] == pytest.approx(-211.8, abs=0.1)


@requires_shared
def test_national_card_gets_the_same_promotion_estimate():
    run, _ = _contrasts("2026-08-24", "NATIONAL")
    impacts = {d["driver"]: d["impact_trx"] for d in run["report"]["drivers"]}
    assert impacts["promotion"] == pytest.approx(-211.8, abs=0.1)
    assert run["stages"][5]["result"]["reconciles"] is True


@requires_shared
def test_mid_atlantic_baseline_is_the_week_before_the_tier_change():
    _, contrasts = _contrasts("2025-08-04", "MID_ATLANTIC")
    access = contrasts["evt_access_mid_atlantic"]
    assert access["baseline_week"] == 42
    assert access["baseline_rule"] == "week_before_event_start"

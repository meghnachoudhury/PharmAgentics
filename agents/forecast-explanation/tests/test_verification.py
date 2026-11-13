import copy
import json

import pytest

from feagent import pipeline
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


def lumina_request(week=18):
    reset()
    return InvestigationRequest.from_dict(
        {
            "request_id": "req_lumina_w18",
            "source": "manual",
            "brand": "LUMINA",
            "week": week,
            "week_ending": "2026-05-08",
            "metric": "TRx",
        }
    )


@pytest.fixture
def asked():
    return lumina_request()


@pytest.fixture
def report(asked):
    return run_investigation(asked, mode="stub")


def failing(result):
    return {c["id"] for c in result["checks"] if c["status"] == "fail"}


def warnings(result):
    return {c["id"] for c in result["checks"] if c["status"] == "warn"}


def recompute_residual(rep):
    rep.residual_trx = rep.variance_trx - sum(d.impact_trx for d in rep.drivers)


def test_a_clean_stub_report_passes(report):
    assert report.verification["verdict"] == "PASS"
    assert report.verification["failures"] == 0
    assert report.verification["warnings"] == 0


def test_verification_travels_with_the_report_as_json(report):
    payload = json.loads(json.dumps(report.to_dict()))
    assert payload["verification"]["verdict"] == "PASS"
    assert {c["id"] for c in payload["verification"]["checks"]} >= {"arithmetic", "abstention"}


def test_an_invented_driver_amount_fails_even_when_the_sum_still_adds_up(report, asked):
    forged = copy.deepcopy(report)
    forged.drivers[0].impact_trx = -2000
    recompute_residual(forged)
    result = verify_report(forged, asked)
    assert "driver_evidence:payer_access" in failing(result)
    assert "arithmetic" not in failing(result)
    assert result["verdict"] == "FAIL"


def test_rounding_inside_the_tolerance_is_accepted_but_a_real_gap_is_not(report, asked):
    rounded = copy.deepcopy(report)
    rounded.drivers[0].impact_trx += 0.3
    recompute_residual(rounded)
    assert verify_report(rounded, asked)["verdict"] == "PASS"
    off = copy.deepcopy(report)
    off.drivers[0].impact_trx += 5
    recompute_residual(off)
    assert "driver_evidence:payer_access" in failing(verify_report(off, asked))


def test_a_driver_with_no_evidence_fails(report, asked):
    forged = copy.deepcopy(report)
    forged.drivers[0].evidence_ids = []
    assert "driver_evidence:payer_access" in failing(verify_report(forged, asked))


def test_a_driver_citing_a_tool_call_that_never_happened_fails(report, asked):
    forged = copy.deepcopy(report)
    forged.drivers[0].evidence_ids = ["t_doesnotexist"]
    assert "driver_evidence:payer_access" in failing(verify_report(forged, asked))


def test_a_driver_citing_another_drivers_evidence_fails(report, asked):
    forged = copy.deepcopy(report)
    forged.drivers[0].evidence_ids, forged.drivers[1].evidence_ids = (
        forged.drivers[1].evidence_ids,
        forged.drivers[0].evidence_ids,
    )
    result = verify_report(forged, asked)
    assert failing(result) == {"driver_evidence:payer_access", "driver_evidence:competitor_activity"}


def test_the_same_driver_listed_twice_breaks_the_arithmetic(report, asked):
    forged = copy.deepcopy(report)
    forged.drivers.append(copy.deepcopy(forged.drivers[0]))
    assert "arithmetic" in failing(verify_report(forged, asked))


def test_a_tampered_variance_fails(report, asked):
    forged = copy.deepcopy(report)
    forged.variance_trx = -1000
    assert "variance_matches_inputs" in failing(verify_report(forged, asked))


def test_abstaining_while_listing_drivers_fails(report, asked):
    forged = copy.deepcopy(report)
    forged.abstained = True
    assert "abstention" in failing(verify_report(forged, asked))


def test_a_report_for_another_week_fails_the_scope_check(report):
    other = lumina_request(week=17)
    assert "scope_matches_request" in failing(verify_report(report, other))


def test_leaving_most_of_the_miss_unexplained_is_a_warning_not_a_failure(report, asked):
    thin = copy.deepcopy(report)
    thin.drivers = []
    recompute_residual(thin)
    result = verify_report(thin, asked)
    assert result["verdict"] == "WARN"
    assert warnings(result) == {"residual_share"}


def test_a_driver_that_pushes_against_the_miss_is_a_warning(report, asked):
    forged = copy.deepcopy(report)
    payer = next(rec for rec in forged.evidence if rec.payload.get("driver") == "payer_access")
    payer.payload["estimated_total_trx"] = 1350.0
    forged.drivers[0].impact_trx = 1350.0
    forged.drivers[0].confidence = "low"
    recompute_residual(forged)
    result = verify_report(forged, asked)
    assert "driver_direction:payer_access" in warnings(result)
    assert failing(result) == set()


def test_pipeline_stage_six_shows_the_checks(asked):
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
    stage = run["stages"][5]
    assert stage["status"] == "COMPLETE"
    assert stage["result"]["verdict"] == "PASS"
    assert stage["result"]["reconciles"] is True
    assert {c["id"] for c in stage["result"]["checks"]} >= {"arithmetic", "driver_evidence:payer_access"}


def test_pipeline_marks_a_failed_verification(monkeypatch):
    real = pipeline.run_investigation

    def forged(request, mode="stub"):
        rep = real(request, mode=mode)
        rep.drivers[0].impact_trx = -2000
        rep.residual_trx = rep.variance_trx - sum(d.impact_trx for d in rep.drivers)
        rep.verification = verify_report(rep, request)
        return rep

    monkeypatch.setattr(pipeline, "run_investigation", forged)
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
    stage = run["stages"][5]
    assert stage["status"] == "FAIL"
    assert stage["summary"].startswith("Verification failed")
    assert run["workflow_status"] == "Verification Failed — Needs Review"


def _bxa(week_start, territory_id):
    reset()
    return run_forecast_pipeline(
        {
            "request_id": f"fcst_{territory_id}",
            "source": "manual",
            "brand": "BXA Cardiovela",
            "week_start": week_start,
            "territory_id": territory_id,
            "metric": "TRx",
        },
        mode="stub",
    )


@requires_shared
def test_the_mid_atlantic_single_week_card_is_flagged_because_the_two_estimators_disagree():
    stage = _bxa("2025-08-04", "MID_ATLANTIC")["stages"][5]
    ids = {c["id"] for c in stage["result"]["checks"] if c["status"] == "warn"}
    assert stage["status"] == "FLAG"
    assert ids == {"estimator_agreement:payer_access"}


@requires_shared
def test_the_national_card_is_flagged_for_its_large_residual():
    stage = _bxa("2026-08-24", "NATIONAL")["stages"][5]
    assert stage["status"] == "FLAG"
    assert {c["id"] for c in stage["result"]["checks"] if c["status"] == "warn"} == {"residual_share"}


@requires_shared
def test_the_southeast_card_passes_all_checks():
    stage = _bxa("2026-08-24", "SOUTHEAST")["stages"][5]
    assert stage["status"] == "COMPLETE"
    assert stage["result"]["verdict"] == "PASS"

import json
import threading

import pytest

from feagent.pipeline import FORECAST_LANE_CASES, run_forecast_pipeline
from feagent.schema import InvestigationRequest
from feagent.shared_world import available as shared_available
from feagent.store import reset

requires_shared = pytest.mark.skipif(
    not shared_available(),
    reason="PharmAgentics data/agent_visible not found; set PHARMAGENTICS_DATA_DIR",
)

LUMINA_NAMES = ("Plan Alpha", "Rivalza", "synthetic", "CMS")


def _lumina(territory_id=None):
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
    reset()
    return run_forecast_pipeline(payload, mode="stub")


def _bxa(week_start, territory_id):
    reset()
    return run_forecast_pipeline(
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


def test_lumina_territory_scope_uses_that_territory_only():
    report = _lumina("Northeast")["report"]
    assert report["territory_id"] == "Northeast"
    assert report["forecast_trx"] == 3000
    assert report["actual_trx"] == 2225
    assert report["variance_trx"] == -775
    impacts = {d["driver"]: d["impact_trx"] for d in report["drivers"]}
    assert impacts == {"payer_access": -675}
    assert report["residual_trx"] == -100


def test_lumina_national_default_is_unchanged():
    report = _lumina()["report"]
    assert report["territory_id"] == "NATIONAL"
    assert report["variance_trx"] == -2400
    assert report["residual_trx"] == -400


def test_lumina_checks_still_name_the_events_from_evidence():
    report = _lumina()["report"]
    text = json.dumps(report["what_to_check"])
    assert "Plan Alpha" in text
    assert "Rivalza" in text


def test_unknown_territory_is_a_value_error():
    with pytest.raises(ValueError):
        _lumina("Atlantis")


@requires_shared
def test_bxa_new_england_scopes_to_the_territory():
    run = _bxa("2026-05-04", "NEW_ENGLAND")
    report = run["report"]
    assert report["territory_id"] == "NEW_ENGLAND"
    assert (report["forecast_trx"], report["actual_trx"], report["variance_trx"]) == (440, 267, -173)
    assert report["abstained"] is True
    assert report["drivers"] == []
    assert run["stages"][1]["status"] == "FLAG"


@requires_shared
def test_bxa_southeast_miss_is_the_territory_number():
    run = _bxa("2026-08-24", "SOUTHEAST")
    report = run["report"]
    assert (report["forecast_trx"], report["actual_trx"], report["variance_trx"]) == (812, 469, -343)
    assert report["abstained"] is False
    assert run["stages"][5]["result"]["reconciles"] is True


@requires_shared
def test_bxa_mid_atlantic_is_a_single_week_not_the_13_week_sum():
    report = _bxa("2025-08-04", "MID_ATLANTIC")["report"]
    assert (report["forecast_trx"], report["actual_trx"], report["variance_trx"]) == (690, 656, -34)


@requires_shared
def test_bxa_cards_carry_no_lumina_text():
    for case in FORECAST_LANE_CASES:
        reset()
        report = run_forecast_pipeline(case["request"], mode="stub")["report"]
        text = json.dumps(report["what_to_check"] + report["caveats"])
        for name in LUMINA_NAMES:
            assert name not in text, f"{name!r} leaked into {case['case_id']}"


@requires_shared
def test_event_without_a_control_is_reported_not_dropped_silently():
    report = _bxa("2026-08-24", "NATIONAL")["report"]
    checks = " ".join(c["question"] for c in report["what_to_check"])
    assert "No clean control" in checks
    assert any("no clean control" in c for c in report["caveats"])


@requires_shared
def test_concurrent_runs_do_not_mix_worlds():
    errors = []

    def lumina():
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
        if run["report"]["variance_trx"] != -2400:
            errors.append(("lumina", run["report"]["variance_trx"]))

    def bxa():
        run = run_forecast_pipeline(
            {
                "request_id": "fcst_nat",
                "source": "manual",
                "brand": "BXA Cardiovela",
                "week_start": "2026-08-24",
                "territory_id": "NATIONAL",
                "metric": "TRx",
            },
            mode="stub",
        )
        if run["report"]["variance_trx"] != -1036:
            errors.append(("bxa", run["report"]["variance_trx"]))

    def guarded(fn):
        try:
            fn()
        except Exception as exc:  # a world mix-up shows up as a wrong number or a missing table
            errors.append((fn.__name__, repr(exc)))

    reset()
    threads = [threading.Thread(target=guarded, args=(fn,)) for _ in range(6) for fn in (lumina, bxa)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_a_request_without_an_id_is_a_value_error_not_a_key_error():
    payload = {
        "source": "manual",
        "brand": "LUMINA",
        "week": 18,
        "week_ending": "2026-05-08",
        "metric": "TRx",
    }
    with pytest.raises(ValueError, match="request_id is required"):
        InvestigationRequest.from_dict(payload)
    reset()
    with pytest.raises(ValueError, match="request_id is required"):
        run_forecast_pipeline(payload, mode="stub")

import pytest

from feagent.pipeline import run_forecast_pipeline
from feagent.shared_world import available as shared_available
from feagent.store import reset

requires_shared = pytest.mark.skipif(
    not shared_available(),
    reason="PharmAgentics data/agent_visible not found; set PHARMAGENTICS_DATA_DIR",
)


def test_lumina_pipeline_still_reconciles():
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
    report = run["report"]
    assert report["variance_trx"] == -2400
    assert report["residual_trx"] == -400
    assert run["stages"][3]["kind"] == "agentic"
    assert run["stages"][5]["status"] == "COMPLETE"
    assert run["stages"][6]["status"] == "PENDING"


@requires_shared
def test_bxa_national_miss_matches_figma_card():
    reset()
    run = run_forecast_pipeline(
        {
            "request_id": "fcst_nat_2026-08-24",
            "source": "manual",
            "brand": "BXA Cardiovela",
            "week_start": "2026-08-24",
            "territory_id": "NATIONAL",
            "metric": "TRx",
        },
        mode="stub",
    )
    report = run["report"]
    assert report["forecast_trx"] == 5141
    assert report["actual_trx"] == 4105
    assert report["variance_trx"] == -1036
    assert run["stages"][5]["result"]["reconciles"] is True


@requires_shared
def test_bxa_provisional_abstains():
    reset()
    run = run_forecast_pipeline(
        {
            "request_id": "fcst_ne_2026-05-04",
            "source": "manual",
            "brand": "BXA Cardiovela",
            "week_start": "2026-05-04",
            "territory_id": "NEW_ENGLAND",
            "metric": "TRx",
        },
        mode="stub",
    )
    assert run["report"]["abstained"] is True
    assert run["report"]["drivers"] == []
    assert run["stages"][3]["status"] == "ABSTAINED"

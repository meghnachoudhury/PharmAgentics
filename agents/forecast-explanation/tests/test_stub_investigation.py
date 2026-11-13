from feagent.data_loader import load_observable
from feagent.investigator import run_investigation
from feagent.schema import InvestigationRequest
from feagent.store import briefing_request
from feagent.tools import INVESTIGATOR_TABLES, compare_exposed_control, validate_and_quantify


def test_week18_national_totals():
    obs = load_observable("week18")
    row = next(r for r in obs["weekly_national"] if r["week"] == 18)
    assert row["forecast"] == 12000
    assert row["actual"] == 9600


def test_did_recovers_injected_totals():
    payer = compare_exposed_control("evt_payer_001", week=18)["payload"]
    competitor = compare_exposed_control("evt_comp_001", week=18)["payload"]
    assert payer["estimated_total_trx"] == -1350
    assert competitor["estimated_total_trx"] == -650
    assert payer["source"].startswith("duckdb")


def test_stub_report_reconciles():
    obs = load_observable("week18")
    request = InvestigationRequest.from_dict(obs["default_request"])
    report = run_investigation(request, mode="stub")
    assert report.variance_trx == -2400
    impacts = {d.driver: d.impact_trx for d in report.drivers}
    assert impacts["payer_access"] == -1350
    assert impacts["competitor_activity"] == -650
    assert report.residual_trx == -400
    quantified = validate_and_quantify(18)["payload"]
    assert quantified["data_complete"] is True


def test_tools_do_not_read_ground_truth():
    assert "eval_ground_truth" not in INVESTIGATOR_TABLES

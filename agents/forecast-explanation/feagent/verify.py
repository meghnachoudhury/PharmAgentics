"""Stage 6 checks on a drafted InvestigationReport.

A "fail" means the report cannot be trusted as written (numbers that no tool
produced, drivers that do not add up, an attribution on a withheld cut). A "warn"
means the report is internally sound but should be read with care.
"""

from __future__ import annotations

from typing import Any

from feagent.confidence import LEVELS, assess_confidence, estimators_disagree, rank
from feagent.schema import DriverEstimate, InvestigationReport, InvestigationRequest, ToolRecord
from feagent.tools import NATIONAL, primary_estimate

RESIDUAL_WARN_SHARE = 0.5
ARITHMETIC_EPS = 1e-6
TOLERANCE_ABS_TRX = 0.5


def verify_report(
    report: InvestigationReport,
    request: InvestigationRequest | None = None,
) -> dict[str, Any]:
    by_id = {rec.tool_id: rec for rec in report.evidence}
    checks: list[dict[str, str]] = []

    def add(check_id: str, status: str, detail: str) -> None:
        checks.append({"id": check_id, "status": status, "detail": detail})

    if request is not None:
        same = (
            report.week == request.week
            and report.territory_id == request.territory_id
            and report.window_weeks == request.window_weeks
        )
        add(
            "scope_matches_request",
            "pass" if same else "fail",
            f"{report.territory_id} week {report.week}, {report.window_weeks} week(s)"
            if same
            else f"report covers {report.territory_id} week {report.week} x {report.window_weeks}, "
            f"request asked for {request.territory_id} week {request.week} x {request.window_weeks}",
        )

    gap = (report.actual_trx - report.forecast_trx) - report.variance_trx
    add(
        "variance_matches_inputs",
        "pass" if abs(gap) < ARITHMETIC_EPS else "fail",
        "V = A - F" if abs(gap) < ARITHMETIC_EPS else f"variance is off by {gap:,.2f} TRx from actual - forecast",
    )

    explained = sum(d.impact_trx for d in report.drivers)
    miss = report.variance_trx - (explained + report.residual_trx)
    add(
        "arithmetic",
        "pass" if abs(miss) < ARITHMETIC_EPS else "fail",
        "V = sum(c) + r"
        if abs(miss) < ARITHMETIC_EPS
        else f"drivers {explained:,.2f} + residual {report.residual_trx:,.2f} differ from V by {miss:,.2f} TRx",
    )

    add(*_abstention_check(report))

    if report.abstained:
        return _verdict(checks)

    for driver in report.drivers:
        problems = _driver_problems(driver, report, by_id)
        add(
            f"driver_evidence:{driver.driver}",
            "fail" if problems else "pass",
            "; ".join(problems) if problems else "impact matches the cited tool result",
        )
        if not problems:
            problem = _confidence_problem(driver, report, by_id)
            add(
                f"driver_confidence:{driver.driver}",
                "fail" if problem else "pass",
                problem or f"{driver.confidence} is within what the evidence supports",
            )
            for rec in _contrasts_for(driver, report, by_id)[:1]:
                gap = estimators_disagree(rec.payload, report.variance_trx, report.territory_id)
                add(
                    f"estimator_agreement:{driver.driver}",
                    "warn" if gap else "pass",
                    gap or "the baseline-change cross-check agrees with the forecast-error estimate",
                )

    variance = report.variance_trx
    if variance:
        share = abs(report.residual_trx) / abs(variance)
        add(
            "residual_share",
            "warn" if share > RESIDUAL_WARN_SHARE else "pass",
            f"residual is {share:.0%} of the miss"
            + ("; the drivers explain only part of it" if share > RESIDUAL_WARN_SHARE else ""),
        )
        for driver in report.drivers:
            if driver.impact_trx * variance < 0:
                add(
                    f"driver_direction:{driver.driver}",
                    "warn",
                    f"{driver.driver} is {driver.impact_trx:+,.1f} TRx, the opposite direction to the miss ({variance:+,.1f})",
                )
    return _verdict(checks)


def _abstention_check(report: InvestigationReport) -> tuple[str, str, str]:
    gate = next(
        (
            rec
            for rec in report.evidence
            if rec.name == "validate_and_quantify"
            and rec.payload.get("ok")
            and rec.payload.get("week") == report.week
            and rec.payload.get("territory_id", NATIONAL) == report.territory_id
            and rec.payload.get("window_weeks", 1) == report.window_weeks
        ),
        None,
    )
    if gate is None:
        return "abstention", "fail", "no validate_and_quantify result for this week and territory"
    provisional = bool(gate.payload.get("actual_is_provisional"))
    if provisional and not report.abstained:
        return "abstention", "fail", "the actual is provisional but the report attributes the miss"
    if report.abstained and report.drivers:
        return "abstention", "fail", "the report abstains but still lists drivers"
    if report.abstained:
        return "abstention", "pass", "attribution withheld on a provisional or incomplete cut"
    return "abstention", "pass", "actual is final; attribution allowed"


def _driver_problems(
    driver: DriverEstimate, report: InvestigationReport, by_id: dict[str, ToolRecord]
) -> list[str]:
    if not driver.evidence_ids:
        return ["cites no evidence"]
    unknown = [i for i in driver.evidence_ids if i not in by_id]
    if unknown:
        return [f"cites evidence ids that do not exist: {unknown}"]
    contrasts = _contrasts_for(driver, report, by_id)
    if not contrasts:
        return ["no cited compare_exposed_control result for this driver and week"]
    figures = [primary_estimate(rec.payload, report.territory_id) for rec in contrasts]
    figures = [f for f in figures if f is not None]
    if not figures:
        return ["the cited tool result has no estimate"]
    if any(abs(driver.impact_trx - f) <= TOLERANCE_ABS_TRX for f in figures):
        return []
    shown = ", ".join(f"{f:,.1f}" for f in figures)
    return [f"impact {driver.impact_trx:,.1f} TRx does not match the tool figure ({shown})"]


def _contrasts_for(
    driver: DriverEstimate, report: InvestigationReport, by_id: dict[str, ToolRecord]
) -> list[ToolRecord]:
    return [
        by_id[i]
        for i in driver.evidence_ids
        if i in by_id
        and by_id[i].name == "compare_exposed_control"
        and by_id[i].payload.get("ok")
        and by_id[i].payload.get("driver") == driver.driver
        and by_id[i].arguments.get("week") == report.week
        and by_id[i].arguments.get("window_weeks", 1) == report.window_weeks
    ]


def _confidence_problem(
    driver: DriverEstimate, report: InvestigationReport, by_id: dict[str, ToolRecord]
) -> str | None:
    if driver.confidence not in LEVELS:
        return f"confidence {driver.confidence!r} is not one of {LEVELS}"
    cap = min(
        (
            assess_confidence(rec.payload, report.variance_trx, report.territory_id)[0]
            for rec in _contrasts_for(driver, report, by_id)
        ),
        key=rank,
        default="inconclusive",
    )
    if rank(driver.confidence) > rank(cap):
        return f"confidence {driver.confidence} is above what the evidence supports ({cap})"
    return None


def _verdict(checks: list[dict[str, str]]) -> dict[str, Any]:
    failures = [c for c in checks if c["status"] == "fail"]
    warnings = [c for c in checks if c["status"] == "warn"]
    return {
        "verdict": "FAIL" if failures else "WARN" if warnings else "PASS",
        "failures": len(failures),
        "warnings": len(warnings),
        "checks": checks,
    }

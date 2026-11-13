"""Forecast lane spine: stages 1-2 and 6 shared, 3b-5 per lane, 4b agentic."""

from __future__ import annotations

import hashlib
import threading
from typing import Any

from feagent import store
from feagent.investigator import run_investigation
from feagent.schema import InvestigationRequest
from feagent.shared_world import available as shared_available
from feagent.shared_world import resolve_week
from feagent.tools import reconcile_attribution, validate_and_quantify

_PIPELINE_LOCK = threading.RLock()

VERIFICATION_STAGE_STATUS = {"PASS": "COMPLETE", "WARN": "FLAG", "FAIL": "FAIL"}


def _check_status(verification: dict[str, Any], check_id: str) -> str | None:
    return next((c["status"] for c in verification["checks"] if c["id"] == check_id), None)


def _verification_summary(verification: dict[str, Any]) -> str:
    verdict = verification["verdict"]
    if verdict == "PASS":
        return "V = Σc + r; all checks passed"
    wanted = "fail" if verdict == "FAIL" else "warn"
    details = "; ".join(c["detail"] for c in verification["checks"] if c["status"] == wanted)
    return ("Verification failed: " if verdict == "FAIL" else "V = Σc + r holds; ") + details

STAGE_META = [
    {"id": 1, "name": "Load & Pin", "kind": "deterministic"},
    {"id": 2, "name": "Validation Gate", "kind": "deterministic"},
    {"id": 3, "name": "Detection", "kind": "deterministic"},
    {"id": 4, "name": "Agentic Investigation", "kind": "agentic"},
    {"id": 5, "name": "Drafting", "kind": "deterministic"},
    {"id": 6, "name": "Verification", "kind": "deterministic"},
    {"id": 7, "name": "Human Review", "kind": "human"},
]


FORECAST_LANE_CASES = [
    {
        "case_id": "ne-provisional-2026-05-04",
        "lane": "forecast",
        "tag": "PROVISIONAL ACTUAL",
        "label": "New England miss on a provisional actual: attribution paused",
        "request": {
            "request_id": "fcst_ne_2026-05-04",
            "source": "manual",
            "brand": "BXA Cardiovela",
            "week_start": "2026-05-04",
            "territory_id": "NEW_ENGLAND",
            "metric": "TRx",
            "notes": "CA-Q1. Feed failed; do not treat as demand.",
        },
    },
    {
        "case_id": "national-miss-2026-08-24",
        "lane": "forecast",
        "tag": "FORECAST MISS",
        "label": "National BXA miss of -1,036 TRx; every territory below forecast",
        "request": {
            "request_id": "fcst_nat_2026-08-24",
            "source": "manual",
            "brand": "BXA Cardiovela",
            "week_start": "2026-08-24",
            "territory_id": "NATIONAL",
            "metric": "TRx",
            "notes": "CA-Q2. Stage 3b material miss.",
        },
    },
    {
        "case_id": "mid-atlantic-access-2025-08-04",
        "lane": "forecast",
        "tag": "FORECAST MISS",
        "label": "Mid-Atlantic -730 TRx over 13 weeks after a Part D tier change",
        "request": {
            "request_id": "fcst_ma_2025-08-04",
            "source": "manual",
            "brand": "BXA Cardiovela",
            "week_start": "2025-08-04",
            "territory_id": "MID_ATLANTIC",
            "metric": "TRx",
            "window_weeks": 13,
            "notes": "CA-Q5. 13-week window from the tier-change week; the 13-week sum is the card's -730.",
        },
    },
]


def select_world(payload: dict[str, Any]) -> str:
    brand = str(payload.get("brand") or "")
    week_start = payload.get("week_start")
    if week_start or "BXA" in brand.upper() or "Cardiovela" in brand:
        if not shared_available():
            raise FileNotFoundError(
                "BXA request needs PharmAgentics data/agent_visible (PHARMAGENTICS_DATA_DIR)."
            )
        return "shared"
    return "lumina"


def run_forecast_pipeline(
    payload: dict[str, Any],
    mode: str = "stub",
) -> dict[str, Any]:
    # store.use_world() and the DuckDB connections are process-wide; FastAPI runs
    # sync handlers on a thread pool, so one run at a time keeps worlds from mixing.
    with _PIPELINE_LOCK:
        return _run_forecast_pipeline(payload, mode)


def _run_forecast_pipeline(payload: dict[str, Any], mode: str) -> dict[str, Any]:
    world = select_world(payload)
    store.use_world(world)
    store.connect()
    request = InvestigationRequest.from_dict(payload)
    if world == "shared":
        resolved = resolve_week(request.week or None, request.week_start)
        request.week = int(resolved["week"])
        request.week_start = str(resolved["week_start"])
        request.week_ending = str(resolved["week_ending"])
        request.brand = "BXA Cardiovela"

    pin = {
        "world": world,
        "week": request.week,
        "week_start": request.week_start,
        "week_ending": request.week_ending,
        "territory_id": request.territory_id,
        "window_weeks": request.window_weeks,
        "product_id": request.product_id,
        "brand": request.brand,
        "forecast_issue_note": "4-week-ahead locked forecast in shared world",
    }
    fingerprint = hashlib.sha256(
        f"{world}|{request.week}|{request.week_start}|{request.territory_id}|{request.window_weeks}".encode()
    ).hexdigest()[:10].upper()

    gate = validate_and_quantify(
        request.week, territory_id=request.territory_id, window_weeks=request.window_weeks
    )["payload"]
    if not gate.get("ok"):
        raise ValueError(gate.get("error") or "validate_and_quantify failed")
    provisional = bool(gate.get("actual_is_provisional"))
    detection = {
        "metric": "TRx",
        "forecast": gate.get("forecast"),
        "actual": gate.get("actual"),
        "variance_trx": gate.get("variance_trx"),
        "variance_pct": gate.get("variance_pct"),
        "window_weeks": request.window_weeks,
        "rule": "V = A − F against the locked forecast",
        "material": abs(float(gate.get("variance_trx") or 0)) >= 100,
        "provisional": provisional,
    }

    report = run_investigation(request, mode=mode)
    verification = report.verification
    recon = reconcile_attribution(
        report.variance_trx,
        {d.driver: d.impact_trx for d in report.drivers},
    )["payload"]

    stages = [
        {**STAGE_META[0], "status": "COMPLETE", "summary": f"Pinned {world} snapshot {fingerprint}"},
        {
            **STAGE_META[1],
            "status": "FLAG" if (not gate.get("data_complete") or provisional) else "COMPLETE",
            "summary": (
                "Provisional actual; attribution paused"
                if provisional
                else "Feed complete for this cut"
            ),
            "result": {
                "data_complete": gate.get("data_complete"),
                "actual_is_provisional": provisional,
            },
        },
        {
            **STAGE_META[2],
            "status": "COMPLETE",
            "summary": (
                f"V = {detection['variance_trx']:+,.0f} TRx "
                f"({float(detection['variance_pct'] or 0):+.1%})"
                + (f" over {request.window_weeks} weeks" if request.window_weeks > 1 else "")
            ),
            "result": detection,
        },
        {
            **STAGE_META[3],
            "status": "ABSTAINED" if report.abstained else "COMPLETE",
            "kind": "agentic",
            "mode": report.investigator_mode,
            "summary": report.headline,
        },
        {
            **STAGE_META[4],
            "status": "COMPLETE",
            "summary": report.headline,
            "result": {
                "headline": report.headline,
                "drivers": [
                    {
                        "driver": d.driver,
                        "impact_trx": d.impact_trx,
                        "confidence": d.confidence,
                        "confidence_reasons": d.confidence_reasons,
                        "method": d.method,
                        "notes": d.notes,
                    }
                    for d in report.drivers
                ],
                "residual_trx": report.residual_trx,
                "what_to_check": [
                    {"question": c.question, "why": c.why, "owner": c.owner}
                    for c in report.what_to_check
                ],
                "caveats": report.caveats,
            },
        },
        {
            **STAGE_META[5],
            "status": VERIFICATION_STAGE_STATUS[verification["verdict"]],
            "summary": _verification_summary(verification),
            "result": {
                **recon,
                "reconciles": _check_status(verification, "arithmetic") == "pass",
                "verdict": verification["verdict"],
                "checks": verification["checks"],
            },
        },
        {
            **STAGE_META[6],
            "status": "PENDING",
            "summary": "Needs Commercial Analytics Analyst review",
        },
    ]
    return {
        "run_id": request.request_id,
        "lane": "forecast",
        "fingerprint": f"FEA-{fingerprint}",
        "workflow": "Forecast Variance Attribution & Explanation",
        "dataset_release": "day1-v1" if world == "shared" else "lumina-week18",
        "seed": 7 if world == "shared" else None,
        "pin": pin,
        "stages": stages,
        "workflow_status": (
            "Verification Failed — Needs Review"
            if verification["verdict"] == "FAIL"
            else "Processing Complete — Pending Human Approval"
        ),
        "report": report.to_dict(),
    }

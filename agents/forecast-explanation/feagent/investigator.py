from __future__ import annotations

import json
from typing import Any

from feagent import store
from feagent.confidence import assess_confidence, capped
from feagent.config import MAX_INVESTIGATOR_STEPS, OLLAMA_MODEL
from feagent.llm import LLMClient, OllamaClient, parse_json_message
from feagent.schema import (
    CheckItem,
    DriverEstimate,
    InvestigationReport,
    InvestigationRequest,
    ToolRecord,
)
from feagent.tools import NATIONAL, TOOL_SPECS, primary_estimate, run_tool, tool_error
from feagent.verify import verify_report


SYSTEM_PROMPT = """You are the Forecast-Explanation Investigator for a pharmaceutical brand.
You explain forecast-versus-actual TRx variance. You do not make commercial decisions.

Rules:
- Cite only numbers returned by tools. Never invent TRx figures.
- If controls are weak, evidence conflicts, or data are missing, abstain or mark confidence inconclusive.
- Overlapping drivers must not be forced into a fully additive story.
- The request fixes the period (window_weeks). The tools apply it for you; you cannot change it.
- Every driver's evidence_ids must hold the tool_id of the compare_exposed_control result that produced it, and its impact_trx must equal that result's estimated_total_trx (national scope) or its effect_by_exposed_region entry for the territory (single territory). Do not list a driver whose result has no estimate.
- Your stated confidence is capped by the evidence (control regions, baseline, direction, spread across controls); state it honestly and never above what the tool results support.
- If your interface supports function calling, call the tools directly and finish by calling submit_report.
- When finished, return action=final with a report object.

Reply with ONLY JSON, one of:
{"action":"tool","name":"<tool_name>","arguments":{...}}
{"action":"final","report":{...}}

final.report fields:
headline (string),
drivers (list of {driver, impact_trx, confidence, method, evidence_ids, notes}),
what_to_check (list of {question, why, owner}),
caveats (list of strings),
abstained (boolean)

Tools:
""" + json.dumps(TOOL_SPECS, indent=2)


def run_investigation(
    request: InvestigationRequest,
    mode: str = "auto",
    case_id: str = "week18",
    client: LLMClient | None = None,
) -> InvestigationReport:
    report = _run_mode(request, mode, case_id, client)
    report.verification = verify_report(report, request)
    return report


def _run_mode(
    request: InvestigationRequest,
    mode: str,
    case_id: str,
    client: LLMClient | None,
) -> InvestigationReport:
    if mode == "stub":
        return run_stub(request, case_id)
    if mode not in {"ollama", "auto"}:
        raise ValueError(f"Unknown investigator mode: {mode}")
    withheld = _provisional_gate(request, case_id)
    if withheld is not None:
        return withheld
    if mode == "ollama":
        return run_ollama(request, case_id, client)
    ollama = client or OllamaClient()
    ok, _reason = ollama.available()
    if ok:
        try:
            return run_ollama(request, case_id, ollama)
        except Exception:
            return run_stub(request, case_id)
    return run_stub(request, case_id)


def _provisional_gate(request: InvestigationRequest, case_id: str) -> InvestigationReport | None:
    """Withhold attribution on a provisional actual before any model is called."""
    record = run_tool(
        "validate_and_quantify",
        {
            "week": request.week,
            "case_id": case_id,
            "territory_id": request.territory_id,
            "window_weeks": request.window_weeks,
        },
    )
    q = record["payload"]
    if not q.get("ok"):
        raise RuntimeError(q.get("error") or "validate_and_quantify failed")
    if q.get("actual_is_provisional"):
        return _provisional_report(request, q, [record], investigator_mode="gate", model=None)
    return None


def _period(q: dict[str, Any]) -> str:
    if q.get("window_weeks", 1) == 1:
        return f"in week ending {q['week_ending']}"
    return f"over the {q['window_weeks']} weeks ending {q['week_ending']}"


def _provisional_report(
    request: InvestigationRequest,
    q: dict[str, Any],
    evidence: list[dict[str, Any]],
    investigator_mode: str,
    model: str | None,
) -> InvestigationReport:
    return _report(
        request,
        q,
        f"{q['brand']} actual is provisional {_period(q)}; attribution is paused.",
        [],
        float(q["variance_trx"]),
        [
            CheckItem(
                question="Re-run this cut after a complete feed lands.",
                why="The forecast table marks the actual provisional; a miss here is not a demand shock.",
                owner="Commercial analytics",
            )
        ],
        [
            "Provisional actuals are withheld from driver attribution (FE-01 to FE-03).",
            "Do not report a percent miss on a failed cut.",
        ],
        evidence,
        investigator_mode=investigator_mode,
        model=model,
        abstained=True,
    )


def run_stub(request: InvestigationRequest, case_id: str = "week18") -> InvestigationReport:
    evidence: list[dict[str, Any]] = []

    territory = request.territory_id
    quantified = run_tool(
        "validate_and_quantify",
        {
            "week": request.week,
            "case_id": case_id,
            "territory_id": territory,
            "window_weeks": request.window_weeks,
        },
    )
    evidence.append(quantified)
    q = quantified["payload"]
    if not q.get("ok"):
        raise RuntimeError(q.get("error") or "validate_and_quantify failed")

    if q.get("actual_is_provisional"):
        return _provisional_report(request, q, evidence, investigator_mode="stub", model=None)

    windowed = {"week": request.week, "case_id": case_id, "window_weeks": request.window_weeks}
    deltas = run_tool("get_region_deltas", windowed)
    evidence.append(deltas)

    events = run_tool("list_candidate_events", windowed)
    evidence.append(events)

    driver_impacts: dict[str, float] = {}
    driver_rows: list[DriverEstimate] = []
    estimated: list[tuple[dict[str, Any], float]] = []
    unestimated: list[dict[str, Any]] = []
    for event in events["payload"]["events"]:
        if territory != NATIONAL and territory not in event["exposed_regions"]:
            continue
        contrast = run_tool(
            "compare_exposed_control",
            {"event_id": event["event_id"], **windowed},
        )
        evidence.append(contrast)
        payload = contrast["payload"]
        if not payload.get("ok"):
            continue
        raw_impact = primary_estimate(payload, territory)
        if raw_impact is None:
            unestimated.append(payload)
            continue
        impact = float(raw_impact)
        estimated.append((payload, impact))
        driver_impacts[payload["driver"]] = impact
        confidence, reasons = assess_confidence(payload, q["variance_trx"], territory)
        driver_rows.append(
            DriverEstimate(
                driver=payload["driver"],
                impact_trx=impact,
                confidence=confidence,
                method=payload["method"],
                evidence_ids=[contrast["tool_id"]],
                notes=payload.get("notes") or payload["label"],
                confidence_reasons=reasons,
            )
        )

    recon = run_tool(
        "reconcile_attribution",
        {"variance_trx": q["variance_trx"], "driver_impacts": driver_impacts},
    )
    evidence.append(recon)
    residual = float(recon["payload"]["residual_trx"])

    headline = (
        f"{q['brand']} missed forecast by {abs(q['variance_trx']):,.0f} {q['metric']} "
        f"({q['variance_pct']:.0%}) {_period(q)}."
    )
    checks = _checks_from_evidence(estimated, unestimated, residual, q["metric"])
    caveats = _caveats_for_world(unestimated)
    return _report(
        request,
        q,
        headline,
        driver_rows,
        residual,
        checks,
        caveats,
        evidence,
        investigator_mode="stub",
        model=None,
        abstained=False,
    )


MAX_UNUSABLE_REPLIES = 2
WINDOWED_TOOLS = {"validate_and_quantify", "get_region_deltas", "list_candidate_events", "compare_exposed_control"}
CONFIDENCE_LEVELS = {"high", "medium", "low", "inconclusive"}

OWNER_BY_DRIVER = {
    "payer_access": "Market access",
    "competitor_activity": "Brand analytics",
    "promotion": "Commercial operations",
}
DEFAULT_OWNER = "Brand analytics"


def _checks_from_evidence(
    estimated: list[tuple[dict[str, Any], float]],
    unestimated: list[dict[str, Any]],
    residual: float,
    metric: str,
) -> list[CheckItem]:
    checks = []
    for payload, impact in estimated:
        notes = (payload.get("notes") or "").strip()
        checks.append(
            CheckItem(
                question=f'Confirm "{payload["label"]}" with {OWNER_BY_DRIVER.get(payload["driver"], DEFAULT_OWNER)}.',
                why=f"Forecast-error estimate vs named controls is {impact:+,.0f} {metric}. {notes}".strip(),
                owner=OWNER_BY_DRIVER.get(payload["driver"], DEFAULT_OWNER),
            )
        )
    for payload in unestimated:
        checks.append(
            CheckItem(
                question=f'No clean control for "{payload["label"]}"; impact not estimated.',
                why="No control region is named, so exposed-vs-control cannot isolate this event.",
                owner=DEFAULT_OWNER,
            )
        )
    checks.append(
        CheckItem(
            question="Inspect the unexplained residual before treating it as noise.",
            why=f"{residual:,.0f} {metric} remains after the estimated drivers.",
            owner="Forecasting",
        )
    )
    return checks


def _caveats_for_world(unestimated: list[dict[str, Any]]) -> list[str]:
    overlap = (
        "v1 identification excludes contaminated regions rather than jointly modeling overlapping shocks."
    )
    if store.current_world() == "shared":
        caveats = [
            "Numbers are from deterministic tools on the day1-v1 shared world (seed 7).",
            "Event calendar is observable-only; magnitudes come from exposed-vs-control contrasts, not labels.",
            overlap,
        ]
    else:
        caveats = [
            "Numbers are from deterministic tools on a synthetic case.",
            overlap,
            "Public CMS calibration has not been applied yet.",
        ]
    caveats.extend(
        f'"{p["label"]}" has no clean control region; its impact is not estimated and sits in the residual.'
        for p in unestimated
    )
    return caveats


def run_ollama(
    request: InvestigationRequest,
    case_id: str = "week18",
    client: LLMClient | None = None,
) -> InvestigationReport:
    client = client or OllamaClient()
    ok, reason = client.available()
    if not ok:
        raise RuntimeError(reason)

    evidence: list[dict[str, Any]] = []
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": "Investigate this forecast miss.",
                    "request": request.__dict__,
                    "case_id": case_id,
                    "instruction": "Start with validate_and_quantify.",
                }
            ),
        },
    ]

    quantified: dict[str, Any] | None = None
    unusable_replies = 0
    for _ in range(MAX_INVESTIGATOR_STEPS):
        raw = client.complete(messages)
        messages.append({"role": "assistant", "content": raw})
        problem = None
        try:
            parsed = parse_json_message(raw)
        except ValueError as exc:
            parsed, problem = {}, f"Reply was not valid JSON: {exc}"
        if problem is None and "action" not in parsed and {"headline", "drivers"} <= set(parsed):
            parsed = {"action": "final", "report": parsed}
        action = parsed.get("action")
        if problem is None and action == "tool":
            result = _run_model_tool(parsed, request, case_id)
            evidence.append(result)
            if result["name"] == "validate_and_quantify" and result["payload"].get("ok"):
                quantified = result["payload"]
            messages.append({"role": "user", "content": json.dumps({"tool_result": result})})
            continue
        if problem is None and action == "final":
            quantified = _quantified_for_request(request, case_id, quantified, evidence)
            try:
                return _report_from_model(
                    request, quantified, parsed.get("report"), list(evidence), client.model
                )
            except (KeyError, TypeError, ValueError) as exc:
                problem = f"final.report is malformed: {exc}"
        problem = problem or f"Unknown action {action!r}; reply with action=tool or action=final."
        unusable_replies += 1
        if unusable_replies > MAX_UNUSABLE_REPLIES:
            raise RuntimeError(f"Model kept sending unusable replies: {problem}")
        messages.append({"role": "user", "content": json.dumps({"error": problem})})

    raise RuntimeError("Investigator exceeded MAX_INVESTIGATOR_STEPS without a final report")


def _run_model_tool(
    parsed: dict[str, Any], request: InvestigationRequest, case_id: str
) -> dict[str, Any]:
    name, arguments = parsed.get("name"), parsed.get("arguments") or {}
    if not isinstance(name, str) or not isinstance(arguments, dict):
        return tool_error(
            str(name), {}, 'A tool call needs {"action":"tool","name":<string>,"arguments":<object>}'
        )
    arguments = dict(arguments)
    arguments.setdefault("case_id", case_id)
    if name == "validate_and_quantify":
        arguments.setdefault("territory_id", request.territory_id)
    if name in WINDOWED_TOOLS:
        arguments["window_weeks"] = request.window_weeks
    try:
        return run_tool(name, arguments)
    except Exception as exc:
        return tool_error(name, arguments, f"{type(exc).__name__}: {exc}")


def _quantified_for_request(
    request: InvestigationRequest,
    case_id: str,
    quantified: dict[str, Any] | None,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    if (
        quantified is not None
        and quantified.get("week") == request.week
        and quantified.get("territory_id") == request.territory_id
        and quantified.get("window_weeks") == request.window_weeks
    ):
        return quantified
    record = run_tool(
        "validate_and_quantify",
        {
            "week": request.week,
            "case_id": case_id,
            "territory_id": request.territory_id,
            "window_weeks": request.window_weeks,
        },
    )
    evidence.append(record)
    if not record["payload"].get("ok"):
        raise RuntimeError(record["payload"].get("error") or "validate_and_quantify failed")
    return record["payload"]


def ollama_status(model: str | None = None) -> dict[str, Any]:
    client = OllamaClient(model=model or OLLAMA_MODEL)
    try:
        installed = client.list_models()
        ok, detail = client.available()
    except Exception as exc:
        return {
            "ok": False,
            "detail": f"Ollama not reachable at {client.host}: {exc}",
            "host": client.host,
            "model": client.model,
            "installed": [],
        }
    return {
        "ok": ok,
        "detail": detail,
        "host": client.host,
        "model": client.model,
        "installed": installed,
    }


def _cap_model_confidence(
    driver: DriverEstimate,
    quantified: dict[str, Any],
    request: InvestigationRequest,
    evidence: list[dict[str, Any]],
) -> None:
    """The model may state less confidence than the evidence supports, never more."""
    by_id = {rec["tool_id"]: rec for rec in evidence}
    contrast = next(
        (
            by_id[i]["payload"]
            for i in driver.evidence_ids
            if i in by_id
            and by_id[i]["name"] == "compare_exposed_control"
            and by_id[i]["payload"].get("ok")
            and by_id[i]["payload"].get("driver") == driver.driver
            and by_id[i]["arguments"].get("week") == request.week
        ),
        None,
    )
    if contrast is None:
        cap, reasons = "inconclusive", ["no cited tool result supports this estimate"]
    else:
        cap, reasons = assess_confidence(contrast, quantified["variance_trx"], request.territory_id)
    stated = driver.confidence
    driver.confidence = capped(stated, cap)
    driver.confidence_reasons = list(reasons)
    if driver.confidence != stated:
        driver.confidence_reasons.append(f"the model stated {stated}; capped to {driver.confidence} by the evidence")


def _report_from_model(
    request: InvestigationRequest,
    quantified: dict[str, Any],
    draft: dict[str, Any],
    evidence: list[dict[str, Any]],
    model: str,
) -> InvestigationReport:
    if not isinstance(draft, dict):
        raise ValueError("report must be a JSON object")
    rows = draft.get("drivers") or []
    for row in rows:
        if not isinstance(row, dict) or "driver" not in row or "impact_trx" not in row:
            raise ValueError(f"each driver needs driver and impact_trx, got {row!r}")
    drivers = [
        DriverEstimate(
            driver=str(row["driver"]),
            impact_trx=float(row["impact_trx"]),
            confidence=row.get("confidence") if row.get("confidence") in CONFIDENCE_LEVELS else "low",
            method=row.get("method", "model_interpreted_tool_output"),
            evidence_ids=[str(i) for i in row.get("evidence_ids") or []],
            notes=row.get("notes", ""),
        )
        for row in rows
    ]
    for driver in drivers:
        _cap_model_confidence(driver, quantified, request, evidence)
    impacts = {d.driver: d.impact_trx for d in drivers}
    recon = run_tool(
        "reconcile_attribution",
        {"variance_trx": quantified["variance_trx"], "driver_impacts": impacts},
    )
    evidence.append(recon)
    items = draft.get("what_to_check") or []
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("what_to_check must be a list of objects")
    checks = [
        CheckItem(
            question=item.get("question", ""),
            why=item.get("why", ""),
            owner=item.get("owner", "Brand analytics"),
        )
        for item in items
    ]
    return _report(
        request,
        quantified,
        draft.get("headline")
        or f"{quantified['brand']} week {quantified['week']} variance {quantified['variance_trx']:,.0f}",
        drivers,
        float(recon["payload"]["residual_trx"]),
        checks,
        list(draft.get("caveats") or []),
        evidence,
        investigator_mode="ollama",
        model=model,
        abstained=bool(draft.get("abstained", False)),
    )


def _report(
    request: InvestigationRequest,
    quantified: dict[str, Any],
    headline: str,
    drivers: list[DriverEstimate],
    residual: float,
    checks: list[CheckItem],
    caveats: list[str],
    evidence: list[dict[str, Any]],
    investigator_mode: str,
    model: str | None,
    abstained: bool,
) -> InvestigationReport:
    return InvestigationReport(
        request_id=request.request_id,
        brand=quantified["brand"],
        week=quantified["week"],
        week_ending=quantified["week_ending"],
        headline=headline,
        forecast_trx=float(quantified["forecast"]),
        actual_trx=float(quantified["actual"]),
        variance_trx=float(quantified["variance_trx"]),
        variance_pct=float(quantified["variance_pct"]),
        drivers=drivers,
        residual_trx=residual,
        what_to_check=checks,
        caveats=caveats,
        evidence=[ToolRecord(**row) for row in evidence],
        investigator_mode=investigator_mode,
        model=model,
        abstained=abstained,
        territory_id=request.territory_id,
        window_weeks=request.window_weeks,
    )

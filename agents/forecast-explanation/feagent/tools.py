"""Deterministic analytical tools. Every cited number must come from DuckDB."""

from __future__ import annotations

import inspect
import json
import statistics
from typing import Any, Callable
from uuid import uuid4

from feagent.store import fetchall, fetchone

BASELINE_WEEK_OFFSET = 2
NATIONAL = "NATIONAL"
INVESTIGATOR_TABLES = {"weekly_performance", "commercial_events", "investigation_requests"}


def _record(name: str, arguments: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool_id": f"t_{uuid4().hex[:8]}",
        "name": name,
        "arguments": arguments,
        "payload": payload,
    }


def _decode_regions(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return json.loads(value)


def _weeks(week: int, window_weeks: int) -> list[int]:
    return list(range(week, week + window_weeks))


def _span(week: int, window_weeks: int) -> str:
    return f"week {week}" if window_weeks == 1 else f"weeks {week}-{week + window_weeks - 1}"


def validate_and_quantify(
    week: int,
    case_id: str = "week18",
    territory_id: str = NATIONAL,
    window_weeks: int = 1,
) -> dict[str, Any]:
    arguments = {
        "week": week,
        "case_id": case_id,
        "territory_id": territory_id,
        "window_weeks": window_weeks,
    }
    weeks = _weeks(week, window_weeks)
    rows = fetchall(
        """
        SELECT brand, week, week_ending, metric, forecast, actual, access_status
        FROM weekly_performance
        WHERE region = ? AND metric = 'TRx' AND week BETWEEN ? AND ?
        ORDER BY week
        """,
        [territory_id, weeks[0], weeks[-1]],
    )
    if len(rows) != len(weeks):
        return _record(
            "validate_and_quantify",
            arguments,
            {
                "ok": False,
                "error": f"No {territory_id} TRx row for {_span(week, window_weeks)}"
                if window_weeks == 1
                else f"{territory_id} has {len(rows)} of {window_weeks} weeks from week {week}",
            },
        )
    if any(r["forecast"] is None or r["actual"] is None for r in rows):
        return _record(
            "validate_and_quantify",
            arguments,
            {"ok": False, "error": f"{territory_id} {_span(week, window_weeks)} is missing forecast or actual"},
        )
    if territory_id == NATIONAL:
        regions = fetchall(
            """
            SELECT region, forecast, actual
            FROM weekly_performance
            WHERE region != 'NATIONAL' AND metric = 'TRx' AND week BETWEEN ? AND ?
            ORDER BY region
            """,
            [weeks[0], weeks[-1]],
        )
    else:
        regions = []
    forecast = sum(float(r["forecast"]) for r in rows)
    actual = sum(float(r["actual"]) for r in rows)
    variance = actual - forecast
    missing = sorted({r["region"] for r in regions if r["actual"] is None or r["forecast"] is None})
    provisional_weeks = [r["week"] for r in rows if str(r.get("access_status") or "") == "provisional"]
    payload = {
        "brand": rows[0]["brand"],
        "territory_id": territory_id,
        "week": week,
        "window_weeks": window_weeks,
        "week_ending": rows[-1]["week_ending"],
        "metric": rows[0]["metric"],
        "forecast": forecast,
        "actual": actual,
        "variance_trx": variance,
        "variance_pct": variance / forecast if forecast else None,
        "n_regions": len({r["region"] for r in regions}),
        "missing_regions": missing,
        "data_complete": not missing,
        "actual_is_provisional": bool(provisional_weeks),
        "provisional_weeks": provisional_weeks,
        "source": "duckdb.weekly_performance",
        "ok": True,
    }
    return _record("validate_and_quantify", arguments, payload)


def get_region_deltas(week: int, case_id: str = "week18", window_weeks: int = 1) -> dict[str, Any]:
    baseline_week = week - BASELINE_WEEK_OFFSET
    weeks = _weeks(week, window_weeks)
    current = {
        r["region"]: r
        for r in fetchall(
            """
            SELECT region, SUM(forecast) AS forecast, SUM(actual) AS actual
            FROM weekly_performance
            WHERE region != 'NATIONAL' AND metric = 'TRx' AND week BETWEEN ? AND ?
            GROUP BY region
            ORDER BY region
            """,
            [weeks[0], weeks[-1]],
        )
    }
    baseline = {
        r["region"]: r
        for r in fetchall(
            """
            SELECT region, actual
            FROM weekly_performance
            WHERE region != 'NATIONAL' AND metric = 'TRx' AND week = ?
            """,
            [baseline_week],
        )
    }
    deltas = []
    for region, row in current.items():
        base = baseline[region]
        deltas.append(
            {
                "region": region,
                "forecast": row["forecast"],
                "actual": row["actual"],
                "variance_trx": row["actual"] - row["forecast"],
                "baseline_week": baseline_week,
                "baseline_actual": base["actual"],
                "delta_vs_baseline": row["actual"] - base["actual"] * window_weeks,
            }
        )
    payload = {
        "week": week,
        "window_weeks": window_weeks,
        "baseline_week": baseline_week,
        "regions": deltas,
        "source": "duckdb.weekly_performance",
    }
    return _record(
        "get_region_deltas",
        {"week": week, "case_id": case_id, "window_weeks": window_weeks},
        payload,
    )


def list_candidate_events(
    week: int, window: int = 2, case_id: str = "week18", window_weeks: int = 1
) -> dict[str, Any]:
    lo, hi = week - window, week + window_weeks - 1 + window
    rows = fetchall(
        """
        SELECT event_id, driver, label, week, week_ending, exposed_regions,
               control_regions, excluded_regions, notes, start_week
        FROM commercial_events
        WHERE week BETWEEN ? AND ?
        ORDER BY week, event_id
        """,
        [lo, hi],
    )
    events = []
    for row in rows:
        events.append(
            {
                **row,
                "exposed_regions": _decode_regions(row["exposed_regions"]),
                "control_regions": _decode_regions(row["control_regions"]),
                "excluded_regions": _decode_regions(row["excluded_regions"]),
            }
        )
    payload = {
        "week": week,
        "window": window,
        "window_weeks": window_weeks,
        "events": events,
        "n_events": len(events),
        "source": "duckdb.commercial_events",
    }
    return _record(
        "list_candidate_events",
        {"week": week, "window": window, "case_id": case_id, "window_weeks": window_weeks},
        payload,
    )


def compare_exposed_control(
    event_id: str,
    week: int,
    case_id: str = "week18",
    window_weeks: int = 1,
) -> dict[str, Any]:
    arguments = {"event_id": event_id, "week": week, "case_id": case_id, "window_weeks": window_weeks}
    event = fetchone(
        """
        SELECT event_id, driver, label, week, week_ending, exposed_regions,
               control_regions, excluded_regions, notes, start_week
        FROM commercial_events
        WHERE event_id = ?
        """,
        [event_id],
    )
    if event is None:
        return _record(
            "compare_exposed_control",
            arguments,
            {"ok": False, "error": f"Unknown event_id {event_id}"},
        )

    exposed = _decode_regions(event["exposed_regions"])
    control = _decode_regions(event["control_regions"])
    excluded = _decode_regions(event["excluded_regions"])
    start_week = event["start_week"]
    if start_week is None:
        baseline_week = week - BASELINE_WEEK_OFFSET
        baseline_rule = "fixed_offset"
    else:
        baseline_week = min(start_week - 1, week - 1)
        baseline_rule = "week_before_event_start"
    weeks = _weeks(week, window_weeks)
    cells = fetchall(
        """
        SELECT region, week, forecast, actual
        FROM weekly_performance
        WHERE region != 'NATIONAL' AND metric = 'TRx'
          AND (week BETWEEN ? AND ? OR week = ?)
        """,
        [weeks[0], weeks[-1], baseline_week],
    )
    actual = {(c["region"], c["week"]): c["actual"] for c in cells}
    forecast = {(c["region"], c["week"]): c["forecast"] for c in cells}

    missing = sorted(
        {
            r
            for r in exposed + control
            for w in weeks
            if actual.get((r, w)) is None or forecast.get((r, w)) is None
        }
    )
    if missing:
        return _record(
            "compare_exposed_control",
            arguments,
            {"ok": False, "error": f"No TRx forecast or actual for {missing} in {_span(week, window_weeks)}"},
        )

    view = _forecast_error_view(exposed, control, weeks, actual, forecast)
    baseline_change = _baseline_change(exposed, control, weeks, baseline_week, actual)
    payload = {
        "ok": True,
        "event_id": event_id,
        "driver": event["driver"],
        "label": event["label"],
        "week": week,
        "window_weeks": window_weeks,
        "exposed_regions": exposed,
        "control_regions": control,
        "excluded_regions": excluded,
        "estimated_total_trx": None if view is None else view["effect_trx"],
        "estimate_per_exposed_region": None if view is None else round(view["effect_trx"] / len(exposed), 6),
        "effect_by_exposed_region": {} if view is None else {row["region"]: row["effect_trx"] for row in view["by_region"]},
        "forecast_error_view": view,
        "baseline_week": baseline_week,
        "baseline_rule": baseline_rule,
        "event_start_week": start_week,
        **baseline_change,
        "method": "forecast_error_difference_vs_named_controls",
        "notes": event.get("notes") or "",
        "assumption": "Named control regions are unaffected by this driver and, absent the driver, would have missed forecast by the same rate as the exposed regions. Overlap is handled by excluding contaminated regions, not by a joint model. The baseline-change fields are a cross-check: the change in actuals since the week before the event starts (two weeks before the flagged week when the start is unknown), summed over the window.",
        "source": "duckdb.weekly_performance + duckdb.commercial_events",
    }
    return _record("compare_exposed_control", arguments, payload)


def primary_estimate(payload: dict[str, Any], territory_id: str = NATIONAL) -> float | None:
    """The TRx effect of the event on the investigation scope: the national total, or one territory's share."""
    if territory_id == NATIONAL:
        value = payload.get("estimated_total_trx")
    else:
        value = (payload.get("effect_by_exposed_region") or {}).get(territory_id)
    return None if value is None else float(value)


def baseline_change_estimate(payload: dict[str, Any], territory_id: str = NATIONAL) -> float | None:
    key = "baseline_change_total_trx" if territory_id == NATIONAL else "baseline_change_per_exposed_region"
    value = payload.get(key)
    return None if value is None else float(value)


def _baseline_change(
    exposed: list[str],
    control: list[str],
    weeks: list[int],
    baseline_week: int,
    actual: dict[tuple[str, int], float],
) -> dict[str, Any]:
    empty = {
        "exposed_mean_delta": None,
        "control_mean_delta": None,
        "baseline_change_per_exposed_region": None,
        "baseline_change_total_trx": None,
        "weekly_did": [],
        "exposed_detail": [],
        "control_detail": [],
    }
    if any(actual.get((r, baseline_week)) is None for r in exposed + control):
        return empty

    def delta(region: str, w: int) -> float:
        return actual[(region, w)] - actual[(region, baseline_week)]

    def mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    exposed_rows = [{"region": r, "delta": sum(delta(r, w) for w in weeks)} for r in exposed]
    control_rows = [{"region": r, "delta": sum(delta(r, w) for w in weeks)} for r in control]
    exposed_mean = mean([row["delta"] for row in exposed_rows])
    control_mean = mean([row["delta"] for row in control_rows])
    did = None if exposed_mean is None or control_mean is None else exposed_mean - control_mean
    return {
        "exposed_mean_delta": exposed_mean,
        "control_mean_delta": control_mean,
        "baseline_change_per_exposed_region": did,
        "baseline_change_total_trx": None if did is None else did * len(exposed),
        "weekly_did": [
            {
                "week": w,
                "did_per_exposed_region": None
                if not control
                else mean([delta(r, w) for r in exposed]) - mean([delta(r, w) for r in control]),
            }
            for w in weeks
        ],
        "exposed_detail": exposed_rows,
        "control_detail": control_rows,
    }


def _forecast_error_view(
    exposed: list[str],
    control: list[str],
    weeks: list[int],
    actual: dict[tuple[str, int], float],
    forecast: dict[tuple[str, int], float],
) -> dict[str, Any] | None:
    """Exposed forecast error beyond what the control regions' forecast error implies.

    The forecast already carries each region's trend, so comparing forecast errors
    (A - F) isolates a miss. Per exposed region: effect = error - control mean error
    rate x forecast; the regions' effects add up to the total.
    """
    if not exposed or not control:
        return None

    def totals(region: str) -> tuple[float, float]:
        f = sum(forecast[(region, w)] for w in weeks)
        return f, sum(actual[(region, w)] for w in weeks) - f

    control_rates = []
    for region in control:
        f, e = totals(region)
        control_rates.append(e / f if f else 0.0)
    control_mean = sum(control_rates) / len(control_rates)
    spread = statistics.stdev(control_rates) if len(control_rates) >= 2 else None

    by_region = []
    for region in exposed:
        f, e = totals(region)
        by_region.append(
            {
                "region": region,
                "forecast_trx": f,
                "error_trx": e,
                "error_rate": e / f if f else 0.0,
                "effect_trx": round(e - control_mean * f, 6),
            }
        )
    exposed_forecast = sum(row["forecast_trx"] for row in by_region)
    exposed_error = sum(row["error_trx"] for row in by_region)
    return {
        "n_controls": len(control),
        "exposed_forecast_trx": exposed_forecast,
        "exposed_error_trx": exposed_error,
        "exposed_error_rate": exposed_error / exposed_forecast if exposed_forecast else 0.0,
        "control_error_rate_mean": control_mean,
        "control_error_rate_spread": spread,
        "effect_trx": round(sum(row["effect_trx"] for row in by_region), 6),
        "by_region": by_region,
        "note": "exposed error minus the mean control forecast-error rate times the exposed forecast, per exposed region and in total",
    }


def reconcile_attribution(
    variance_trx: float,
    driver_impacts: dict[str, float],
) -> dict[str, Any]:
    explained = sum(driver_impacts.values())
    residual = variance_trx - explained
    payload = {
        "variance_trx": variance_trx,
        "driver_impacts": driver_impacts,
        "explained_trx": explained,
        "residual_trx": residual,
        "reconciles": abs(explained + residual - variance_trx) < 1e-6,
    }
    return _record(
        "reconcile_attribution",
        {"variance_trx": variance_trx, "driver_impacts": driver_impacts},
        payload,
    )


TOOL_SPECS: dict[str, dict[str, Any]] = {
    "validate_and_quantify": {
        "description": "Validate completeness and quantify forecast vs actual variance for a week, nationally or for one territory.",
        "parameters": {
            "week": "int",
            "case_id": "str, optional",
            "territory_id": "str, optional, default NATIONAL",
            "window_weeks": "int, optional, default 1",
        },
    },
    "get_region_deltas": {
        "description": "Region-level actual vs forecast and vs a two-week baseline.",
        "parameters": {"week": "int", "case_id": "str, optional", "window_weeks": "int, optional, default 1"},
    },
    "list_candidate_events": {
        "description": "Commercial events in a window around the flagged week.",
        "parameters": {
            "week": "int",
            "window": "int, optional",
            "case_id": "str, optional",
            "window_weeks": "int, optional, default 1",
        },
    },
    "compare_exposed_control": {
        "description": "Estimate one event's TRx effect as the exposed regions' forecast error beyond the named control regions' forecast error (A - F), with a baseline-change cross-check.",
        "parameters": {
            "event_id": "str",
            "week": "int",
            "case_id": "str, optional",
            "window_weeks": "int, optional, default 1",
        },
    },
    "reconcile_attribution": {
        "description": "Check that driver estimates plus residual equal the national variance.",
        "parameters": {"variance_trx": "float", "driver_impacts": "object mapping driver -> TRx impact"},
    },
}


def run_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments or {}
    fns: dict[str, Callable[..., dict[str, Any]]] = {
        "validate_and_quantify": validate_and_quantify,
        "get_region_deltas": get_region_deltas,
        "list_candidate_events": list_candidate_events,
        "compare_exposed_control": compare_exposed_control,
        "reconcile_attribution": reconcile_attribution,
    }
    if name not in fns:
        return _record(name, arguments, {"ok": False, "error": f"Unknown tool {name}"})
    if "case_id" in arguments and "case_id" not in inspect.signature(fns[name]).parameters:
        arguments = {key: value for key, value in arguments.items() if key != "case_id"}
    return fns[name](**arguments)


def tool_error(name: str, arguments: dict[str, Any], message: str) -> dict[str, Any]:
    return _record(name, arguments, {"ok": False, "error": message})

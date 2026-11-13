"""Views of one briefing (core-007 FR-002 to FR-006).

The leadership view is cut from the full answer by code: it keeps every line except the
driver-check detail, so each number it shows is already a claim of the same run and every
caveat (withheld cuts, restatements, abstentions) survives. It carries no claims, evidence,
query text or trace.
"""
from __future__ import annotations

CHECKS_HEADER = "Checked, in this order:"
DROPPED_PREFIX = "Considered and dropped:"


def executive_summary(answer: str) -> str:
    keep: list[str] = []
    in_checks = False
    for line in answer.splitlines():
        if not line.strip():
            continue
        if line.startswith(CHECKS_HEADER):
            in_checks = True
            continue
        if in_checks and line.lstrip().startswith("- "):
            continue
        in_checks = False
        if line.startswith(DROPPED_PREFIX):
            continue
        keep.append(line)
    return "\n".join(keep)


LEADERSHIP_FIELDS = ("brief_id", "engine", "system", "brand_id", "territory_id", "week_start",
                     "data_version", "abstained", "review_status", "reviewed_at")


def leadership(record: dict) -> dict:
    """Build the leadership response from a stored brief. Allow-list, so a new field on the
    analyst result never reaches a leader by accident."""
    result = record["result"]
    out = {k: (record.get(k) if k in record else result.get(k)) for k in LEADERSHIP_FIELDS}
    out["view"] = "leadership"
    out["summary"] = executive_summary(result["answer"])
    return out


REVIEW_STATE = {"pending": "IN_REVIEW", "approved": "PUBLISHED", "rejected": "RETURNED"}  # Briefing §6, stage 7


def analyst(record: dict) -> dict:
    out = dict(record["result"])
    out.update(brief_id=record["brief_id"], view="analyst", review_status=record["review_status"],
               reviewed_at=record.get("reviewed_at"), review_reason=record.get("review_reason"))
    if out.get("flow"):
        flow = [dict(s) for s in out["flow"]]
        flow[-1]["states"] = ["IN_REVIEW"] if record["review_status"] == "pending" else ["IN_REVIEW", REVIEW_STATE[record["review_status"]]]
        out["flow"] = flow
    return out


# Forecast leadership view: an executive summary. No stage trace, evidence, tool calls or check detail.
FORECAST_LEADERSHIP_REPORT = ("headline", "brand", "territory_id", "week", "week_ending", "window_weeks", "forecast_trx",
                              "actual_trx", "variance_trx", "variance_pct", "residual_trx", "caveats", "abstained")


def forecast_leadership(run: dict) -> dict:
    """Allow-list, so a new field on the analyst run never reaches a leader by accident."""
    report = run["report"]
    out = {k: run.get(k) for k in ("run_id", "lane", "workflow_status", "dataset_release")}
    out["report"] = {k: report.get(k) for k in FORECAST_LEADERSHIP_REPORT}
    out["report"]["drivers"] = [{k: d.get(k) for k in ("driver", "impact_trx", "confidence")} for d in report["drivers"]]
    out["report"]["what_to_check"] = [{k: c.get(k) for k in ("question", "why", "owner")} for c in report["what_to_check"]]
    out["report"]["verification"] = {"verdict": (report.get("verification") or {}).get("verdict")}
    return out


def forecast_record(record: dict, view: str) -> dict:
    """A stored Forecast run for one view, with its review state. The analyst also sees who did what (pseudonyms)."""
    narrative = record.get("narrative")
    out = {"view": view, "forecast_run_id": record["run_id"], "review_status": record["review_status"],
           "reviewed_at": record["reviewed_at"], "review_note": record["review_note"],
           "report_model": record.get("report_model", "none"), "writer_status": record.get("writer_status", "skipped")}
    if view == "leadership":  # the writer's notes for the analyst never reach a leader
        leadership_narrative = {k: v for k, v in narrative.items() if k != "analyst_notes"} if narrative else None
        return {**out, "narrative": leadership_narrative, **forecast_leadership(record["result"])}
    return {**out, "narrative": narrative, "writer_attempts": record.get("writer_attempts", []),
            "submitted_at": record["submitted_at"], "history": record["history"], **record["result"]}


def forecast_summary(record: dict) -> dict:
    """One row of a list: enough to pick a run, no evidence."""
    report, request = record["result"]["report"], record["request"]
    return {"forecast_run_id": record["run_id"], "territory_id": request["territory_id"], "week_start": request["week_start"],
            "window_weeks": request["window_weeks"], "variance_trx": report["variance_trx"], "abstained": report["abstained"],
            "headline": report["headline"], "review_status": record["review_status"], "created_at": record["created_at"],
            "reviewed_at": record["reviewed_at"]}

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


def analyst(record: dict) -> dict:
    out = dict(record["result"])
    out.update(brief_id=record["brief_id"], view="analyst", review_status=record["review_status"],
               reviewed_at=record.get("reviewed_at"), review_reason=record.get("review_reason"))
    return out

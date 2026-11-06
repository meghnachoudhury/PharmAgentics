"""Adapter from a validated browser request to the existing scripted Briefing engine.

No SQL is accepted from callers. No evaluation data is imported. This is an MVP
backend seam; neither human approval nor saved history is implemented here.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from .schemas import BriefingQuery, BriefingResult, ReleaseContext

ROOT = Path(__file__).resolve().parents[3]
BRIEFING_DIR = ROOT / "agents" / "brand-briefing"
DB = ROOT / "local" / "pharmagentics.duckdb"
TERRITORIES = {
    "GREAT_LAKES": "Great Lakes", "MID_ATLANTIC": "Mid-Atlantic",
    "MOUNTAIN": "Mountain", "NEW_ENGLAND": "New England",
    "NORTHWEST": "Northwest", "PACIFIC": "Pacific",
    "SOUTHEAST": "Southeast", "SOUTH_CENTRAL": "South Central",
    "NATIONAL": "National",
}


class MissingDatabase(RuntimeError):
    pass


class OutsideRelease(ValueError):
    pass


def release_context() -> ReleaseContext:
    """Read available Monday weeks from the actual data release (not wall-clock time)."""
    if not DB.is_file():
        raise MissingDatabase("DuckDB has not been built. Run the data loader first.")
    from pharmagentics.tools import Registry

    reg = Registry(DB)
    try:
        first, latest = reg.rows(
            "SELECT min(week_start)::varchar, max(week_start)::varchar FROM raw.calendar"
        )[0]
    finally:
        reg.close()
    if not first or not latest:
        raise MissingDatabase("DuckDB calendar is empty. Reload the synthetic release.")
    return ReleaseContext(
        first_week=date.fromisoformat(first),
        latest_week=date.fromisoformat(latest),
        territory_ids=list(TERRITORIES),
    )


def normalize_question(request: BriefingQuery) -> str:
    """Place *both* the ISO date and territory before ':' for window.parse().

    The existing parser only inspects text before the first colon. The UI does
    not rely on the LLM or the free-text question to choose its data scope.
    """
    label = TERRITORIES[request.territory_id]
    return f"Week of {request.week_start.isoformat()} in {label}: {request.question.strip()}"


def run_briefing(request: BriefingQuery) -> BriefingResult:
    bounds = release_context()
    if not bounds.first_week <= request.week_start <= bounds.latest_week:
        raise OutsideRelease(
            f"Requested week is outside the synthetic data release "
            f"({bounds.first_week.isoformat()} to {bounds.latest_week.isoformat()})."
        )
    # Import the existing lane directly, exactly as eval/harness/systems.py does.
    # Do not import eval/ from runtime code or reconstruct KPI logic here.
    path = str(BRIEFING_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    from briefing_baseline.pipeline import answer

    question = normalize_question(request)
    raw = answer(question, db=DB)

    claims = raw.get("claims", [])
    evidence = raw.get("evidence", [])
    evidence_by_id = {e["id"]: e for e in evidence}
    if any(c["evidence_id"] not in evidence_by_id for c in claims):
        raise RuntimeError("The briefing returned an untraceable claim.")
    versions = {e.get("data_version") for e in evidence if e.get("data_version")}
    if len(versions) > 1:
        raise RuntimeError("The briefing returned evidence from multiple data versions.")

    return BriefingResult(
        system=raw["system"], question=question,
        brand_id=request.brand_id, territory_id=request.territory_id,
        week_start=request.week_start,
        answer=raw["answer"], claims=claims, evidence=evidence,
        data_version=next(iter(versions), None),
        abstained=bool(raw.get("abstained", False)),
    )

"""Adapter from a validated browser request to the existing scripted Briefing engine.

No SQL is accepted from callers. No evaluation data is imported. This is an MVP
backend seam; neither human approval nor saved history is implemented here.
"""
from __future__ import annotations

import re
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
        week_rows = reg.rows(
            "SELECT DISTINCT week_start::varchar FROM raw.calendar ORDER BY 1"
        )
        territory_rows = reg.rows(
            "SELECT DISTINCT territory_id FROM raw.dim_territory ORDER BY 1"
        )
        product_rows = reg.rows(
            "SELECT DISTINCT product_id FROM raw.dim_product ORDER BY 1"
        )
    finally:
        reg.close()
    if not week_rows:
        raise MissingDatabase("DuckDB calendar is empty. Reload the synthetic release.")
    weeks = [date.fromisoformat(row[0]) for row in week_rows]
    # Only expose real, supported territories; don't imply district/plan-level UI.
    available_territories = [row[0] for row in territory_rows if row[0] in TERRITORIES and row[0] != "NATIONAL"]
    if not available_territories:
        raise MissingDatabase("No supported territories found in the data release.")
    # The scripted engine is specifically BXA-only, even though the synthetic
    # product dimension includes competitors. Never advertise the competitors
    # as selectable brands without corresponding Briefing engine support.
    supported_products = [row[0] for row in product_rows if row[0] == "BXA"]
    if not supported_products:
        raise MissingDatabase("The scripted Briefing brand is missing from the synthetic release.")
    return ReleaseContext(
        first_week=weeks[0], latest_week=weeks[-1],
        territory_ids=available_territories,
        available_weeks=weeks, product_ids=supported_products,
    )


def current_data_version() -> str:
    """The pinned version of the loaded release; approved briefs from another version are not served."""
    if not DB.is_file():
        raise MissingDatabase("DuckDB has not been built. Run the data loader first.")
    from pharmagentics.tools import Registry

    reg = Registry(DB)
    try:
        return reg.data_version
    finally:
        reg.close()


def normalize_question(request: BriefingQuery) -> str:
    """Place *both* the ISO date and territory before ':' for window.parse().

    The existing parser only inspects text before the first colon. The UI does
    not rely on the LLM or the free-text question to choose its data scope.
    """
    label = TERRITORIES[request.territory_id]
    return f"Week of {request.week_start.isoformat()} in {label}: {request.question.strip()}"


class StalePlan(ValueError):
    """The triage decision names a plan that code no longer builds (brief-002; HTTP 409)."""


class BadDecision(ValueError):
    """The triage decision names a story the plan does not propose (brief-002 FR-023; HTTP 400)."""


def _check_scope(request: BriefingQuery) -> None:
    bounds = release_context()
    if request.week_start not in bounds.available_weeks:
        raise OutsideRelease(
            f"Requested week is outside the synthetic data release "
            f"({bounds.first_week.isoformat()} to {bounds.latest_week.isoformat()})."
        )
    if request.territory_id not in bounds.territory_ids:
        raise OutsideRelease("Territory not present in the supported synthetic data release.")
    # Import the existing lane directly, exactly as eval/harness/systems.py does.
    # Do not import eval/ from runtime code or reconstruct KPI logic here.
    path = str(BRIEFING_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)


def _traceable(claims: list, evidence: list) -> str | None:
    evidence_by_id = {e["id"]: e for e in evidence}
    if any(c["evidence_id"] not in evidence_by_id for c in claims):
        raise RuntimeError("The briefing returned an untraceable claim.")
    versions = {e.get("data_version") for e in evidence if e.get("data_version")}
    if len(versions) > 1:
        raise RuntimeError("The briefing returned evidence from multiple data versions.")
    return next(iter(versions), None)


def run_triage(request: BriefingQuery) -> dict:
    """Stages 1 to 3 and the code triage plan for P1 (brief-002 US8)."""
    _check_scope(request)
    from briefing_baseline.pipeline import triage

    plan = triage(normalize_question(request), db=DB)
    _traceable(plan["claims"], plan["evidence"])
    plan.update(brand_id=request.brand_id, territory_id=request.territory_id, week_start=request.week_start.isoformat())
    return plan


def run_briefing(request: BriefingQuery) -> BriefingResult:
    _check_scope(request)
    question = normalize_question(request)
    extra = {}
    if request.triage is None:
        from briefing_baseline.pipeline import answer

        raw = answer(question, db=DB)
    else:
        from briefing_baseline import pipeline

        try:
            out = pipeline.run_with_plan(question, request.triage.model_dump(), db=DB)
        except pipeline.StalePlan as exc:
            raise StalePlan(str(exc)) from exc
        except ValueError as exc:
            raise BadDecision(str(exc)) from exc
        raw, extra = out["envelope"], {"triage": out["triage"], "flow": out["flow"]}

    claims = raw.get("claims", [])
    evidence = raw.get("evidence", [])
    return BriefingResult(
        system=raw["system"], question=question,
        brand_id=request.brand_id, territory_id=request.territory_id,
        week_start=request.week_start,
        answer=raw["answer"], claims=claims, evidence=evidence,
        data_version=_traceable(claims, evidence),
        abstained=bool(raw.get("abstained", False)), **extra,
    )


_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_NUMBER = re.compile(r"(?<![\w.-])\d[\d,.]*%?")


def untraced_numbers(answer: str, claims: list[dict], data_version: str | None) -> list[str]:
    """Numbers in a brief's text that are not one of its claim values (core-007 FR-027). Dates, the data
    version and identifiers with letters (plan IDs) are not numbers."""
    text = _DATE.sub(" ", answer.replace(data_version, " ") if data_version else answer)
    values = {c["value"] for c in claims}
    return [n for n in (m.group(0).rstrip(".,") for m in _NUMBER.finditer(text)) if n and n not in values]


def accept_agent_brief(query: BriefingQuery, posted: dict) -> BriefingResult:
    """A brief posted by the worker, admitted only if it is traceable on this app's data version (FR-027)."""
    env = posted.get("envelope") or {}
    claims, evidence = env.get("claims") or [], env.get("evidence") or []
    version = _traceable(claims, evidence)
    if version != current_data_version():
        raise RuntimeError(f"The agent ran on data version {version}, not this app's {current_data_version()}.")
    if (bad := untraced_numbers(env.get("answer", ""), claims, version)):
        raise RuntimeError(f"Numbers with no claim behind them: {', '.join(bad[:5])}.")
    return BriefingResult(
        engine="agent", system=str(env.get("system", "briefing_agent")), question=normalize_question(query),
        brand_id=query.brand_id, territory_id=query.territory_id, week_start=query.week_start,
        answer=env.get("answer", ""), claims=claims, evidence=evidence, data_version=version,
        abstained=bool(env.get("abstained", False)), triage=posted.get("triage"), flow=posted.get("flow"),
    )

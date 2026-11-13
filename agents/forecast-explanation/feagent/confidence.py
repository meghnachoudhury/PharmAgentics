"""Confidence for an exposed-vs-control estimate is decided by the evidence, not by the model."""

from __future__ import annotations

from typing import Any

from feagent.tools import NATIONAL, baseline_change_estimate, primary_estimate

LEVELS = ["inconclusive", "low", "medium", "high"]
MIN_CONTROLS_FOR_HIGH = 2
NOISE_LOW = 2.0
NOISE_HIGH = 3.0
AGREEMENT_SHARE = 0.25


def rank(level: str) -> int:
    return LEVELS.index(level) if level in LEVELS else LEVELS.index("low")


def estimators_disagree(contrast: dict[str, Any], variance_trx: float, territory_id: str = NATIONAL) -> str | None:
    """Describe a material gap between the primary estimate and the baseline-change cross-check."""
    primary = primary_estimate(contrast, territory_id)
    cross = baseline_change_estimate(contrast, territory_id)
    if primary is None or cross is None or not variance_trx:
        return None
    if abs(primary - cross) <= AGREEMENT_SHARE * abs(variance_trx):
        return None
    return (
        f"the baseline-change cross-check ({cross:+,.1f} TRx) differs from the forecast-error estimate "
        f"({primary:+,.1f} TRx) by more than {AGREEMENT_SHARE:.0%} of the miss"
    )


def assess_confidence(
    contrast: dict[str, Any], variance_trx: float, territory_id: str = NATIONAL
) -> tuple[str, list[str]]:
    """The highest confidence the compare_exposed_control payload supports, and why it is capped."""
    cap, reasons = "high", []

    def limit(level: str, reason: str) -> None:
        nonlocal cap
        reasons.append(reason)
        if rank(level) < rank(cap):
            cap = level

    view = contrast.get("forecast_error_view")
    effect = primary_estimate(contrast, territory_id)
    if view is None or effect is None:
        limit("inconclusive", "no control region, so the effect cannot be isolated")
        return cap, reasons
    if view["n_controls"] < MIN_CONTROLS_FOR_HIGH:
        limit("medium", f"only {view['n_controls']} control region; at least {MIN_CONTROLS_FOR_HIGH} needed for high")
    if variance_trx and effect * variance_trx < 0:
        limit("low", "the estimate points against the miss")
    spread = view["control_error_rate_spread"]
    if spread is not None:
        exposed_rate = view["exposed_error_rate"]
        if territory_id != NATIONAL:
            exposed_rate = next(r["error_rate"] for r in view["by_region"] if r["region"] == territory_id)
        gap = abs(exposed_rate - view["control_error_rate_mean"])
        shown = (
            f"the exposed error rate differs from the control mean by {gap * 100:.1f} points, "
            f"against a spread of {spread * 100:.1f} points across control regions"
        )
        if gap < NOISE_LOW * spread:
            limit("low", f"{shown}: within {NOISE_LOW:g}x the spread")
        elif gap < NOISE_HIGH * spread:
            limit("medium", f"{shown}: under {NOISE_HIGH:g}x the spread")
    disagreement = estimators_disagree(contrast, variance_trx, territory_id)
    if disagreement:
        limit("medium", disagreement)
    return cap, reasons


def capped(level: str, cap: str) -> str:
    level = level if level in LEVELS else "low"
    return level if rank(level) <= rank(cap) else cap

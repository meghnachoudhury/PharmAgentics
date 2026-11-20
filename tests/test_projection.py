"""Projected national (brief-003 FR-022, SC-011; ADR 0001).

The hand calculation here reads the raw feed directly and shares no SQL with the tools, so a mistake in
`reporting.v_rx_projection` or `queries.projection_ctes` shows up as a mismatch.
"""
import duckdb
import pytest

from pharmagentics.tools import DEFAULT_DB, Registry
from pharmagentics.tools import queries as q
from pharmagentics.tools.registry import FORMATS

needs_db = pytest.mark.skipif(not DEFAULT_DB.exists(), reason="build it with: uv run python src/pharmagentics/data/load_duckdb.py")

COMPLETENESS = {"MISSING_RX_KEYS", "ROW_COUNT_MISMATCH", "LOW_OR_INVALID_COVERAGE", "LATE_OR_UNKNOWN_DELIVERY",
                "SOURCE_NOT_COMPLETE"}


def _hand(con) -> dict[str, float | None]:
    """Week -> projected national BXA TRx, computed from raw rows in Python."""
    health = {(w, t): (s, r or "", c) for w, t, s, r, c in con.execute(
        "select week_start::varchar, territory_id, health_status, flag_reasons, panel_coverage_ratio from reporting.v_feed_health").fetchall()}
    trx = {(w, t): float(x) for w, t, x in con.execute(
        "select week_start::varchar, territory_id, sum(trx) from raw.rx_weekly where product_id = 'BXA' group by 1, 2").fetchall()}
    calendar = {w: bool(h or r) for w, h, r in con.execute(
        "select week_start::varchar, holiday_flag, plan_year_reset from raw.calendar").fetchall()}
    weeks = sorted(calendar)
    terrs = sorted({t for _, t in health})
    clean = [w for w in weeks if not calendar[w] and all(health[(w, t)][0] == "PASS" for t in terrs)]

    def basis(w, t):
        status, reasons, cov = health[(w, t)]
        if status == "PASS":
            return "observed"
        if set(reasons.split(";")) <= COMPLETENESS and cov is not None and cov >= 0.5:
            return "projected"
        return "estimated"

    out = {}
    for w in weeks:
        known, shares = 0.0, 0.0
        before = [c for c in clean if c < w][-4:]
        for t in terrs:
            b = basis(w, t)
            if b == "estimated":
                total = sum(trx.get((c, o), 0.0) for c in before for o in terrs)
                shares += sum(trx.get((c, t), 0.0) for c in before) / total
            else:
                known += trx.get((w, t), 0.0) / health[(w, t)][2]
        out[w] = known / (1 - shares) if any(basis(w, t) != "estimated" for t in terrs) else None
    return out


@needs_db
def test_projected_national_matches_the_hand_calculation_every_week():
    con = duckdb.connect(str(DEFAULT_DB), read_only=True)
    try:
        hand = _hand(con)
        wrong = []
        for w, want in hand.items():
            got = con.execute(q.projected_national([w])).fetchone()[0]
            if FORMATS["int"](got) != FORMATS["int"](want):
                wrong.append((w, got, want))
        assert len(hand) == 104 and not wrong
    finally:
        con.close()


@needs_db
@pytest.mark.parametrize("week, territory, basis, value, national", [
    ("2026-04-06", "MID_ATLANTIC", "estimated", "711", "4,571"),  # restatement review
    ("2026-05-04", "NEW_ENGLAND", "projected", "407", "4,491"),  # 267 observed at coverage 0.656
    ("2026-07-06", "GREAT_LAKES", "estimated", "620", "4,285"),  # duplicate keys
])
def test_the_three_failed_cuts(week, territory, basis, value, national):
    con = duckdb.connect(str(DEFAULT_DB), read_only=True)
    try:
        assert con.execute(q.projection_cell(week, territory, "basis")).fetchone()[0] == basis
        assert FORMATS["int"](con.execute(q.projected_territory([week], territory)).fetchone()[0]) == value
        assert FORMATS["int"](con.execute(q.projected_national([week])).fetchone()[0]) == national
        if basis == "estimated":  # a duplicate or under-review cut never exposes its own count
            assert con.execute(q.projection_cell(week, territory, "observed_trx")).fetchone()[0] is None
    finally:
        con.close()


@needs_db
def test_a_clean_week_projects_to_the_observed_sum():
    reg = Registry()
    try:
        observed = reg.scalar(q.trx_sum(["2025-04-21"]))
        assert reg.scalar(q.projected_national(["2025-04-21"])) == pytest.approx(observed)
    finally:
        reg.close()


@needs_db
@pytest.mark.parametrize("question, territory", [
    ("Week of 2026-05-04: Is this week's data complete?", "New England"),
    ("Week of 2026-07-06: What changed?", "Great Lakes"),
])
def test_no_story_is_opened_for_a_projected_or_estimated_cut(question, territory):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents" / "brand-briefing"))
    from briefing_baseline import answer

    text = answer(question)["answer"]
    assert not any(line.startswith("Story") and territory in line for line in text.splitlines())

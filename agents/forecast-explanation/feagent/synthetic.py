"""Build the Week 18 reference case.

National totals match the Oct 9 illustrative miss:
  forecast 12,000 / actual 9,600 / variance -2,400
  payer -1,350, competitor -650, residual -400

Regional design is identifiable on purpose so v1 tools can recover
those totals. Overlapping national launches are listed in DATA_GAPS.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from feagent.config import BRAND, METRIC

N_WEEKS = 24
FLAGGED_WEEK = 18
REGIONS = ("Northeast", "Midwest", "South", "West")
FORECAST_PER_REGION = 3_000.0

# Injected effects that shape the LUMINA engineering fixture. Nothing reads them back as an answer.
PAYER_IMPACT = {"Northeast": -675.0, "South": -675.0}
COMPETITOR_IMPACT = {"Midwest": -650.0}
RESIDUAL_PER_REGION = -100.0


def week_ending(week: int) -> str:
    # Synthetic calendar: week 1 ends Friday 2026-01-09.
    start = date(2026, 1, 9)
    return (start + timedelta(weeks=week - 1)).isoformat()


def region_actual(region: str, week: int) -> float:
    actual = FORECAST_PER_REGION
    if week >= FLAGGED_WEEK:
        actual += PAYER_IMPACT.get(region, 0.0)
        actual += COMPETITOR_IMPACT.get(region, 0.0)
        actual += RESIDUAL_PER_REGION
    return actual


def build_case() -> dict[str, Any]:
    weekly_region: list[dict[str, Any]] = []
    weekly_national: list[dict[str, Any]] = []

    for week in range(1, N_WEEKS + 1):
        ending = week_ending(week)
        region_rows = []
        for region in REGIONS:
            row = {
                "brand": BRAND,
                "week": week,
                "week_ending": ending,
                "region": region,
                "metric": METRIC,
                "forecast": FORECAST_PER_REGION,
                "actual": region_actual(region, week),
            }
            region_rows.append(row)
            weekly_region.append(row)
        weekly_national.append(
            {
                "brand": BRAND,
                "week": week,
                "week_ending": ending,
                "metric": METRIC,
                "forecast": sum(r["forecast"] for r in region_rows),
                "actual": sum(r["actual"] for r in region_rows),
            }
        )

    events = [
        {
            "event_id": "evt_payer_001",
            "driver": "payer_access",
            "label": "Formulary downgrade (Plan Alpha)",
            "week": 17,
            "week_ending": week_ending(17),
            "exposed_regions": ["Northeast", "South"],
            "control_regions": ["West"],
            "excluded_regions": ["Midwest"],
            "notes": "Midwest excluded from this contrast because a competitor event lands there in week 18.",
        },
        {
            "event_id": "evt_comp_001",
            "driver": "competitor_activity",
            "label": "Competitor launch (Rivalza)",
            "week": 18,
            "week_ending": week_ending(18),
            "exposed_regions": ["Midwest"],
            "control_regions": ["West"],
            "excluded_regions": ["Northeast", "South"],
            "notes": "Payer-exposed regions excluded so the competitor contrast is not mixed with the access shock.",
        },
    ]

    request = {
        "request_id": "req_lumina_w18",
        "source": "manual",
        "brand": BRAND,
        "week": FLAGGED_WEEK,
        "week_ending": week_ending(FLAGGED_WEEK),
        "metric": METRIC,
        "notes": "Material TRx miss flagged for investigation.",
    }

    observable = {
        "brand": BRAND,
        "metric": METRIC,
        "flagged_week": FLAGGED_WEEK,
        "weekly_national": weekly_national,
        "weekly_region": weekly_region,
        "events": events,
        "default_request": request,
        "data_status": {
            "forecast_actuals": "synthetic_placeholder",
            "events": "synthetic_placeholder",
            "public_calibration": "missing",
        },
    }

    return {"observable": observable}

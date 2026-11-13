from __future__ import annotations

from typing import Any

from feagent.store import connect, fetchall, fetchone


def load_observable(case_id: str = "week18") -> dict[str, Any]:
    connect()
    national = fetchall(
        """
        SELECT brand, week, week_ending, metric, forecast, actual
        FROM weekly_performance
        WHERE region = 'NATIONAL' AND metric = 'TRx'
        ORDER BY week
        """
    )
    regional = fetchall(
        """
        SELECT brand, week, week_ending, region, metric, forecast, actual,
               access_status, competitor_share, segment
        FROM weekly_performance
        WHERE region != 'NATIONAL' AND metric = 'TRx'
        ORDER BY week, region
        """
    )
    flagged = next(row for row in national if row["week"] == 18)
    return {
        "brand": flagged["brand"],
        "metric": flagged["metric"],
        "flagged_week": 18,
        "weekly_national": national,
        "weekly_region": regional,
        "default_request": fetchone(
            "SELECT request_id, source, brand, week, week_ending, metric, notes "
            "FROM investigation_requests WHERE request_id = 'req_lumina_w18'"
        ),
        "data_status": {"source": "duckdb", "case_id": case_id},
    }

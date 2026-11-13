"""Meghna day1-v1 world, projected onto the Investigator table names.

Does not replace the 14 source tables. Tools keep reading weekly_performance
and commercial_events; those become views over forecast_vs_actual_weekly plus
a small observable event calendar (no answer-key magnitudes).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb

from feagent import config

_connection: duckdb.DuckDBPyConnection | None = None

TERRITORIES = [
    "NEW_ENGLAND",
    "MID_ATLANTIC",
    "GREAT_LAKES",
    "SOUTHEAST",
    "SOUTH_CENTRAL",
    "MOUNTAIN",
    "PACIFIC",
    "NORTHWEST",
]


def reset() -> None:
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None


def data_dir() -> Path | None:
    env = os.environ.get("PHARMAGENTICS_DATA_DIR") or config.PHARMAGENTICS_DATA_DIR
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.extend(
        [
            config.ROOT.parent.parent / "data" / "agent_visible",
            config.ROOT.parent / "data" / "agent_visible",
        ]
    )
    for path in candidates:
        if (path / "forecast_vs_actual_weekly.csv").exists():
            return path
    return None


def available() -> bool:
    return data_dir() is not None


def connect() -> duckdb.DuckDBPyConnection:
    global _connection
    if _connection is None:
        root = data_dir()
        if root is None:
            raise FileNotFoundError(
                "Shared world CSVs not found. Set PHARMAGENTICS_DATA_DIR to "
                "PharmAgentics/data/agent_visible."
            )
        _connection = duckdb.connect(":memory:")
        _load(root, _connection)
    return _connection


def resolve_week(week: int | None, week_start: str | None) -> dict[str, object]:
    con = connect()
    if week_start:
        row = con.execute(
            """
            SELECT week, week_start, week_ending
            FROM weekly_performance
            WHERE week_start = ? AND region = 'NATIONAL' AND metric = 'TRx'
            LIMIT 1
            """,
            [week_start],
        ).fetchone()
    elif week:
        row = con.execute(
            """
            SELECT week, week_start, week_ending
            FROM weekly_performance
            WHERE week = ? AND region = 'NATIONAL' AND metric = 'TRx'
            LIMIT 1
            """,
            [int(week)],
        ).fetchone()
    else:
        row = None
    if row is None:
        raise ValueError(f"No BXA national week for week={week} week_start={week_start}")
    return {"week": int(row[0]), "week_start": str(row[1]), "week_ending": str(row[2])}


def _week_of(con: duckdb.DuckDBPyConnection, start_date: str) -> int:
    row = con.execute(
        "SELECT week FROM week_index WHERE week_start <= CAST(? AS DATE) AND CAST(? AS DATE) <= week_end",
        [start_date, start_date],
    ).fetchone()
    if row is None:
        raise ValueError(f"Event start {start_date} is outside the calendar")
    return int(row[0])


def _load(root: Path, con: duckdb.DuckDBPyConnection) -> None:
    forecast = root / "forecast_vs_actual_weekly.csv"
    calendar = root / "calendar.csv"
    product = root / "dim_product.csv"
    con.execute(
        f"""
        CREATE TABLE raw_forecast AS
        SELECT * FROM read_csv_auto('{forecast.as_posix()}', header=true);
        CREATE TABLE raw_calendar AS
        SELECT * FROM read_csv_auto('{calendar.as_posix()}', header=true);
        CREATE TABLE raw_product AS
        SELECT * FROM read_csv_auto('{product.as_posix()}', header=true);
        """
    )
    con.execute(
        """
        CREATE VIEW week_index AS
        SELECT
            CAST(week_start AS DATE) AS week_start,
            CAST(week_end AS DATE) AS week_end,
            CAST(week_end AS VARCHAR) AS week_ending,
            row_number() OVER (ORDER BY CAST(week_start AS DATE)) AS week
        FROM raw_calendar;

        CREATE VIEW weekly_performance AS
        SELECT
            'BXA Cardiovela' AS brand,
            i.week,
            CAST(f.week_start AS VARCHAR) AS week_start,
            i.week_ending,
            f.territory_id AS region,
            'all' AS segment,
            'TRx' AS metric,
            CAST(f.forecast_trx AS DOUBLE) AS forecast,
            CAST(f.actual_trx AS DOUBLE) AS actual,
            CASE WHEN CAST(f.actual_is_provisional AS INTEGER) = 1
                 THEN 'provisional' ELSE 'ok' END AS access_status,
            NULL::DOUBLE AS competitor_share
        FROM raw_forecast f
        LEFT JOIN week_index i ON CAST(f.week_start AS DATE) = i.week_start
        WHERE f.product_id = 'BXA'
        """
    )
    events = [
        (
            "evt_access_mid_atlantic",
            "payer_access",
            "Mid-Atlantic Medicare Part D tier 2→3 with PA and ST",
            43,
            "2025-08-10",
            ["MID_ATLANTIC"],
            [t for t in TERRITORIES if t != "MID_ATLANTIC"],
            [],
            "Observable access change from 2025-08-04. Magnitude comes from DiD, not a label.",
            "2025-08-04",
        ),
        (
            "evt_promo_southeast",
            "promotion",
            "Southeast promotion lapse still active in the flagged week",
            98,
            "2026-08-30",
            ["SOUTHEAST"],
            [t for t in TERRITORIES if t != "SOUTHEAST"],
            [],
            "Lapse began 2026-08-03. Event is dated to the investigation week so the window catches it.",
            "2026-08-03",
        ),
        (
            "evt_comp_metacora",
            "competitor_activity",
            "BXE Metacora launch (in-basket from 2026-03-02)",
            98,
            "2026-08-30",
            TERRITORIES,
            [],
            [],
            "National launch: no clean control region. Stub should treat confidence as low.",
            "2026-03-02",
        ),
    ]
    con.execute(
        """
        CREATE TABLE commercial_events (
            event_id VARCHAR,
            driver VARCHAR,
            label VARCHAR,
            week INTEGER,
            week_ending VARCHAR,
            exposed_regions VARCHAR,
            control_regions VARCHAR,
            excluded_regions VARCHAR,
            notes VARCHAR,
            start_week INTEGER
        )
        """
    )
    con.executemany(
        "INSERT INTO commercial_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                event_id,
                driver,
                label,
                week,
                week_ending,
                json.dumps(exposed),
                json.dumps(control),
                json.dumps(excluded),
                notes,
                _week_of(con, start_date),
            )
            for event_id, driver, label, week, week_ending, exposed, control, excluded, notes, start_date in events
        ],
    )
    con.execute(
        """
        CREATE TABLE investigation_requests (
            request_id VARCHAR PRIMARY KEY,
            source VARCHAR,
            brand VARCHAR,
            week INTEGER,
            week_ending VARCHAR,
            metric VARCHAR,
            notes VARCHAR
        )
        """
    )

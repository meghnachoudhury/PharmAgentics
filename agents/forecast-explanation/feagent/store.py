"""DuckDB shared data layer for briefing + forecast-explanation.

Investigator tools may read weekly_performance, commercial_events, and
investigation_requests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from feagent import config
from feagent.config import BRAND, METRIC
from feagent.synthetic import build_case, week_ending

SCHEMA_VERSION = "3"
_connection: duckdb.DuckDBPyConnection | None = None
_world = "lumina"

BRIEFING_REQUEST = {
    "request_id": "brief_lumina_w18",
    "source": "briefing_agent",
    "brand": BRAND,
    "week": 18,
    "week_ending": week_ending(18),
    "metric": METRIC,
    "notes": (
        "Brand-Performance Briefing Agent flagged a material national TRx miss "
        "in week 18 (actual 9,600 vs forecast 12,000). Please explain drivers, "
        "magnitude, confidence, and what to check."
    ),
}


def use_world(name: str) -> None:
    """lumina = Week 18 fixture; shared = Meghna day1-v1 forecast tables."""
    global _world
    if name not in {"lumina", "shared"}:
        raise ValueError(f"Unknown world: {name}")
    _world = name


def current_world() -> str:
    return _world


def reset() -> None:
    global _connection, _world
    if _connection is not None:
        _connection.close()
        _connection = None
    from feagent.shared_world import reset as reset_shared

    reset_shared()
    _world = "lumina"


def connect() -> duckdb.DuckDBPyConnection:
    if _world == "shared":
        from feagent.shared_world import connect as shared_connect

        return shared_connect()
    global _connection
    if _connection is None:
        Path(config.DUCKDB_PATH).parent.mkdir(parents=True, exist_ok=True)
        _connection = duckdb.connect(config.DUCKDB_PATH)
        _ensure_schema(_connection)
    return _connection


def fetchone(sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
    rel = connect().execute(sql, params or [])
    columns = [c[0] for c in rel.description]
    row = rel.fetchone()
    if row is None:
        return None
    return dict(zip(columns, row))


def fetchall(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    rel = connect().execute(sql, params or [])
    columns = [c[0] for c in rel.description]
    return [dict(zip(columns, row)) for row in rel.fetchall()]


def default_request() -> dict[str, Any]:
    connect()
    row = fetchone(
        "SELECT request_id, source, brand, week, week_ending, metric, notes "
        "FROM investigation_requests WHERE request_id = 'req_lumina_w18'"
    )
    if row is None:
        return BRIEFING_REQUEST
    return row


def briefing_request() -> dict[str, Any]:
    connect()
    row = fetchone(
        "SELECT request_id, source, brand, week, week_ending, metric, notes "
        "FROM investigation_requests WHERE request_id = 'brief_lumina_w18'"
    )
    return row or dict(BRIEFING_REQUEST)


def _ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE TABLE IF NOT EXISTS meta (key VARCHAR PRIMARY KEY, value VARCHAR)")
    current = con.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    if current and current[0] == SCHEMA_VERSION:
        n = con.execute("SELECT COUNT(*) FROM weekly_performance").fetchone()[0]
        if n:
            return
    for table in (
        "weekly_performance",
        "commercial_events",
        "investigation_requests",
        "meta",
    ):
        con.execute(f"DROP TABLE IF EXISTS {table}")
    con.execute("CREATE TABLE meta (key VARCHAR PRIMARY KEY, value VARCHAR)")
    con.execute(
        """
        CREATE TABLE weekly_performance (
            brand VARCHAR,
            week INTEGER,
            week_ending VARCHAR,
            region VARCHAR,
            segment VARCHAR,
            metric VARCHAR,
            forecast DOUBLE,
            actual DOUBLE,
            access_status VARCHAR,
            competitor_share DOUBLE
        )
        """
    )
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
    _seed(con)
    con.execute(
        "INSERT INTO meta VALUES ('schema_version', ?)",
        [SCHEMA_VERSION],
    )


def _seed(con: duckdb.DuckDBPyConnection) -> None:
    case = build_case()
    obs = case["observable"]
    perf_rows = []
    for row in obs["weekly_region"]:
        access = "preferred"
        share = 0.05
        if row["region"] in {"Northeast", "South"} and row["week"] >= 17:
            access = "formulary_downgrade"
        if row["region"] == "Midwest" and row["week"] >= 18:
            share = 0.18
        for metric, forecast, actual in (
            ("TRx", row["forecast"], row["actual"]),
            ("NRx", None, None),
            ("NBRx", None, None),
        ):
            perf_rows.append(
                (
                    row["brand"],
                    row["week"],
                    row["week_ending"],
                    row["region"],
                    "all",
                    metric,
                    forecast,
                    actual,
                    access if metric == "TRx" else None,
                    share if metric == "TRx" else None,
                )
            )
    for row in obs["weekly_national"]:
        for metric, forecast, actual in (
            ("TRx", row["forecast"], row["actual"]),
            ("NRx", None, None),
            ("NBRx", None, None),
        ):
            perf_rows.append(
                (
                    row["brand"],
                    row["week"],
                    row["week_ending"],
                    "NATIONAL",
                    "all",
                    metric,
                    forecast,
                    actual,
                    None,
                    None,
                )
            )
    con.executemany(
        "INSERT INTO weekly_performance VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        perf_rows,
    )
    event_rows = [
        (
            event["event_id"],
            event["driver"],
            event["label"],
            event["week"],
            event["week_ending"],
            json.dumps(event["exposed_regions"]),
            json.dumps(event["control_regions"]),
            json.dumps(event.get("excluded_regions", [])),
            event.get("notes", ""),
            event.get("start_week"),
        )
        for event in obs["events"]
    ]
    con.executemany(
        "INSERT INTO commercial_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        event_rows,
    )
    manual = obs["default_request"]
    con.executemany(
        "INSERT INTO investigation_requests VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                manual["request_id"],
                manual["source"],
                manual["brand"],
                manual["week"],
                manual["week_ending"],
                manual["metric"],
                manual.get("notes"),
            ),
            (
                BRIEFING_REQUEST["request_id"],
                BRIEFING_REQUEST["source"],
                BRIEFING_REQUEST["brand"],
                BRIEFING_REQUEST["week"],
                BRIEFING_REQUEST["week_ending"],
                BRIEFING_REQUEST["metric"],
                BRIEFING_REQUEST["notes"],
            ),
        ],
    )

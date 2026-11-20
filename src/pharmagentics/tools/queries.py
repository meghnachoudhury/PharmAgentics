"""SQL builders over the governed views. Each returns one self-contained SELECT, so an evidence item
can be re-run later against the pinned data and must give the same value."""
from __future__ import annotations

from datetime import date, timedelta

RX = "reporting.v_reportable_rx"
TERRITORY_NAMES = {
    "GREAT_LAKES": "Great Lakes", "MID_ATLANTIC": "Mid-Atlantic", "MOUNTAIN": "Mountain",
    "NEW_ENGLAND": "New England", "NORTHWEST": "Northwest", "PACIFIC": "Pacific",
    "SOUTHEAST": "Southeast", "SOUTH_CENTRAL": "South Central", "NATIONAL": "National",
}
REASONS = {
    "MISSING_RX_KEYS": "missing keys", "DUPLICATE_RX_KEYS": "duplicate keys",
    "LOW_OR_INVALID_COVERAGE": "low panel coverage", "LATE_OR_UNKNOWN_DELIVERY": "late delivery",
    "SOURCE_NOT_COMPLETE": "incomplete source", "RESTATEMENT_REVIEW": "restatement review",
    "ROW_COUNT_MISMATCH": "row counts that do not reconcile", "INVALID_RX_METRICS": "invalid metrics",
    "UNEXPECTED_CUT": "an unexpected cut", "MISSING_FEED_METADATA": "missing feed metadata",
    "DUPLICATE_FEED_METADATA": "duplicate feed metadata", "UNKNOWN_SCHEMA": "an unknown schema",
}


def name(territory: str) -> str:
    return TERRITORY_NAMES.get(territory, territory.title())


def iso(d: date) -> str:
    return d.isoformat()


def mondays(start: str, end: str) -> list[str]:
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    return [iso(a + timedelta(days=7 * i)) for i in range((b - a).days // 7 + 1)]


def shift(week: str, weeks: int) -> str:
    return iso(date.fromisoformat(week) + timedelta(days=7 * weeks))


def _dates(weeks) -> str:
    return "(" + ",".join(f"DATE '{w}'" for w in weeks) + ")"


def _in(col: str, values) -> str:
    return f"{col} in (" + ",".join(f"'{v}'" for v in values) + ")"


def sub(sql: str) -> str:
    return f"({sql})"


def trx_sum(weeks, terrs=None, plan=None, product="BXA", col="trx") -> str:
    sql = f"select coalesce(sum({col}),0) from {RX} where product_id = '{product}' and week_start in {_dates(weeks)}"
    if terrs:
        sql += " and " + _in("territory_id", terrs)
    if plan:
        sql += f" and plan_id = '{plan}'"
    return sql


def mean_weekly(weeks, **kw) -> str:
    return f"select {sub(trx_sum(weeks, **kw))} / {len(weeks)}.0"


def pct_change(new_sql: str, old_sql: str) -> str:
    return f"select 100.0 * ({sub(new_sql)} / nullif({sub(old_sql)}, 0) - 1)"


def share(weeks, product: str, terrs=None, exclude=None) -> str:
    sql = (f"select 100.0 * sum(trx) filter (where product_id = '{product}') / nullif(sum(trx), 0) "
           f"from {RX} where week_start in {_dates(weeks)}")
    if terrs:
        sql += " and " + _in("territory_id", terrs)
    if exclude:
        sql += f" and territory_id <> '{exclude}'"
    return sql


def feed(week: str, terr: str, col: str) -> str:
    return f"select {col} from reporting.v_feed_health where week_start = DATE '{week}' and territory_id = '{terr}'"


def context_mean(table: str, col: str, weeks, terr: str, scale: float = 1.0) -> str:
    return (f"select {scale} * avg({col}) from raw.{table} where product_id = 'BXA' "
            f"and territory_id = '{terr}' and week_start in {_dates(weeks)}")


def calendar(week: str, col: str) -> str:
    return f"select {col} from raw.calendar where week_start = DATE '{week}'"


FVA = "raw.forecast_vs_actual_weekly"


def fva_sum(col: str, weeks, terr: str = "NATIONAL") -> str:
    """Sum of a forecast-table column (forecast_trx, actual_trx, variance_trx) for one cut over weeks."""
    return (f"select coalesce(sum({col}), 0) from {FVA} where product_id = 'BXA' "
            f"and territory_id = '{terr}' and week_start in {_dates(weeks)}")


def fva_peers(col: str, weeks, terr: str) -> str:
    return (f"select coalesce(sum({col}), 0) from {FVA} where product_id = 'BXA' "
            f"and territory_id not in ('NATIONAL', '{terr}') and week_start in {_dates(weeks)}")


# Projected national (brief-003 FR-022; ADR 0001) -----------------------------------------------------
# Each builder returns one self-contained SELECT over governed relations, so a claim can be re-run later.

PROJ = "reporting.v_rx_projection"


def projection_ctes(weeks, product: str = "BXA") -> str:
    """CTEs for the target weeks: each cut's basis and projected TRx, the four clean weeks before each target
    week (every territory passes, no holiday or plan-year reset), each territory's share of national in them,
    and the national: (observed + projected) / (1 - shares of the estimated territories)."""
    targets = ", ".join(f"DATE '{w}'" for w in weeks)
    return (
        f"with wk as (select unnest([{targets}]) as week_start), "
        f"cut as (select p.week_start, p.territory_id, p.basis, p.projected_trx from {PROJ} p join wk using (week_start) "
        f"where p.product_id = '{product}'), "
        "clean as (select wk.week_start as target, c.week_start from wk join raw.calendar c on c.week_start < wk.week_start "
        "where c.holiday_flag = 0 and c.plan_year_reset = 0 and not exists (select 1 from reporting.v_feed_health h "
        "where h.week_start = c.week_start and h.health_status <> 'PASS') "
        "qualify row_number() over (partition by wk.week_start order by c.week_start desc) <= 4), "
        "share as (select cl.target, r.territory_id, sum(r.trx) / sum(sum(r.trx)) over (partition by cl.target) as s "
        f"from clean cl join {RX} r on r.week_start = cl.week_start and r.product_id = '{product}' group by 1, 2), "
        "nat as (select c.week_start, sum(c.projected_trx) filter (where c.basis <> 'estimated') "
        "/ (1 - coalesce(sum(s.s) filter (where c.basis = 'estimated'), 0)) as national "
        "from cut c left join share s on s.target = c.week_start and s.territory_id = c.territory_id group by 1 "
        "having count(*) filter (where c.basis <> 'estimated') > 0) "
    )


def projected_national(weeks, product: str = "BXA") -> str:
    """Average weekly projected national TRx over `weeks` (NULL when no week can be reported)."""
    return projection_ctes(weeks, product) + "select avg(national) from nat"


def projected_territory(weeks, territory: str, product: str = "BXA") -> str:
    """Average weekly TRx of one territory: observed or projected from the view, or share × national when estimated."""
    return (projection_ctes(weeks, product)
            + "select avg(case when c.basis = 'estimated' then s.s * n.national else c.projected_trx end) "
              "from cut c join nat n using (week_start) left join share s on s.target = c.week_start "
              f"and s.territory_id = c.territory_id where c.territory_id = '{territory}'")


def projection_cell(week: str, territory: str, col: str, product: str = "BXA") -> str:
    return (f"select {col} from {PROJ} where week_start = DATE '{week}' and territory_id = '{territory}' "
            f"and product_id = '{product}'")

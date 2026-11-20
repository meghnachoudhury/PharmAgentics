"""SQL builders for the Forecast lane. Every number in an answer is one of these queries, run through the
governed Registry, so an evidence item can be re-run on the pinned data and must give the same value."""
from __future__ import annotations

from pharmagentics.tools.queries import RX

FVA = "raw.forecast_vs_actual_weekly"
TERRITORIES = ["NEW_ENGLAND", "MID_ATLANTIC", "GREAT_LAKES", "SOUTHEAST", "SOUTH_CENTRAL", "MOUNTAIN", "PACIFIC", "NORTHWEST"]


def dates(weeks) -> str:
    return "(" + ",".join(f"DATE '{w}'" for w in weeks) + ")"


def _terrs(cut) -> str:
    """A cut is NATIONAL, one territory id, or a list of territory ids."""
    if isinstance(cut, str):
        return f"territory_id = '{cut}'"
    return "territory_id in (" + ",".join(f"'{t}'" for t in cut) + ")"


def fva(col: str, weeks, cut="NATIONAL") -> str:
    return (f"select coalesce(sum({col}), 0) from {FVA} where product_id = 'BXA' and {_terrs(cut)} "
            f"and week_start in {dates(weeks)}")


def pct_of_forecast(weeks, cut="NATIONAL") -> str:
    return f"select 100.0 * ({fva('variance_trx', weeks, cut)}) / nullif(({fva('forecast_trx', weeks, cut)}), 0)"


def rate(weeks, cut) -> str:
    """Miss as a fraction of forecast."""
    return f"({fva('variance_trx', weeks, cut)}) / nullif(({fva('forecast_trx', weeks, cut)}), 0)"


def excess(terr: str, weeks, controls: list[str]) -> str:
    """The territory's miss beyond what the control territories' miss rate predicts for its forecast."""
    return (f"select ({fva('variance_trx', weeks, terr)}) - ({fva('forecast_trx', weeks, terr)}) * "
            f"({rate(weeks, controls)})")


def at_rate(terr_or_cut, weeks, controls: list[str]) -> str:
    """What the control territories' miss rate predicts for this cut's forecast."""
    return f"select ({fva('forecast_trx', weeks, terr_or_cut)}) * ({rate(weeks, controls)})"


def pct_rate(weeks, cut) -> str:
    return f"select 100.0 * {rate(weeks, cut)}"


def share_of(part_sql: str, whole_sql: str) -> str:
    return f"select 100.0 * ({part_sql}) / nullif(({whole_sql}), 0)"


def bias_rate(launch: str) -> str:
    """The national forecast's usual error before the competitor launch, on final actuals only."""
    return (f"(select sum(variance_trx) / nullif(sum(forecast_trx), 0) from {FVA} where product_id = 'BXA' "
            f"and territory_id = 'NATIONAL' and actual_is_provisional = 0 and week_start < DATE '{launch}')")


def bias(weeks, cut, launch: str) -> str:
    return f"select ({fva('forecast_trx', weeks, cut)}) * {bias_rate(launch)}"


def bxa_share(weeks, terrs: list[str]) -> str:
    return (f"select 100.0 * sum(trx) filter (where product_id = 'BXA') / nullif(sum(trx), 0) from {RX} "
            f"where week_start in {dates(weeks)} and {_terrs(terrs)}")


def product_share(weeks, product: str, terrs: list[str]) -> str:
    return (f"select 100.0 * sum(trx) filter (where product_id = '{product}') / nullif(sum(trx), 0) from {RX} "
            f"where week_start in {dates(weeks)} and {_terrs(terrs)}")


def share_loss(weeks, pre, terrs: list[str]) -> str:
    """Relative change in BXA's basket share against the weeks before launch, as a fraction."""
    return f"(({bxa_share(weeks, terrs)}) / nullif(({bxa_share(pre, terrs)}), 0) - 1)"


def competitor(weeks, cut, pre, terrs: list[str]) -> str:
    """The share loss applied to the forecast: what the forecast would have lost had the basket held to plan."""
    return f"select ({fva('forecast_trx', weeks, cut)}) * {share_loss(weeks, pre, terrs)}"


def minus(total_sql: str, parts: list[str]) -> str:
    if not parts:
        return total_sql
    return f"select ({total_sql}) - " + " - ".join(f"({p})" for p in parts)


def context_mean(table: str, col: str, weeks, terr: str, scale: float = 1.0) -> str:
    return (f"select {scale} * avg({col}) from raw.{table} where product_id = 'BXA' and territory_id = '{terr}' "
            f"and week_start in {dates(weeks)}")


def monthly_national_pct(start: str, end: str) -> str:
    return (f"select 100.0 * sum(variance_trx) / nullif(sum(forecast_trx), 0) from {FVA} where product_id = 'BXA' "
            f"and territory_id = 'NATIONAL' and week_start between DATE '{start}' and DATE '{end}'")

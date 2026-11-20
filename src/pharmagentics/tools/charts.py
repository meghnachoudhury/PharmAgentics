"""Charts for the memo (brief-003 FR-024, slice 2), built by code from governed rows.

Each chart comes from one multi-row SELECT that is recorded as an evidence item, so every plotted point traces
to a query an analyst can open and download (FR-025). Captions are code with claim tokens; the explanation is a
code template here (the scripted engine), which the agent's writer may replace with its own sentence.

    §2 trend      13 weeks of projected national BXA TRx and the territory the question names; restated weeks
                  dotted, projected or estimated weeks hollow (an assumption); no forecast line.
    §3 story      the territory's weekly TRx against the band of its baseline weeks, and a second panel for the
                  first supported driver (none supported: TRx only, and the caption says so).
    §4 coverage   territory by week: observed, projected, estimated, restated.
"""
from __future__ import annotations

from . import queries as q
from .registry import Registry

WINDOW = 13
DRIVER_SERIES = {  # driver -> (label, unit, SQL builder over weeks, territory, plan)
    "supply": ("BXA inventory fill rate", "rate",
               lambda W, t, plan, brand: f"select week_start::varchar, avg(inventory_fill_rate) from raw.inventory_weekly "
                                  f"where product_id = '{brand}' and territory_id = '{t}' and week_start in {q._dates(W)} group by 1 order by 1"),
    "promotion": ("Aggregated rep calls a week", "count",
                  lambda W, t, plan, brand: f"select week_start::varchar, sum(rep_calls_aggregated) from raw.promo_activity "
                                     f"where product_id = '{brand}' and territory_id = '{t}' and week_start in {q._dates(W)} group by 1 order by 1"),
    "access": ("BXA TRx on the plan whose access changed", "count",
               lambda W, t, plan, brand: f"select week_start::varchar, sum(trx) from {q.RX} where product_id = '{brand}' "
                                  f"and plan_id = '{plan}' and week_start in {q._dates(W)} group by 1 order by 1"),
    "competitor": ("Metacora share of the four-brand basket here", "percent",
                   lambda W, t, plan, brand: f"select week_start::varchar, 100.0 * sum(trx) filter (where product_id = 'BXE') "
                                      f"/ nullif(sum(trx), 0) from {q.RX} where territory_id = '{t}' "
                                      f"and week_start in {q._dates(W)} group by 1 order by 1"),
}


def window(p) -> list[str]:
    """The 13 weeks ending with the brief's last week, inside the release."""
    end = p.weeks[-1]
    return [w for w in (q.shift(end, -i) for i in range(WINDOW - 1, -1, -1)) if w >= p.first]


def _table(reg: Registry, tool: str, sql: str, columns: list[str], **params) -> dict:
    rows = reg.rows(sql)
    eid = reg._evidence(tool, sql, f"{len(rows)} rows", params)
    return {"evidence_id": eid, "query": sql.strip(), "columns": columns,
            "rows": [[(round(float(v), 4) if isinstance(v, float) else v) for v in r] for r in rows]}


def _restated(W: list[str], brand_id: str = "BXA") -> str:
    return (f"exists (select 1 from raw.restatement_log r where r.product_id = '{brand_id}' and r.week_start = n.week_start "
            f"and r.revised_at <= DATE '{q.shift(W[-1], 1)}')")


def trend(reg: Registry, p) -> dict:
    """§2: projected national and, if the question names one, the territory, week by week."""
    W = window(p)
    t = p.focus if p.focus and p.focus != "NATIONAL" else None
    terr_cols = (", (select case when c.basis = 'estimated' then s.s * n.national else c.projected_trx end from cut c "
                 "left join share s on s.target = c.week_start and s.territory_id = c.territory_id "
                 f"where c.week_start = n.week_start and c.territory_id = '{t}'), "
                 f"(select c.basis from cut c where c.week_start = n.week_start and c.territory_id = '{t}')") if t else ""
    sql = (q.projection_ctes(W, product=p.brand_id)
           + "select n.week_start::varchar, n.national, (select case when bool_or(c.basis = 'estimated') then 'estimated' "
             "when bool_or(c.basis = 'projected') then 'projected' else 'observed' end from cut c where c.week_start = n.week_start), "
           + _restated(W, p.brand_id) + terr_cols + " from nat n order by 1")
    cols = ["week", "projected_national", "national_basis", "restated"] + (["territory_trx", "territory_basis"] if t else [])
    table = _table(reg, "chart_trend", sql, cols, territory=t or "NATIONAL")
    series = [{"name": "Projected national", "points": [
        {"week": r[0], "value": r[1], "basis": r[2], "restated": bool(r[3])} for r in table["rows"]]}]
    if t:
        series.append({"name": q.name(t), "points": [
            {"week": r[0], "value": r[4], "basis": r[5] or "observed", "restated": bool(r[3])} for r in table["rows"]]})
    first = reg.claim("project_national", q.projected_national([W[0]], product=p.brand_id), "int", week=W[0], scope="projected national")
    last = reg.claim("project_national", q.projected_national([W[-1]], product=p.brand_id), "int", week=W[-1], scope="projected national")
    # The legend names only what the chart shows, so no reader (or writer) takes it as a claim (slice 2 smoke run).
    points = [pt for s in series for pt in s["points"]]
    assumed, restated = [pt["week"] for pt in points if pt["basis"] != "observed"], [pt["week"] for pt in points if pt["restated"]]
    caption = (f"{p.brand_id} TRx a week, {W[0]} to {W[-1]}: projected national" + (f" and {q.name(t)}" if t else "") + "."
               + (f" Hollow points are projected or estimated, an assumption (weeks of {', '.join(sorted(set(assumed)))})." if assumed else "")
               + (f" Dotted points were restated (weeks of {', '.join(sorted(set(restated)))})." if restated else "")
               + " No forecast is drawn.")
    explanation = f"Projected national moved from {first} in the week of {W[0]} to {last} in the week of {W[-1]}."
    return {"kind": "trend", "weeks": W, "series": series, "band": None, "panel": None,
            "caption": caption, "explanation": explanation, "table": table}


def story(reg: Registry, p, territory: str, drivers: list[str], plan: str | None = None) -> dict:
    """§3: the territory's weekly TRx against its baseline band, and the first supported driver's series."""
    W, t = window(p), territory
    sql = (f"select week_start::varchar, sum(trx) from {q.RX} where product_id = '{p.brand_id}' and territory_id = '{t}' "
           f"and week_start in {q._dates(W)} group by 1 order by 1")
    table = _table(reg, "chart_story", sql, ["week", "trx"], territory=t)
    weekly = (f"select week_start, sum(trx) s from {q.RX} where product_id = '{p.brand_id}' and territory_id = '{t}' "
              f"and week_start in {q._dates(p.baseline)} group by 1")
    band = None
    if p.baseline:
        low = reg.claim("chart_story", f"select min(s) from ({weekly})", "int", territory=t, scope="baseline band")
        high = reg.claim("chart_story", f"select max(s) from ({weekly})", "int", territory=t, scope="baseline band")
        band = {"low": reg.scalar(f"select min(s) from ({weekly})"), "high": reg.scalar(f"select max(s) from ({weekly})"),
                "weeks": list(p.baseline), "label": f"Baseline weeks, {p.baseline[0]} to {p.baseline[-1]}"}
    panel = None
    driver = next((d for d in drivers if d in DRIVER_SERIES and (d != "access" or plan)), None)
    if driver:
        label, unit, build = DRIVER_SERIES[driver]
        ptable = _table(reg, f"chart_{driver}", build(W, t, plan, p.brand_id), ["week", "value"], territory=t, driver=driver)
        panel = {"name": label.replace("BXA", p.brand_id), "unit": unit, "driver": driver, "table": ptable,
                 "points": [{"week": r[0], "value": r[1]} for r in ptable["rows"]]}
    latest = reg.claim("chart_story", f"select coalesce(sum(trx), 0) from {q.RX} where product_id = '{p.brand_id}' "
                       f"and territory_id = '{t}' and week_start = DATE '{W[-1]}'", "int", territory=t, week=W[-1])
    name = q.name(t)
    caption = (f"{name} {p.brand_id} TRx a week, {W[0]} to {W[-1]}"
               + (f", against the band of its baseline weeks ({low} to {high})" if band else "") + ". "
               + (f"Second panel: {panel['name']}, the driver the checks support." if driver
                  else "No driver was supported, so only TRx is shown."))
    position = ""
    if band:
        value = reg.scalar(f"select coalesce(sum(trx), 0) from {q.RX} where product_id = '{p.brand_id}' and territory_id = '{t}' "
                           f"and week_start = DATE '{W[-1]}'") or 0
        position = (" below its baseline band" if value < band["low"] else " above its baseline band"
                    if value > band["high"] else " inside its baseline band")
    explanation = f"In the week of {W[-1]}, {name} had {latest} {p.brand_id} TRx,{position}." if position else \
        f"In the week of {W[-1]}, {name} had {latest} {p.brand_id} TRx."
    return {"kind": "story", "weeks": W, "series": [{"name": name, "points": [
        {"week": r[0], "value": r[1], "basis": "observed", "restated": False} for r in table["rows"]]}],
        "band": band, "panel": panel, "caption": caption, "explanation": explanation, "table": table}


def competitor(reg: Registry, p) -> dict:
    """§3, the continuing Metacora story: BXA and Metacora shares of the basket, week by week."""
    W = window(p)
    sql = (f"select week_start::varchar, 100.0 * sum(trx) filter (where product_id = '{p.brand_id}') / nullif(sum(trx), 0), "
           f"100.0 * sum(trx) filter (where product_id = 'BXE') / nullif(sum(trx), 0) from {q.RX} "
           f"where week_start in {q._dates(W)} group by 1 order by 1")
    table = _table(reg, "chart_competitor", sql, ["week", f"{p.brand_id.lower()}_share", "bxe_share"])
    bxe = reg.claim("compare_competitors", q.share([W[-1]], "BXE"), "pct1", product="BXE", week=W[-1])
    return {"kind": "share", "weeks": W, "series": [
        {"name": f"{p.brand_id} share", "points": [{"week": r[0], "value": r[1], "basis": "observed", "restated": False} for r in table["rows"]]},
        {"name": "Metacora share", "points": [{"week": r[0], "value": r[2], "basis": "observed", "restated": False} for r in table["rows"]]}],
        "band": None, "panel": None, "table": table,
        "caption": f"Shares of the four-brand basket, {W[0]} to {W[-1]}, every reportable territory.",
        "explanation": f"Metacora held {bxe} of the basket in the week of {W[-1]}."}


def coverage(reg: Registry, p) -> dict:
    """§4: territory by week, the basis of each cut and whether it was restated."""
    W = window(p)
    sql = (f"select v.territory_id, v.week_start::varchar, v.basis, exists (select 1 from raw.restatement_log r "
           f"where r.product_id = '{p.brand_id}' and r.week_start = v.week_start and r.territory_id = v.territory_id "
           f"and r.revised_at <= DATE '{q.shift(W[-1], 1)}') from {q.PROJ} v where v.product_id = '{p.brand_id}' "
           f"and v.week_start in {q._dates(W)} order by 1, 2")
    table = _table(reg, "chart_coverage", sql, ["territory", "week", "basis", "restated"])
    rows: dict[str, list] = {}
    for t, w, basis, restated in table["rows"]:
        rows.setdefault(t, []).append({"week": w, "basis": basis, "restated": bool(restated)})
    count_sql = (f"select count(*) from {q.PROJ} where product_id = '{p.brand_id}' and basis <> 'observed' "
                 f"and week_start in {q._dates(W)}")
    off = reg.scalar(count_sql) or 0
    n = reg.claim("chart_coverage", count_sql, "int", scope="territory-weeks not observed") if off else None
    cells = [c for cs in rows.values() for c in cs]
    marks = [m for m, present in (("hollow cells are projected", any(c["basis"] == "projected" for c in cells)),
                                   ("crossed cells are estimated", any(c["basis"] == "estimated" for c in cells))) if present]
    legend = (" " + " and ".join(marks).capitalize() + ", both assumptions." if len(marks) == 2 else
              " " + marks[0].capitalize() + ", an assumption." if marks else " Every cell is an observed count.")
    if any(c["restated"] for c in cells):
        legend += " Ringed cells were restated."
    return {"kind": "coverage", "weeks": W, "table": table,
            "rows": [{"territory": q.name(t), "cells": cs} for t, cs in sorted(rows.items(), key=lambda kv: q.name(kv[0]))],
            "caption": f"Feed coverage by territory and week, {W[0]} to {W[-1]}." + legend,
            "explanation": (f"{n} territory-weeks in this window are not observed counts." if n else
                            "Every territory-week in this window is an observed count.")}

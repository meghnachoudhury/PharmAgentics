"""The analyst's brand overview for one week: headline figures, every territory judged by the briefing triage's own
rule (stages.resolve + stages.screen), 13-week series, data health and product mix. Code only, no model.
Headline figures are claims with evidence items; the series and mix come from recorded governed queries.
"""
from __future__ import annotations

from datetime import date
from statistics import fmean

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from starlette.concurrency import run_in_threadpool

from pharmagentics.tools import Registry, stages
from pharmagentics.tools import queries as q

from . import rbac, service

router = APIRouter(prefix="/api/briefing", tags=["briefing"])
PRODUCT = "BXA"
SERIES_WEEKS = 13


def _claim(reg: Registry, tool: str, sql: str, fmt: str, **params) -> dict:
    reg.claim(tool, sql, fmt, **params)
    c = reg.claims[-1]
    raw = next(e["result"] for e in reg.evidence if e["id"] == c["evidence_id"])
    return {"value": c["value"], "raw": raw, "evidence_id": c["evidence_id"]}


def _count_in(reg: Registry, week: str, terrs: list[str], scope: str) -> dict:
    where = q._in("territory_id", terrs) if terrs else "false"
    sql = f"select count(distinct territory_id) from {q.RX} where week_start = DATE '{week}' and {where}"
    return _claim(reg, "detect_changes", sql, "int", week=week, scope=scope)


def _stat(key: str, label: str, value: dict, change: dict | None = None, adverse_when: str | None = None) -> dict:
    out = {"key": key, "label": label, **value, "change": change}
    if change and adverse_when:
        raw = change["raw"] or 0.0  # a change that rounds to 0.0% is not adverse
        out["adverse"] = raw <= -0.05 if adverse_when == "down" else raw >= 0.05
    return out


def build(week: str | None = None) -> dict:
    if not service.DB.is_file():
        raise service.MissingDatabase("DuckDB has not been built. Run the data loader first.")
    reg = Registry(service.DB)
    try:
        first, latest = reg.rows("select min(week_start)::varchar, max(week_start)::varchar from raw.calendar")[0]
        week = week or latest
        if not first <= week <= latest:
            raise service.OutsideRelease(f"The release covers {first} to {latest}.")
        p = stages.resolve(reg, f"Week of {week} in {q.name('NATIONAL')}: What changed this week?")
        screened: dict[str, dict] = {}
        found, _ = stages.screen(reg, p, screened)
        material = {s["territory"]: s for s in found if s["kind"] == "territory"}
        prev = q.shift(week, -1)
        has_prev = prev >= first

        def wow(col: str, label: str) -> dict | None:
            if not has_prev:
                return None
            return _claim(reg, "get_metric", q.pct_change(q.trx_sum([week], col=col), q.trx_sum([prev], col=col)), "pct1",
                          week=week, scope=f"{label}, week over week")

        stats = [
            _stat("trx", "TRx", _claim(reg, "get_metric", q.trx_sum([week]), "int", week=week, scope="national TRx"),
                  wow("trx", "TRx"), "down"),
            _stat("nbrx", "New patients (NBRx)", _claim(reg, "get_metric", q.trx_sum([week], col="nbrx"), "int", week=week,
                                                        scope="national NBRx"), wow("nbrx", "NBRx"), "down"),
            _stat("material", "Territories with a material change",
                  _count_in(reg, week, sorted(material), "territories with a material change"),
                  {"label": "of", **_count_in(reg, week, p.ok, "like-for-like territories")}),
            _stat("health", "Territories with a data-health flag",
                  _claim(reg, "check_feed_health", f"select count(*) from reporting.v_feed_health where week_start = DATE '{week}' "
                         "and health_status <> 'PASS'", "int", week=week, scope="feed health")),
        ]

        start = q.shift(week, -(SERIES_WEEKS - 1))
        series_rows, series_ev = reg.table(
            "get_series", f"select week_start::varchar, territory_id, sum(trx), sum(nrx), sum(nbrx) from {q.RX} "
            f"where product_id = '{PRODUCT}' and week_start between DATE '{start}' and DATE '{week}' group by 1, 2 order by 1, 2",
            weeks=f"{start} to {week}", scope="13-week series")
        health_rows, health_ev = reg.table(
            "check_feed_health", "select territory_id, health_status, flag_reasons, missing_key_count, duplicate_key_count "
            f"from reporting.v_feed_health where week_start = DATE '{week}'", week=week, scope="feed health by territory")
        mix_rows, mix_ev = reg.table(
            "get_share", f"select territory_id, product_id, sum(trx) from {q.RX} where week_start = DATE '{week}' group by 1, 2",
            week=week, scope="TRx by product")
        names = dict(reg.rows("select product_id, product_name from raw.dim_product"))

        series: dict[str, dict[str, tuple]] = {}
        for w, t, trx, nrx, nbrx in series_rows:
            series.setdefault(t, {})[w] = (float(trx), float(nrx), float(nbrx))
        health = {t: {"status": s, "reasons": [q.REASONS.get(r, r) for r in (rs or "").split("|") if r],
                      "missing_keys": int(m or 0), "duplicate_keys": int(d or 0)} for t, s, rs, m, d in health_rows}
        mix: dict[str, list] = {}
        for t, prod, trx in mix_rows:
            mix.setdefault(t, []).append([prod, float(trx)])

        def mean_of(t: str, weeks: list[str]) -> float | None:
            vals = [series.get(t, {}).get(w, (None,))[0] for w in weeks]
            vals = [v for v in vals if v is not None]
            return fmean(vals) if vals and len(vals) == len(weeks) else None

        territories = []
        for t in sorted({*series, *health}):
            x, b = mean_of(t, p.weeks), mean_of(t, p.baseline)
            judged = screened.get(t, {})
            status = ("material" if t in material else "no_baseline" if not p.baseline
                      else "normal" if t in p.ok else "held_back")
            total = sum(v for _, v in mix.get(t, []))
            territories.append({
                "id": t, "label": q.name(t), "status": status,
                "trx": series.get(t, {}).get(week, (None,))[0], "change": judged.get("change"), "gap": judged.get("gap"),
                "threshold": judged.get("threshold"),
                "impact": abs(x - b) if x is not None and b is not None else 0.0,
                "series": [{"week": w, "trx": v[0], "nrx": v[1], "nbrx": v[2]} for w, v in sorted(series.get(t, {}).items())],
                "health": health.get(t), "evidence_ids": [series_ev, health_ev, mix_ev],
                "mix": [{"product": prod, "name": names.get(prod, prod), "trx": v, "share": v / total if total else None}
                        for prod, v in sorted(mix.get(t, []), key=lambda m: -m[1])],
            })
        order = {"material": 0, "normal": 1, "no_baseline": 2, "held_back": 3}
        territories.sort(key=lambda r: (order[r["status"]], -(r["impact"] if r["status"] == "material" else abs(r["change"] or 0))))
        return {
            "week": week, "first_week": first, "latest_week": latest, "data_version": reg.data_version, "product": PRODUCT,
            "product_name": names.get(PRODUCT, PRODUCT), "weeks": p.weeks, "baseline": p.baseline,
            "rule": {"material_change": stages.MATERIAL_CHANGE, "material_gap": stages.MATERIAL_GAP, "noise_z": stages.NOISE_Z},
            "note": p.calendar_note or ("This is a holiday or plan-year week, so lower volume is expected." if p.calendar else None),
            "stats": stats, "territories": territories, "evidence": reg.evidence,
        }
    finally:
        reg.close()


@router.get("/overview")
async def overview(response: Response, week: date | None = Query(default=None), who=Depends(rbac.require_briefing)) -> dict:
    _, role = who
    rbac.allow(role, "run")
    response.headers["Cache-Control"] = "no-store"
    try:
        return await run_in_threadpool(build, week.isoformat() if week else None)
    except service.MissingDatabase as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except service.OutsideRelease as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

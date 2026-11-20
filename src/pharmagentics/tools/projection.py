"""Projected national TRx, territory by territory (brief-003 FR-022; ADR 0001).

A passing cut is observed. A failed cut with only completeness faults and coverage of at least 0.5 is
projected (observed ÷ coverage). Any other failed cut is estimated from the territory's share of national
in the four latest clean weeks. The national is a level, never a cause: no story or driver is built on a
projected or estimated cut (FR-023). Every value is a claim token from one SELECT in `queries`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import queries as q
from .registry import Registry

ORDER = {"observed": 0, "projected": 1, "estimated": 2}


@dataclass
class Row:
    territory: str
    token: str  # average weekly BXA TRx over the period, observed, projected or estimated
    basis: str  # the least certain basis in any week of the period
    weeks: dict[str, str] = field(default_factory=dict)  # week -> basis, for weeks not observed
    reasons: dict[str, str] = field(default_factory=dict)  # week -> flag reasons, for weeks not observed
    observed: str | None = None  # single projected week: the observed TRx
    coverage: str | None = None  # single projected week: the panel coverage


@dataclass
class Projection:
    weeks: list[str]
    national: str | None  # None when no week in the period can be read at all
    rows: list[Row]
    brand_id: str = "BXA"

    def territories(self, basis: str) -> list[str]:
        return [r.territory for r in self.rows if basis in r.weeks.values()]

    def row(self, territory: str) -> Row | None:
        return next((r for r in self.rows if r.territory == territory), None)


def build(reg: Registry, p) -> Projection:
    W = p.weeks
    cells = reg.rows(f"select week_start::varchar, territory_id, basis, flag_reasons from {q.PROJ} "
                     f"where product_id = '{p.brand_id}' and week_start in {q._dates(W)} order by 2, 1")
    national_value = reg.scalar(q.projected_national(W, product=p.brand_id))
    national = None if national_value is None else reg.claim("project_national", q.projected_national(W, product=p.brand_id), "int",
                                                               scope="projected national")
    by_t: dict[str, list[tuple]] = {}
    for w, t, basis, reasons in cells:
        by_t.setdefault(t, []).append((w, basis, reasons))
    rows = []
    if national is not None:
        for t, weeks in sorted(by_t.items(), key=lambda kv: q.name(kv[0])):
            off = {w: b for w, b, _ in weeks if b != "observed"}
            worst = max((b for _, b, _ in weeks), key=ORDER.get)
            row = Row(t, reg.claim("project_national", q.projected_territory(W, t, product=p.brand_id), "int", territory=t, scope="projected"),
                      worst, off, {w: r for w, b, r in weeks if b != "observed"})
            if len(W) == 1 and worst == "projected":
                row.observed = reg.claim("project_national", q.projection_cell(W[0], t, "observed_trx", product=p.brand_id), "int", territory=t, week=W[0])
                row.coverage = reg.claim("project_national", q.projection_cell(W[0], t, "panel_coverage_ratio", product=p.brand_id), "dec3", territory=t, week=W[0])
            rows.append(row)
    return Projection(W, national, rows, p.brand_id)


def _label(row: Row, single: bool) -> str:
    if row.basis == "observed":
        return ""
    if single and row.basis == "projected":
        return f" (projected, an assumption: {row.observed} observed at panel coverage {row.coverage})"
    if single:
        return (" (estimated, an assumption: its share of national in the four clean weeks before; "
                "its feed failed the gate)")
    parts = []
    for basis in ("projected", "estimated"):
        weeks = sorted(w for w, b in row.weeks.items() if b == basis)
        if weeks:
            parts.append(f"{basis} in the week{'s' if len(weeks) > 1 else ''} of {', '.join(weeks)}")
    return f" ({'; '.join(parts)}; an assumption)"


def table_lines(proj: Projection) -> list[str]:
    """§2: the projected national and one line per territory, with projected and estimated rows labelled."""
    W = proj.weeks
    if proj.national is None:
        return ["No projected national is given: no territory in these weeks can be read."]
    single = len(W) == 1
    head = (f"Projected national {proj.brand_id} TRx for the week of {W[0]}: {proj.national}." if single else
            f"Projected national {proj.brand_id} TRx averaged {proj.national} a week from {W[0]} to {W[-1]}.")
    marked = [r for r in proj.rows if r.basis != "observed"]
    lines = [head, "By territory" + (", observed unless marked; a projected or estimated level is an assumption, "
                                     "not an observed count:" if marked else ", all observed:")]
    lines += [f"- {q.name(r.territory)}: {r.token}{_label(r, single)}" for r in proj.rows]
    return lines


def _names(ts: list[str]) -> str:
    names = [q.name(t) for t in ts]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _reason_words(proj: Projection, territories: list[str]) -> str:
    found: list[str] = []
    for t in territories:
        row = proj.row(t)
        for w, basis in (row.weeks if row else {}).items():
            if basis == "estimated":
                for r in (row.reasons.get(w) or "").split(";"):
                    word = q.REASONS.get(r, r.lower().replace("_", " ")) if r else ""
                    if word and word not in found:
                        found.append(word)
    return ", ".join(found) or "no feed"


def method_lines(proj: Projection) -> list[str]:
    """§4: how the projected and estimated territories were built. No digits."""
    lines = []
    projected, estimated = proj.territories("projected"), proj.territories("estimated")
    if projected:
        verb = "is" if len(projected) == 1 else "are"
        lines.append(f"{_names(projected)} {verb} projected: observed TRx divided by panel coverage, "
                     "because part of the feed is missing.")
    if estimated:
        verb, own = ("is", "its") if len(estimated) == 1 else ("are", "their")
        lines.append(f"{_names(estimated)} {verb} estimated from {own} share of national in the four latest weeks "
                     f"in which every territory passed the gate, because the cut failed for reasons that make "
                     f"its own count unusable ({_reason_words(proj, estimated)}).")
    if projected or estimated:
        lines.append("Assumption: a projected or estimated level is not an observed count, so the projected national "
                     "rests on it. It is a level only: no story or driver is given for it.")
    return lines

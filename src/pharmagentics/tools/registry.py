"""Governed read-only access to the DuckDB release, with evidence items and claim tokens.

Rules (constitution Principle I; Briefing B-III, B-IV):
- Rx metrics only through the reporting views; no raw.rx_weekly.
- Context only from an allowlist of agent-visible tables. Read-only. SELECT only.
- Every number in an output is a claim token `{cN}` that code fills from one evidence query.
"""
from __future__ import annotations

import hashlib
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import duckdb

from ..tracing import finish, span

DEFAULT_DB = Path(__file__).resolve().parents[3] / "local" / "pharmagentics.duckdb"

ALLOWED = {
    "reporting.v_reportable_rx", "reporting.v_weekly_rx_kpis", "reporting.v_feed_health",
    "raw.calendar", "raw.dim_plan", "raw.dim_product", "raw.dim_territory", "raw.dim_specialty",
    "raw.access_status_monthly", "raw.inventory_weekly", "raw.promo_activity", "raw.market_basket",
    "raw.market_share_weekly", "raw.restatement_log", "raw.forecast_vs_actual_weekly",
    "metadata.import_manifest", "metadata.import_runs",
}
_RELATION = re.compile(r"\b(raw|reporting|metadata)\.([a-z_0-9]+)", re.I)

def _half_up(value: float, decimals: int, percent: bool = False) -> str:
    """Round half up, the convention the Evaluation Pack and the harness use (Python's round() goes to even)."""
    d = Decimal(str(abs(value) if percent else value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    return f"{d:,.{decimals}f}" + ("%" if percent else "")


FORMATS = {
    "int": lambda v: _half_up(v, 0),
    "pct1": lambda v: _half_up(v, 1, percent=True),
    "dec2": lambda v: _half_up(v, 2),
    "dec3": lambda v: _half_up(v, 3),
}


class Refused(Exception):
    """A query the governance rules do not allow."""


def check_sql(sql: str) -> None:
    body = sql.strip().rstrip(";").strip()
    if not re.match(r"(?is)^(select|with)\b", body) or ";" in body:
        raise Refused("only a single SELECT is allowed")
    relations = {f"{s}.{t}".lower() for s, t in _RELATION.findall(body)}
    if not relations:
        raise Refused("a query must read a governed relation")
    refused = relations - ALLOWED
    if refused:
        raise Refused(f"relation not allowed: {', '.join(sorted(refused))}")


def data_version(con) -> str:
    try:
        rows = con.execute(
            "select table_name, sha256 from metadata.import_manifest where load_id = "
            "(select load_id from metadata.import_runs order by completed_at desc limit 1) order by 1").fetchall()
    except duckdb.Error:
        return "unavailable"
    return hashlib.sha256(repr(rows).encode()).hexdigest()[:12]


class Registry:
    """One per run: pins the data version and collects evidence items and claims."""

    def __init__(self, db: Path | str = DEFAULT_DB):
        self.con = duckdb.connect(str(db), read_only=True)
        self.data_version = data_version(self.con)
        self.evidence: list[dict] = []
        self.claims: list[dict] = []
        self._by_query: dict[tuple, str] = {}

    def close(self) -> None:
        self.con.close()

    def rows(self, sql: str) -> list[tuple]:
        """Internal screening query: governed, not recorded as evidence."""
        check_sql(sql)
        return self.con.execute(sql).fetchall()

    def scalar(self, sql: str):
        check_sql(sql)
        row = self.con.execute(sql).fetchone()
        return None if row is None else row[0]

    def _evidence(self, tool: str, sql: str, result, params: dict) -> str:
        key = (tool, sql)
        if key not in self._by_query:
            eid = f"e{len(self.evidence) + 1}"
            self.evidence.append({"id": eid, "tool": tool, "params": params, "query": sql.strip(),
                                  "result": result if isinstance(result, (int, float, str)) or result is None else str(result),
                                  "data_version": self.data_version})
            self._by_query[key] = eid
        return self._by_query[key]

    def claim(self, tool: str, sql: str, fmt: str = "int", **params) -> str:
        """Run `sql` (one value), record the evidence item and return the token `{cN}` for the narrative."""
        with span(tool, "TOOL", inputs={"query": sql.strip(), **params}, data_version=self.data_version) as sp:
            value = self.scalar(sql)
            if value is None:
                value = 0
            eid = self._evidence(tool, sql, float(value), params)
            self.claims.append({"value": FORMATS[fmt](float(value)), "evidence_id": eid})
            finish(sp, {"value": self.claims[-1]["value"], "evidence_id": eid})
        return "{c%d}" % len(self.claims)

    def fact(self, tool: str, sql: str, **params):
        """A non-numeric or internal value that the narrative states in words; recorded as evidence."""
        value = self.scalar(sql)
        self._evidence(tool, sql, value, params)
        return value

    def render(self, text: str) -> str:
        return re.sub(r"\{c(\d+)\}", lambda m: self.claims[int(m.group(1)) - 1]["value"], text)

    def render_cited(self, text: str) -> tuple[str, list[dict]]:
        """`render`, plus where each claim value sits in the rendered text (inline citations in the UI)."""
        return cite(text, self.claims)


def cite(template: str, claims: list[dict], index: dict[int, int] | None = None) -> tuple[str, list[dict]]:
    """Fill `{cN}` tokens and return the text with spans `{start, end, claim}`; `claim` indexes `claims`, or
    `index` maps token numbers to positions in another claim list. Same text as `Registry.render`."""
    out, spans, pos = [], [], 0
    for m in re.finditer(r"\{c(\d+)\}", template):
        n = int(m.group(1))
        out.append(template[pos:m.start()])
        start = sum(len(s) for s in out)
        if 0 < n <= len(claims):
            value = claims[n - 1]["value"]
            out.append(value)
            spans.append({"start": start, "end": start + len(value), "claim": index[n] if index else n - 1})
        else:
            out.append(m.group(0))
        pos = m.end()
    out.append(template[pos:])
    return "".join(out), spans



def digits_outside_tokens(template: str) -> list[str]:
    """Verifier rule (FR-008): a digit may appear only inside a claim token or in an ISO date."""
    stripped = re.sub(r"\{c\d+\}", " ", template)
    stripped = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", stripped)
    # Identifiers that mix letters and digits (a data version, a plan ID) are not measurements.
    stripped = re.sub(r"\b\w*[A-Za-z_]\w*\d\w*\b|\b\d+[A-Za-z_]\w*\b", " ", stripped)
    return re.findall(r"\S*\d\S*", stripped)

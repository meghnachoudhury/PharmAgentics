"""Checks that the golden set itself is sound: valid IDs, and every frozen number recomputes."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import duckdb

from .cases import Case
from .paths import DATABASE, EVAL_PACK

# FE-01 to FE-31: Sienna Mao, "Personas & Eval Design" (Oct 16), §3.2. Cited by ID only.
FE_IDS = {f"FE-{i:02d}" for i in range(1, 32)}
BRIEFING_STORIES = ({f"P{p}-Q{q}" for p in range(1, 5) for q in range(1, 7)}
                    | {f"FU-{n}" for n in range(1, 7)})  # two-turn cases (brief-006 FR-013)
FORECAST_STORIES = {f"{p}-Q{q}" for p in ("CA", "BM", "FM") for q in range(1, 7)}


def ev_ids(pack: Path = EVAL_PACK) -> set[str]:
    return set(re.findall(r"^\| (EV-\d\.\d) \|", pack.read_text(encoding="utf8"), flags=re.M))


def id_problems(cases: list[Case]) -> list[str]:
    known = ev_ids() | FE_IDS
    problems = []
    for c in cases:
        prefix = "EV-" if c.lane == "briefing" else "FE-"
        for item in c.eval_items:
            if item not in known or not item.startswith(prefix):
                problems.append(f"{c.story}: eval item {item} is not a {c.lane} item")
        if not c.eval_items:
            problems.append(f"{c.story}: no eval items")
    return problems


def tolerance(expected: int | float) -> float:
    """Half a unit in the last stated decimal place: 0.656 allows 0.0005, 3860 allows 0.5."""
    text = repr(float(expected)) if isinstance(expected, float) else str(expected)
    decimals = len(text.split(".")[1]) if "." in text and isinstance(expected, float) else 0
    return 0.5 * 10 ** -decimals


@dataclass
class FactResult:
    case: str
    fact: str
    expected: object
    actual: object
    ok: bool


def check_facts(cases: list[Case], database: Path = DATABASE) -> list[FactResult]:
    results = []
    with duckdb.connect(str(database), read_only=True) as con:
        for c in cases:
            for f in c.facts:
                try:
                    row = con.execute(f.sql).fetchone()
                    actual = row[0] if row else None
                except duckdb.Error as exc:
                    results.append(FactResult(c.story, f.id, f.value, f"SQL error: {exc}", False))
                    continue
                if isinstance(f.value, str):
                    ok = actual is not None and str(actual) == f.value
                else:
                    ok = actual is not None and abs(float(actual) - float(f.value)) <= tolerance(f.value) + 1e-9
                results.append(FactResult(c.story, f.id, f.value, actual, ok))
    return results

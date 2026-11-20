"""The weekly brief as a memo with a fixed outline (brief-003 User Story 2, FR-004, FR-020, FR-021).

    §1 Bottom line · §2 The numbers · §3 What changed and why (§3.1, §3.2 …) · §4 What the data can't tell us
    · §5 Next checks · §6 Appendix

Code builds every section and every number; the writer (agent) or nothing (scripted) adds prose: the §1
answer and one sentence per story. Both Briefing engines compose through `compose`, so they emit the same
skeleton. Headings carry no digits (research R6): section numbers live in the structured `sections`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import queries as q
from . import stages
from .checks import DECISION, OWNER
from .projection import Projection, method_lines, table_lines
from .registry import Registry

HEADINGS = [("1", "Bottom line"), ("2", "The numbers"), ("3", "What changed and why"),
            ("4", "What the data can't tell us"), ("5", "Next checks"), ("6", "Appendix")]
EMPTY = {"1": "Nothing can be reported for this period.", "2": "No figure can be given for this period.",
         "3": "No material change was found, and territory swings stayed in their normal range.",
         "4": "Nothing in this period limits the figures above.", "5": "No check is open.", "6": ""}
HEADING_PREFIX = "## "
TOKEN = re.compile(r"\{c(\d+)\}")
_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
_RANK = {"Low": 0, "Medium": 1, "High": 2}

# What a reader needs to know about each term the brief uses (from GLOSSARY.md; no digits).
GLOSSARY = {
    "like for like": "Like for like: a comparison that uses only territories whose feed passed its checks in every week compared.",
    "panel coverage": "Panel coverage: the share of a territory's expected prescription records that arrived in a given week.",
    "projected national": "Projected national: national TRx built territory by territory, each territory's observed TRx divided by its panel coverage, summed.",
    "estimated": "Estimated territory: a territory whose coverage is too low to project, or whose count failed its checks, filled from its own recent share of national and labelled as estimated, an assumption.",
    "withheld cut": "Withheld cut: a territory or week whose data failed its checks, so no story or driver is given for it.",
}


@dataclass
class StoryBlock:
    id: str
    title: str
    lines: list[str]  # head line, checks, closing confidence; no "Next:" (it lives in §5)
    prose: str = ""  # one sentence by the writer; empty for the scripted engine


@dataclass
class MemoParts:
    title: list[str]
    bottom_line: list[str]
    numbers: list[str]
    limits: list[str]
    next_checks: list[str]
    appendix: list[str]
    stories: list[StoryBlock] = field(default_factory=list)
    story_notes: list[str] = field(default_factory=list)  # calendar, left out, considered and dropped, routine
    answer: str = ""  # §1 prose


def compose(parts: MemoParts) -> tuple[str, list[dict]]:
    """The token template (flattened answer) and the sections, each {number, title, lines, prose}."""
    body = {"1": parts.bottom_line, "2": parts.numbers, "3": parts.story_notes, "4": parts.limits,
            "5": parts.next_checks, "6": parts.appendix}
    prose = {"1": parts.answer}
    seen = "\n".join(parts.title + [x for n, _ in HEADINGS for x in body[n]] + [parts.answer]
                     + [x for s in parts.stories for x in s.lines + [s.prose]]).lower()
    glossary = [d for term, d in GLOSSARY.items() if term in seen]
    body["6"] = parts.appendix + (["Glossary:"] + [f"- {d}" for d in glossary] if glossary else [])
    out, sections = list(parts.title), []
    for number, title in HEADINGS:
        lines = [x for x in body[number] if x]
        if number == "3":
            out.append(HEADING_PREFIX + title)
            for s in parts.stories:
                story_lines = [x for x in s.lines if x]
                out += story_lines[:1] + ([s.prose] if s.prose else []) + story_lines[1:]
            if not lines and not parts.stories:
                lines = [EMPTY["3"]]
            out += lines
            sections.append({"number": number, "title": title, "lines": lines, "prose": ""})
            sections += [{"number": f"3.{i}", "title": s.title, "lines": [x for x in s.lines if x], "prose": s.prose}
                         for i, s in enumerate(parts.stories, 1)]
            continue
        if not lines and not prose.get(number) and EMPTY[number]:
            lines = [EMPTY[number]]
        out.append(HEADING_PREFIX + title)
        out += lines + ([prose[number]] if prose.get(number) else [])
        sections.append({"number": number, "title": title, "lines": lines, "prose": prose.get(number, "")})
    return "\n".join(out), sections


def render_sections(sections: list[dict], claims: list[dict], index: dict[int, int] | None = None) -> list[dict]:
    """Fill each section's tokens. `claims` are the claims the tokens number; `index` maps a token number to
    its position in the envelope's claims when the envelope keeps only the claims it uses (the agent)."""
    def fill(text: str) -> str:
        return TOKEN.sub(lambda m: claims[int(m.group(1)) - 1]["value"] if 0 < int(m.group(1)) <= len(claims) else m.group(0), text)

    out = []
    for s in sections:
        text = "\n".join(s["lines"])
        used = list(dict.fromkeys(int(n) for n in TOKEN.findall(text + "\n" + s["prose"])))
        refs = [index[n] if index is not None else n - 1 for n in used
                if 0 < n <= len(claims) and (index is None or n in index)]
        out.append({"number": s["number"], "title": s["title"], "text": fill(text), "prose": fill(s["prose"]), "claims": refs})
    return out


# Code-built sections -----------------------------------------------------------------------------

def title_lines(p) -> list[str]:
    return [f"Brief for {stages.describe(p)}. Product: BXA."] + ([p.note] if p.note else [])


def withheld(p) -> list[tuple[str, str]]:
    """(week, territory) cuts in the requested weeks that failed the feed gate."""
    return sorted((w, t) for w in p.requested for t in p.terrs if p.status.get((w, t), ("PASS", ""))[0] == "FLAG")


def _owner(t: str) -> str:
    """A territory's possessive: "New England's", "Great Lakes'"."""
    name = q.name(t)
    return name + ("'" if name.endswith("s") else "'s")


def _warning(p, proj: Projection) -> str | None:
    cuts = withheld(p)
    if not cuts:
        return None
    if len(p.requested) > 1 or len(cuts) > 2:
        return ("Data warning: some territory-weeks in this period failed the feed gate. They are labelled in "
                "The numbers, and no story is given for them.")
    parts = []
    for w, t in cuts:
        row = proj.row(t)
        if row is not None and row.basis == "projected":
            parts.append(f"{_owner(t)} feed for {w} is incomplete, so its TRx is projected from panel coverage, an assumption")
        else:
            parts.append(f"{_owner(t)} feed for {w} failed its checks, so its TRx is estimated from its recent "
                         "share of national, an assumption")
    return "Data warning: " + "; ".join(parts) + ". No story is given for " + ("it." if len(cuts) == 1 else "them.")


def _like_for_like(reg: Registry, p) -> str:
    W, B, ok = p.weeks, p.baseline, p.ok
    if not ok:
        return "No like-for-like change is given: no territory passes the feed gate in every week compared."
    if not B:
        return "No like-for-like change is given: the release has no earlier weeks to compare with."
    cur, base = q.mean_weekly(W, terrs=ok), q.mean_weekly(B, terrs=ok)
    change = reg.scalar(q.pct_change(cur, base)) or 0
    n = reg.claim("get_metric", f"select count(distinct territory_id) from {q.RX} where week_start in {q._dates(W)} "
                  f"and {q._in('territory_id', ok)}", "int")
    total = reg.claim("get_metric", "select count(*) from raw.dim_territory", "int")
    pct = reg.claim("get_metric", q.pct_change(cur, base), "pct1", scope="like-for-like national")
    span = f"the {_WORDS[len(B)]} weeks before" if len(W) == 1 and len(B) in _WORDS else "the weeks before"
    return f"Like for like on {n} of {total} territories, BXA TRx is {stages.word(change)} {pct} against {span}."


def _least_sure(reg: Registry, p, proj: Projection, stories: list[dict]) -> str | None:
    """Research R8: estimated territory, else projected, else the lowest-confidence story's change, else the
    change built on the fewest prescriptions. The competitor story is left out: its share is measured."""
    single = len(proj.weeks) == 1
    for basis in ("estimated", "projected"):
        ts = proj.territories(basis)
        if ts:
            row = proj.row(ts[0])
            if single and basis == "projected":
                why = f"is an assumption, projected from panel coverage of {row.coverage}"
            elif single:
                why = "is an assumption, estimated from its recent share of national, because its feed failed its checks"
            else:
                why = (f"rests on an assumption: it is {basis} for the week{'s' if len(row.weeks) > 1 else ''} "
                       f"of {', '.join(sorted(row.weeks))}")
            amount = f"TRx of {row.token}" if single else f"TRx, {row.token} a week,"
            return f"Least sure: {_owner(ts[0])} {amount} {why}."
    if stories:
        s = min(stories, key=lambda s: _RANK.get(s["confidence"], 0))
        t = s["territory"]
        x, b = q.mean_weekly(p.weeks, terrs=[t]), q.mean_weekly(p.baseline, terrs=[t])
        change = reg.scalar(q.pct_change(x, b)) or 0
        pct = reg.claim("get_metric", q.pct_change(x, b), "pct1", territory=t)
        return f"Least sure: the {q.name(t)} change ({stages.word(change)} {pct}), because its confidence is {s['confidence']}."
    if len(p.weeks) == 1 and p.baseline:
        w, prev = p.weeks[0], p.baseline[-1]
        sql = q.pct_change(q.trx_sum([w]), q.trx_sum([prev]))
        change = reg.scalar(sql) or 0
        pct = reg.claim("get_metric", sql, "pct1", scope="week over week, reportable cuts")
        return (f"Least sure: the week-over-week change ({stages.word(change)} {pct}), "
                "because it compares one week with one week.")
    if p.ok and p.baseline:
        return "Least sure: the like-for-like change, the only change this brief states."
    return None


def bottom_line(reg: Registry, p, proj: Projection, stories: list[dict], restated: bool) -> list[str]:
    """§1 in FR-021 order, after a data warning or restatement note when there is one. `stories` are the
    territory stories in brief order: {territory, confidence}."""
    lines = [x for x in [_warning(p, proj)] if x]
    if restated:
        lines.append("Data note: an earlier week was restated. The new value and the reason are in The numbers.")
    W = proj.weeks
    if proj.national is None:
        lines.append("This period cannot be reported nationally: no territory's feed can be read.")
    elif len(W) == 1:
        lines.append(f"Projected national BXA TRx is {proj.national} for the week of {W[0]}.")
    else:
        lines.append(f"Projected national BXA TRx averaged {proj.national} a week from {W[0]} to {W[-1]}.")
    lines.append(_like_for_like(reg, p))
    share = reg.claim("compare_competitors", q.share(W, "BXA"), "pct1", product="BXA")
    lines.append(f"BXA held {share} of the four-brand market basket.")
    least = _least_sure(reg, p, proj, stories)
    if least:
        lines.append(least)
    return lines


def limits(p, proj: Projection, health: str) -> list[str]:
    """§4: data health with the gate detail (`stages.data_health`, already claimed), the withheld focus
    territory, how the projection was built, and calendar weeks left out."""
    lines = [health]
    if p.focus in p.terrs and p.focus not in p.ok:
        lines.append(f"{q.name(p.focus)} has withheld cuts in these weeks, so no like-for-like story is given for it.")
    lines += method_lines(proj)
    if p.calendar_note:
        lines.append(p.calendar_note)
    return lines


def appendix(reg: Registry) -> list[str]:
    return ["Method: like-for-like figures use only territories whose feed passed the gate in every week compared. "
            "The projected national divides each territory's observed TRx by its panel coverage, and estimates a "
            "territory that cannot be read from its recent share of national. Changes, stories and drivers use "
            "like-for-like cuts only.",
            f"Data version {reg.data_version}. Product: BXA (Cardiovela), synthetic data."]


def _line(subject: str, action: str, owner: str, decision: str) -> str:
    return f"- {subject}: {action}. Owner: {owner}. Unlocks: {decision}."


def next_checks(p, stories: list[dict], competitor: bool) -> list[str]:
    """§5 (research R10): one line per territory story ({territory, confidence, drivers}), per withheld cut,
    and for a continuing competitor story."""
    lines = []
    for s in stories:
        name = q.name(s["territory"])
        drivers = [d for d in s.get("drivers", []) if d in OWNER]
        if s["confidence"] == "Low" or not drivers:
            lines.append(_line(name, "split by plan and specialty, and ask for local context", "sales leadership",
                               DECISION["unresolved"]))
        else:
            owners = ", ".join(dict.fromkeys(OWNER[d] for d in drivers))
            decisions = "; ".join(DECISION[d] for d in drivers)
            lines.append(_line(name, f"confirm the {' and '.join(drivers)} finding", owners, decisions))
    for w, t in withheld(p):
        lines.append(_line(f"{q.name(t)}, week of {w}", "re-run when the corrected feed lands, and disclose the restated week",
                           OWNER["data"], DECISION["data"]))
    if competitor:
        lines.append(_line("Metacora", "track the basket shares each week", OWNER["competitor"], DECISION["competitor"]))
    return lines


def without_next(closing: str) -> str:
    """A story's closing line without its "Next: …" clause, which moves to §5."""
    return re.sub(r"\s*Next: [^.]*\.", "", closing).rstrip()


def numbers(proj: Projection, kpi_lines: list[str], restatement_lines: list[str]) -> list[str]:
    """§2: the projection table, the KPI lines (like for like, week over week, calendar) and restatements,
    which sit here so leaders see them (research R7)."""
    return table_lines(proj) + kpi_lines + restatement_lines

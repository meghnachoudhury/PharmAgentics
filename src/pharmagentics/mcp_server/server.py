"""The MCP server and its per-run session.

One session is one run: `open_run` pins the question's period and one data version, the agent tools
add evidence items and claim tokens to the session's Registry, and `export_run` hands them back to the
caller (code, never the model). Admin tools are for the caller; agents get `AGENT_TOOLS` only.

Every number in a tool's text is a claim token such as {c7}; the model writes tokens and code fills them
(B-III). With `legend=True` a legend after the text also gives each token's value, for models that reason
about size; it is off by default because a small model copies the legend's values into its prose.
Verdicts and confidence are computed by code; the model chooses which tools to call and in what order.
"""
from __future__ import annotations

import json
import re

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from pharmagentics.tools import DEFAULT_DB, Registry
from pharmagentics.tools import queries as q
from pharmagentics.tools import stages
from pharmagentics.tools.checks import (DRIVERS, OWNER, Check, check_access, check_competitor, check_data,
                                        check_promotion, check_supply, confidence, context_baseline)

ADMIN_TOOLS = ("open_run", "export_run")
AGENT_TOOLS = {
    # Briefing Data Forensics: is the data wrong, and what is the like-for-like change?
    "data_forensics": ("feed_health", "restatements", "national_kpis", "check_data"),
    # Briefing Driver Investigator: where did it move, and why?
    "driver_investigator": ("screen_territories", "territory_change", "check_access", "check_promotion",
                            "check_supply", "check_competitor", "competitor_status", "story_confidence"),
}
_TERRITORIES = {k: v for k, v in q.TERRITORY_NAMES.items() if k != "NATIONAL"}
_TOKEN = re.compile(r"\{c(\d+)\}")


class RunSession:
    """State for one run: the Registry (pinned data version, evidence, claims), the period, driver verdicts."""

    def __init__(self, db=DEFAULT_DB, legend: bool = False):
        self.db = db
        self.legend = legend
        self.reg: Registry | None = None
        self.p: stages.Period | None = None
        self.checks: dict[str, dict[str, Check]] = {}
        self.stories: dict[str, dict] = {}
        self.calls: list[dict] = []

    # admin -------------------------------------------------------------------------------------
    def open_run(self, question: str) -> str:
        self.close()
        self.reg = Registry(self.db)
        self.p = stages.resolve(self.reg, question)
        self.checks, self.stories, self.calls = {}, {}, []
        if not self.p.requested:
            return stages.outside_release(self.p)
        lines = [f"Period: {stages.describe(self.p)}, compared with the {len(self.p.baseline)} weeks before "
                 f"({self.p.baseline[0]} to {self.p.baseline[-1]}).",
                 f"Data version {self.reg.data_version}. Product: BXA (Cardiovela)."]
        if self.p.note:
            lines.append(self.p.note)
        if self.p.focus:
            lines.append(f"The question names {q.name(self.p.focus)} ({self.p.focus}).")
        return "\n".join(lines)

    def export_run(self) -> dict:
        reg = self._reg()
        return {"data_version": reg.data_version, "claims": reg.claims, "evidence": reg.evidence,
                "abstained": any(st["confidence"] == "Low" for st in self.stories.values()),
                "stories": self.stories, "calls": self.calls}

    def close(self) -> None:
        if self.reg is not None:
            self.reg.close()
            self.reg = None

    # helpers -----------------------------------------------------------------------------------
    def _reg(self) -> Registry:
        if self.reg is None or self.p is None:
            raise ToolError("no run is open; the caller must call open_run first")
        return self.reg

    def _log(self, tool: str, **args) -> None:
        self._reg()
        self.calls.append({"tool": tool, "args": args})

    def _out(self, text: str) -> str:
        """A tool's text, with the legend of token values when the session has it on."""
        reg = self._reg()
        seen = sorted({int(n) for n in _TOKEN.findall(text)})
        if not seen or not self.legend:
            return text
        legend = "; ".join(f"{{c{n}}} = {reg.claims[n - 1]['value']}" for n in seen)
        return f"{text}\n\nToken values, for your reasoning only. Write the token, never the value: {legend}"

    def _territory(self, territory: str) -> str | None:
        key = re.sub(r"[\s\-]+", "_", (territory or "").strip()).upper()
        if key in _TERRITORIES:
            return key
        by_name = {v.upper(): k for k, v in _TERRITORIES.items()}
        return by_name.get((territory or "").strip().upper())

    def _bad_territory(self, territory: str) -> str:
        return f"Unknown territory {territory!r}. Use one of: {', '.join(_TERRITORIES)}."

    def _withheld(self, t: str) -> str | None:
        if t not in self.p.ok:
            return (f"{q.name(t)} has cuts that fail the feed gate in these weeks, so no like-for-like test is given "
                    f"for it. Use check_data on it, and report it as withheld.")
        return None

    # Data Forensics ----------------------------------------------------------------------------
    def feed_health(self) -> str:
        self._log("feed_health")
        p = self.p
        lines = [stages.data_health(self.reg, p)]
        lines.append(f"Like-for-like territories (every week passes the gate): {', '.join(p.ok) or 'none'}.")
        withheld = [t for t in p.terrs if t not in p.ok]
        if withheld:
            lines.append(f"Not like for like in these weeks: {', '.join(withheld)}.")
        if p.focus in p.terrs and p.focus not in p.ok:
            lines.append(f"{q.name(p.focus)} has withheld cuts in these weeks, so no like-for-like story is given for it.")
        return self._out("\n".join(lines))

    def restatements(self) -> str:
        self._log("restatements")
        lines = stages.restatements(self.reg, self.p)
        return self._out("\n".join(lines) if lines else "No BXA restatement touches these weeks.")

    def national_kpis(self) -> str:
        self._log("national_kpis")
        lines = ([self.p.calendar_note] if self.p.calendar_note else []) + stages.kpis(self.reg, self.p)
        if self.p.calendar:
            lines.append("No story is opened for a calendar week. Expect a rebound in the next regular week.")
        return self._out("\n".join(lines))

    def check_data(self, territory: str) -> str:
        self._log("check_data", territory=territory)
        t = self._territory(territory)
        if t is None:
            return self._bad_territory(territory)
        return self._record(t, check_data(self.reg, t, self.p.weeks, self.p.baseline))

    # Driver Investigator -----------------------------------------------------------------------
    def screen_territories(self) -> str:
        self._log("screen_territories")
        p = self.p
        if p.calendar:
            return "Calendar mode: most of these weeks are holiday or plan-year-reset weeks, so no territory story is opened."
        found, quiet = stages.screen(self.reg, p)
        if not found:
            return "No territory moved beyond its normal range against its peers. Routine week: no story to investigate."
        lines = ["Territories with a material change, largest impact first:"]
        for s in found:
            why = f"BXA volume on plan {s['plan']} changed after an access change" if s["kind"] == "plan" else "beyond its normal range and its peers"
            lines.append(f"- {s['territory']} ({q.name(s['territory'])}): {why}.")
        if quiet:
            lines.append(f"Considered and dropped: {stages.dropped_count(self.reg, p, quiet)} territories moved within their normal range.")
        lines.append("Next: territory_change, then every check_*, then story_confidence, for each territory above.")
        return self._out("\n".join(lines))

    def territory_change(self, territory: str) -> str:
        self._log("territory_change", territory=territory)
        t = self._territory(territory)
        if t is None:
            return self._bad_territory(territory)
        return self._withheld(t) or self._out(stages.territory_change(self.reg, self.p, t))

    def _driver(self, name: str, territory: str, fn, reference: bool) -> str:
        self._log(name, territory=territory)
        t = self._territory(territory)
        if t is None:
            return self._bad_territory(territory)
        if (msg := self._withheld(t)):
            return msg
        B = context_baseline(self.p.weeks, self.p.baseline) if reference else self.p.baseline
        return self._record(t, fn(self.reg, t, self.p.weeks, B))

    def _record(self, t: str, check: Check) -> str:
        self.checks.setdefault(t, {})[check.driver] = check
        return self._out(f"{q.name(t)}. {check.text}\n{self._status(t, closing=False)}")

    def check_access(self, territory: str) -> str:
        return self._driver("check_access", territory, check_access, reference=False)

    def check_promotion(self, territory: str) -> str:
        return self._driver("check_promotion", territory, check_promotion, reference=True)

    def check_supply(self, territory: str) -> str:
        return self._driver("check_supply", territory, check_supply, reference=False)

    def check_competitor(self, territory: str) -> str:
        return self._driver("check_competitor", territory, check_competitor, reference=True)

    def competitor_status(self) -> str:
        self._log("competitor_status")
        text = stages.competitor_status(self.reg, self.p)
        return self._out(text) if text else "Metacora is not a story in these weeks: not launched yet, or still a small share of the basket."

    def story_confidence(self, territory: str) -> str:
        self._log("story_confidence", territory=territory)
        t = self._territory(territory)
        if t is None:
            return self._bad_territory(territory)
        return self._status(t, closing=True)

    def _status(self, t: str, closing: bool) -> str:
        """Confidence by code from the checks run so far (Briefing scale); every driver check reports it."""
        done = self.checks.get(t, {})
        missing = [d for d in DRIVERS if d not in done]
        level, lead = confidence(list(done.values()))
        if missing and level == "High":
            level = "Medium"  # an untested driver is an alternative still open
        supported = [c for c in done.values() if c.verdict == "supported"]
        self.stories[t] = {"confidence": level, "lead": None if level == "Low" else lead, "not_tested": missing,
                           "verdicts": {d: c.verdict for d, c in done.items()}, "closed": closing}
        if not closing:
            return (f"Story so far for {q.name(t)}: confidence {level}"
                    + (f", candidate drivers: {lead}" if level != "Low" else ", no driver supported yet")
                    + (f". Not tested yet: {', '.join(missing)}." if missing else ". Every driver is tested.")
                    + " Close the story with story_confidence.")
        if level == "Low":
            text = (f"Confidence for {q.name(t)}: Low. Unresolved, investigate next. No driver is named. "
                    f"Next: split {q.name(t)} by plan and specialty, and ask sales leadership for local context.")
        else:
            verb = "Leading driver" if level == "High" else "Candidate drivers"
            text = f"Confidence for {q.name(t)}: {level}. {verb}: {lead}. Next: involve {', '.join(OWNER[c.driver] for c in supported)}."
        if missing:
            text += f" Not tested: {', '.join(missing)}."
        return text


def build_server(db=DEFAULT_DB, legend: bool = False) -> MCPServer:
    """A fresh server with one session. Over stdio, one process serves one run at a time."""
    s = RunSession(db, legend=legend)
    server = MCPServer(
        name="pharmagentics",
        instructions=("Governed, read-only tools over the PharmAgentics synthetic data (product BXA, Cardiovela). "
                      "The caller opens a run first. Numbers come back as claim tokens like {c7}: write the token, "
                      "never the number; code fills it in."),
    )
    text = dict(structured_output=False)

    @server.tool(**text)
    async def open_run(question: str) -> str:
        """Admin: start a run for one question. Pins the period and the data version. Callers only, not agents."""
        return s.open_run(question)

    @server.tool(**text)
    async def export_run() -> str:
        """Admin: the run's claims, evidence items and verdicts as JSON. Callers only, not agents."""
        return json.dumps(s.export_run(), default=str)

    @server.tool(**text)
    async def feed_health() -> str:
        """Which territory-week cuts pass the feed gate for the run's weeks, why any are withheld, and the like-for-like territories. Call this first."""
        return s.feed_health()

    @server.tool(**text)
    async def restatements() -> str:
        """BXA restatements touching the run's weeks: old and new values. Quote the new value with the note."""
        return s.restatements()

    @server.tool(**text)
    async def national_kpis() -> str:
        """National BXA TRx: like for like against the weeks before, week over week for a one-week period, a headline total distorted by withheld cuts, and calendar effects."""
        return s.national_kpis()

    @server.tool(**text)
    async def check_data(territory: str) -> str:
        """Data-artifact check for one territory: do its cuts in these weeks pass the feed gate? Verdict by code."""
        return s.check_data(territory)

    @server.tool(**text)
    async def screen_territories() -> str:
        """Competitive intelligence: territories whose BXA change is beyond their normal range and their peers', largest impact first."""
        return s.screen_territories()

    @server.tool(**text)
    async def territory_change(territory: str) -> str:
        """One territory's BXA TRx in the run's weeks against the weeks before, and the other territories' change."""
        return s.territory_change(territory)

    @server.tool(**text)
    async def check_access(territory: str) -> str:
        """Driver check: did a payer plan in this territory change BXA tier, prior authorization, step therapy or coverage? Verdict by code."""
        return s.check_access(territory)

    @server.tool(**text)
    async def check_promotion(territory: str) -> str:
        """Driver check: did aggregated rep calls in this territory change? Supported only as an association. Verdict by code."""
        return s.check_promotion(territory)

    @server.tool(**text)
    async def check_supply(territory: str) -> str:
        """Driver check: was BXA inventory fill low or backordered in this territory? Verdict by code."""
        return s.check_supply(territory)

    @server.tool(**text)
    async def check_competitor(territory: str) -> str:
        """Driver check: was competitor Metacora stronger in this territory than elsewhere before the change? Verdict by code."""
        return s.check_competitor(territory)

    @server.tool(**text)
    async def competitor_status() -> str:
        """Metacora (competitor, launched 2026-03-02) as a continuing national story: weeks since launch, direction, basket shares."""
        return s.competitor_status()

    @server.tool(**text)
    async def story_confidence(territory: str) -> str:
        """Close a territory story: confidence (High, Medium or Low), leading driver and who to involve, computed by code from the checks run so far."""
        return s.story_confidence(territory)

    return server

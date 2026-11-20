"""Systems under test. Each takes the question text and returns an AnswerEnvelope dict.

reference: returns the golden answer. Positive control: if it fails a code check, the check is wrong.
naive_llm: a local model with no data and no tools. Negative control: it should fail numeric checks.
The fresh scripted baseline and the agents plug in here as they are built.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

import mlflow

from .cases import Case
from .envelope import AnswerEnvelope
from .paths import DEFAULT_LOCAL_MODEL, REPO_ROOT

NAIVE_PROMPT = (
    "You are a commercial analyst for Cardiovela (product code BXA), a fictional cardiovascular brand. "
    "Answer the brand team's question in a short paragraph."
)


class ReferenceSystem:
    name = "reference"
    uses_llm = False
    returns_evidence = False

    def __init__(self, cases: list[Case]):
        self._answers = {c.question: c.reference_answer for c in cases}

    def predict(self, question: str) -> dict:
        return AnswerEnvelope(system=self.name, answer=self._answers[question]).model_dump()


class NaiveLLMSystem:
    name = "naive_llm"
    uses_llm = True
    returns_evidence = False

    def __init__(self, cases: list[Case], model: str | None = None):
        self.model = model or os.environ.get("PHARMAGENTICS_LOCAL_MODEL", DEFAULT_LOCAL_MODEL)
        self.host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
        if not self.host.startswith("http"):
            self.host = "http://" + self.host

    @mlflow.trace(span_type="LLM", name="ollama_chat")
    def _chat(self, question: str) -> str:
        body = {"model": self.model, "stream": False, "options": {"temperature": 0},
                "messages": [{"role": "system", "content": NAIVE_PROMPT}, {"role": "user", "content": question}]}
        req = urllib.request.Request(f"{self.host}/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read())["message"]["content"].strip()

    def predict(self, question: str) -> dict:
        return AnswerEnvelope(system=f"{self.name}:{self.model}", answer=self._chat(question)).model_dump()


def _lane_package(folder: str, package: str):
    """Agent code lives in agents/<lane>/<package>; the harness imports it, never the other way round."""
    for path in (REPO_ROOT / "src", REPO_ROOT / "agents" / folder):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    return __import__(package)


class _ScriptedLane:
    """A lane's scripted baseline (Evaluation Pack section 6): fixed pipeline, no model, evidence on every number."""

    uses_llm = False
    returns_evidence = True
    folder = package = name = ""

    def __init__(self, cases: list[Case]):
        self._answer = _lane_package(self.folder, self.package).answer

    def predict(self, question: str) -> dict:
        return AnswerEnvelope.model_validate(self._answer(question)).model_dump()


def transcript(system: str, brief: dict, turn: dict, brief_seconds: float, turn_seconds: float) -> dict:
    """A two-turn case as one envelope (brief-006 FR-013): the answer, claims and evidence of both turns, so every
    gated check covers both, plus what the follow-up said and cited. Follow-up evidence keeps its own ids."""
    have = {e["id"] for e in brief.get("evidence", [])}
    return AnswerEnvelope.model_validate({
        "system": system, "answer": brief["answer"] + "\n\n" + turn["answer"],
        "claims": list(brief.get("claims", [])) + list(turn.get("claims", [])),
        "evidence": list(brief.get("evidence", [])) + [e for e in turn.get("evidence", []) if e["id"] not in have],
        "abstained": bool(brief.get("abstained")), "sections": brief.get("sections"),
        "follow_up_answer": turn["answer"], "cited": turn.get("cited", []),
        "brief_sections": [s["number"] for s in brief.get("sections") or []],
        "latency": {"brief": brief_seconds, "turn": turn_seconds},
        "trajectory": {**(brief.get("trajectory") or {}), "follow_up": turn.get("trajectory")} if brief.get("trajectory") else None,
    }).model_dump()


class BriefingScripted(_ScriptedLane):
    name, folder, package = "briefing_scripted", "brand-briefing", "briefing_baseline"

    def predict_follow_up(self, question: str, follow_up: str, section: str | None) -> dict:
        """The scripted brief, then the rule-based follow-up from that brief alone (brief-006 FR-004)."""
        import time

        from pharmagentics.tools import followup
        pkg = _lane_package(self.folder, self.package)
        started = time.perf_counter()
        brief = self._answer(question)
        middle = time.perf_counter()
        turn = followup.answer({**brief, **pkg.pipeline.scope(question)}, follow_up, section)
        return transcript(self.name, brief, turn, middle - started, time.perf_counter() - middle)


class ForecastScripted(_ScriptedLane):
    name, folder, package = "forecast_scripted", "forecast-explanation", "forecast_baseline"


class BriefingLowCode:
    """Briefing low-code build: Agent Framework's Magentic-One over the PharmAgentics MCP server
    (agents/brand-briefing/briefing_lowcode/). Local model by default; `--model gemini:<model>` switches."""

    name = "briefing_lowcode"
    uses_llm = True
    returns_evidence = True
    returns_trajectory = True

    def __init__(self, cases: list[Case], model: str | None = None):
        pkg = _lane_package("brand-briefing", "briefing_lowcode")
        from pharmagentics.llm import model_spec

        self._answer = pkg.answer
        self.model = model_spec(model)
        self.params = {"agent_config_version": pkg.config_version()}

    def predict(self, question: str) -> dict:
        return AnswerEnvelope.model_validate(self._answer(question, self.model)).model_dump()

    def runtime(self) -> dict:
        """The model server's state after a rerun (e.g. how much of a local model sits in VRAM)."""
        from pharmagentics.llm import ollama_runtime

        return ollama_runtime(self.model)


class BriefingAgent(BriefingLowCode):
    """Briefing build 3 (agents/brand-briefing/briefing_agent/; brief-002 Phase B): code triage, the manager's
    plan, a bounded team per story, code-built sections with the writer's answer and story sentences."""

    name = "briefing_agent"

    def __init__(self, cases: list[Case], model: str | None = None):
        _lane_package("brand-briefing", "briefing_lowcode")  # build 3 reuses build 2's middleware
        pkg = _lane_package("brand-briefing", "briefing_agent")
        from pharmagentics.llm import model_spec

        self._answer = pkg.answer
        self.model = model_spec(model)
        self.params = {"agent_config_version": pkg.config_version()}

    def predict_follow_up(self, question: str, follow_up: str, section: str | None) -> dict:
        """The agent's brief, then one agent follow-up on it (brief-006 slice 4). A turn that runs out of time is
        a run error, never a score (FR-010)."""
        import time

        from briefing_agent import followup
        from briefing_baseline import pipeline
        started = time.perf_counter()
        brief = self._answer(question, self.model)
        middle = time.perf_counter()
        turn = followup.answer({**brief, **pipeline.scope(question)}, follow_up, section, self.model)
        if turn.get("error") == "timeout":
            raise TimeoutError(f"follow-up: {turn['answer']}")
        return transcript(f"{self.name}:{self.model}", brief, turn, middle - started, time.perf_counter() - middle)


class ForecastRules:
    """Forecast redesign (fcst-001), scripted arm: question, code scope, discovered episodes, the rules policy
    choosing comparisons and verdicts, code-written answer (agents/forecast-explanation/forecast_agent/)."""

    name = "forecast_rules"
    uses_llm = False
    returns_evidence = True
    returns_trajectory = True

    def __init__(self, cases: list[Case], model: str | None = None):
        pkg = _lane_package("forecast-explanation", "forecast_agent")
        self._answer = pkg.answer
        self.model = None
        self.params = {"agent_config_version": pkg.config_version()}

    def predict(self, question: str) -> dict:
        return AnswerEnvelope.model_validate(self._answer(question, model=self.model)).model_dump()


class ForecastAgent(ForecastRules):
    """Forecast product (fcst-002): a model reads the question and writes the summary; the rules investigate."""

    name = "forecast_agent"
    uses_llm = True
    investigator = "rules"

    def __init__(self, cases: list[Case], model: str | None = None):
        super().__init__(cases)
        from pharmagentics.llm import model_spec

        self.model = model_spec(model)
        self.params["investigator"] = self.investigator

    def predict(self, question: str) -> dict:
        return AnswerEnvelope.model_validate(self._answer(question, model=self.model,
                                                          investigator=self.investigator)).model_dump()

    def runtime(self) -> dict:
        from pharmagentics.llm import ollama_runtime

        return ollama_runtime(self.model)


class ForecastInvestigator(ForecastAgent):
    """Forecast comparison arm (fcst-002): the model also investigates (step 6), to test whether it adds anything."""

    name = "forecast_investigator"
    investigator = "model"


SYSTEMS = {"reference": ReferenceSystem, "naive_llm": NaiveLLMSystem, "briefing_scripted": BriefingScripted,
           "forecast_scripted": ForecastScripted, "briefing_lowcode": BriefingLowCode, "briefing_agent": BriefingAgent,
           "forecast_rules": ForecastRules, "forecast_agent": ForecastAgent,
           "forecast_investigator": ForecastInvestigator}

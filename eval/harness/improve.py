"""The feedback loop: the system proposes, people promote (core-008 FR-019, FR-020; ADR 0003).

    uv run python -m eval improve [--state-dir DIR] [--baseline RUN_ID] [--model anthropic:claude-haiku-5-5]

Reads new votes (with their comments) and saved threads from the state store, and writes proposals to its review
list (`review/proposals/<id>.json`) for the tester admin to approve or reject:

- a downvote with a comment on a Briefing answer → a draft **lesson** (Haiku, number-free), checked by code (no digit,
  no banned term, short), then tested: the flagged question is rerun with the lesson, the gated code checks run on
  the new answer, and an agent reviewer (Haiku) says whether the reported problem is still there. With `--baseline`,
  one golden-set run with every candidate lesson is gated against that run.
- an upvote, or a saved thread → a draft **case** for labelling (a vote is an opinion, never ground truth).

A lesson is **confident** only when its code checks pass, the rerun passes every gated check, the reviewer says the
problem is gone, and the gate passed (FR-020). Anything else is **flagged** with its reasons. Either way a person
decides. The loop never edits code or prompts, and never writes the knowledge base: `eval promote` does, on approval.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from pathlib import Path

from .candidates import DEFAULT_STATE_DIRS, VOTES, drafts, load_votes
from .paths import REPO_ROOT

PROPOSALS = "review/proposals/"
BANNED = [(re.compile(r"surveillance", re.I), 'says "surveillance"'),
          (re.compile(r"new patients?(?![^.]*\bNBRx\b)", re.I), 'says "new patients" about something other than NBRx')]
LESSON_PROMPT = """You review feedback on a weekly brand-performance brief for the fictional brand BXA (synthetic data).
An analyst marked an answer down and said why. Write ONE lesson for the writer that would prevent this problem next
time: a single sentence of guidance about wording, order or what to check, under thirty words.

Rules: no numbers or digits at all; no names of people; do not restate the answer; do not promise data the brief
does not have. Say "competitive intelligence", never "surveillance".

Question: {question}
The answer (numbers masked): {answer}
The analyst's comment: {comment}

Reply with the lesson sentence only."""
REVIEW_PROMPT = """An analyst reported this problem with an answer: "{comment}"
Here is a new answer to the same question, written with a lesson meant to fix it (numbers masked):
{answer}

Is the reported problem still present in the new answer? Reply with JSON only:
{{"still_present": true or false, "reason": "<one short sentence>"}}"""


def _mask(text: str) -> str:
    return re.sub(r"(?<![\w-])\d[\d,.]*%?", "[n]", text or "")


def lesson_problems(text: str) -> list[str]:
    """Code checks on a draft lesson (FR-020): it must hold no number and no unapproved term."""
    text = (text or "").strip()
    out = []
    if not text:
        out.append("empty")
    if re.search(r"\d", text):
        out.append("holds a digit")
    if len(text) > 300:
        out.append("longer than three hundred characters")
    out += [why for rx, why in BANNED if rx.search(text)]
    return out


def decide(problems: list[str], checks_ok: bool | None, resolved: bool | None, gate_ok: bool | None) -> tuple[bool, list[str]]:
    """Confident only when every condition holds (FR-020); otherwise the reasons a reviewer needs."""
    reasons = list(problems)
    if checks_ok is None:
        reasons.append("the rerun did not run")
    elif not checks_ok:
        reasons.append("the rerun fails a gated check")
    if resolved is None:
        reasons.append("the reviewer could not judge the rerun")
    elif not resolved:
        reasons.append("the reviewer says the reported problem is still there")
    if gate_ok is None:
        reasons.append("the eval gate was not run with this lesson (needs --baseline and a clean rerun)")
    elif not gate_ok:
        reasons.append("the eval gate shows a regression")
    return not reasons, reasons


def proposal_id(kind: str, source: str, text: str = "") -> str:
    return "p-" + hashlib.sha256(f"{kind}|{source}|{text}".encode()).hexdigest()[:12]


def saved_threads(state_dir: Path) -> list[dict]:
    folder = state_dir / "threads"
    found = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.rglob("*.json"))] if folder.is_dir() else []
    return [t for t in found if t.get("saved") and t.get("turns")]


def gated_ok(envelope: dict) -> bool:
    from .scorers import claims_reconcile, governed_terms, links_resolve, no_individual_rep, numbers_traced

    values = [s(outputs=envelope).value for s in (claims_reconcile, numbers_traced, links_resolve)]
    values += [bool(s(outputs=envelope).value) for s in (governed_terms, no_individual_rep)]
    return all(v is True or v == 1.0 for v in values)


async def _ask(spec: str, prompt: str) -> str:
    from agent_framework import Agent

    from pharmagentics.llm import chat_client, chat_options
    return (await Agent(client=chat_client(spec), name="improve", default_options=chat_options(spec)).run(prompt)).text or ""


def draft_lesson(spec: str, vote: dict) -> str:
    shown = vote.get("shown") if isinstance(vote.get("shown"), str) else json.dumps(vote.get("shown"))
    prompt = LESSON_PROMPT.format(question=(vote.get("scope") or {}).get("question") or "", answer=_mask(shown)[:4000],
                                  comment=vote.get("comment") or "")
    return asyncio.run(_ask(spec, prompt)).strip().strip('"')


def review(spec: str, comment: str, answer: str) -> tuple[bool | None, str]:
    """The agent reviewer (Session 2026-11-20): does the rerun still show the reported problem? Advisory only."""
    raw = asyncio.run(_ask(spec, REVIEW_PROMPT.format(comment=comment, answer=_mask(answer)[:6000])))
    try:
        data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        return not bool(data["still_present"]), str(data.get("reason", ""))
    except (AttributeError, KeyError, ValueError):
        return None, f"unreadable reviewer reply: {raw[:120]}"


def rerun(question: str, lessons: list[str], spec: str) -> dict:
    """The flagged question answered again by the agent with the draft lesson(s) as trial lessons."""
    import sys
    for path in (REPO_ROOT / "src", REPO_ROOT / "agents" / "brand-briefing"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from briefing_agent import answer
    from briefing_agent.lessons import TRIAL
    before = os.environ.get(TRIAL)
    os.environ[TRIAL] = json.dumps(lessons)
    try:
        return answer(question, spec)
    finally:
        if before is None:
            os.environ.pop(TRIAL, None)
        else:
            os.environ[TRIAL] = before


def gate_with(lessons: list[str], baseline: str, spec: str) -> bool:
    """One golden-set run of the agent with every candidate lesson, gated against `baseline` (FR-019)."""
    from .run import gate, run_suite
    os.environ["PHARMAGENTICS_TRIAL_LESSONS"] = json.dumps(lessons)
    try:
        candidate = run_suite("briefing_agent", lane="briefing", model=spec)
    finally:
        os.environ.pop("PHARMAGENTICS_TRIAL_LESSONS", None)
    return gate(candidate, baseline) == 0


def run(state_dir: Path | None = None, baseline: str | None = None, model: str | None = None,
        backend=None, now: str | None = None) -> list[dict]:
    """Write new proposals; return them. `backend` is a state-store backend (defaults to the state folder read)."""
    from pharmagentics.api import store
    from pharmagentics.llm import model_spec

    if state_dir is None:
        state_dir = next((d for d in DEFAULT_STATE_DIRS if (d / VOTES).is_dir() or (d / "threads").is_dir()), None)
        if state_dir is None:
            return []
    backend = backend or store.LocalBackend(state_dir)
    seen = {json.loads(backend.read(k) or "{}").get("source") for k in backend.keys(PROPOSALS)}
    spec = model_spec(model or "anthropic:claude-haiku-5-5")
    votes = load_votes(state_dir)
    made: list[dict] = []
    stamp = now or store.now()

    lessons: list[dict] = []
    for v in votes:  # lessons from Briefing downvotes that say what was wrong
        source = f"vote:{v['lane']}/{v['ref']}/{v.get('ts')}"
        if v["lane"] != "briefing" or v["vote"] != "down" or not v.get("comment") or source in seen:
            continue
        text = draft_lesson(spec, v)
        problems = lesson_problems(text)
        question = (v.get("scope") or {}).get("question") or ""
        checks_ok = resolved = None
        why = ""
        after = ""
        if not problems and question:
            env = rerun(question, [text], spec)
            after = env.get("answer", "")
            checks_ok = gated_ok(env)
            resolved, why = review(spec, v["comment"], after)
        lessons.append({"id": proposal_id("lesson", source, text), "kind": "lesson", "source": source, "text": text,
                        "applies_to": "writer", "question": question, "comment": v["comment"],
                        "before": v.get("shown"), "after": after, "problems": problems, "checks_ok": checks_ok,
                        "resolved": resolved, "reviewer_reason": why})
    gate_ok = None
    testable = [x["text"] for x in lessons if not x["problems"] and x["checks_ok"] and x["resolved"]]
    if baseline and testable:
        gate_ok = gate_with(testable, baseline, spec)
    for x in lessons:
        confident, reasons = decide(x["problems"], x["checks_ok"], x["resolved"], gate_ok if x["text"] in testable else None)
        made.append({**x, "gate_ok": gate_ok, "confident": confident, "reasons": reasons})

    for (lane, ref), d in drafts([v for v in votes if v["vote"] == "up"]).items():  # regression cases from upvotes
        source = f"upvote:{lane}/{ref}"
        if source not in seen:
            made.append({"id": proposal_id("case", source), "kind": "case", "source": source, "confident": False,
                         "reasons": ["a vote is an opinion: write facts and a reference answer before it counts"],
                         "draft_case": d})
    for t in saved_threads(state_dir):  # two-turn cases from saved threads (brief-006 FR-009)
        source = f"thread:{t['brief_id']}/{t['owner']}"
        if source not in seen:
            first = t["turns"][0]
            made.append({"id": proposal_id("case", source), "kind": "case", "source": source, "confident": False,
                         "reasons": ["a saved thread is a candidate: write facts and a reference answer"],
                         "draft_case": {"lane": "briefing", "status": "candidate", "brief_id": t["brief_id"],
                                        "follow_up": {"question": first["question"], "section": first.get("section")},
                                        "shown": first["answer"]}})
    for p in made:
        p.update(status="proposed", created_at=stamp, decided_by=None, decided_at=None, note=None)
        backend.write(f"{PROPOSALS}{p['id']}.json", json.dumps(p, indent=1, default=str))
    return made

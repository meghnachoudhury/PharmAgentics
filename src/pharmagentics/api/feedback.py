"""UAT feedback (core-008): a quick "how is this session going" pulse, and the platform questionnaire.

Both are stored as small JSON documents next to the other UAT state (the local folder or the Cloud Storage
bucket), keyed by a pseudonymous participant ID: never a name or an email (core-007 FR-025). The questions live
in questionnaire.json, so the team or the mentor can change them without code. Results are read by an owner
through deploy/feedback_report.py (or `gcp.py feedback`), not through the web app: no role can read other people's
answers in the browser.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from collections import Counter
from functools import lru_cache
from pathlib import Path
from statistics import mean, median
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import brand_access, forecast_store, rbac, store, views

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/feedback", tags=["feedback"])

QUESTIONNAIRE_FILE = Path(__file__).with_name("questionnaire.json")
RATINGS = ("good", "fine", "bad")
ITEM_TYPES = {"agree5", "nps", "choice", "multi", "text"}
PULSE_PREFIX, SURVEY_PREFIX, RESPONSE_PREFIX = "feedback/pulse/", "feedback/survey/", "feedback/response/"
COMMENT_PREFIX = "feedback/comment/"  # free-text suggestions for the platform (core-008 FR-018)


# --- the questionnaire file -----------------------------------------------------------------------

def items(q: dict) -> list[dict]:
    return [item for section in q["sections"] for item in section["items"]]


def check_questionnaire(q: dict) -> None:
    """A malformed edit must fail loudly (and in CI), not at a participant's expense."""
    ids = [i["id"] for i in items(q)]
    if len(ids) != len(set(ids)):
        raise ValueError("questionnaire.json: question ids must be unique")
    if not isinstance(q.get("version"), int) or q["version"] < 1:
        raise ValueError("questionnaire.json: version must be a positive integer")
    for i in items(q):
        if i["type"] not in ITEM_TYPES:
            raise ValueError(f"questionnaire.json: {i['id']} has unknown type {i['type']!r}")
        if i["type"] in ("choice", "multi") and not i.get("options"):
            raise ValueError(f"questionnaire.json: {i['id']} needs options")
    by_id = {i["id"]: i for i in items(q)}
    for sid in q.get("scoring", {}).get("sus", []):
        if by_id.get(sid, {}).get("type") != "agree5":
            raise ValueError(f"questionnaire.json: SUS item {sid} must exist and be agree5")


@lru_cache(maxsize=1)
def questionnaire() -> dict:
    q = json.loads(QUESTIONNAIRE_FILE.read_text(encoding="utf-8"))
    check_questionnaire(q)
    return q


def _int(value: Any, low: int, high: int, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise HTTPException(status_code=422, detail=f"{key}: answer with a whole number from {low} to {high}.")
    return value


def validate_answers(q: dict, answers: dict[str, Any]) -> dict[str, Any]:
    """The answers a participant may store: known questions, the right kind of value, blanks dropped."""
    by_id = {i["id"]: i for i in items(q)}
    clean: dict[str, Any] = {}
    for key, value in answers.items():
        item = by_id.get(key)
        if item is None:
            raise HTTPException(status_code=422, detail=f"Unknown question: {key}")
        kind = item["type"]
        if kind == "agree5":
            clean[key] = _int(value, 1, 5, key)
        elif kind == "nps":
            clean[key] = _int(value, 0, 10, key)
        elif kind in ("choice", "multi"):
            allowed = {o["value"] for o in item["options"]}
            picked = value if kind == "multi" else [value]
            if not isinstance(picked, list) or any(not isinstance(v, str) or v not in allowed for v in picked):
                raise HTTPException(status_code=422, detail=f"{key}: choose from the listed options.")
            picked = list(dict.fromkeys(picked))
            if picked:
                clean[key] = picked if kind == "multi" else picked[0]
        else:  # text
            if not isinstance(value, str):
                raise HTTPException(status_code=422, detail=f"{key}: write text.")
            text = value.strip()
            if len(text) > item.get("max", 1000):
                raise HTTPException(status_code=422, detail=f"{key}: at most {item.get('max', 1000)} characters.")
            if text:
                clean[key] = text
    if not clean:
        raise HTTPException(status_code=422, detail="Answer at least one question.")
    return clean


def sus_score(q: dict, answers: dict[str, Any]) -> float | None:
    """System Usability Scale, 0 to 100, by code. Odd statements are worded positively (score - 1), even ones
    negatively (5 - score); the sum is multiplied by 2.5. None unless all ten statements were answered."""
    ids = q.get("scoring", {}).get("sus") or []
    if len(ids) != 10 or any(i not in answers for i in ids):
        return None
    return sum((answers[i] - 1) if n % 2 == 0 else (5 - answers[i]) for n, i in enumerate(ids)) * 2.5


# --- requests -------------------------------------------------------------------------------------

class CommentIn(BaseModel):
    """A suggestion about the platform, from anywhere in the app."""
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1000)
    topic: Literal["briefing", "forecast", "agent", "design", "other"] = "other"

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Write a suggestion first.")
        return value.strip()


class PulseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: Literal["good", "fine", "bad"]
    comment: str | None = Field(default=None, max_length=300)
    where: Literal["briefing", "forecast", "approved", "other"] = "other"
    ref: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._:-]{1,64}$")  # a brief or run ID, if the UI knows it

    @field_validator("comment")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value else None


class SurveyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    answers: dict[str, Any] = Field(max_length=60)


ANSWER_ID = r"^(b|f)-[0-9a-f]{12}(:t\d{1,2})?$"  # a brief, a Forecast run, or a follow-up turn "b-…:t3" (brief-006)


class VoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lane: Literal["briefing", "forecast"]
    ref: str = Field(pattern=ANSWER_ID)
    view: Literal["analyst", "leadership"]
    vote: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("comment")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value else None


# --- who, and the documents -----------------------------------------------------------------------

def participant(request: Request) -> tuple[rbac.Principal, list[rbac.Role]]:
    """Signed in and holding at least one role. A dependency, so access is refused (401, 403) before FastAPI
    validates a request body: a signed-out caller never learns what a valid body looks like."""
    p = rbac.require_user(request)
    roles = p.lanes
    if not roles:
        raise HTTPException(status_code=403, detail="Your account has no PharmAgentics role.")
    return p, roles


def _sid(request: Request) -> str:
    """One sign-in is one session (the session cookie is cleared at every sign-in)."""
    sid = request.session.get("sid")
    if not sid:
        sid = secrets.token_hex(6)
        request.session["sid"] = sid
    return sid


def _who(p: rbac.Principal, roles: list[rbac.Role]) -> dict:
    return {"user": rbac.pseudonym(p.sub), "roles": [r.name for r in roles], "personas": [r.persona for r in roles], **p.tag()}


def _survey_key(user: str) -> str:
    return f"{SURVEY_PREFIX}{user}.json"


def _read_survey(user: str) -> dict | None:
    text = store.backend().read(_survey_key(user))
    return json.loads(text) if text else None


def _write(key: str, doc: dict) -> None:
    try:
        store.backend().write(key, json.dumps(doc, indent=1))
    except Exception as exc:  # noqa: BLE001 - feedback is something the participant is waiting on: say so, never drop it
        logger.exception("Feedback not saved")
        raise HTTPException(status_code=503, detail="Could not save your feedback. Please try again.") from exc


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


# --- routes ---------------------------------------------------------------------------------------

@router.get("/status")
def status(request: Request, response: Response, who=Depends(participant)) -> dict:
    """What this participant has already given: this session's rating, and whether the questionnaire is done."""
    _no_store(response)
    p, _ = who
    mine = _read_survey(rbac.pseudonym(p.sub))
    return {"pulse": request.session.get("pulse"),
            "survey": {"submitted_at": mine["ts"] if mine else None, "version": mine["version"] if mine else None},
            "questionnaire_version": questionnaire()["version"]}


@router.post("/comment")
def comment(body: CommentIn, response: Response, who=Depends(participant)) -> dict:
    """A free-text suggestion for the platform. Every one is kept; nobody else can read it in the app."""
    _no_store(response)
    p, roles = who
    ts = store.now()
    doc = {"kind": "comment", "id": secrets.token_hex(4), "ts": ts, **_who(p, roles), "topic": body.topic,
           "text": body.text, "app_version": os.environ.get("PHARMAGENTICS_VERSION", "dev")}
    _write(f"{COMMENT_PREFIX}{ts[:10]}/{ts.replace(':', '')}-{doc['id']}.json", doc)
    return {"saved_at": ts}


@router.post("/pulse")
def pulse(body: PulseIn, request: Request, response: Response, who=Depends(participant)) -> dict:
    """A one-click rating of this session. The last rating of a session is the one that counts."""
    _no_store(response)
    p, roles = who
    ts = store.now()
    doc = {"kind": "pulse", "id": secrets.token_hex(4), "ts": ts, "session": _sid(request), **_who(p, roles),
           "rating": body.rating, "comment": body.comment, "where": body.where, "ref": body.ref,
           "app_version": os.environ.get("PHARMAGENTICS_VERSION", "dev")}
    _write(f"{PULSE_PREFIX}{ts[:10]}/{ts.replace(':', '')}-{doc['id']}.json", doc)
    request.session["pulse"] = {"rating": body.rating, "at": ts}
    return request.session["pulse"]


@router.get("/questionnaire")
def get_questionnaire(response: Response, who=Depends(participant)) -> dict:
    _no_store(response)
    return {k: v for k, v in questionnaire().items() if not k.startswith("_")}


@router.get("/survey")
def my_survey(response: Response, who=Depends(participant)) -> dict:
    """The participant's own earlier answers, so they can update them. Nobody else's."""
    _no_store(response)
    p, _ = who
    mine = _read_survey(rbac.pseudonym(p.sub))
    return {"version": mine["version"], "answers": mine["answers"], "submitted_at": mine["ts"]} if mine else \
           {"version": None, "answers": {}, "submitted_at": None}


@router.post("/survey")
def submit_survey(body: SurveyIn, response: Response, who=Depends(participant)) -> dict:
    """Store the questionnaire. One document per participant: sending again replaces the earlier answers."""
    _no_store(response)
    p, roles = who
    q = questionnaire()
    if body.version != q["version"]:
        raise HTTPException(status_code=409, detail="The questionnaire changed while you were answering. Reload it.")
    answers = validate_answers(q, body.answers)
    user = rbac.pseudonym(p.sub)
    before = _read_survey(user)
    doc = {"kind": "survey", "ts": store.now(), "version": q["version"], **_who(p, roles), "answers": answers,
           "sus": sus_score(q, answers), "updates": (before["updates"] + 1) if before else 0}
    _write(_survey_key(user), doc)
    return {"submitted_at": doc["ts"], "answered": len(answers)}


# --- votes on one answer (User Story 5) -----------------------------------------------------------

def _answer(p: rbac.Principal, lane: str, ref: str, view: str) -> dict:
    """What the participant was shown, if they may open this answer in this view; otherwise 404 (or 403 for a
    view their role does not hold), exactly as opening it would answer, so a vote never reveals that it exists."""
    role = p.role(lane)
    if role is None:
        raise HTTPException(status_code=403, detail="Your account has no access to this workspace.")
    rbac.view_for(role, view)
    if lane == "briefing" and ":t" in ref:  # a follow-up turn in the voter's own thread (brief-006 FR-012)
        from . import threads

        bid, n = ref.split(":t")
        record = brand_access.brief_for(p, role, bid)
        shown = threads.turn_shown(p, bid, int(n)) if record and "review" in role.actions else None
        if shown is None:
            raise HTTPException(status_code=404, detail="No such follow-up.")
        r = record["result"]
        return {"scope": {k: r.get(k) for k in ("brand_id", "territory_id", "week_start", "question")},
                "engine": "scripted", "system": r.get("system"), "data_version": r.get("data_version"),
                "review_status": record["review_status"], "shown": shown}
    if lane == "briefing":
        record = brand_access.brief_for(p, role, ref)
        r = record["result"]
        shown = r.get("answer") or ""
        return {"scope": {k: r.get(k) for k in ("brand_id", "territory_id", "week_start", "question")},
                "engine": r.get("engine"), "system": r.get("system"), "data_version": r.get("data_version"),
                "review_status": record["review_status"],
                "shown": views.executive_summary(shown) if view == "leadership" else shown}
    brand_access.require_brand(p, "BXA")
    record = forecast_store.get(ref)
    if record is None or ("run" not in role.actions and record["review_status"] == forecast_store.NOT_SUBMITTED):
        raise HTTPException(status_code=404, detail="No such Forecast run.")
    report, narrative = record["result"]["report"], record.get("narrative") or {}
    if view == "leadership":
        narrative = {k: v for k, v in narrative.items() if k != "analyst_notes"}
    return {"scope": {k: record["request"].get(k) for k in ("territory_id", "week_start", "window_weeks")},
            "engine": report.get("investigator_mode"), "system": record.get("report_model"),
            "data_version": record["result"].get("dataset_release"), "review_status": record["review_status"],
            "shown": {"headline": report.get("headline"), "narrative": narrative or None}}


def _vote_key(lane: str, ref: str, user: str, view: str) -> str:
    return f"{RESPONSE_PREFIX}{lane}/{ref.replace(':', '/')}/{user}-{view}.json"  # a turn "b-…:t3" nests under its brief


@router.get("/vote")
def my_vote(response: Response, lane: Literal["briefing", "forecast"], ref: str = Query(pattern=ANSWER_ID),
            view: Literal["analyst", "leadership"] = "analyst", who=Depends(participant)) -> dict:
    """The participant's own vote on one answer, so the page can show it again. Nobody else's."""
    _no_store(response)
    p, _ = who
    _answer(p, lane, ref, view)
    text = store.backend().read(_vote_key(lane, ref, rbac.pseudonym(p.sub), view))
    doc = json.loads(text) if text else None
    return {"vote": doc["vote"], "comment": doc["comment"], "at": doc["ts"]} if doc else {"vote": None, "comment": None, "at": None}


@router.post("/vote")
def vote(body: VoteIn, response: Response, who=Depends(participant)) -> dict:
    """Thumbs up or down on one answer, with an optional comment. One per participant, answer and view."""
    _no_store(response)
    p, roles = who
    answer = _answer(p, body.lane, body.ref, body.view)
    user = rbac.pseudonym(p.sub)
    key = _vote_key(body.lane, body.ref, user, body.view)
    before = store.backend().read(key)
    doc = {"kind": "vote", "ts": store.now(), **_who(p, roles), "lane": body.lane, "ref": body.ref, "view": body.view,
           "vote": body.vote, "comment": body.comment, **answer,
           "updates": (json.loads(before)["updates"] + 1) if before else 0,
           "app_version": os.environ.get("PHARMAGENTICS_VERSION", "dev")}
    _write(key, doc)
    return {"vote": doc["vote"], "comment": doc["comment"], "at": doc["ts"]}


# --- reading the results (owners, through deploy/feedback_report.py) -----------------------------

def load_feedback(backend) -> tuple[list[dict], list[dict]]:
    """Every pulse and survey document in a state backend."""
    def docs(prefix: str) -> list[dict]:
        return [json.loads(t) for k in backend.keys(prefix) if (t := backend.read(k))]
    return docs(PULSE_PREFIX), docs(SURVEY_PREFIX)


PERSONA_ORDER = ("P1", "P3", "CA", "BM")  # the Briefing pair, then the Forecast pair


def _role_key(doc: dict) -> str:
    return "/".join(sorted(doc.get("personas") or ["?"], key=lambda x: (PERSONA_ORDER.index(x) if x in PERSONA_ORDER else 99, x)))


def _role_order(key: str) -> tuple[int, int, str]:
    """Single personas first in the natural order (P1, P3, CA, BM), then logins that hold two."""
    parts = key.split("/")
    return (len(parts), min((PERSONA_ORDER.index(x) if x in PERSONA_ORDER else 99) for x in parts), key)


def load_comments(backend) -> list[dict]:
    """Every platform suggestion in a state backend, oldest first."""
    return sorted((json.loads(t) for k in backend.keys(COMMENT_PREFIX) if (t := backend.read(k))), key=lambda d: d["ts"])


def load_votes(backend) -> list[dict]:
    """Every per-answer vote in a state backend (one document per participant, answer and view)."""
    return [json.loads(t) for k in backend.keys(RESPONSE_PREFIX) if (t := backend.read(k))]


def summarize_votes(votes: list[dict]) -> dict:
    """Up and down counts by lane, engine and view, and every downvote with its comment. Pure: no I/O."""
    by: dict[str, dict[str, int]] = {}
    for v in votes:
        by.setdefault(f"{v['lane']} · {v.get('engine') or '?'} · {v['view']}", {"up": 0, "down": 0})[v["vote"]] += 1
    down = [{"ts": v["ts"][:16], "lane": v["lane"], "ref": v["ref"], "view": v["view"], "role": _role_key(v),
             "comment": v.get("comment")} for v in sorted(votes, key=lambda d: d["ts"]) if v["vote"] == "down"]
    return {"votes": len(votes), "answers": len({(v["lane"], v["ref"]) for v in votes}),
            "up": sum(v["vote"] == "up" for v in votes), "down": len(down), "by": dict(sorted(by.items())), "downvotes": down}


def summarize(pulses: list[dict], surveys: list[dict], q: dict, votes: list[dict] | None = None) -> dict:
    """Counts, means and the written answers, from the stored documents. Pure: no I/O."""
    latest: dict[str, dict] = {}
    for doc in sorted(pulses, key=lambda d: d["ts"]):  # the last rating of each session counts
        latest[doc["session"]] = doc
    sessions = list(latest.values())
    by_rating = {r: sum(1 for s in sessions if s["rating"] == r) for r in RATINGS}
    by_role: dict[str, dict[str, int]] = {}
    for s in sessions:
        by_role.setdefault(_role_key(s), dict.fromkeys(RATINGS, 0))[s["rating"]] += 1
    out: dict[str, Any] = {
        "pulse": {"submissions": len(pulses), "sessions": len(sessions), "by_rating": by_rating, "by_role": by_role,
                  "comments": [{"ts": s["ts"][:16], "rating": s["rating"], "role": _role_key(s), "where": s["where"],
                                "comment": s["comment"]} for s in sessions if s.get("comment")]}}

    by_id = {i["id"]: i for i in items(q)}
    sus = [s["sus"] for s in surveys if s.get("sus") is not None]
    survey: dict[str, Any] = {"responses": len(surveys), "versions": dict(Counter(s["version"] for s in surveys)),
                              "sus": ({"n": len(sus), "mean": round(mean(sus), 1), "median": median(sus),
                                       "min": min(sus), "max": max(sus)} if sus else None)}
    rows: list[dict] = []
    for item_id, item in by_id.items():
        given = [(s, s["answers"][item_id]) for s in surveys if item_id in s["answers"]]
        if not given:
            continue
        row: dict[str, Any] = {"id": item_id, "text": item["text"], "type": item["type"], "n": len(given)}
        values = [v for _, v in given]
        if item["type"] == "agree5":
            row.update(mean=round(mean(values), 2), counts={str(k): values.count(k) for k in range(1, 6)},
                       reverse=bool(item.get("reverse")))
        elif item["type"] == "nps":
            promoters, detractors = sum(v >= 9 for v in values), sum(v <= 6 for v in values)
            row.update(mean=round(mean(values), 1), promoters=promoters, detractors=detractors,
                       passives=len(values) - promoters - detractors,
                       nps=round(100 * (promoters - detractors) / len(values)))
        elif item["type"] in ("choice", "multi"):
            labels = {o["value"]: o["label"] for o in item["options"]}
            flat = [v for vs in values for v in (vs if isinstance(vs, list) else [vs])]
            row["counts"] = {labels[o["value"]]: flat.count(o["value"]) for o in item["options"]}
        else:
            row["answers"] = [{"role": _role_key(s), "text": v} for s, v in given]
        rows.append(row)
    survey["items"] = rows
    out["survey"] = survey
    if votes is not None:
        out["answers"] = summarize_votes(votes)
    return out


def to_markdown(summary: dict, q: dict) -> str:
    """The summary as a short report for the team and the mentor."""
    pulse, survey = summary["pulse"], summary["survey"]
    lines = ["# PharmAgentics UAT feedback", "",
             "## Session pulse: good, fine or bad", ""]
    if not pulse["sessions"]:
        lines.append("No session ratings yet.")
    else:
        r = pulse["by_rating"]
        lines += [f"{pulse['sessions']} sessions rated ({pulse['submissions']} ratings in all; the last rating of each session counts).", "",
                  "| Rating | Sessions |", "| :- | -: |", *(f"| {k.capitalize()} | {r[k]} |" for k in RATINGS), ""]
        lines += ["| Persona | Good | Fine | Bad |", "| :- | -: | -: | -: |",
                  *(f"| {role} | {c['good']} | {c['fine']} | {c['bad']} |" for role, c in sorted(pulse["by_role"].items(), key=lambda kv: _role_order(kv[0]))), ""]
        if pulse["comments"]:
            lines += ["Comments:", "", *(f"- {c['ts']} · {c['role']} · {c['rating']} · {c['where']}: {c['comment']}" for c in pulse["comments"]), ""]
    if summary.get("comments") is not None:
        c = summary["comments"]
        lines += ["## Suggestions for the platform", ""]
        lines += ([f"- {d['ts'][:16]} · {_role_key(d)} · {d['topic']}: {d['text']}" for d in c] or ["No suggestions yet."]) + [""]
    if "answers" in summary:
        a = summary["answers"]
        lines += ["## Votes on answers: thumbs up or down", ""]
        if not a["votes"]:
            lines += ["No votes on answers yet.", ""]
        else:
            lines += [f"{a['votes']} votes on {a['answers']} answers: {a['up']} up, {a['down']} down. "
                      "`python -m eval candidates` turns them into draft golden-set cases.", "",
                      "| Lane · engine · view | Up | Down |", "| :- | -: | -: |",
                      *(f"| {k} | {c['up']} | {c['down']} |" for k, c in a["by"].items()), ""]
            if a["downvotes"]:
                lines += ["Downvotes:", "", *(f"- {d['ts']} · {d['role']} · {d['lane']} {d['ref']} ({d['view']}): "
                                              f"{d['comment'] or '(no comment)'}" for d in a["downvotes"]), ""]
    lines += [f"## {q['title']}", ""]
    if not survey["responses"]:
        lines.append("No questionnaire responses yet.")
        return "\n".join(lines) + "\n"
    lines.append(f"{survey['responses']} responses (questionnaire versions: "
                 + ", ".join(f"v{k}: {v}" for k, v in sorted(survey["versions"].items())) + ").")
    lines.append("")
    if survey["sus"]:
        s = survey["sus"]
        lines += [f"**System Usability Scale:** mean {s['mean']} (median {s['median']}, range {s['min']} to {s['max']}, "
                  f"{s['n']} complete). 68 is the commonly cited average across products; above 80 is usually read as excellent.", ""]
    else:
        lines += ["System Usability Scale: no respondent answered all ten statements.", ""]
    for section in q["sections"]:
        rows = [r for r in survey["items"] if r["id"] in {i["id"] for i in section["items"]}]
        if not rows:
            continue
        lines += [f"### {section['title']}", ""]
        for r in rows:
            if r["type"] == "agree5":
                note = " (negatively worded: lower is better)" if r["reverse"] else ""
                lines.append(f"- {r['text']} Mean {r['mean']} of 5, n={r['n']}{note}.")
            elif r["type"] == "nps":
                lines.append(f"- {r['text']} Mean {r['mean']} of 10; promoters {r['promoters']}, passives {r['passives']}, "
                             f"detractors {r['detractors']}; net promoter score {r['nps']}.")
            elif r["type"] in ("choice", "multi"):
                lines.append(f"- {r['text']} " + "; ".join(f"{k}: {v}" for k, v in r["counts"].items()) + ".")
            else:
                lines += [f"- {r['text']}", *(f"  - ({a['role']}) {a['text']}" for a in r["answers"])]
        lines.append("")
    return "\n".join(lines)

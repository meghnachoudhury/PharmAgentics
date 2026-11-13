"""The report writer: plain-language prose for a verified Forecast report.

It runs after stage 6, on a report that has already been verified. The investigator stays scripted; the writer
never chooses tools and never computes a number. It may say what to check next, who owns it, and how to put the
miss, the residual and the confidence into words (BM-Q5, BM-Q6). It may not add a TRx figure, a driver, or a
commercial action (price, targeting, budget, a change to the forecast).

Order: GPT Terra (the key and the call are on the server), then a local Qwen model through Ollama, then nothing:
if both fail, or the prose breaks a rule, the run keeps the scripted report and ``writer_status`` is
``fallback_stub``. A run is never failed by the writer, and the numbers of the scripted report are never touched.

Every piece of prose is checked in code before it is kept: it must be the expected JSON, every number in it must be
one the verified report already holds, it may only name drivers the report names, only assign owners the report
names, and recommend no commercial action. The caller cannot choose the model.
"""
from __future__ import annotations

import json
import os
import re
import socket
import urllib.error
import urllib.request
from typing import Any, Callable

TERRA_DEFAULT_MODEL = "gpt-6.1-terra"  # until the id is confirmed on the account
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
LOCAL_DEFAULT_MODEL = "qwen2.5:7b"
OLLAMA_DEFAULT_HOST = "http://localhost:11434"

MAX_TEXT = 700
MAX_CHECKS = 5
ALWAYS_ALLOWED_OWNERS = ("Commercial Analyst", "Brand Manager")


def settings() -> dict[str, Any]:
    """Read at call time. The key is only ever sent in an Authorization header and never logged."""
    return {
        "mode": "off" if os.environ.get("FEAGENT_WRITER", "on").strip().lower() == "off" else "on",
        "terra_key": os.environ.get("OPENAI_API_KEY", "").strip(),
        "terra_model": os.environ.get("OPENAI_MODEL", "").strip() or TERRA_DEFAULT_MODEL,
        "terra_base": (os.environ.get("OPENAI_BASE_URL", "").strip() or OPENAI_DEFAULT_BASE_URL).rstrip("/"),
        "terra_timeout": float(os.environ.get("FEAGENT_WRITER_TERRA_TIMEOUT_SEC", "25")),
        "local_model": os.environ.get("OLLAMA_WRITER_MODEL", "").strip() or LOCAL_DEFAULT_MODEL,
        "local_host": (os.environ.get("OLLAMA_HOST", "").strip() or OLLAMA_DEFAULT_HOST).rstrip("/"),
        "local_timeout": float(os.environ.get("FEAGENT_WRITER_LOCAL_TIMEOUT_SEC", "45")),
    }


def describe() -> dict[str, Any]:
    """What the writer would use, for the status route. Says whether a key is set, never the key."""
    cfg = settings()
    return {"enabled": cfg["mode"] == "on", "primary": cfg["terra_model"] if cfg["terra_key"] else None,
            "fallback": cfg["local_model"]}


def needs_model(report: dict[str, Any]) -> bool:
    """False when the writer would answer at once without a model: switched off, or the attribution is paused."""
    return settings()["mode"] == "on" and not report.get("abstained")


class WriterError(Exception):
    """A model call that did not give usable text. ``code`` is short and safe to store."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# --- what the writer is given ------------------------------------------------------------------------------

def build_facts(report: dict[str, Any]) -> dict[str, Any]:
    """The verified numbers and texts the writer may use. No evidence ids, tool output or internal week numbers."""
    variance = float(report["variance_trx"])

    def share(x: float) -> int | None:
        return round(abs(float(x)) / abs(variance) * 100) if variance else None

    verification = report.get("verification") or {}
    return {
        "brand": report.get("brand"),
        "territory": report.get("territory_id"),
        "week_ending": report.get("week_ending"),
        "window_weeks": report.get("window_weeks"),
        "forecast_trx": round(float(report["forecast_trx"])),
        "actual_trx": round(float(report["actual_trx"])),
        "variance_trx": round(variance),
        # the engine keeps the miss as a fraction (-0.2015); the writer gets it as the percent it is written as
        "variance_pct_of_forecast": round(float(report["variance_pct"]) * 100, 1) if report.get("variance_pct") is not None else None,
        "headline": report.get("headline"),
        "residual_trx": round(float(report["residual_trx"]), 1),
        "residual_share_of_miss_pct": share(report["residual_trx"]),
        "drivers": [
            {"name": d["driver"], "impact_trx": round(float(d["impact_trx"]), 1),
             "share_of_miss_pct": share(d["impact_trx"]), "confidence": d["confidence"],
             "confidence_reasons": d.get("confidence_reasons", [])}
            for d in report.get("drivers", [])
        ],
        "caveats": report.get("caveats", []),
        "what_to_check": [{"question": c["question"], "why": c["why"], "owner": c["owner"]}
                          for c in report.get("what_to_check", [])],
        "verification": {
            "verdict": verification.get("verdict"),
            "warnings": [c["detail"] for c in verification.get("checks", []) if c.get("status") == "warn"],
        },
    }


SYSTEM_PROMPT = """You write a short plain-language explanation of a pharmaceutical brand's forecast miss for a
commercial team. You are given verified facts as JSON. You do not analyse, estimate or decide anything.

Rules:
- Use ONLY the numbers in the facts, copied exactly as written. Do not round, add, subtract, convert or compute any
  number. Do not invent a figure, a percentage or a date. If you are unsure of a number, leave it out.
- Name only the drivers listed in the facts. Do not suggest another cause as if it were found.
- Say plainly that the estimates are associations measured against comparison regions, not proof of cause.
- State the residual and the confidence as given. Do not make a weak result sound certain.
- Do NOT recommend any commercial action: no price, discount, targeting, budget, spend or reallocation, and do not
  say the forecast should be raised, lowered or changed.
- "Next checks" are investigations or verifications only (what to look at, why, and which owner). Each owner must be
  one of the owners given in the facts, or "Commercial Analyst" or "Brand Manager".
- Do not mention tools, queries, ids or how the numbers were computed.

Reply with ONLY a JSON object with these keys:
"summary" (two or three sentences for a leader), "miss" (the miss in words), "residual" (what remains unexplained),
"confidence" (how sure we are and why), "next_checks" (a list of up to 5 objects with "check", "why", "owner"),
"analyst_notes" (optional, two sentences for the analyst on caveats and data quality).
Keep every text under 600 characters."""


def build_messages(facts: dict[str, Any]) -> list[dict[str, str]]:
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Facts:\n" + json.dumps(facts, indent=1, ensure_ascii=False)}]


# --- the model calls ---------------------------------------------------------------------------------------

def _post(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise WriterError(f"http_{exc.code}") from None
    except (socket.timeout, TimeoutError):
        raise WriterError("timeout") from None
    except urllib.error.URLError as exc:
        raise WriterError("timeout" if isinstance(exc.reason, (socket.timeout, TimeoutError)) else "unreachable") from None
    except (ValueError, OSError):
        raise WriterError("bad_response") from None


def call_terra(messages: list[dict[str, str]], cfg: dict[str, Any]) -> str:
    """Chat Completions. The key goes in the Authorization header only."""
    if not cfg["terra_key"]:
        raise WriterError("no_key")
    payload: dict[str, Any] = {"model": cfg["terra_model"], "messages": messages,
                               "response_format": {"type": "json_object"}}
    headers = {"Authorization": f"Bearer {cfg['terra_key']}"}
    url = cfg["terra_base"] + "/chat/completions"
    try:
        data = _post(url, payload, headers, cfg["terra_timeout"])
    except WriterError as exc:
        if exc.code != "http_400":
            raise
        payload.pop("response_format")  # a model that does not take a JSON mode: ask in the prompt only
        data = _post(url, payload, headers, cfg["terra_timeout"])
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise WriterError("bad_response") from None


def call_ollama(messages: list[dict[str, str]], cfg: dict[str, Any]) -> str:
    payload = {"model": cfg["local_model"], "messages": messages, "stream": False, "format": "json",
               "options": {"temperature": 0}}
    data = _post(cfg["local_host"] + "/api/chat", payload, {}, cfg["local_timeout"])
    try:
        return data["message"]["content"] or ""
    except (KeyError, TypeError):
        raise WriterError("bad_response") from None


# --- the checks on the prose -------------------------------------------------------------------------------

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NUMBER = re.compile(r"(?<![\w.])[-−–]?\d[\d,]*(?:\.\d+)?")
_ROUNDING = 0.5  # a TRx amount or a percent of ten or more may be written to the nearest whole number
_SMALL = 0.051  # below ten the figure must be as given (to one decimal)
_SCALED = re.compile(r"\d\s?(?:k|m|thousand|million|billion)\b", re.I)

# A recommended commercial action. A verb of change near a commercial lever is only an action when it is framed as
# advice ("should lower the forecast", "recommend raising the budget") or is an instruction opening a sentence;
# describing the data ("the baseline-change cross-check differs from the forecast") is not.
_LEVER = r"(?:forecast|price|pricing|budget|spend|spending|target|targeting|quota|discount)"
_VERB = r"(?:lower|raise|increase|decrease|cut|adjust|change|revise|reduce|boost|shift|move)(?:ing|s|d|ed)?"
_ACTIONS = (
    re.compile(rf"\b(?:should|recommend(?:s|ed)?|consider(?:ing)?|suggest(?:s|ed)?|advis(?:e|es|ed)|propos(?:e|es|ed)|"
               rf"need(?:s)? to|must|ought to)\b[^.;]{{0,40}}\b{_VERB}\b[^.;]{{0,40}}\b{_LEVER}\b", re.I),
    re.compile(rf"(?:^|[.;:]\s+){_VERB}\b(?!\s+in\b)[^.;]{{0,40}}\b{_LEVER}\b", re.I),
    re.compile(r"\b(?:recommend\w*|consider\w*|suggest\w*|propos\w*)\b[^.;]{0,40}"
               r"\b(?:discount|price|pricing|budget|targeting|quota)\b", re.I),
    re.compile(r"\b(?:reallocat\w*|rebalanc\w*|re-?target\w*|discounting|price (?:cut|increase|change|reduction))\b", re.I),
)
_CATEGORIES = {
    "payer_access": re.compile(r"\b(payer|formulary|access|tier|prior authori[sz]ation)\b", re.I),
    "promotion": re.compile(r"\bpromo(?:tion|tional|tions)?\b", re.I),
    "competitor_activity": re.compile(r"\b(competitor|competitors|competitive|rival)\b", re.I),
    "supply": re.compile(r"\b(supply|stock-?out|inventory)\b", re.I),
}


def _tolerance(allowed: float) -> float:
    return _ROUNDING if abs(allowed) >= 10 else _SMALL


def _numbers(text: str) -> list[float]:
    out = []
    for token in _NUMBER.findall(_DATE.sub(" ", text)):
        try:
            out.append(float(token.replace(",", "").replace("−", "-").replace("–", "-")))
        except ValueError:
            continue
    return out


def _strings(node: Any):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def _all_numbers(node: Any) -> list[float]:
    if isinstance(node, bool):
        return []
    if isinstance(node, (int, float)):
        return [float(node)]
    if isinstance(node, str):
        return _numbers(node)
    if isinstance(node, dict):
        return [n for v in node.values() for n in _all_numbers(v)]
    if isinstance(node, list):
        return [n for v in node for n in _all_numbers(v)]
    return []


def _text(value: Any, limit: int = MAX_TEXT) -> str | None:
    return value.strip() if isinstance(value, str) and 0 < len(value.strip()) <= limit else None


def check_prose(raw: str, facts: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Parse and check the model's text. Returns (prose, None) or (None, reason code)."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return None, "bad_json"
    try:
        prose = json.loads(raw[start:end + 1])
    except ValueError:
        return None, "bad_json"
    if not isinstance(prose, dict):
        return None, "bad_json"

    clean: dict[str, Any] = {}
    for key in ("summary", "miss", "residual", "confidence"):
        text = _text(prose.get(key))
        if text is None:
            return None, "bad_shape"
        clean[key] = text
    checks = prose.get("next_checks")
    if not isinstance(checks, list) or not 1 <= len(checks) <= MAX_CHECKS:
        return None, "bad_shape"
    clean["next_checks"] = []
    for item in checks:
        if not isinstance(item, dict):
            return None, "bad_shape"
        entry = {k: _text(item.get(k), 400) for k in ("check", "why", "owner")}
        if not all(entry.values()):
            return None, "bad_shape"
        clean["next_checks"].append(entry)
    if prose.get("analyst_notes") not in (None, ""):
        notes = _text(prose["analyst_notes"])
        if notes is None:
            return None, "bad_shape"
        clean["analyst_notes"] = notes

    everything = list(_strings(clean))
    if any(_SCALED.search(text) for text in everything):  # "1.2k", "3 million": a rounded figure the report does not hold
        return None, "invented_number"
    allowed_numbers = _all_numbers(facts)
    for text in everything:
        for value in _numbers(text):
            if not any(abs(abs(value) - abs(a)) <= _tolerance(a) for a in allowed_numbers):
                return None, "invented_number"
    if any(pattern.search(text) for text in everything for pattern in _ACTIONS):
        return None, "commercial_action"
    known = " ".join(_strings(facts)).replace("_", " ").lower()
    for name, pattern in _CATEGORIES.items():
        if not pattern.search(known) and any(pattern.search(text) for text in everything):
            return None, "new_driver"
    owners = {o.lower() for o in ALWAYS_ALLOWED_OWNERS} | {c["owner"].lower() for c in facts["what_to_check"]}
    if any(item["owner"].lower() not in owners for item in clean["next_checks"]):
        return None, "unknown_owner"
    return clean, None


# --- the whole thing ---------------------------------------------------------------------------------------

def _result(narrative: dict | None, model: str, status: str, attempts: list[dict[str, str]]) -> dict[str, Any]:
    return {"narrative": narrative, "report_model": model, "writer_status": status, "writer_attempts": attempts}


def write_report(report: dict[str, Any], *, terra: Callable = call_terra, local: Callable = call_ollama) -> dict[str, Any]:
    """The prose for one verified report, or the fallback. Never raises for a model problem."""
    cfg = settings()
    if cfg["mode"] == "off":
        return _result(None, "none", "skipped", [{"model": "none", "outcome": "disabled"}])
    if report.get("abstained"):
        return _result(None, "none", "skipped", [{"model": "none", "outcome": "attribution_paused"}])
    facts = build_facts(report)
    messages = build_messages(facts)
    attempts: list[dict[str, str]] = []
    for model, call in ((cfg["terra_model"], terra), (cfg["local_model"], local)):
        try:
            raw = call(messages, cfg)
        except WriterError as exc:
            attempts.append({"model": model, "outcome": exc.code})
            continue
        except Exception:  # noqa: BLE001 - a writer problem must never fail the run
            attempts.append({"model": model, "outcome": "error"})
            continue
        prose, problem = check_prose(raw, facts)
        if problem:
            attempts.append({"model": model, "outcome": f"rejected_{problem}"})
            continue
        attempts.append({"model": model, "outcome": "ok"})
        return _result(prose, model, "ok", attempts)
    return _result(None, "none", "fallback_stub", attempts)

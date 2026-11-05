"""Scorers. Code checks run on every run; LLM judges run only with --judge and stay report-only
until their agreement with human labels is measured (Evaluation Pack open item 2)."""
from __future__ import annotations

import re

import duckdb
from mlflow.entities import Feedback
from mlflow.genai.scorers import scorer

from .numbers import Number, as_numbers, contains_phrase, extract, parse_token, same
from .paths import DATABASE
from .versions import data_fingerprint

# numbers_match_golden stays report-only: a system with evidence may state correct numbers the golden answer omits.
GATED = ("must_not_say", "governed_terms", "no_individual_rep", "claims_reconcile", "numbers_traced", "links_resolve")


def _answer(outputs) -> str:
    return (outputs.get("answer") or "") if isinstance(outputs, dict) else str(outputs or "")


def _golden(expectations) -> list:
    return extract(expectations.get("expected_response", "")) + as_numbers(expectations.get("golden_numbers", []))


@scorer(name="numbers_match_golden",
        description="Share of numbers in the answer that match a golden number (EV-1.1 / FE-04 proxy).")
def numbers_match_golden(outputs, expectations) -> Feedback:
    found, golden = extract(_answer(outputs)), _golden(expectations)
    if not found:
        return Feedback(value=1.0, rationale="The answer states no numbers to check.")
    unmatched = [n.text for n in found if not any(same(n, g) for g in golden)]
    share = 1 - len(unmatched) / len(found)
    note = f"{len(found) - len(unmatched)} of {len(found)} numbers match the golden answer"
    return Feedback(value=round(share, 4), rationale=note + (f"; unmatched: {', '.join(unmatched)}" if unmatched else "."))


@scorer(name="golden_number_recall",
        description="Share of the golden answer's numbers that the answer states.")
def golden_number_recall(outputs, expectations) -> Feedback:
    golden, found = extract(expectations.get("expected_response", "")), extract(_answer(outputs))
    if not golden:
        return Feedback(value=1.0, rationale="The golden answer states no numbers.")
    missing = [g.text for g in golden if not any(same(g, n) for n in found)]
    note = f"{len(golden) - len(missing)} of {len(golden)} golden numbers stated"
    return Feedback(value=round(1 - len(missing) / len(golden), 4),
                    rationale=note + (f"; missing: {', '.join(missing[:12])}" if missing else "."))


@scorer(name="must_not_say", description="None of the case's must-not-say phrases appears.")
def must_not_say(outputs, expectations) -> Feedback:
    text, phrases = _answer(outputs), expectations.get("must_not_say", [])
    hits = [p for p in phrases if contains_phrase(text, p)]
    if hits:
        return Feedback(value=False, rationale="Says: " + "; ".join(f'"{h}"' for h in hits))
    return Feedback(value=True, rationale=f"None of {len(phrases)} literal phrases appears.")


@scorer(name="governed_terms",
        description='No "surveillance"; "new patients" only for NBRx (EV-9.2).')
def governed_terms(outputs) -> Feedback:
    text, problems = _answer(outputs), []
    if re.search(r"\bsurveillance\b", text, re.I):
        problems.append('uses "surveillance"')
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if re.search(r"\bnew patients\b", sentence, re.I) and not re.search(r"\bNBRx\b|new-to-brand", sentence, re.I):
            problems.append(f'"new patients" not tied to NBRx: "{sentence.strip()[:120]}"')
    return Feedback(value=not problems, rationale="; ".join(problems) or "Governed wording.")


_REP = re.compile(
    r"\b(?:[Ss]ales\s+)?[Rr]ep(?:resentative)?s?\s+(?:named\s+)?"
    r"(?!(?:Calls?|Vacanc\w*|Activity|Coverage|Counts?|Visits?)\b)[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b"
    r"|\b[Rr]ep(?:resentative)?\s*(?:ID|Id|id|#|[Nn]o\.)\s*[\w-]+"
)


@scorer(name="no_individual_rep", description="No line names or numbers an individual rep (EV-9.1). Heuristic.")
def no_individual_rep(outputs) -> Feedback:
    hits = [m.group(0) for m in _REP.finditer(_answer(outputs))]
    return Feedback(value=not hits, rationale=("Points to a rep: " + "; ".join(hits)) if hits else "No rep-level line.")


DETERMINISTIC = [numbers_match_golden, golden_number_recall, must_not_say, governed_terms, no_individual_rep]


def _claims(outputs):
    outputs = outputs if isinstance(outputs, dict) else {}
    return outputs.get("claims") or [], {e["id"]: e for e in outputs.get("evidence") or []}


@scorer(name="claims_reconcile",
        description="Share of claims whose evidence query, re-run on the data, gives the claimed value (EV-1.1).")
def claims_reconcile(outputs) -> Feedback:
    claims, evidence = _claims(outputs)
    if not claims:
        return Feedback(value=0.0, rationale="The answer carries no claims.")
    bad = []
    with duckdb.connect(str(DATABASE), read_only=True) as con:
        for c in claims:
            e = evidence.get(c["evidence_id"])
            want = parse_token(c["value"])
            if not e or not e.get("query") or want is None:
                bad.append(f"{c['value']}: no usable evidence")
                continue
            row = con.execute(e["query"]).fetchone()
            got = row[0] if row else None
            if got is None or not same(want, Number(float(got), 12, False, str(got))):
                bad.append(f"{c['value']} but the data gives {got}")
    ok = len(claims) - len(bad)
    return Feedback(value=round(ok / len(claims), 4),
                    rationale=f"{ok} of {len(claims)} claims reconcile" + (f"; failed: {'; '.join(bad[:8])}" if bad else "."))


_UNFILLED = re.compile(r"\{c\d+\}")


@scorer(name="numbers_traced",
        description="Share of numbers in the answer text that are filled claims with evidence (EV-6.1).")
def numbers_traced(outputs) -> Feedback:
    claims, _ = _claims(outputs)
    text = _answer(outputs)
    # A claim token left in the text is a number no code filled: a model wrote a token that does not exist.
    unfilled = _UNFILLED.findall(text)
    found = extract(_UNFILLED.sub(" ", text))
    total = len(found) + len(unfilled)
    if not total:
        return Feedback(value=1.0, rationale="The answer states no numbers.")
    known = [n for n in (parse_token(c["value"]) for c in claims) if n]
    loose = [n.text for n in found if not any(same(n, k) for k in known)] + unfilled
    return Feedback(value=round(1 - len(loose) / total, 4),
                    rationale=f"{total - len(loose)} of {total} numbers trace to a claim"
                              + (f"; untraced: {', '.join(loose[:8])}" if loose else "."))


@scorer(name="links_resolve",
        description="Every claim links to an evidence item pinned to the data version of the run (EV-6.2).")
def links_resolve(outputs) -> Feedback:
    claims, evidence = _claims(outputs)
    if not claims:
        return Feedback(value=0.0, rationale="The answer carries no claims.")
    pinned = data_fingerprint()
    bad = [c["value"] for c in claims
           if c["evidence_id"] not in evidence or evidence[c["evidence_id"]].get("data_version") != pinned]
    return Feedback(value=round(1 - len(bad) / len(claims), 4),
                    rationale=f"{len(claims) - len(bad)} of {len(claims)} claims link to evidence on data version {pinned}"
                              + (f"; broken: {', '.join(bad[:8])}" if bad else "."))


EVIDENCE = [claims_reconcile, numbers_traced, links_resolve]


# Trajectory: white-box and report-only, never gated. For agent systems that return `trajectory`.
def _trajectory(outputs) -> dict:
    return (outputs or {}).get("trajectory") or {}


@scorer(name="tool_calls", description="MCP tool calls the agents made (report only).")
def tool_calls(outputs) -> Feedback:
    tools = _trajectory(outputs).get("tools", [])
    return Feedback(value=len(tools), rationale=" > ".join(tools) or "No tool call.")


@scorer(name="llm_calls", description="Model calls across manager and specialists (report only).")
def llm_calls(outputs) -> Feedback:
    t = _trajectory(outputs)
    tokens = t.get("tokens", {})
    return Feedback(value=t.get("llm_calls", 0),
                    rationale=f"{tokens.get('input', 0)} input and {tokens.get('output', 0)} output tokens; {t.get('model', '?')}.")


@scorer(name="seconds", description="Wall time of one answer (report only).")
def seconds(outputs) -> Feedback:
    return Feedback(value=_trajectory(outputs).get("seconds", 0.0))


@scorer(name="hit_cap", description="The team hit its round cap and the brief came from the reports so far (report only).")
def hit_cap(outputs) -> Feedback:
    why = _trajectory(outputs).get("capped")
    return Feedback(value=bool(why), rationale=f"Stopped early: {why}." if why else "Finished within its caps.")


@scorer(name="needed_revision", description="The draft had digits outside claim tokens and got one revision (report only).")
def needed_revision(outputs) -> Feedback:
    t = _trajectory(outputs)
    left = t.get("digits_outside_tokens") or []
    return Feedback(value=bool(t.get("revised")), rationale=("Still outside tokens: " + ", ".join(left[:8])) if left else None)


TRAJECTORY = [tool_calls, llm_calls, seconds, hit_cap, needed_revision]


def judge_scorers(model: str) -> list:
    """RAGAS judges on `model` (e.g. ollama:/gemma3:4b). The judge sees only the question, the answer
    text and the golden answer: MLflow would otherwise join every expectation into RAGAS's reference."""
    from mlflow.genai.scorers.ragas import FactualCorrectness

    factual = FactualCorrectness(model=model)

    @scorer(name="judge_factual_correctness",
            description=f"RAGAS FactualCorrectness against the golden answer (EV-1.3), judged by {model}.")
    def judge_factual_correctness(inputs, outputs, expectations) -> Feedback:
        fb = factual(inputs=inputs, outputs=_answer(outputs),
                     expectations={"expected_response": expectations["expected_response"]})
        if fb.error:
            return Feedback(error=fb.error)
        return Feedback(value=fb.value, rationale=fb.rationale)

    return [judge_factual_correctness]

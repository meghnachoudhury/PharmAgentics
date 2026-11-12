"""Stages 5 and 6 for build 3 (brief-002 FR-026; Nov 6 traces C-018 and C-001).

Code writes every section. The writer adds the answer and one sentence per story; verification fails a
typed digit, a token no tool produced, a token from another story, and banned terms; one revision; what
still fails is dropped. Then the brief is assembled and rendered from the run's claims.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from pharmagentics.tools.registry import digits_outside_tokens

TOKEN = re.compile(r"\{c(\d+)\}")
BANNED = [(re.compile(r"surveillance", re.I), 'says "surveillance" (use "competitive intelligence")'),
          (re.compile(r"new patients?(?![^.]*\bNBRx\b)", re.I), 'says "new patients" about something other than NBRx')]


# What each number measures, written by code from the claim's own SQL, so the writer never has to guess a
# comparison (Nov 6 trace C-018; brief-002 FR-026). No counts: weeks are named by their dates.
_WEEK_SETS = re.compile(r"week_start in \(([^)]*)\)")
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
TOKEN_NUMBERS = re.compile(r"\{c(\d+)\}")
RELATIVE_WEEK = re.compile(r"\b(week before|last week|previous week|prior week|week earlier|week[- ]over[- ]week)\b", re.I)
YEAR_BACK = re.compile(r"\b(last year|year[- ]over[- ]year|a year ago|same week last year)\b", re.I)


def _span(weeks: list[str]) -> str:
    return f"the week of {weeks[0]}" if len(weeks) == 1 else f"the weeks {weeks[0]} to {weeks[-1]}"


def gloss(claim: dict, evidence: dict | None) -> dict:
    """{'text': what the number is, 'base_single': True when it compares with the single week before}."""
    query = (evidence or {}).get("query") or ""
    sets: list[list[str]] = []
    for group in _WEEK_SETS.findall(query):
        weeks = sorted(set(_ISO.findall(group)))
        if weeks and (not sets or sets[-1] != weeks):
            sets.append(weeks)
    params = ", ".join(f"{k} {v}" for k, v in ((evidence or {}).get("params") or {}).items())
    single = False
    if len(sets) >= 2 and claim["value"].endswith("%"):
        new, old = sets[0], sets[1]
        single = len(old) == 1 and len(new) == 1 and date.fromisoformat(old[0]) == date.fromisoformat(new[0]) - timedelta(days=7)
        text = f"a change: {_span(new)} against {_span(old)}" + (" (a week-over-week comparison)" if single else " (not week over week)")
    elif sets:
        text = f"a value for {_span(sets[0])}"
    else:
        text = "a value taken from the data"
    return {"text": text + (f" [{params}]" if params else ""), "base_single": single}


def glossary(shown: str, claims: list[dict], evidence: list[dict]) -> tuple[str, dict[str, dict]]:
    """Lines for the writer, one per token that appears in the sections, and the gloss data by token."""
    by_id = {e["id"]: e for e in evidence}
    seen = sorted({int(n) for n in TOKEN_NUMBERS.findall(shown) if 0 < int(n) <= len(claims)})
    data = {f"{{c{n}}}": gloss(claims[n - 1], by_id.get(claims[n - 1]["evidence_id"])) for n in seen}
    return "\n".join(f"{t} = {g['text']}" for t, g in data.items()), data


def tokens(text: str) -> set[str]:
    return {m.group(0) for m in TOKEN.finditer(text or "")}


def problems(piece: str, allowed: set[str], n_claims: int, glosses: dict[str, dict] | None = None) -> list[str]:
    out = []
    if (bad := digits_outside_tokens(piece)):
        out.append(f"typed numbers {', '.join(bad[:5])}")
    used = tokens(piece)
    invented = sorted(t for t in used if not 0 < int(t[2:-1]) <= n_claims)
    if invented:
        out.append(f"tokens no tool produced {', '.join(invented)}")
    foreign = sorted(t for t in used - allowed if t not in invented)
    if foreign:
        out.append(f"tokens from another part of the brief {', '.join(foreign)}")
    out += [why for rx, why in BANNED if rx.search(piece or "")]
    if glosses is not None:  # wording: a comparison is described only as the glossary states it
        if RELATIVE_WEEK.search(piece or "") and not any(glosses.get(t, {}).get("base_single") for t in used):
            out.append('compares with "the week before", but none of its numbers is a week-over-week comparison '
                       "(describe it as the glossary does)")
        if YEAR_BACK.search(piece or ""):
            out.append("compares with last year, but no number in this brief does")
    return out


def normalize(reply: dict, story_ids) -> dict:
    """Match the writer's story keys to story ids leniently ('PACIFIC' or 'Pacific' for 'territory:PACIFIC')."""
    ids = [s for s in story_ids if s != "_sections"]
    out = {}
    for key, sentence in (reply.get("stories") or {}).items():
        k = str(key).strip()
        match = k if k in ids else next((i for i in ids if i.split(":", 1)[-1].lower() == k.lower().replace(" ", "_").replace("-", "_")), k)
        out[match] = sentence
    return {**reply, "stories": out}


def check(reply: dict, story_tokens: dict[str, set[str]], n_claims: int,
          glosses: dict[str, dict] | None = None) -> dict[str, list[str]]:
    """Problems per piece: 'answer' and each story id."""
    reply = normalize(reply, story_tokens)
    every = set().union(*story_tokens.values(), story_tokens.get("_sections", set()))
    found = {}
    if (p := problems(str(reply.get("answer", "")), every, n_claims, glosses)):
        found["answer"] = p
    for sid, sentence in (reply.get("stories") or {}).items():
        if sid not in story_tokens:
            continue  # an entry for a story this brief does not have is discarded, not revised (small models invent them)
        elif (p := problems(str(sentence), story_tokens[sid], n_claims, glosses)):
            found[sid] = p
    return found


def clean(reply: dict, story_tokens: dict[str, set[str]], n_claims: int,
          glosses: dict[str, dict] | None = None) -> tuple[str, dict[str, str], list[str]]:
    """Keep only the pieces that pass; report what was dropped."""
    reply = normalize(reply, story_tokens)
    bad = check(reply, story_tokens, n_claims, glosses)
    answer = "" if "answer" in bad else str(reply.get("answer", "")).strip()
    stories = {sid: str(s).strip() for sid, s in (reply.get("stories") or {}).items()
               if sid in story_tokens and sid != "_sections" and sid not in bad and str(s).strip()}
    dropped = [f"{k}: {'; '.join(v)}" for k, v in bad.items()]
    return answer, stories, dropped


def sections_text(sections: dict, stories: list[dict]) -> str:
    """What the writer sees: the code sections, each story labelled with its id."""
    parts = ["[data and KPIs]", *sections["header"], *sections["data_health"], *sections["kpis"]]
    for s in stories:
        parts += [f"[story {s['id']}]", s["section"]]
    return "\n".join(parts)


def assemble(sections: dict, stories: list[dict], answer: str, sentences: dict[str, str], left_out: list[str],
             dropped_line: str) -> str:
    out = ([answer] if answer else []) + sections["header"] + sections["data_health"] + sections["kpis"]
    if sections.get("calendar"):
        out.append("No story is opened for a calendar week. Expect a rebound in the next regular week.")
    else:
        if sections.get("withheld_focus"):
            out.append(sections["withheld_focus"])
        for s in stories:
            lines = s["section"].split("\n")
            if sentences.get(s["id"]):
                lines.insert(1, sentences[s["id"]])
            out += lines
        out += left_out
        if not stories and not left_out:
            out.append("Routine week. No material change was found, and territory swings stayed in their normal range.")
        elif dropped_line:
            out.append(dropped_line)
    return "\n".join(x for x in out if x)


def render(template: str, claims: list[dict]) -> tuple[str, list[dict], list[dict]]:
    """Fill tokens from the run's claims; return the text, the claims it uses (in order of use) and where
    each sits in the text (inline citations, indexed into the used claims)."""
    from pharmagentics.tools.registry import cite

    used = list(dict.fromkeys(int(m.group(1)) for m in TOKEN.finditer(template) if 0 < int(m.group(1)) <= len(claims)))
    text, spans = cite(template, claims, index={n: i for i, n in enumerate(used)})
    return text, [claims[n - 1] for n in used], spans


def flow(base: list[dict], plan: dict, record: dict, tools: list[str], revised: bool, model: str) -> list[dict]:
    """The Phase A stage flow with the agents named (brief-002 US7 scenario 2)."""
    out = [dict(s) for s in base]
    agent = lambda name: {"kind": "agent", "name": name}  # noqa: E731
    s4 = out[3]
    if s4["states"]:
        actors = [{"kind": "code", "name": "triage rules (screen, caps, withheld cuts, continuing stories)"},
                  agent(f"manager (triage plan, {model})")]
        if record.get("reviewed_by_person"):
            actors.append({"kind": "human", "name": "Commercial Analyst (plan review)"})
        actors += [agent("manager (coordinates each story)"), agent("Data Forensics"), agent("Driver Investigator")]
        s4 = dict(s4, actors=actors)
        called = sorted(set(tools))
        s4["note"] = (s4["note"].replace(" The analyst changed the code plan.", "")
                      + (" Plan flagged: " + " ".join(plan.get("flags", [])) if plan.get("flagged") else "")
                      + (f" Tools called: {', '.join(called)}." if called else ""))
        out[3] = s4
    out[4] = dict(out[4], actors=[{"kind": "code", "name": "brief sections (claim tokens)"},
                                  {"kind": "llm", "name": f"writer: answer and one sentence per story ({model})"}],
                  note="Code writes every section; the writer adds the answer and one sentence per story.")
    actors6 = [{"kind": "code", "name": "number, token and wording checks"}]
    if revised:
        actors6.append({"kind": "llm", "name": "one revision of failing sentences"})
    out[5] = dict(out[5], actors=actors6)
    return out

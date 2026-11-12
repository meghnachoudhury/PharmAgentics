"""Stages 5 and 6 for build 3 (brief-002 FR-026; Nov 6 traces C-018 and C-001).

Code writes every section. The writer adds the answer and one sentence per story; verification fails a
typed digit, a token no tool produced, a token from another story, and banned terms; one revision; what
still fails is dropped. Then the brief is assembled and rendered from the run's claims.
"""
from __future__ import annotations

import re

from pharmagentics.tools.registry import digits_outside_tokens

TOKEN = re.compile(r"\{c(\d+)\}")
BANNED = [(re.compile(r"surveillance", re.I), 'says "surveillance" (use "competitive intelligence")'),
          (re.compile(r"new patients?(?![^.]*\bNBRx\b)", re.I), 'says "new patients" about something other than NBRx')]


def tokens(text: str) -> set[str]:
    return {m.group(0) for m in TOKEN.finditer(text or "")}


def problems(piece: str, allowed: set[str], n_claims: int) -> list[str]:
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


def check(reply: dict, story_tokens: dict[str, set[str]], n_claims: int) -> dict[str, list[str]]:
    """Problems per piece: 'answer' and each story id."""
    reply = normalize(reply, story_tokens)
    every = set().union(*story_tokens.values(), story_tokens.get("_sections", set()))
    found = {}
    if (p := problems(str(reply.get("answer", "")), every, n_claims)):
        found["answer"] = p
    for sid, sentence in (reply.get("stories") or {}).items():
        if sid not in story_tokens:
            found[sid] = ["not a story in this brief"]
        elif (p := problems(str(sentence), story_tokens[sid], n_claims)):
            found[sid] = p
    return found


def clean(reply: dict, story_tokens: dict[str, set[str]], n_claims: int) -> tuple[str, dict[str, str], list[str]]:
    """Keep only the pieces that pass; report what was dropped."""
    reply = normalize(reply, story_tokens)
    bad = check(reply, story_tokens, n_claims)
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


def render(template: str, claims: list[dict]) -> tuple[str, list[dict]]:
    """Fill tokens from the run's claims; return the text and the claims it uses, in order of use."""
    used: list[int] = []

    def fill(m):
        n = int(m.group(1))
        if not 0 < n <= len(claims):
            return m.group(0)
        if n not in used:
            used.append(n)
        return claims[n - 1]["value"]

    text = TOKEN.sub(fill, template)
    return text, [claims[n - 1] for n in used]


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

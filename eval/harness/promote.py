"""Promote approved proposals (core-008 FR-021; ADR 0003, amended 2026-11-20).

    uv run python -m eval promote [--state-dir DIR]

Approved lessons go into `agents/brand-briefing/knowledge/lessons.yaml`; approved cases become drafts in
`eval/candidates/` for labelling. Each proposal is marked promoted in the state store. Nothing is committed or
pushed: the command prints the git steps, and Michael opens the pull request, so CI and the eval gate run before the
lessons reach the app. The hosted app holds no GitHub token.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml

from .candidates import CANDIDATES_DIR, DEFAULT_STATE_DIRS
from .improve import PROPOSALS, lesson_problems
from .paths import REPO_ROOT

LESSONS = REPO_ROOT / "agents" / "brand-briefing" / "knowledge" / "lessons.yaml"
HEADER = ("# Approved lessons for the Briefing agents (core-008 FR-021, FR-022; ADR 0003).\n"
          "# Proposed by `python -m eval improve`, approved by the tester admin on the Feedback review panel, written here by\n"
          "# `python -m eval promote`, and merged by pull request so CI and the eval gate run first. Agents read only this file:\n"
          "# never threads or raw feedback. A lesson holds no digit.\n")


def run(state_dir: Path | None = None, backend=None, lessons_file: Path = LESSONS,
        candidates_dir: Path = CANDIDATES_DIR, today: str | None = None) -> dict:
    from pharmagentics.api import store

    if backend is None:
        state_dir = state_dir or next((d for d in DEFAULT_STATE_DIRS if (d / PROPOSALS).is_dir()), None)
        if state_dir is None:
            return {"lessons": [], "cases": [], "skipped": []}
        backend = store.LocalBackend(state_dir)
    data = yaml.safe_load(lessons_file.read_text(encoding="utf-8")) if lessons_file.is_file() else None
    current = list((data or {}).get("lessons") or [])
    known = {x["id"] for x in current}
    out = {"lessons": [], "cases": [], "skipped": []}
    for key in backend.keys(PROPOSALS):
        p = json.loads(backend.read(key) or "{}")
        if p.get("status") != "approved":
            continue
        if p["kind"] == "lesson":
            if lesson_problems(p["text"]):  # re-checked at promotion: a lesson never carries a number
                out["skipped"].append(p["id"])
                continue
            if p["id"] not in known:
                current.append({"id": p["id"], "text": p["text"], "applies_to": p.get("applies_to", "writer"),
                                "source": p["source"], "approved_by": p.get("decided_by"),
                                "approved_at": p.get("decided_at")})
                known.add(p["id"])
            out["lessons"].append(p["id"])
        else:
            path = candidates_dir / "briefing" / f"{p['id']}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({**p["draft_case"], "source": p["source"], "approved_by": p.get("decided_by")},
                                           sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
            out["cases"].append(str(path))
        p["status"] = "promoted"
        backend.write(key, json.dumps(p, indent=1, default=str))
    if out["lessons"]:
        lessons_file.write_text(HEADER + yaml.safe_dump({"lessons": current}, sort_keys=False, allow_unicode=True,
                                                         width=120), encoding="utf-8")
    out["git"] = [] if not out["lessons"] else [
        f"git switch -c lessons/{today or date.today().isoformat()}",
        "git add agents/brand-briefing/knowledge/lessons.yaml",
        'git commit -m "Promote approved lessons (core-008 FR-021)"',
        "git push -u origin HEAD   # then open the pull request; CI and the eval gate run on it",
    ]
    return out

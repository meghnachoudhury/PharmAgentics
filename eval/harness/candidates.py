"""Draft golden-set candidates from UAT votes on answers (core-008 User Story 6).

    uv run python -m eval candidates [--state-dir DIR] [--force]

Reads the vote documents the web app stored (feedback/response/<lane>/<answer>/...) from a downloaded state
folder: `uv run python deploy/gcp.py feedback ...` puts the cloud copy in local/feedback-export, and a local stack
writes to local/state. Writes one draft per voted answer to eval/candidates/<lane>/<answer>.yaml (git-ignored):

- downvoted answers (any down vote) are "investigate" drafts: find out what was wrong;
- answers with only up votes are "regression" drafts: worth keeping right.

A draft is not a case. It has no ID, no facts and no reference answer: a person reviews it, writes the facts with
SQL from the governed views, gives it an ID and moves it into eval/golden/<lane>/, where `eval check` recomputes the
facts. A vote is an opinion, not ground truth, so nothing here decides what is correct. Existing drafts are left
alone (a person may have started editing them) unless --force is given.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from .paths import EVAL_DIR, REPO_ROOT as ROOT

CANDIDATES_DIR = EVAL_DIR / "candidates"
VOTES = Path("feedback") / "response"
DEFAULT_STATE_DIRS = (ROOT / "local" / "feedback-export", ROOT / "local" / "state")


def load_votes(state_dir: Path) -> list[dict]:
    folder = state_dir / VOTES
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.rglob("*.json"))] if folder.is_dir() else []


def _question(lane: str, scope: dict) -> str:
    if lane == "briefing":
        return scope.get("question") or (f"Weekly briefing for {scope.get('brand_id')}, {scope.get('territory_id')}, "
                                         f"week of {scope.get('week_start')}")
    weeks = scope.get("window_weeks")
    return (f"Forecast explanation for BXA TRx, {scope.get('territory_id')}, week of {scope.get('week_start')}, "
            f"{weeks}-week window")


def drafts(votes: list[dict]) -> dict[tuple[str, str], dict]:
    """One draft per answer (lane, answer ID), from every vote on it in any view. Pure: no I/O."""
    by_answer: dict[tuple[str, str], list[dict]] = {}
    for v in votes:
        by_answer.setdefault((v["lane"], v["ref"]), []).append(v)
    out: dict[tuple[str, str], dict] = {}
    for (lane, ref), vs in sorted(by_answer.items()):
        vs = sorted(vs, key=lambda d: d["ts"])
        latest = vs[-1]
        down = sum(v["vote"] == "down" for v in vs)
        up = len(vs) - down
        out[(lane, ref)] = {
            "id": None,
            "lane": lane,
            "status": "candidate",
            "kind": "investigate" if down else "regression",
            "source": f"uat-feedback:{lane}/{ref}",
            "question": _question(lane, latest.get("scope") or {}),
            "scope": latest.get("scope"),
            "votes": {"up": up, "down": down},
            "comments": [{"vote": v["vote"], "view": v["view"], "personas": "/".join(v.get("personas") or []),
                          "comment": v["comment"]} for v in vs if v.get("comment")],
            "engine": latest.get("engine"),
            "system": latest.get("system"),
            "data_version": latest.get("data_version"),
            "shown": {v["view"]: v.get("shown") for v in vs},
            "review_note": ("Downvoted: decide what was wrong, then write facts (SQL on the governed views) and a "
                            "reference answer before promoting." if down else
                            "Upvoted only: a vote is not proof of correctness. Check the figures against the data, "
                            "then write facts and a reference answer before promoting."),
            "reference_answer": None,
            "facts": [],
        }
    return out


def run(state_dir: Path | None = None, force: bool = False, out_dir: Path = CANDIDATES_DIR) -> tuple[list[Path], list[Path], Path | None]:
    """Write the drafts. Returns (written, kept because they already exist, the state folder read)."""
    if state_dir is None:
        state_dir = next((d for d in DEFAULT_STATE_DIRS if (d / VOTES).is_dir()), None)
        if state_dir is None:
            return [], [], None
    written, kept = [], []
    for (lane, ref), draft in drafts(load_votes(state_dir)).items():
        path = out_dir / lane / f"{ref}.yaml"
        if path.exists() and not force:
            kept.append(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(draft, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
        written.append(path)
    return written, kept, state_dir

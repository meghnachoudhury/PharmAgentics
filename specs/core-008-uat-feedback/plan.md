# Implementation Plan: the feedback loop (core-008 FR-019 to FR-022; memo slice 5)

**Branch**: `feature/brief-memo-follow-ups` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md) (Sessions 2026-11-19 and 2026-11-20) | **ADR**: `docs/adr/0003-feedback-loop-proposes-people-promote.md`

This plan covers only the feedback loop added on 2026-11-19 (FR-019 to FR-022). The earlier core-008 stories (pulse, questionnaire, votes, candidates) are built and unchanged.

## Summary

The system proposes, people promote. `python -m eval improve` turns new votes and saved threads into proposals: number-free lessons for the agents and draft golden cases. It checks each lesson by code, reruns the flagged question with it, lets an agent reviewer judge whether the reported problem is gone, and runs the eval gate. The tester admin approves or rejects proposals on a review panel of the Evaluation page. `python -m eval promote` writes approved lessons into `agents/brand-briefing/knowledge/lessons.yaml` (and approved cases into `eval/candidates/`) and prints the git commands for Michael's pull request. The agents read only approved lessons.

## Technical Context

**Language/Version**: Python 3.12; TypeScript (React 19)

**Primary Dependencies**: the eval harness (`run_suite`, `gate`, the gated scorers), the state store (`api/store.py`, local folder or bucket), Claude Haiku through `pharmagentics.llm` for drafting and reviewing (core-007 FR-032)

**Storage**: proposals at `review/proposals/<id>.json` in the state store; approved lessons in `agents/brand-briefing/knowledge/lessons.yaml` (versioned, outside `eval/`)

**Constraints**: agent code never reads `eval/` (lessons live in `agents/`); no new persona or role (Session 2026-11-20): the tester admin approves; review actions are not UAT events; the app holds no GitHub token; LLM judgement here only advises a person, it gates nothing

## Constitution Check

| Article | How |
| :- | :- |
| I Numbers from tools | Lessons hold no digit (checked by code); they guide wording and order of checks, never values |
| II People decide | Every lesson and case waits for the tester admin's approval and Michael's pull request (FR-021) |
| III Isolation | `improve` and `promote` live in `eval/`; the knowledge base lives in `agents/`; agents never import `eval/` |
| V Abstain | A lesson the reviewer, the checks or the gate cannot clear is flagged with its reason, never promoted silently |
| VI Synthetic data | Prompts to Haiku carry the answer with numbers masked, the comment and the question |
| B-VII Gate | A lesson is confident only after `eval gate` passes with it; the slice itself is gated on both engines |

## Design

| Piece | Where | Does |
| :- | :- | :- |
| Lessons file | `agents/brand-briefing/knowledge/lessons.yaml` | `lessons: [{id, text, applies_to: writer, source, approved_at}]`; starts empty |
| Lessons in the agent | `briefing_agent/lessons.py`, `write` prompt | Approved lessons appended to the writer prompt; nothing added when there are none; the file is part of `config_version`. `PHARMAGENTICS_TRIAL_LESSONS` (JSON) adds draft lessons for `eval improve` reruns only; the app never sets it |
| Improve | `eval/harness/improve.py`, `python -m eval improve [--state-dir] [--baseline RUN]` | New downvotes with a comment → Haiku drafts a lesson; code check (no digit, no banned term, under 300 characters); rerun the flagged question with it; agent reviewer (Haiku) says whether the reported problem persists; with `--baseline`, one gate run with the candidate lessons; upvotes → draft regression cases. Writes proposals to the state store |
| Review API | `src/pharmagentics/api/review.py` | `GET /api/review/proposals`, `POST /api/review/proposals/{id}` (approve or reject, note); tester admin only, others 404; no UAT event |
| Review panel | `frontend/figma-make/src/FeedbackReview.tsx` | Under the Evaluation page for the tester admin: each proposal, confident or flagged with reasons, the lesson, the rerun before and after, approve or reject |
| Promote | `eval/harness/promote.py`, `python -m eval promote` | Approved lessons into `lessons.yaml`, approved cases into `eval/candidates/`, proposals marked promoted, git commands printed |

## Complexity Tracking

None.

# Implementation Plan: Follow-ups and Threads

**Branch**: `feature/brief-memo-follow-ups` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md) (Draft v1, Sessions 2026-11-19 and 2026-11-20)

## Summary

Slice 3 (this plan's first part) gives analysts a message bar docked at the bottom of the Briefing screens, threads of follow-ups attached to a brief, and the scripted engine's rule-based answers. Slice 4 (second part, below) adds Claude Haiku answers, two-turn golden cases and the `sections_exist` check. Every decision comes from the spec's clarifications; nothing here reopens them.

## Technical Context

**Language/Version**: Python 3.12, TypeScript (React 19)

**Primary Dependencies**: FastAPI (an `APIRouter` in a new module), the shared state store (`api/store.py`), the memo sections from brief-003 (slices 1 and 2)

**Storage**: the state store, `threads/<brief_id>/<owner>.json`, where `<owner>` is a short hash of the analyst's subject (no names in keys)

**Testing**: pytest with FastAPI's TestClient (dev identities); the real app in headless Chrome over the DevTools protocol (as in brief-003 slice 2)

**Constraints**: `app.py`, `App.tsx` and `Telemetry.tsx` carry another session's uncommitted edits, so new code goes in new files (`api/threads.py`, `tools/followup.py`, `MessageBar.tsx`) with one-line hooks; agent code never reads `eval/`; no digit outside a claim

## Constitution Check

| Article | How |
| :- | :- |
| I Every number from a tool | A scripted answer reuses the brief's own claims (same values, same evidence); it never makes a new number (FR-004) |
| II People decide | A thread is never part of the approved brief (ADR 0002); leaders cannot read threads (404) |
| III Isolation | No `eval/` import outside the harness |
| IV Typed contracts | Thread and turn shapes below; the follow-up answer reuses the claim and evidence shapes |
| V Abstain | A request for a number the brief does not hold says so; a "why" on a projected or estimated cut says no driver can be named (FR-023) |
| B-VI No individual | Thread files key the analyst by a hash; answers carry no rep data |
| B-VII Gate | Slice 3 changes no brief: both engines must hold the slice 2 gate; follow-ups enter the golden set in slice 4 |

## Design (slice 3)

**Scripted follow-ups**: `src/pharmagentics/tools/followup.py`, pure and deterministic, over the brief's `sections`, `claims` and `evidence`:

1. Section reference: the pinned chip, else `§N` or `§N.M` in the text, else the Bottom line.
2. Out of scope: the text names another territory, another product (BXC, BXD, BXE or their names) or another week → "This brief covers BXA, <territory>, week of <week>." plus an offer `{"brand", "territory", "week"}` to generate a brief for that scope. No number.
3. A "why" or a driver question about a territory the brief shows as projected or estimated → no driver can be named for that cut (brief-003 FR-023), citing §4.
4. A request for a split, a breakdown or a number not in the section ("by plan", "by specialty", "how many", "split", "break down", "what about") → "That number is not in this brief." and an offer to ask the agent (slice 4).
5. Otherwise → the section restated, citing it: "§3.1 Pacific: <its text>", with its claims.

The answer's `claims` are the brief's own claims it states; `cited` lists the section numbers; an answer never holds a digit outside a claim value or a date.

**Threads**: `src/pharmagentics/api/threads.py`, an `APIRouter` under `/api/briefing/{brief_id}/thread`:

| Method | Path | Does |
| :- | :- | :- |
| GET | `` | My thread for this brief (empty if none) and the suggestions per section |
| POST | `/ask` | `{question, section?}` → a scripted turn appended (max 20; then 409 "thread full") |
| POST | `/save` | Marks it saved (kept past 30 days, in the feedback review list); returns the share path |
| GET | `/shared/{owner}` | Someone's saved thread, read-only, for any Briefing analyst |
| POST | `/continue/{owner}` | Copies a saved thread's turns into my own thread |

Only roles with the `review` action (analysts, the tester in analyst view) reach them; everyone else gets 404. Unsaved threads untouched for 30 days are deleted when threads are listed or opened (lazy purge, once per process start too). Each turn records its seconds. The thumbs and comment on a turn use `b-<id>:t<n>` as the answer reference (`feedback.py`).

**Suggestions**: code templates per section kind (bottom line, numbers, story, data limits, next checks), two or three each, phrased so the scripted engine can answer them.

**UI**: `frontend/figma-make/src/MessageBar.tsx`: the bar docked at the bottom of the brief column, the suggestion bubbles, the answers panel opening upward (at most half the screen, collapsible), the section chip; "Ask about this" on each memo section (`Memo.tsx`). On New briefing the bar's text becomes the agent brief's question (FR-002, uses the existing agent job path); while a brief is written, the message waits and is sent when the brief opens. Leaders get no bar.

## Design (slice 4, outline)

- `briefing_agent.follow_up(brief, question, section)`: one Haiku agent with both specialist tool sets over an MCP session opened on the brief's question, the sections as context, 60-second limit; prose through the same token checks and one revision.
- The harness: `follow_up` on a case; `predict` runs the brief then the follow-up; `sections_exist` gated; median and p95 latency logged.
- Six draft two-turn cases (FR-013).

As built (2026-11-20), two additions the smoke runs showed were needed:

- **`split_change(territory, by)`**, a governed agent tool in its own `follow_up` tool set: a territory's change split by plan, specialty or channel, each value a claim token, the largest moves first, cuts under 50 TRx a week marked noisy (brief-003 FR-015). `by` is a closed enum, so no tool takes free text (FR-020). Without it the agent could not answer "split §3.1 by plan" (FU-2).
- **Follow-up mode** in the MCP session (`PHARMAGENTICS_MCP_FOLLOW_UP=1`): driver checks return their verdict only. In investigation mode each check also reports the story-so-far status, which after a single check reads "Low, no driver yet"; the agent took that as a contradiction of the finished brief.
- Code guards run before the model (out of scope, no driver for a projected or estimated cut, no individual rep, no such section), so those answers never depend on the model.

## Project Structure

```text
src/pharmagentics/tools/followup.py      NEW  scripted follow-up rules
src/pharmagentics/api/threads.py         NEW  thread store and routes
src/pharmagentics/api/app.py             +1   include_router
src/pharmagentics/api/feedback.py        turn references for votes
frontend/figma-make/src/MessageBar.tsx   NEW  bar, chip, suggestions, answers panel
frontend/figma-make/src/agent/threadApi.ts NEW
frontend/figma-make/src/Memo.tsx         "Ask about this" per section
frontend/figma-make/src/App.tsx          +2   mount the bar in the analyst views
tests/test_followup.py, tests/test_threads.py  NEW
```

## Complexity Tracking

None.

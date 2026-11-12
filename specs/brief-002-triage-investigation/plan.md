# Implementation Plan: Triage, Manager and Specialists — Phase A (triage review and stage flow)

**Branch**: `core-007-uat-deploy` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

**Input**: Phase A of brief-002: User Story 7 (stage flow, FR-024) and User Story 8 (triage plan review, FR-019, FR-022, FR-023), on the scripted engine, served by the core-007 app. Phase B (build 3: the manager takes the code triage, the writer reads only the evidence pack, the Nov 6 trace fixes) gets its own plan after Phase A ships.

## Summary

The scripted Briefing pipeline already triages by code: `stages.screen()` flags territories and access-event plans, `competitor_status()` adds the continuing Metacora story, and the rest are dropped as within their normal range. Nobody sees that triage. Phase A makes it a reviewable step: the pipeline splits at the end of stage 3, a **triage plan** with one card per candidate story goes to P1 in `TRIAGE_REVIEW`, and stages 4 to 6 run on the plan P1 approves, in P1's order. Every brief also carries its **stage flow**: the seven stages, the run states reached, and who acted. With no plan given, `answer()` is untouched, so the eval baseline and the gate stay as they are. No model runs anywhere in Phase A.

## Technical Context

**Language/Version**: Python 3.12 (floor 3.11); TypeScript 5.9 and React 19 for the UI

**Primary Dependencies**: DuckDB (governed views), FastAPI and pydantic (core-007 API), Vite and Tailwind (Meghna's UI). No new dependency.

**Storage**: Triage plans are not stored: they are recomputed by code from the question and the pinned data version (deterministic). The approved decision, the triage record and the stage flow are stored with the brief (core-007 store: local folder or Cloud Storage bucket).

**Testing**: pytest (`tests/test_triage.py` on the real release; API tests in `tests/test_rbac.py` style); the eval suite's scripted run plus `eval gate` against `c58f99fc6e09` to prove the baseline is unchanged; UI type-checked in the image build.

**Target Platform**: The core-007 container on Cloud Run and in `docker compose`.

**Project Type**: Web service and single-page UI over a library pipeline.

**Performance Goals**: Triage plan within 5 seconds of asking on a warm instance; the brief within 5 seconds of approving (scripted pipeline is about 2 seconds per pass).

**Constraints**: `answer(question)` output byte-identical to today (B-VII); every number on a card is a claim (Principle I); P1 cannot add a candidate code dropped for a withheld cut (FR-023); leadership responses carry no plan, triage record or flow (core-007 FR-003, FR-024).

**Scale/Scope**: One brand (BXA), 8 territories, at most 4 investigated territory stories per brief (`MAX_STORIES`, unchanged) plus the continuing Metacora story.

## Constitution Check

*GATE: passed before Phase 0; re-checked after Phase 1 (no change).*

| Article | How Phase A meets it |
| :- | :- |
| I. Every number from a tool | Card numbers come from `reg.claim()` in the triage step; cards are checked by `digits_outside_tokens` like the brief. Counts in the flow are names or code-computed metadata, not brief text |
| II. People decide | P1 approves or edits every triage plan in UAT (FR-019); the brief still needs P1 approval before leaders see it (core-007) |
| III. Answer-key isolation | No eval import in `agents/` or `src/`; `eval/tests/test_isolation.py` still runs |
| IV. Typed contracts | `TriagePlan`, `TriageDecision`, `TriageRecord`, `StageFlow` are pydantic models; the decision carries `plan_id`, which pins the question and data version; a mismatch stops the run (409) |
| V. Abstain when weak | Unchanged: stories close as today; a dropped story is stated as left out by the analyst, never as resolved |
| VI. Synthetic only | Unchanged |
| VII. Every loop ends | No loop in Phase A; the story cap stays |
| B-II. Declared mode | The stage flow names code, person or agent for every stage; stage 4 reads "fixed order of checks, manager off" |
| B-III. Pinned version | `plan_id` hashes the data version; a stale plan is refused |
| B-IV. Traceable | The triage step returns its claims and evidence items; the flow is stored with the brief |
| B-VII. Evaluation gate | `answer()` unchanged; a test asserts default-plan output equals `answer()` on the anchor weeks; the scripted eval run is gated against `c58f99fc6e09` |

No violations; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/brief-002-triage-investigation/
├── spec.md
├── plan.md              # this file (Phase A)
├── research.md          # decisions R1 to R8
├── data-model.md        # TriagePlan, StoryCard, TriageDecision, TriageRecord, StageFlow
├── quickstart.md        # how to prove Phase A works
├── contracts/
│   └── api.md           # HTTP contract additions
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
agents/brand-briefing/briefing_baseline/
├── pipeline.py          # split: _front (stages 1-3), _investigate (4-6); answer() unchanged; run_with_plan()
└── triage.py            # NEW: build_plan(reg, p, found, quiet, comp) -> TriagePlan; cards; stage flow builder

src/pharmagentics/api/
├── schemas.py           # TriagePlan, StoryCard, TriageDecision models; BriefingQuery.triage (optional)
├── service.py           # run_triage(), run_briefing(..., decision)
├── app.py               # POST /api/briefing/triage; query accepts a decision; flow and triage record in the analyst view
├── store.py             # brief_id includes a non-default decision
└── views.py             # analyst view adds flow and triage record; leadership allow-list unchanged

frontend/figma-make/src/
├── App.tsx              # triage review screen; "How this brief was made" panel
└── agent/briefingApi.ts # getTriage(), getBriefing(q, decision), types

tests/
├── test_triage.py       # NEW: plan contents, identity with answer(), drop and reorder, withheld cuts, card claims
└── test_rbac.py         # triage endpoint analyst-only; leadership carries no plan, record or flow
```

**Structure Decision**: The triage step lives in the Briefing lane's baseline package (it is lane logic over shared stage steps). The API and UI only carry its typed output.

## Complexity Tracking

None.

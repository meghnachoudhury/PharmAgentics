---
description: "Tasks for brief-002 Phase A: triage plan review and stage flow"
---

# Tasks: Triage, Manager and Specialists — Phase A

**Input**: [plan.md](plan.md), [spec.md](spec.md) (User Stories 7 and 8), [research.md](research.md), [data-model.md](data-model.md), [contracts/api.md](contracts/api.md), [quickstart.md](quickstart.md)

**Tests**: Included. The spec's independent tests and the eval-driven workflow (B-VII) require them.

**Organization**: Phase 2 splits the pipeline (blocks both stories). US8 (triage review) comes before US7 (stage flow) because the flow reports the triage state. Phase B (build 3) is not in this file.

## Phase 1: Setup

- [x] T001 Record the scripted baseline before any change: `uv run python -m eval run --system briefing_scripted --lane briefing`, note the run ID next to `c58f99fc6e09` in this file's Notes

## Phase 2: Foundational (blocks US7 and US8)

- [x] T002 Split `_brief()` in agents/brand-briefing/briefing_baseline/pipeline.py into `_front(reg, question)` (stages 1 to 3: resolve, load-and-pin line, data health, restatements, calendar note, KPIs, `screen()`, `competitor_status()` text) and `_investigate(reg, front, order)` (stage 4 stories in `order`, the "Considered and dropped" line, template, verification); `answer(question, db)` calls them with the default order and returns exactly what it returns today
- [x] T003 Before T002, freeze today's outputs: write tests/fixtures/scripted_answers.json with `answer()` (answer, claims, evidence, abstained) for weeks 2026-06-08 (Pacific), 2026-07-13 (Mid-Atlantic), 2026-05-04 (New England), 2026-04-06, 2025-04-21 and 2025-12-29; then add `tests/test_triage.py::test_answer_unchanged` asserting `answer()` equals the fixture after the split (the fixture holds agent-visible outputs only, no answer key)

**Checkpoint**: `uv run pytest tests/test_triage.py -q` passes; `answer()` is byte-identical.

## Phase 3: User Story 8 — P1 reviews the triage plan before investigation (P1)

**Goal**: After stages 1 to 3 the analyst sees the triage plan and approves, drops or reorders stories; stage 4 runs on that decision.

**Independent test**: Week 2026-07-13: approve the plan, then drop Mid-Atlantic and rerun; compare the briefs (spec US8).

### Tests for US8

- [x] T004 [P] [US8] In tests/test_triage.py: `build_plan` for 2026-06-08 Pacific proposes `territory:PACIFIC` then `competitor:BXE`, lists the 7 quiet territories as dropped by code ("within their normal range"), state `TRIAGE_REVIEW`
- [x] T005 [P] [US8] In tests/test_triage.py: for 2026-05-04 New England the plan lists New England as withheld with its feed-gate reasons, layer `code`; a decision naming `territory:NEW_ENGLAND` is refused (`ValueError` naming the ID)
- [x] T006 [P] [US8] In tests/test_triage.py: `run_with_plan` with the default decision returns the same answer, claims and evidence as `answer()` for 2026-06-08 and 2026-07-13
- [x] T007 [P] [US8] In tests/test_triage.py: dropping `territory:MID_ATLANTIC` on 2026-07-13 removes its story, adds "Left out of this brief by the analyst: Mid-Atlantic.", renumbers the stories, and the triage record shows `{story: territory:MID_ATLANTIC, outcome: dropped, layer: human}`; reordering puts Mid-Atlantic first
- [x] T008 [P] [US8] In tests/test_triage.py: no card has a digit outside a claim token before rendering (`digits_outside_tokens` on the card templates) and every plan claim resolves to a plan evidence item on the plan's data version; 2025-04-21 gives state `ROUTINE` with no cards
- [x] T009 [P] [US8] In tests/test_rbac.py: `POST /api/briefing/triage` is 401 signed out, 403 for the director and forecast roles, 200 for the analyst; a decision with a stale `plan_id` is 409; a non-proposed story ID is 400

### Implementation for US8

- [x] T010 [US8] Create agents/brand-briefing/briefing_baseline/triage.py: `build_plan(reg, front)` returns the TriagePlan dict per data-model.md: card IDs `territory:<TERRITORY_ID>`, `plan:<plan_id>` or `competitor:BXE`; the first `MAX_STORIES` territory or plan candidates `proposed: investigate`, the rest `over_cap`; `what_moved` from `stages.territory_change` (territory), a plan-level claim (plan), or a Metacora share claim (competitor); `decision`, `population` (territory names, no counts), `granularity`, `time` (dates only) per research.md R3; the focus territory's decision says the question names it; `dropped` lists quiet territories ("within their normal range") and withheld ones (reasons from `p.status`), layer `code`; `plan_id = "t-" + sha256(question | data_version | proposed IDs)[:12]`; state `TRIAGE_REVIEW`, `ROUTINE` (no cards) or `CALENDAR` (calendar mode)
- [x] T011 [US8] In agents/brand-briefing/briefing_baseline/pipeline.py add `triage(question, db)` (front plus `build_plan`, with the plan's claims and evidence, rendered) and `run_with_plan(question, decision, db)`: recompute the plan, raise `StalePlan` on a `plan_id` mismatch, raise `ValueError` for an ID not proposed for investigation, run `_investigate` in the decision's order, add the "Left out of this brief by the analyst: …" line when stories were dropped, and return `{envelope, triage_record, flow}` with `triage_record.default` true when the decision equals the proposal
- [x] T012 [US8] In src/pharmagentics/api/schemas.py add `StoryCard`, `TriagePlan`, `TriageDecision` (`plan_id: str`, `stories: list[str]`, extra forbidden) and optional `BriefingQuery.triage: TriageDecision | None = None`
- [x] T013 [US8] In src/pharmagentics/api/service.py add `run_triage(query)` and pass `query.triage` to the pipeline in `run_briefing` (no decision: today's path); map `StalePlan` to a new `service.StalePlan` and the bad-ID `ValueError` to `OutsideRelease`-style 400
- [x] T014 [US8] In src/pharmagentics/api/app.py add `POST /api/briefing/triage` (analyst action `run`, `Cache-Control: no-store`, UAT event `triaged` with latency, `plan_id` and card count) and return 409 for a stale plan in `POST /api/briefing/query`; store `triage` and `flow` inside the brief's `result`
- [x] T015 [US8] In src/pharmagentics/api/store.py make `brief_id` hash the decision's story list only when `triage.default` is false (research.md R6)
- [x] T016 [US8] In frontend/figma-make/src/agent/briefingApi.ts add `StoryCard`, `TriagePlan`, `TriageDecision` types, `getTriage(query)` with contract checks (cards have `id`, `proposed`, the four question strings; claims resolve to evidence), and a `triage` argument on `getBriefing`
- [x] T017 [US8] In frontend/figma-make/src/App.tsx add the triage review screen between "Generate" and the brief: one card per story with title, "what moved", and Decision / Population / Granularity / Time; an Investigate toggle and up/down buttons for `investigate` cards; over-cap cards and code-dropped territories shown read-only with reasons; "Approve plan and investigate" sends the decision; ROUTINE and CALENDAR plans show one line and an approve button

**Checkpoint**: US8 tests pass; in the browser the analyst reviews a plan and gets the matching brief.

## Phase 4: User Story 7 — The analyst sees how the brief was made (P1)

**Goal**: Every analyst-view brief carries its seven-stage flow with run states and actors; leaders never get it.

**Independent test**: Run 2026-06-08 on the scripted engine; read the stage list (spec US7).

### Tests for US7

- [x] T018 [P] [US7] In tests/test_triage.py: the flow for 2026-05-04 has 7 stages; stage 2 states `["VALIDATION_WARNING"]` naming New England; stage 3 `INVESTIGATION_REQUESTED`; stage 4 actors are code triage rules, human plan review, and code "fixed order of checks (manager off)", states `TRIAGE_REVIEW, INVESTIGATING, EVIDENCE_RECEIVED`; 2025-04-21 stage 3 is `ROUTINE` and stage 4 is skipped
- [x] T019 [P] [US7] In tests/test_rbac.py: the analyst view has `flow` with stage 7 `IN_REVIEW` while pending and `PUBLISHED` after approval (`RETURNED` after rejection); the leadership view has no `flow` and no `triage`

### Implementation for US7

- [x] T020 [US7] In agents/brand-briefing/briefing_baseline/triage.py add `stage_flow(front, plan, decision, verified)` returning the StageFlow list per data-model.md (`actors` items `{kind: code | agent | llm | human, name}`, Briefing §6 state names), with stage 7 `IN_REVIEW`
- [x] T021 [US7] In src/pharmagentics/api/views.py set stage 7 states from the review (`pending` → `IN_REVIEW`, `approved` → `PUBLISHED`, `rejected` → `RETURNED`) in `analyst()`; keep `LEADERSHIP_FIELDS` unchanged (it already excludes `flow` and `triage`)
- [x] T022 [US7] In frontend/figma-make/src/App.tsx add a collapsible "How this brief was made" panel to the analyst brief: seven rows with stage name, actor chips (Code, Agent, LLM, Person, each with its name) and states; also show the triage record (which calls were code and which were yours)

**Checkpoint**: US7 tests pass; the panel shows in the analyst view and never in the leadership view.

## Phase 5: Polish and cross-cutting

- [x] T023 Run the full suite `uv run pytest -q` and the scripted eval run; `uv run python -m eval gate <new-run-id> c58f99fc6e09` must pass (B-VII)
- [x] T024 Rebuild and recheck locally: `docker compose up --build`; run quickstart.md section 3 in the browser flow via the scripted end-to-end script
- [ ] T025 Deploy the app to Cloud Run: `uv run python deploy/gcp.py app --project pharmagentics --account mwc2150@columbia.edu`; rerun the end-to-end script against the cloud URL
- [x] T026 [P] Update the spec index row for brief-002 in specs/README.md (Phase A done) and the "Implemented functionality" text in frontend/figma-make/src/App.tsx

## Dependencies

- Phase 2 blocks everything. Inside it, T003's fixture is written before T002 changes the pipeline, and its test runs after.
- US8 (T004 to T017) before US7 (T018 to T022): the flow reports the triage state and is returned by `run_with_plan`.
- T012 → T013 → T014 → T016 → T017 (contract, service, route, client, screen).
- Polish after both stories.

## Parallel opportunities

- T004 to T009 (tests, different functions) together; T018 and T019 together.
- T012 (schemas) can be written while T010 and T011 are in progress.
- T026 any time after T017.

## Implementation strategy

MVP is Phase 2 plus US8: the analyst reviews a triage plan on the hosted app. US7 then adds the flow panel. Each checkpoint is shippable to Cloud Run.

## Notes

- Baseline run IDs: scripted `c58f99fc6e09` (2026-11-04); before Phase A `3de6fe53d21d` (T001, same scores); after Phase A `ba76420932c3`: `eval gate` passes against `c58f99fc6e09`, every gated check equal (2026-11-11).
- T024 checked with the end-to-end script through real Keycloak sign-in (triage, a P1 drop, flow, leadership view); the browser walk-through is for Michael.

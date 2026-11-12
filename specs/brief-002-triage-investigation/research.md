# Research: brief-002 Phase A

No `[NEEDS CLARIFICATION]` in the Technical Context. FR-005's open item (A1, the junction for the agent) is out of Phase A: with the manager off, code makes every triage call (Clarifications, 2026-11-11).

## R1. Where to split the pipeline

- **Decision**: Split `_brief()` into `_front()` (stages 1 to 3: load and pin, validation gate, restatements, KPIs, screen, competitor check) and `_investigate()` (stage 4 stories, then the template and verification). `answer(question)` calls both with the default order, exactly as today. A new `run_with_plan(question, decision)` calls both with P1's order. `triage(question)` calls `_front()` and builds the plan.
- **Rationale**: `answer()` stays byte-identical, so the scripted eval run, the golden-set scores and the gate are untouched (B-VII). One code path for both keeps them from drifting.
- **Alternatives**: Re-implementing stage 4 for the app (drift risk); adding a `plan=` argument to `answer()` (changes the eval entry point's signature).

## R2. What a candidate story is

- **Decision**: Three kinds, each with a stable ID: `territory:<ID>` (from `screen()`, kind territory), `plan:<plan_id>` (access-event plan stories from `screen()`), `competitor:BXE` (continuing Metacora, when `competitor_status()` returns text). The first `MAX_STORIES` (4) territory-or-plan candidates are proposed for investigation; candidates beyond the cap are listed as "over the story cap" (code). Quiet territories and withheld territories are listed as dropped by code, with reasons.
- **Rationale**: Mirrors what the scripted brief does today, so a default plan reproduces it (US8 scenario 2).
- **Alternatives**: Letting P1 add capped candidates (breaks the story cap, B-V); one card per raw candidate rather than per story (no grouping exists in the scripted engine yet).

## R3. Card contents (FR-022)

- **Decision**: Each card: title; rank; `what_moved` (a sentence from the same claim helpers the brief uses, so every number is a claim); and the four questions from the course triage: **Decision** (why code flagged it, and the proposed action: "investigate: data check, then access, promotion, supply and competitor"); **Population** (the territories whose cuts pass the gate in every week, by name; withheld ones named); **Granularity** (territory, or the named plan); **Time** (requested weeks and baseline weeks, as dates).
- **Rationale**: Dates are allowed in text; counts become names, so no digit sits outside a token. The four questions are the ones P1 needs to approve quickly.
- **Alternatives**: Cost and rights (the fifth question) is per release, not per story; it stays in the data plan doc.

## R4. Plan identity and staleness

- **Decision**: `plan_id = "t-" + sha256(question | data_version | proposed story IDs)[:12]`. The plan is not stored; on run, the server recomputes it and refuses a decision whose `plan_id` does not match (409, "the plan changed; review it again").
- **Rationale**: Code triage is deterministic; recomputing is cheap (about 2 s) and avoids a store. Pins the data version (B-III).
- **Alternatives**: Storing plans (another document type, expiry rules).

## R5. P1's edits and the triage record

- **Decision**: A decision lists the story IDs to investigate, in order. Allowed: any subset of the proposed stories, in any order. Refused (400): an ID that is not proposed (withheld, quiet or over the cap). The triage record lists every candidate with its outcome and the layer that decided it: `code` (proposed, dropped, capped) and `human` (dropped by P1, moved by P1, approved). When P1 drops a story, the brief adds one line: "Left out of this brief by the analyst: <names>." Nothing else in the text changes.
- **Rationale**: FR-002 (record the layer of each call), FR-023, US8 scenario 3; the brief stays honest about what it did not check.

## R6. Brief identity with a decision

- **Decision**: `brief_id` hashes the decision's story list only when it differs from the default, so existing brief IDs and approvals stay valid.
- **Rationale**: Two different decisions are two different briefs; the default decision is the same brief as before.

## R7. Stage flow (FR-024)

- **Decision**: The pipeline returns, with `run_with_plan()`, a list of seven stages: number, name, actors (each `{kind: code | agent | llm | human, name}`), run states reached (Briefing §6 names), and a short note. Scripted: 1 code, LOADED; 2 code, VALIDATED or VALIDATION_WARNING (withheld territories named); 3 code, INVESTIGATION_REQUESTED or ROUTINE; 4 code triage plus human review (TRIAGE_REVIEW), then code investigation "fixed order of checks, manager off" (INVESTIGATING, EVIDENCE_RECEIVED); 5 code template, DRAFTED; 6 code checks, VERIFIED; 7 human, computed by the API from the review state: IN_REVIEW, PUBLISHED (approved in UAT) or RETURNED (rejected). Agent snapshots (Phase B, core-007 US7) fill agent names in stage 4.
- **Rationale**: Briefing §6 states and §9 modes; B-II.
- **Alternatives**: Deriving the flow from MLflow spans (tracing is off in the app; spans are an eval-time feature).

## R8. API and UI shape

- **Decision**: `POST /api/briefing/triage` (analyst, action `run`) returns the plan with its claims and evidence. `POST /api/briefing/query` accepts an optional `triage` decision; without one it behaves as today (keeps Meghna's contract tests). The UI always goes through triage (A10, always on in UAT). The analyst view adds `flow` and `triage`; the leadership view's allow-list already excludes them.
- **Rationale**: Backward compatible; one round trip per step; no state between the two calls but the `plan_id`.

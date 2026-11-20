---

description: "Tasks for brief-003 slice 1: memo outline and projected national"
---

# Tasks: Narrative and Renderer, slice 1 (memo outline and projected national)

**Input**: `specs/brief-003-narrative-renderer/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: Included. SC-011 asks for a hand-calculation check on every dev week, and the eval gate (B-VII) is the merge condition.

**Scope**: Slice 1 only. User Story 7 (projected national) and User Story 2 (memo outline), with the parts of User Story 4 the outline moves (restatement in §2, next checks in §5). Charts, evidence tables, CSV and the UI's section rendering are slice 2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US7, US2, US4 from spec.md

---

## Phase 1: Setup

**Purpose**: baselines and the data layer the projection reads.

- [X] T001 Take baselines at `c15ccde` in this worktree's MLflow store before any code change: `uv run python -m eval run --system briefing_scripted --lane briefing`, then `--system briefing_agent --lane briefing --model anthropic:claude-haiku-5-5`; record both run IDs in specs/brief-003-narrative-renderer/tasks.md (Notes)
- [X] T002 Add `reporting.v_rx_projection` to sql/001_reporting_views.sql per contracts/v_rx_projection.md: one row per (week_start, territory_id, product_id) over `reporting.v_feed_health`; `basis` = 'observed' iff PASS, 'projected' iff FLAG and every `flag_reasons` item in (MISSING_RX_KEYS, ROW_COUNT_MISMATCH, LOW_OR_INVALID_COVERAGE, LATE_OR_UNKNOWN_DELIVERY, SOURCE_NOT_COMPLETE) and `panel_coverage_ratio >= 0.5`, else 'estimated'; `observed_trx` and `projected_trx` NULL when estimated
- [X] T003 Rebuild and check the database: `uv run python src/pharmagentics/data/load_duckdb.py` and `uv run python src/pharmagentics/data/check_duckdb.py`; confirm the data version stays `47bcfd650564`

---

## Phase 2: Foundational

**Purpose**: shared pieces both stories need.

- [X] T004 Add `"reporting.v_rx_projection"` to `ALLOWED` in src/pharmagentics/tools/registry.py (one-line hunk; the main tree has another session's edit in this file)
- [X] T005 [P] Add projection SQL builders to src/pharmagentics/tools/queries.py: `PROJ = "reporting.v_rx_projection"`, `projection_ctes(weeks)` (wk, cut, clean, share, nat CTEs per research R3 and R4), `projected_national(weeks)` (average weekly national), `projected_territory(weeks, t)` (average weekly territory value, estimated by share × national), `projection_cell(week, t, col)` (one view column)
- [X] T006 [P] Add an optional `sections: list[dict] | None = None` field to `AnswerEnvelope` in eval/harness/envelope.py (new optional field; scorers ignore it)

**Checkpoint**: the view is queryable through `Registry`, and every projection value is one SELECT.

---

## Phase 3: User Story 7 - A national number every week (Priority: P1)

**Goal**: every brief states a projected national TRx built territory by territory, labelling projected and estimated territories, and never names a driver for them.

**Independent Test**: 2026-05-04 gives national 4,491 with New England projected at 407 (observed 267, coverage 0.656); a routine week's projected national equals the observed sum; 2026-07-06 gives Great Lakes estimated at 620.

- [X] T007 [P] [US7] Write tests/test_projection.py: for all 104 weeks, `projected_national([w])` equals an independent hand calculation from `raw.rx_weekly` and `reporting.v_feed_health` (observed ÷ coverage per projectable territory, share rule for the rest) to the integer rounding rule (SC-011); the three flagged weeks give the bases and values in research.md; a PASS-only week equals `sum(trx)` of `reporting.v_reportable_rx`
- [X] T008 [US7] Create src/pharmagentics/tools/projection.py: `build(reg, p) -> Projection` with `national` token (None when no week can be reported), one row per territory (token, worst basis across `p.weeks`, non-observed weeks, observed and coverage tokens for a single projected week), and `table_lines()` returning the §2 table lines ("- New England: {cN} (projected: observed {cM} at panel coverage {cK})", "- Great Lakes: {cN} (estimated from its share of national in the four clean weeks before)")
- [X] T009 [US7] Add `method_lines(proj)` to src/pharmagentics/tools/projection.py for §4 (how projected and estimated territories were built, which weeks; no digits) and `least_sure_candidates(proj)` (estimated first, then projected)
- [X] T010 [US7] Add a test to tests/test_projection.py that no story or driver is opened for a projected or estimated cut (FR-023): the scripted brief for 2026-05-04 has no "Story" line naming New England and the one for 2026-07-06 none naming Great Lakes

**Checkpoint**: projection values reconcile on every week; nothing else changes yet.

---

## Phase 4: User Story 2 - The Monday memo, every week (Priority: P1)

**Goal**: scripted and agent briefs follow the six-section outline with code-built §1, §2, §4, §5, §6 and the same skeleton in both engines.

**Independent Test**: briefs for 2025-04-21 (routine), 2026-05-04 (withheld cut) and 2026-08-24 (eventful) each carry the six headings in order, §1's four statements in FR-021 order, and no digit outside a token.

### Tests

- [X] T011 [P] [US2] Write tests/test_memo.py: composition is pure (same parts, same template); six `## ` headings in order on the three dev weeks; §1 order: data warning (when withheld) → projected national → like-for-like change → brand share → least sure; least-sure rule picks New England on 2026-05-04 and the Low Pacific story on 2026-07-13; `digits_outside_tokens(template) == []`; `sections` numbers run 1, 2, 3, 3.1 …, 4, 5, 6
- [X] T012 [P] [US2] Add leadership-cut tests to tests/test_memo.py: `executive_summary` keeps title, §1, §2, §3 without "Checked, in this order" lists or "Considered and dropped", and §5; drops §4 and §6; an old brief without headings is cut as before

### Implementation

- [X] T013 [US2] Create src/pharmagentics/tools/memo.py: `HEADINGS` (Bottom line, The numbers, What changed and why, What the data can't tell us, Next checks, Appendix), `MemoParts` dataclass, `compose(parts) -> (template, sections)` per contracts/memo-envelope.md, empty-section sentences, and `render_sections(sections, claims, index)` returning `{number, title, text, prose, claims}`
- [X] T014 [US2] Add to src/pharmagentics/tools/memo.py the code builders: `title_lines(p)`, `bottom_line(reg, p, proj, stories)` (FR-021 order; data warning when any requested cut is withheld; restatement note; least-sure by research R8 with tokens re-claimed from the story's change SQL), `limits(reg, p, proj)` (data health, withheld focus, method lines, calendar note), `appendix(reg, p)` (method, data version, glossary terms used, copied from GLOSSARY.md)
- [X] T015 [US2] Rework agents/brand-briefing/briefing_baseline/pipeline.py to build `MemoParts` and call `memo.compose`; `_story` returns a StoryBlock without the "Next:" clause; keep `Front.out` for the triage context; return `sections` in the envelope
- [X] T016 [US2] Update src/pharmagentics/mcp_server/server.py: `brief_sections()` returns `title`, `numbers`, `limits`, `appendix`, `calendar`, `withheld_focus` (contracts/mcp-admin-tools.md); `story_section` closes without "Next:"; new admin tool `memo_close(competitor)` returning `bottom_line` and `next_checks`; add it to `ADMIN_TOOLS` and `build_server`
- [X] T017 [US2] Update agents/brand-briefing/briefing_agent/write.py: `sections_text` shows the memo skeleton to the writer; `assemble` builds `MemoParts` (writer answer → §1 prose, story sentences → §3.x prose) and calls `memo.compose`; `render` also returns rendered sections
- [X] T018 [US2] Update agents/brand-briefing/briefing_agent/__init__.py: call `memo_close` after the investigation and before `export_run`; `_section` tokens for the writer include §1, §2 and §4 lines; return `sections` in the envelope; out-of-scope path prefixes the scope line to the title
- [X] T019 [US2] Update agents/brand-briefing/briefing_agent/prompts/writer.md: the answer is §1's prose after code's statements and must not repeat them; story sentences are §3 prose; JSON shape unchanged
- [X] T020 [US2] Update `executive_summary` in src/pharmagentics/api/views.py to cut by heading (research R11), keeping today's behaviour for briefs without headings

**Checkpoint**: both engines emit the memo; tests T007 to T012 pass.

---

## Phase 5: User Story 4 - Restatements and next steps in the memo (Priority: P2, slice-1 part only)

**Goal**: the restatement reaches a section leaders see, and each open story, withheld cut and continuing competitor story has a next check with an owner and the decision it unlocks.

**Independent Test**: the 2026-07-13 brief has the 692 → 742 restatement in §2 and a restatement note in §1; §5 lists Pacific (Low: split by plan and specialty; sales leadership) and Metacora (marketing and sales).

- [X] T021 [P] [US4] Add a `DECISION` map beside `OWNER` in src/pharmagentics/tools/checks.py (the decision each driver's check unlocks)
- [X] T022 [US4] Add `next_checks(p, stories, competitor)` to src/pharmagentics/tools/memo.py (research R10): "- {subject}: {action}. Owner: {owner}. Unlocks: {decision}."; used by pipeline.py and `memo_close`
- [X] T023 [US4] Place `stages.restatements` lines in §2 and the one-line note in §1 in src/pharmagentics/tools/memo.py; add a test in tests/test_memo.py for the 2026-07-13 brief

---

## Phase 6: Golden cases, tests and the gate

**Purpose**: the golden set expects the projection, every suite passes, and the gate holds for both systems.

- [X] T024 [P] Update eval/golden/briefing/P1-Q2.yaml (then, reference_answer, facts `ne_projected_trx` 407 and `national_projected_trx` 4,491 via `reporting.v_rx_projection`; must-not-say unchanged) per research R13
- [X] T025 [P] Update eval/golden/briefing/P3-Q6.yaml (then, reference_answer with 692 → 742 and projected national 4,240; facts for old, new and projected national)
- [X] T026 [P] Add a row to eval/golden/CHANGELOG.md for P1-Q2 and P3-Q6 (source: ADR 0001, brief-003 v3) and an open item: the Drive user stories need the same change
- [X] T027 Run `uv run python -m eval check`; every fact recomputes
- [X] T028 Update string expectations in eval/tests/test_baselines.py, tests/test_agent_build3.py, tests/test_mcp_server.py, tests/test_briefing_api.py and tests/test_triage.py where the memo changed wording (headings, "Next:" moved to §5, title line); then `uv run pytest`
- [X] T029 Candidate `uv run python -m eval run --system briefing_scripted --lane briefing`; `uv run python -m eval gate <candidate> <T001 scripted baseline>` exits 0
- [X] T030 Candidate `uv run python -m eval run --system briefing_agent --lane briefing --model anthropic:claude-haiku-5-5`; `uv run python -m eval gate <candidate> <T001 agent baseline>` exits 0 (rerun once on a failure before it counts, research R15)
- [X] T031 [P] Update eval/README.md (results row for the memo runs) and record run IDs and gate output in specs/brief-003-narrative-renderer/tasks.md (Notes)
- [X] T032 Commit by path on feature/brief-memo-follow-ups (another session edits the main tree)

---

## Dependencies & Execution Order

- T001 runs first and must finish before any code change (the agent's MCP server reloads `src/` per case).
- Phase 1 → Phase 2 → US7 (Phase 3) → US2 (Phase 4) → US4 (Phase 5) → Phase 6.
- US2 depends on US7 (§1 and §2 state the projection). US4 depends on US2's composer.
- T029 and T030 run one after the other (local machine limits: sequential eval runs).

## Parallel Opportunities

- T005 and T006 (different files).
- T007 alongside T008 (test first, then module).
- T011 and T012 before T013.
- T024, T025, T026 together.

## Implementation Strategy

MVP is US7 + US2 on the scripted engine (T001 to T015 plus T020), which already answers P1-Q2 and P3-Q6. Then the agent (T016 to T019), US4, and the gate. Nothing merges until T029 and T030 pass.

## Notes

- Baselines (T001), at `c15ccde`, worktree MLflow store: `briefing_scripted` `71e565e279a0`; `briefing_agent` on `anthropic:claude-haiku-5-5` `be655807ea8a`. Every gated check 1.000, 0 run errors.
- First candidates (T029, T030), before the assumption wording: scripted `6f48cbaba034`, gate exit 0; agent `1d9b819bf45b`, gate exit 0. The agent's `needed_revision` rose from 0 to 0.167: the new writer prompt said "do not repeat those numbers", so four answers named "the week before" without its token and the comparison check caught them (two §1 answers dropped). Fixed in the prompt, not by loosening the check.
- Final candidates on the committed code, after the assumption wording and the writer prompt fix: scripted `ca90ac39769c` (gate exit 0 against `71e565e279a0`), agent `83e4bb6adb0f` (gate exit 0 against `be655807ea8a`; `needed_revision` 0.042). Full test suite: 564 passed.

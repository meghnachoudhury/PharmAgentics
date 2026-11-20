# Research: brief-003 slice 1 (memo outline and projected national)

Decisions made while planning slice 1 on 2026-11-19. Each one resolves a gap between the spec and the code or the data. Numbers below come from `local/pharmagentics.duckdb` (data version `47bcfd650564`).

## What the data holds

Only three cuts in the release fail the feed gate, and only one has low coverage:

| Week | Territory | Coverage | Reasons |
| :- | :- | :- | :- |
| 2026-04-06 | Mid-Atlantic | 1.000 | RESTATEMENT_REVIEW |
| 2026-05-04 | New England | 0.656 | MISSING_RX_KEYS, ROW_COUNT_MISMATCH, LOW_OR_INVALID_COVERAGE, LATE_OR_UNKNOWN_DELIVERY, SOURCE_NOT_COMPLETE |
| 2026-07-06 | Great Lakes | 1.000 | DUPLICATE_RX_KEYS, ROW_COUNT_MISMATCH, SOURCE_NOT_COMPLETE |

Every passing cut has coverage 1.0. `reporting.v_reportable_rx` keeps only passing cuts, so no governed view shows New England's observed 267 TRx.

## R1. How tools reach a failed cut's TRx

- **Decision**: add the governed view `reporting.v_rx_projection` to `sql/001_reporting_views.sql` and to `Registry.ALLOWED`. It exposes the observed TRx only for cuts whose faults are all completeness faults (R2).
- **Rationale**: the hard rule is "agent tools read data only through the governed views"; a view is how the data layer grants a new, narrow read.
- **Alternatives**: read `raw.rx_weekly` (breaks the rule); project only from `v_reportable_rx` (New England would have no level, so the spec's scenario US7-2 fails).

## R2. Which failed cuts are projected and which are estimated

- **Decision**: a passing cut is *observed*. A failed cut is *projected* (observed ÷ coverage) when every reason is a completeness reason (missing keys, row-count mismatch, low coverage, late delivery, incomplete source) and coverage is at least 0.5. Any other failed cut is *estimated*: duplicate keys, restatement review, invalid metrics, unknown schema, unexpected cut, or missing or duplicate metadata, and any coverage below 0.5.
- **Rationale**: the spec's bands assume the observed rows are right but incomplete. Duplicate keys inflate the level (Great Lakes shows 670 with duplicates), and a cut under restatement review is not final (Mid-Atlantic shows 742, the revised value). Dividing either by coverage 1.0 would publish a number the gate rejected.
- **Consequence**: Mid-Atlantic 2026-04-06 is estimated at 711 and Great Lakes 2026-07-06 at 620. The 742 restated value still appears in the restatement disclosure.
- **Alternatives**: coverage bands only (publishes duplicate-inflated and under-review levels); leave such cuts out of national (no national level, which the spec rejects).
- **Spec gap**: the Clarifications define bands by coverage only. This rule adds the fault type; it is recorded in the spec's FR-022 note.

## R3. Which weeks give an estimated territory its share

- **Decision**: the four latest weeks before the target week in which **every** territory passes the gate and that are neither holiday nor plan-year-reset weeks.
- **Rationale**: the share is the territory's TRx over national TRx, so the national in those weeks must be complete. For 2026-05-04 this skips 2026-04-06 (Mid-Atlantic withheld) and uses 2026-03-30, 04-13, 04-20 and 04-27.
- **Alternatives**: the territory's own last four passing weeks (the spec's words), whose denominator can miss another territory and so inflate the share.

## R4. The estimate formula

- **Decision**: national = (sum of observed and projected territories) ÷ (1 − sum of the estimated territories' shares); an estimated territory = its share × national. With one estimated territory this is the same as others × s ÷ (1 − s).
- **Check**: 2026-07-06 gives national 4,285 and Great Lakes 620; 2026-04-06 gives 4,571 and Mid-Atlantic 711; 2026-05-04 gives 4,491 with New England projected at 407.
- **Edge**: if no territory in a week is observed or projected, the national is not given and §1 says the week cannot be reported (spec edge case).

## R5. Multi-week periods

- **Decision**: §1 and §2 state the weekly average of the projected national over `Period.weeks`, the same weeks the like-for-like change uses (calendar weeks left out when they are a minority). A territory row says which weeks were projected or estimated.

## R6. Section headings in the flattened text

- **Decision**: the flattened `answer` marks sections with heading lines `## Bottom line`, `## The numbers`, `## What changed and why`, `## What the data can't tell us`, `## Next checks`, `## Appendix`, with no section numbers. Stories keep "Story one:" labels. Section numbers (`1`, `3.1` …) live in the structured `sections` field.
- **Rationale**: a heading such as "3.1" is a number to the verifier (`digits_outside_tokens`) and to the `numbers_traced` scorer; exempting it would weaken a gated check.

## R7. Where restatements and data warnings go

- **Decision**: §1 leads with a one-line data warning when any cut in the period is withheld, and a one-line note when an earlier week was restated. The restatement itself (old value, new value, date, reason) sits in §2 beside the KPIs. The full gate detail (rows, keys, coverage, lag) sits in §4.
- **Rationale**: leaders see §1, §2, §3 and §5 only. P3-Q6 is the director's question, so the restatement must reach a section she sees.

## R8. The number we are least sure of (§1)

- **Decision**, in order: an estimated territory in the period; else a projected territory; else the lead number (the change) of the lowest-confidence story (Low before Medium before High; ties go to the first story); else the change built on the fewest prescriptions, which is the week-over-week change when the brief states one and the like-for-like change otherwise.
- **Rationale**: the Clarification lists estimated → lowest-confidence story → fewest TRx; User Story 7 scenario 2 adds that a projected territory comes first when nothing is estimated.

## R9. One composer for both engines

- **Decision**: `pharmagentics/tools/memo.py` takes the parts (code lines per section, story blocks, writer prose) and returns the token template and the `sections` list. The scripted pipeline calls it directly; the agent calls it after the MCP admin tools hand back the parts.
- **Rationale**: FR-020 (same skeleton); and new modules keep clear of the other session's edits to `stages.py`.

## R10. Next checks (§5)

- **Decision**: code builds §5 from the stories and the data: one line per story (supported drivers → their owners from `OWNER`; Low confidence → split by plan and specialty, sales leadership), one per withheld cut (re-run when the corrected feed lands; commercial analyst), and one for a continuing competitor story (marketing and sales). Each line names the decision it unlocks from a new `DECISION` map beside `OWNER`. The "Next: …" clause leaves the §3 story text so it is not said twice.

## R11. Leadership view

- **Decision**: `executive_summary` keeps the title, §1, §2, §3 (without the "Checked, in this order" list and the "Considered and dropped" line) and §5; it drops §4 and §6. Older briefs without headings keep today's behaviour.

## R12. Envelope

- **Decision**: `AnswerEnvelope.sections: list[dict] | None`. Each section: `number`, `title`, `text` (rendered code lines), `prose` (rendered writer or template prose), `claims` (indexes into the envelope's `claims`). Story subsections are their own entries (`3.1`, `3.2`). `chart` and `evidence` stay absent until slice 2.

## R13. Golden cases

- **Decision**: P1-Q2 expects §1 to open with New England's incomplete feed, §2 to give a projected national of 4,491 with New England projected at 407 (267 at coverage 0.656), §4 to name the three-plus reasons, and no New England story. P3-Q6 expects the 692 → 742 restatement and a projected national of 4,240 for 2026-07-13 with all territories observed, and like-for-like figures that state their territory count. Facts recompute through SQL. The Drive copy of the user stories needs the same change; that is an open item in the golden CHANGELOG, not a blocker (the case follows ADR 0001 and the spec, which Michael approved).
- **Spec correction**: User Story 2 scenario 2 says the like-for-like change covers "7 of 8 territories". Against the four weeks before 2026-05-04 it covers 6 of 8, because Mid-Atlantic 2026-04-06 is also withheld; week over week it covers 7 of 8. The spec is corrected to "states its territory count".

## R14. The writer

- **Decision**: the writer's `answer` becomes the §1 prose after code's four statements, and each story sentence the §3.x prose. The prompt shows the memo skeleton and says the answer must not repeat §1's numbers. Its JSON shape is unchanged, so the verification and one-revision logic stay as they are.

## R15. Gate

- **Decision**: baselines at `c15ccde` in this worktree's MLflow store: `briefing_scripted` and `briefing_agent` on `anthropic:claude-haiku-5-5`. Candidates on the same 24 cases. Merge only if `python -m eval gate` passes for both. Agent reruns vary, so a failure on the agent is rerun once before it counts.

## R16. Database rebuild

- **Decision**: the view needs `load_duckdb.py` once per checkout. The Docker image runs the loader, so Cloud Run picks it up. The data version is the manifest hash and does not change.

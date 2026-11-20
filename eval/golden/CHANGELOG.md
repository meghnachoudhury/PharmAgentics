# Golden set changelog

A case changes only after its source changes (Evaluation Pack, user stories or the Forecast eval design: pack first, then cases). One line per change.

| Date | Cases | Change | Source |
| :- | :- | :- | :- |
| 2026-10-29 | All 42 | Drafted by `python -m eval import-stories`: one case per persona question, C-001 to C-024 (Briefing P1-Q1 to P4-Q6) and F-001 to F-018 (Forecast CA-Q1 to FM-Q6). All `status: draft` until reviewed by hand. | `docs/planning/user-stories.md` (copy of 2026-10-23, checked against Drive 2026-10-29) |
| 2026-10-29 | 14 | Added 69 facts (number plus the SQL that recomputes it) to P1-Q1, P1-Q2, P1-Q3, P1-Q5, P2-Q1, P2-Q2, P2-Q5, P3-Q1, P3-Q2, P3-Q4, P3-Q5, CA-Q1, CA-Q2, FM-Q1. All recompute from `day1-v1`. | `local/pharmagentics.duckdb` |
| 2026-11-20 | P1-Q2, P3-Q6 | Projected national (brief-003 slice 1). P1-Q2: New England is projected at 407 (267 observed at coverage 0.656) and labelled, projected national 4,491, still no New England story; "then" follows the memo outline. P3-Q6: projected national 4,240 for 2026-07-13, the 692 → 742 restatement where leaders see it, like-for-like on 7 of 8; "national sums cover 7 of 8" becomes "the projected national labels the missing territory". 8 new facts, computed from the raw feed and the existing views, not from `reporting.v_rx_projection`. | `docs/adr/0001-projected-national-without-projected-drivers.md`, `specs/brief-003-narrative-renderer/spec.md` v3 (Clarifications 2026-11-19) |
| 2026-11-20 | FU-1 to FU-6 (C-025 to C-030) | Six draft two-turn cases (brief-006 FR-013): a section reference, a new query, a scope change, a negation trap, a "why" with no supported driver, a request for an individual rep. Each has a `follow_up`; the harness scores the whole exchange on the gated checks plus `sections_exist`. Drafted by Claude from real weeks (Session 2026-11-20); 5 facts. Michael labels them. | `specs/brief-006-follow-ups/spec.md` FR-013 |
| 2026-11-20 | P1-Q2, P3-Q6 | `then` and `reference_answer` set to the Drive master's new wording, which calls projected and estimated levels an assumption. Facts unchanged. | Drive "User stories", SoT drop 2026-11-20 |

## Open before freezing

- **Questions without a period** (the story names no weeks): P2-Q6, P4-Q2, P4-Q3, P4-Q5, P4-Q6, FM-Q4. Each carries a `review_note`.
- **Briefing categories** are draft assignments to the Evaluation Pack §4 taxonomy; check them.
- **Forecast scenarios** (`scenario: null`): Alvin and Sienna map each Forecast case to TC-01 to TC-12 and confirm the cases (core-006).
- **Facts** for the other 28 cases.

# Feature Specification: Data classification labels per tab

**Spec ID**: `core-009-data-classification` (shared; started by Michael, owned from here by Meghna)
**Feature Branch**: `feature/finalize-data-classification`
**Created**: 2026-11-19
**Status**: v1 tab and role mappings finalized. Labels only; no enforcement yet.
**Input**: Replace the "Synthetic data" chip with a data classification on every tab, on four levels (public, proprietary, confidential, sensitive, the highest), so that role-based access can later follow the level of data each tab shows.

## Context

core-007 decides access by role and view (analyst or leadership). This spec adds a second, independent idea: how sensitive the data on a tab is. Version 1 only states and shows the level. Meghna's finalized v1 mappings are recorded below. Enforcement is a later version, so a role can never open a tab above its clearance.

## Clarifications

### Session 2026-11-19

- Q: Is anything refused by level in version 1? → A: No. Labels only. Access stays exactly as core-007 sets it.
- Q: Where do the levels live? → A: One file, `src/pharmagentics/api/classification.json`: the four levels in order, a level per tab or view, and a clearance per role. Changing a level needs no code.
- Q: What do the starting values say? → A: They mirror today's access, so no badge contradicts what a role can already see: analyst views (evidence, SQL, claims) are Confidential; leadership summaries and the approved lists are Proprietary; nothing is Public or Sensitive yet. Analysts are cleared to Confidential, leaders to Proprietary. These are placeholders for Meghna.

### Session 2026-11-20

- Q: What is the final v1 tab and view mapping? → A: The following policy is confirmed for the current screens. All four levels remain available; no current screen is Public or Sensitive.

  | Screen or view | Level | Reason |
  | :- | :- | :- |
  | Briefing Overview, New Briefing, Analyst report | Confidential | Detailed brand KPIs, investigation scope, claims or evidence |
  | Forecast New Explanation, Analyst report | Confidential | Detailed investigation inputs and results |
  | Approved Briefings, Forecast To Review, Approved Explanations | Proprietary | Internal summaries and review information |
  | Briefing and Forecast leadership reports | Proprietary | Internal executive summaries |
  | Evaluation | Proprietary | Internal evaluation scores and aggregated usage metrics |

- Q: What clearances do the roles retain? → A: Briefing and Forecast analysts retain Confidential clearance. The Brand Director and Brand Manager retain Proprietary clearance. This resolves core-009 open item 1; the mappings mirror their existing analyst and leadership permissions.
- Q: What does this PR implement? → A: User Story 1: finalize the labels and clearance mappings, classify Evaluation, and keep the Briefing and Forecast tab labels visible on mobile. Classification does not grant or refuse access in v1. User Story 2 remains a later change; how clearance enforcement combines with core-007 is still open item 2.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See how sensitive a tab is (Priority: P1)

Each tab and each view (analyst, leadership preview) shows a small badge with its level, so the person knows how to treat what they see.

**Independent Test**: Sign in as each persona and check every tab and view shows the level from the file.

**Acceptance Scenarios**:

1. **Given** a signed-in participant, **When** they open any tab or switch view, **Then** a badge shows that tab's or view's level from the file.
2. **Given** the file changes a level, **When** the page reloads, **Then** the badge shows the new level, with no code change.
3. **Given** a tab missing from the file, **When** it is shown, **Then** it shows no badge, and the tests fail (every tab must be classified).

### User Story 2 - Enforce access by level (Priority: P2, not built)

A role whose clearance is below a tab's level cannot open it: the server refuses, and the tab is not shown. The tab levels and role clearances are finalized in the 2026-11-20 clarification (core-009 open item 1, resolved). [NEEDS CLARIFICATION: how classification combines with the core-007 role and view checks, for example whether either may refuse (core-009 open item 2, Meghna)]

### Edge Cases

- A login holding two roles (the mentor and both-lane logins) has one clearance per lane.
- A level name not among the four in the file is a configuration error, caught by the tests.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The levels MUST be, from lowest to highest: Public, Proprietary, Confidential, Sensitive, defined once in `classification.json`.
- **FR-002**: Every tab and view the app shows MUST have a level in the file, and every role in `roles.json` MUST have a clearance; the tests MUST fail otherwise.
- **FR-003**: `GET /api/classification` MUST return the levels, the level of every tab and view, and the caller's clearance per lane, to signed-in callers with a role only.
- **FR-004**: The web app MUST show each tab's and view's level as a badge, and MUST NOT show the old "Synthetic data" chip.
- **FR-005** (version 1): Classification MUST NOT change what any role can open. Enforcement is User Story 2.

### Key Entities

- **Level**: one of the four, ordered.
- **Tab classification**: a tab or view key (for example `briefing.view.analyst`) and its level.
- **Clearance**: a role and the highest level it may see.

## Success Criteria *(mandatory)*

- **SC-001**: 100% of tabs and views show a badge that matches the file.
- **SC-002**: A level change in the file shows after a reload, with no code change.
- **SC-003**: No role gains or loses access in version 1 (the core-007 role tests pass unchanged).

## Assumptions

- The data is synthetic today; the levels describe how the real data would be treated, which is what UAT should rehearse.
- Not in scope for version 1: enforcement, per-field redaction, audit of level changes.

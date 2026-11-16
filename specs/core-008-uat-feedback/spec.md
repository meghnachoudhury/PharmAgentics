# Feature Specification: UAT Feedback (session rating and platform questionnaire)

**Spec ID**: `core-008-uat-feedback` (shared; owner: Michael; requested by the mentor, Dr. Admasu)
**Feature Branch**: `feature/uat-feedback`
**Created**: 2026-11-15
**Status**: Draft v1. Built on the branch; not yet deployed.
**Input**: The mentor asked for two kinds of feedback from people who try PharmAgentics: a quick "is PharmAgentics doing good, fine or bad this session?", and a questionnaire about the overall platform for the broader user.

## Context

core-007 (UAT deployment) records what people do: timings, approvals, flagged claims. It does not record what they think. This spec adds two ways to ask. Both work for every role in both lanes (Briefing and Forecast), are stored the way core-007 stores UAT events (a pseudonymous participant ID, never a name or an email), and are read by an owner through a report, not through the web app.

## Clarifications

### Session 2026-11-15

- Q: When is the session rating asked? → A: Always available in the page header, and once at sign-out ("before you go") if the session has no rating yet. A session is one sign-in. The last rating of a session counts.
- Q: What does the questionnaire contain? → A: The System Usability Scale (SUS: ten standard statements, scored 0 to 100 by code), four questions about trusting what PharmAgentics says, a recommend score (0 to 10), which parts were used, how often the person would use something like it, and three written questions. Every question is optional. These are drafts for the mentor to review: see the open item below.
- Q: Who can read the answers? → A: Owners and teammates with access to the state bucket, through a report. No role can read other people's answers in the app. A participant can reopen their own questionnaire to update it.
- Q: Are the answers anonymous? → A: Pseudonymous, like every UAT event (core-007 FR-025): the same participant ID across their ratings and questionnaire, no name or email. Written answers are stored as typed, so the form asks people not to write names or personal details.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Rate the session in one click (Priority: P1)

A participant clicks Good, Fine or Bad in the page header. They may add a note saying why. If they sign out without having rated, the app asks once ("before you go") and lets them skip.

**Why this priority**: It is the lowest-effort signal and the one the mentor asked for first.

**Independent Test**: Sign in as each persona, rate, change the rating, sign out with and without a rating.

**Acceptance Scenarios**:

1. **Given** a signed-in participant, **When** they click Good, **Then** one rating is stored with their role, a pseudonymous ID and the workspace they were in, and the header shows "This session: Good".
2. **Given** a rating, **When** they change it or add a note, **Then** the new submission is stored, and the report counts the session once, by its last rating.
3. **Given** a participant who has not rated, **When** they click Sign out, **Then** a prompt asks for a rating and offers "Skip and sign out"; if they have rated, they sign out straight away.
4. **Given** a rating that could not be saved, **When** the participant submits, **Then** the app says so; it never shows "Thank you" for something that was lost.
5. **Given** a leader (Brand Director or Brand Manager), **When** they rate, **Then** it works the same; no persona is excluded.

---

### User Story 2 - Answer the platform questionnaire (Priority: P1)

From their account menu (or a dismissible banner), a participant opens a questionnaire about the whole platform, answers what they like, and sends it. Reopening it later shows their earlier answers so they can change them.

**Why this priority**: The mentor's second request; it gives a standard usability score and the written reasons behind it.

**Independent Test**: Answer all ten SUS statements and send; check the stored score against a hand calculation; send again with a change and check it replaced the first.

**Acceptance Scenarios**:

1. **Given** the questionnaire, **When** the participant answers some questions and sends, **Then** only the answered questions are stored, with the questionnaire version.
2. **Given** all ten SUS statements answered, **When** the answers are stored, **Then** a SUS score (0 to 100) is computed by code and stored with them; with fewer than ten, no score is stored.
3. **Given** an earlier submission, **When** the participant reopens the questionnaire, **Then** their answers are filled in, and sending replaces the earlier document (one per participant).
4. **Given** an answer outside the allowed values (a rating of 6, an unknown option, text over its limit, an unknown question), **When** it is sent, **Then** it is refused with a clear message and nothing is stored.
5. **Given** the questionnaire changed after the participant opened it, **When** they send, **Then** they are told to reload, and nothing is stored under the wrong version.

---

### User Story 3 - The owners read the results (Priority: P2)

An owner runs one command and gets a report: sessions rated good, fine and bad by persona; every written note; the SUS score; each question's mean; the net promoter score; the written answers by question. A CSV export is available for a spreadsheet.

**Why this priority**: Feedback nobody can read is wasted, and the mentor wants to see it.

**Independent Test**: Store a few ratings and responses, run the report, and check each number by hand.

**Acceptance Scenarios**:

1. **Given** stored ratings, **When** the report runs, **Then** each session counts once, by its last rating, and counts are shown by persona.
2. **Given** stored questionnaires, **When** the report runs, **Then** the SUS mean, the net promoter score and every item's mean match a hand calculation.
3. **Given** the cloud deployment, **When** an owner or teammate runs `gcp.py feedback`, **Then** the bucket's feedback folder is downloaded and the same report is printed.
4. **Given** no feedback yet, **When** the report runs, **Then** it says so instead of failing.

---

### User Story 4 - Change the questions without code (Priority: P3)

The team or the mentor edits one file to reword, add or remove questions. A malformed edit fails the tests rather than a participant.

**Independent Test**: Edit the file, bump its version, run the tests and the report.

**Acceptance Scenarios**:

1. **Given** an edit that duplicates a question ID, uses an unknown type, drops the options of a choice question, or breaks the SUS list, **When** the tests run, **Then** they fail with the reason.
2. **Given** a new version, **When** a participant who answered the old one sends again, **Then** their answers are stored under the new version, and the report shows responses by version.

### Edge Cases

- A participant with no role in either lane (so no PharmAgentics access) cannot rate or answer: refused, not stored.
- A signed-out caller gets 401 before any validation, so no caller learns what a valid body looks like.
- The state store is unreachable: the participant sees an error, and a rating that was not saved is not remembered as given.
- A participant clears an answer by clicking it again: cleared answers are not sent.
- The same participant rates in two browsers at once: both ratings are stored, each under its own session.
- Written answers may contain personal details despite the warning: they are stored as typed and are readable only through the report; the report must not be posted publicly.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Any signed-in participant holding a role in either lane MUST be able to submit a session rating of good, fine or bad, with an optional note of at most 300 characters and the workspace they were in. Everyone else MUST be refused before validation (401 signed out, 403 no role).
- **FR-002**: A session is one sign-in. The report MUST count each session once, by its last rating, and MUST keep every submission in the stored history.
- **FR-003**: The page header MUST offer the rating at all times, and signing out without a rating MUST ask once and allow skipping.
- **FR-004**: The platform questionnaire MUST be defined in one versioned file with question types (agreement 1 to 5, recommend 0 to 10, choice, multiple choice, text), served by the API, and validated on submit: known questions, the right kind of value, allowed options, text length limits. Blank answers MUST be dropped, and a submission with no answers MUST be refused.
- **FR-005**: The questionnaire MUST include the ten System Usability Scale statements. The SUS score MUST be computed by code (positive statements score the answer minus 1, negative ones 5 minus the answer, summed and multiplied by 2.5) and stored only when all ten were answered.
- **FR-006**: A participant MUST have at most one stored questionnaire (sending again replaces it) and MUST be able to read back their own answers and nobody else's.
- **FR-007**: A submission for another questionnaire version than the current one MUST be refused with a reload message.
- **FR-008**: Stored feedback MUST hold the pseudonymous participant ID, role names and personas, a timestamp and the app version, and MUST NOT hold a name, email or sign-in identifier (core-007 FR-025).
- **FR-009**: A feedback save that fails MUST be reported to the participant and MUST NOT be reported as saved.
- **FR-010**: Stored feedback MUST live in the same state store as other UAT state (local folder or Cloud Storage bucket) under a `feedback/` prefix, one document per rating and one per participant questionnaire. The web app MUST NOT expose any route that returns other participants' feedback.
- **FR-011**: A report command MUST summarize ratings (by rating and by persona, with the notes), the SUS score, each question's mean or counts, the net promoter score and the written answers, in markdown, and MUST be able to write CSV files. A cloud command MUST download the bucket's feedback folder and run the same report.
- **FR-012**: A malformed edit of the questionnaire file MUST fail the test suite.

### Key Entities

- **Pulse**: one rating submission: time, session, pseudonymous participant, roles, personas, rating, note, workspace, optional reference, app version.
- **Questionnaire**: a versioned list of sections and questions (the file).
- **Survey response**: one per participant: time, questionnaire version, roles, personas, answers, SUS score, number of updates.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A participant can rate a session with one click, and the rating is stored in under 2 seconds on a warm app.
- **SC-002**: 100% of stored feedback documents hold no name, email or sign-in identifier (checked by test across every persona).
- **SC-003**: SUS scores computed by code equal a hand calculation on six reference answer sets, and no score is stored for incomplete sets.
- **SC-004**: 100% of signed-out and role-less requests to the feedback routes are refused with 401 or 403.
- **SC-005**: The report's counts and means equal hand calculations on a reference set of ratings and responses.
- **SC-006**: The questionnaire is completed in under 8 minutes by the median participant (measured in UAT; the target may be adjusted once seen).
- **SC-007**: A bad edit of the questionnaire file is caught by the test suite 100% of the time for the five mistakes covered (duplicate ID, unknown type, bad version, missing options, broken SUS list).

## Assumptions

- The SUS is a published, widely used instrument. A mean of 68 is the commonly cited average across products and above 80 is usually read as excellent; the report states both as context, not as targets.
- Statement wording says "PharmAgentics" where the standard says "the system", a common adaptation.
- Feedback is for learning about the platform; it is not used to gate a merge or score an agent, and the eval harness never reads it.
- Participants are the selected UAT users (core-007), so volumes are small; the report reads every document each time.
- [NEEDS CLARIFICATION: the mentor's own questionnaire items, if he has them: the shipped questions are a draft to review (core-008 open item 1)]
- [NEEDS CLARIFICATION: whether participants should see aggregate results, or only the owners (core-008 open item 2); today only owners and teammates with bucket access can]
- Not in scope: asking for a rating after each brief or forecast run, email reminders, anonymous (unauthenticated) responses, and importing feedback into MLflow (core-007 User Story 6 owns that import and can read the same files).

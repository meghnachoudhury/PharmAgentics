# Feature Specification: Follow-ups and Threads

**Spec ID**: `brief-006-follow-ups` (Briefing lane; owners: Michael, Meghna)
**Feature Branch**: `feature/brief-memo-follow-ups`
**Created**: 2026-11-19 | **Updated**: 2026-11-19
**Status**: Draft v1. Not started.
**Input**: Planning session 2026-11-19 (`GLOSSARY.md`; `docs/adr/0002`, `0003`); brief-003 v3 (memo outline and section numbers); core-007 FR-032 (agent on Claude Haiku in the app); core-008 (feedback); Personas P1, P3.

## Clarifications

### Session 2026-11-19

- Q: Is the agent conversational? → A: **Yes, through follow-ups on a brief.** One Claude Haiku agent answers each turn with the governed data tools; every new number is a claim token with its evidence. The scripted engine also answers follow-ups, limited to numbers already in the brief and its evidence, as the no-model baseline.
- Q: Where does the analyst type? → A: A message bar always docked at the bottom of every analyst screen of the Briefing lane, the width of the brief column, in the style of the Claude app. Answers open upward in a panel at most half the screen tall, with the brief still scrollable above; one click collapses it. Up to three suggestion bubbles sit above the bar.
- Q: What does the bar do before a brief exists? → A: On New briefing it starts an agent brief for the selected brand, territory and week, with the question as its focus (replacing the optional question box). While a brief is being written, a typed message is sent when the brief is ready. On a draft, approved or rejected brief, it asks a follow-up. Leaders get no bar; the Forecast lane is out of scope (Alvin and Sienna's lane).
- Q: How does a follow-up refer to the brief? → A: By section number (§1–§6, §3.1 …). "Ask about this" on a section pins a chip such as "§3.1 Pacific" in the bar, leaves the text empty, and shows two or three code-written suggestions for that kind of section. Every section reference in an answer links back to the section.
- Q: A question outside the brief's scope? → A: A different brand, territory or week gets a short answer from governed queries and an offer to generate a new brief for that scope; the current brief is never rewritten.
- Q: Who owns a thread? → A: One thread per analyst per brief. A thread holds at most 20 follow-ups; each answer sees every section of the brief and the last 6 turns. Unsaved threads are deleted after 30 days. A saved thread is kept, enters the feedback review list (core-008), and can be shared by link read-only with any Briefing analyst, who may continue it in their own thread. Leaders never open a thread. A thread is never part of the approved brief (ADR 0002).
- Q: Time limits? → A: 60 seconds per follow-up and 10 minutes per agent brief (down from the CPU host's 90 minutes). A turn over its limit shows "Didn't finish in time; nothing was guessed", is recorded as a run error, and no fallback answer is written. Median and 95th-percentile latency per turn and per brief are logged to MLflow for every run.
- Q: Feedback in the thread? → A: Each answer gets the thumbs and comment (core-008 User Story 5); the session rating appears once per thread after the third follow-up.

### Session 2026-11-20

Settled with Michael before the overnight build of slices 3 and 4; the rest are the recommended defaults he accepted.

- Q: How does the scripted engine answer a follow-up? → A: By rules, with no model. It reads the section reference (a pinned chip or "§3.1" in the text), restates that section's claims with their evidence, and answers any request for a number the brief does not hold with "That number is not in this brief" and an offer to ask the agent (FR-004).
- Q: Where are threads kept? → A: In the existing state store, one file per analyst per brief (`threads/<brief_id>/<analyst>.json`). Unsaved threads older than 30 days are purged when threads are listed or opened and when the app starts; there is no scheduler.
- Q: Where do suggestions come from? → A: Fixed code templates per section kind (bottom line, numbers, story, data limits, next checks); no model writes them.
- Q: How does the Haiku agent answer a follow-up? → A: One agent with the existing governed MCP tools (both specialist tool sets) and the brief's sections as context. It answers in one turn under a 60-second limit; its prose goes through the same token checks and one revision as the writer's; median and 95th-percentile latency are logged per run.
- Q: How does the harness score two turns? → A: A case may carry a `follow_up` (question, then, must-not-say). The harness runs the brief, then the follow-up on that brief, and scores the follow-up answer with the existing code checks plus a new gated check, `sections_exist` (every cited § number exists in the brief).
- Q: Who writes the six two-turn cases (FR-013)? → A: Claude drafts them from real weeks with SQL facts, `status: draft`, source `brief-006 FR-013`. Michael labels them. Until then they count toward the gated code checks only (rules, not answers).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask about a section (Priority: P1)

The analyst reads §3.1, presses "Ask about this", and asks why the change happened or how it splits by plan. The answer cites the section, runs any new query it needs, and shows its new numbers with their evidence.

**Why this priority**: A one-shot brief leaves the analyst with questions the brief cannot answer (planning session 2026-11-19).

**Independent Test**: On the 2026-08-24 brief, ask "Split §3.1 by plan" with the scripted engine and with Haiku.

**Acceptance Scenarios**:

1. **Given** the 2026-08-24 brief, **When** the analyst asks about §3.1, **Then** the answer cites §3.1, every number in it is a claim token with an evidence table, and the reference links to §3.1.
2. **Given** the scripted engine, **When** the analyst asks for a number not in the brief, **Then** it says the number is not in this brief and offers the agent; it never invents one.
3. **Given** a question that asks the agent to name a driver for a withheld or projected cut, **When** it answers, **Then** it says no driver can be named for that cut (brief-003 FR-023).

---

### User Story 2 - The message bar everywhere (Priority: P1)

The analyst can type at any time: before a brief exists to start one, while one is written, and after it is reviewed.

**Why this priority**: The bar is the one entry point to the agent (planning session 2026-11-19).

**Independent Test**: Use the bar on New briefing, during a running agent job, and on an approved brief.

**Acceptance Scenarios**:

1. **Given** New briefing with a scope selected, **When** the analyst asks "Why did Pacific drop?", **Then** an agent brief starts for that scope with the question as its focus.
2. **Given** a brief being written, **When** the analyst sends a message, **Then** it waits and is answered once the brief is ready.
3. **Given** the director, **When** any Briefing screen opens, **Then** no message bar is shown.

---

### User Story 3 - Out of scope (Priority: P2)

**Acceptance Scenarios**:

1. **Given** a BXA Pacific brief, **When** the analyst asks "What about BXE in the South?", **Then** the answer is short, from governed queries, and offers "Generate a brief for BXE · South Central"; the BXA brief is unchanged.

---

### User Story 4 - Save, share and continue a thread (Priority: P2)

**Acceptance Scenarios**:

1. **Given** a thread, **When** the analyst saves it, **Then** it is kept beyond 30 days, enters the feedback review list, and gets a share link.
2. **Given** a share link, **When** another Briefing analyst opens it, **Then** it is read-only and "Continue in my thread" copies it into their own thread; a leader opening it gets "not found".

---

### User Story 5 - Never a guess on a timeout (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a follow-up that runs past 60 seconds, **When** the limit is reached, **Then** the turn shows "Didn't finish in time; nothing was guessed", the eval records a run error, and no answer text is stored for that turn.
2. **Given** any eval run, **When** it finishes, **Then** MLflow holds median and 95th-percentile latency per turn and per brief.

### Edge Cases

- The 20-follow-up cap is reached: the bar says the thread is full and offers a new thread.
- The model API is unreachable: the turn fails visibly with the error; the draft text stays in the bar.
- A follow-up arrives for a brief whose data version has changed: the answer says the brief is on an older release and offers a new brief.
- An empty brief (routine week): suggestions offer "Show the weeks before" and "Which territory moved most?".

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Analysts of the Briefing lane MUST have a message bar docked at the bottom of every Briefing screen, with up to three suggestion bubbles; leaders MUST NOT.
- **FR-002**: On New briefing the bar MUST start an agent brief for the selected scope with the question as its focus; during a running brief it MUST queue the message; on a brief it MUST ask a follow-up.
- **FR-003**: A follow-up MUST be answered by one agent turn using only the governed tools; every number MUST be a claim token with its evidence attached to the answer; the no-digit rule applies.
- **FR-004**: The scripted engine MUST answer follow-ups from the brief's claims and evidence only, and say so when a number is not there.
- **FR-005**: Answers MUST cite section numbers that exist in the brief; each citation MUST link to its section.
- **FR-006**: "Ask about this" MUST pin the section, leave the text empty and show code-written suggestions for the section's kind.
- **FR-007**: A question outside the brief's scope MUST get a short answer and an offer to generate a brief for that scope; the brief MUST NOT change.
- **FR-008**: Threads MUST be one per analyst per brief, at most 20 follow-ups, each turn given every section and the last 6 turns; unsaved threads MUST be deleted after 30 days.
- **FR-009**: A saved thread MUST be kept, enter the feedback review list (core-008 FR-019), and be shareable read-only with Briefing analysts, who may continue it in their own thread. Leaders MUST NOT read threads. A thread MUST NOT be part of the approved brief.
- **FR-010**: A follow-up MUST stop at 60 seconds and an agent brief at 10 minutes; a stopped turn MUST be shown and recorded as a run error with no answer text.
- **FR-011**: Every eval run MUST log median and 95th-percentile latency per turn and per brief to MLflow.
- **FR-012**: Each answer MUST carry the thumbs and comment (core-008); the session rating MUST appear once per thread after the third follow-up.
- **FR-013**: The golden set MUST gain six two-turn Briefing cases (a section reference, a new query, a scope change, a negation trap, a "why" with no supported driver, a leader-forbidden request), scored per turn by the existing code checks plus a check that cited section numbers exist. They stay drafts until labelled.

### Key Entities

Follow-up, thread, saved thread, turn, section reference, suggestion, share link (terms in `GLOSSARY.md`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero digits outside claim tokens in any answer; 100% of answer claims resolve to evidence.
- **SC-002**: 100% of cited section numbers exist in their brief.
- **SC-003**: Zero answers written after a timeout; every timeout recorded as a run error.
- **SC-004**: The six two-turn golden cases pass every gated code check on both engines.
- **SC-005**: 95th-percentile follow-up latency on Haiku under 30 seconds on the dev set (target to confirm after the first run).
- **SC-006**: Zero thread reads by a leadership role.

## Assumptions

- Builds on brief-003 v3: the follow-up refers to the memo's section numbers and evidence tables.
- The agent model is Claude Haiku 5.5 through the Anthropic API, run by the app (core-007 FR-032); about half a cent per turn.
- Thread storage uses the existing state store (local folder or bucket); Postgres is a future open item (core-008).

# Feature Specification: Question-driven Forecast-Explanation agent

**Feature Branch**: `fcst-002-question-driven-agent`

**Created**: 2026-11-20

**Status**: Draft (Forecast lane; owners Alvin and Sienna; written with Sienna, not yet reviewed by Alvin)

**Input**: Redesign of the Forecast lane so the agent owns the investigation: the analyst asks in words; code reads the scope, finds candidate episodes in the data and computes every number; an investigator (rules or a model) chooses comparisons and verdicts; follow-ups refine one report. Built in `agents/forecast-explanation/forecast_agent/`. `fcst-001` stays reserved for Alvin's v1 spec.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask a question, confirm the scope, get an attribution (Priority: P1)

The Commercial Analyst types a question about the BXA forecast miss. The agent shows how it read the question (intent, weeks, territory) before running; the analyst can change the territory or weeks. The answer gives the miss, each driver's contribution with its method and confidence, the residual, and who should check what.

**Why this priority**: It replaces the territory and week form with the personas' own questions (CA, BM, FM stories) and is the core of the lane.

**Independent Test**: Ask the eighteen Forecast golden questions; score with `python -m eval run --system forecast_rules --lane forecast`.

**Acceptance Scenarios**:

1. **Given** the week of 2026-08-24, **When** the analyst asks how much each driver explains, **Then** the answer gives the miss of −1,036, Metacora about −655, a Southeast local driver, the usual bias and a residual, and the parts plus the residual equal the miss.
2. **Given** a question with a provisional week inside a long period (March to September 2026), **When** the agent runs, **Then** it sets the provisional weeks aside, says so, and still attributes the rest.
3. **Given** a single provisional week (New England, 2026-05-04), **When** the agent runs, **Then** it names no driver and says why.
4. **Given** a question about another product's forecast or a commercial action, **When** it is read, **Then** nothing runs and the scope card says why.

### User Story 2 - The investigator's decisions are visible and bounded (Priority: P1)

The analyst sees which episodes were found, which comparison each used, which control territories were dropped, and why each was accepted or rejected, labelled by who decided (code, rules, agent, analyst).

**Independent Test**: The analyst view lists decisions and comparisons; the leadership view never does (`tests/test_forecast_api.py`).

**Acceptance Scenarios**:

1. **Given** a model as investigator, **When** it gives a reason containing a digit, **Then** the tool refuses it.
2. **Given** a model that fails or leaves a candidate undecided, **When** the run ends, **Then** the rules decide what is open and the decision log says so.

### User Story 3 - Follow-ups on one report (Priority: P2)

The analyst asks follow-ups on a finished report: rerun for another territory or period, drop control territories, explain a decision, or show the miss week by week.

**Acceptance Scenarios**:

1. **Given** the 2026-08-24 report, **When** the analyst asks to drop South Central from the controls, **Then** a linked rerun gives Southeast about −204 and a residual about −145.

### User Story 4 - Driver recovery is measured (Priority: P2)

The team sees, per system, whether it accepts the drivers that act in a window and no others, with a confusion matrix and the misses listed.

**Independent Test**: `python -m eval drivers --system forecast_rules` and `--system forecast_agent --model <spec>`; the app's Driver recovery tab.

### Edge Cases

- A window that straddles an episode, or holds provisional weeks.
- A control territory with its own episode (contaminated control).
- An access restriction that is later eased (the easing is not a new driver).
- A holiday week (already in the forecast; never a driver).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A model, when configured, MUST read a question into a scope (weeks, territory, intent) through one tool call; code MUST check every field against the release and fall back to the keyword rules when the reading is unusable. The scope MUST be shown before any investigation runs; the analyst MAY edit intent, territory and weeks, and the run MUST use the confirmed scope.
- **FR-002**: A week whose actual is provisional in any territory MUST NOT enter a comparison; if every week asked about is provisional, the answer MUST abstain.
- **FR-003**: Candidate episodes MUST be discovered from the agent-visible context tables (promotion, inventory, access, market basket, calendar), not from a hand-written calendar.
- **FR-004**: A local driver's contribution MUST be the territory's miss beyond the control territories' rate over the episode's usable weeks; a broad launch's contribution MUST be the relative basket-share loss applied to the forecast; the usual bias MUST be the pre-launch national error rate.
- **FR-005**: The answer MUST report a residual so that the parts plus the residual equal the miss; every figure MUST be a claim token from one governed query.
- **FR-006**: Confidence MUST be set per driver by code and may only be lowered: no control group, association only, few or contaminated controls, a gap that predates the episode, control noise, a failed leave-one-out or recovery check, overlap.
- **FR-007**: The rules MUST investigate by default. A model MAY investigate only as the comparison arm (`FORECAST_INVESTIGATOR=model`), acting only through engine operations (compare, accept, reject, abstain, finish) with a step budget and a wall-clock cap; candidates it leaves open are decided by the rules and labelled so. A model MUST NOT supply a number.
- **FR-008**: Follow-ups MUST map to one operation (rerun, explain, weekly) run by code; a rerun MUST be stored as a linked run that can be submitted.
- **FR-009**: The leadership view MUST NOT include the decision log, comparisons, candidates, progress or evidence.
- **FR-011**: A model MAY word the summary using claim tokens only; code MUST refuse the text (and keep the code summary) if it holds a stray digit or unknown token, omits the residual, adds a driver or territory, recommends a commercial action, or uses a banned term.
- **FR-012**: The whole pipeline MUST run with no model configured, with the same numbers.
- **FR-010**: Both arms MUST be scored on the golden set and on driver recovery, and a merge MUST pass `eval gate` against the previous Forecast run.

### Key Entities

- **Scope**: question, weeks, territory, intent, notes, out-of-scope reason.
- **Episode**: driver, territory (or ALL), active weeks, signal, status, reason.
- **Comparison**: method, weeks, controls, effect, statistics, flags, robustness.
- **Decision**: who (code, rules, agent, analyst), action, target, reason in words.
- **Follow-up**: question, operation, answer, linked run.

## Success Criteria *(mandatory)*

- **SC-001**: Golden number recall on the Forecast golden set at or above the old scripted baseline (0.29 on 2026-11-20); measured 0.59 for the rules arm.
- **SC-002**: Driver recovery on the draft probes: no false driver, and every expected driver recovered by the rules arm.
- **SC-004**: The model reader beats the keyword rules on the draft paraphrases (`python -m eval scopes`). Measured 2026-11-20 on the forty: rules 35% fully right (period 40%, intent 80%); local Qwen 4B 90% (period 90%, intent 100%), about fifteen seconds a question, never falling back. On the eighteen golden questions the product with Qwen scored 0.57 golden number recall against 0.59 for the rules, because Qwen read three intents differently; the analyst corrects these on the scope card. [NEEDS CLARIFICATION: rerun with the hosted model (Haiku) once a key is available locally (open item for Michael)]
- **SC-003**: The agent arm earns its place only if it beats the rules arm on driver recovery, exact answers or analyst ratings at an agreed cost. [NEEDS CLARIFICATION: cost budget per question, and which model (Haiku needs the team key) (open item for Alvin)]

## Assumptions

- The driver-recovery labels in `eval/labels/forecast_drivers.yaml` come from the user stories, not the private answer key, and stay a draft until Alvin and Sienna confirm them. [NEEDS CLARIFICATION: which golden cases also score driver recovery (open item for Alvin)]
- The form engine (`feagent/`, `POST /api/forecast/runs`) stays until Alvin agrees to retire it. [NEEDS CLARIFICATION: retire the form engine, or keep it as an ablation (open item for Alvin)]
- The Briefing-to-Forecast handoff is out of scope here. [NEEDS CLARIFICATION: handoff contract with the Briefing lane (System Architecture section 5)]

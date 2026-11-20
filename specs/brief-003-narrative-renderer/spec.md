# Feature Specification: Narrative and Renderer (Stage 5)

**Spec ID**: `brief-003-narrative-renderer` (Briefing lane; owners: Michael, Meghna)
**Feature Branch**: `speckit-briefing`
**Created**: 2026-10-16 | **Updated**: 2026-11-19
**Status**: Draft v3. Memo outline, projected national, charts and evidence tables (2026-11-19 planning session; `GLOSSARY.md`, `docs/adr/0001`). Slice 1 (memo outline, projected national) planned 2026-11-19 in `plan.md`.
**Replaces**: `007-narrative-renderer` (Oct 16)
**Input**: System Architecture §4 (stage 5, Briefing); Briefing Architecture §5.5, decision 6, decision 20; Evaluation Pack EV-1.1 to EV-1.3, EV-7.1 to EV-7.5, EV-8.5; Personas P1, P3, P4; User stories P1-Q1, P1-Q2, P1-Q3, P1-Q6, P3-Q2, P3-Q3, P3-Q4, P3-Q5, P3-Q6, P4-Q2, P4-Q3, P4-Q6

## Clarifications

### Session 2026-11-19

Settled in a structured planning session with Michael; terms are in `GLOSSARY.md`, decisions in `docs/adr/0001` to `0003`.

- Q: What template does the brief follow (Evaluation Pack open item 4)? → A: **A memo with a fixed outline**, modelled on the course's MMM and forecasting memos: §1 Bottom line, §2 The numbers, §3 What changed and why (§3.1, §3.2 … one per story), §4 What the data can't tell us, §5 Next checks, §6 Appendix (method and the checks run). Replaces the User Story 2 template. Every brief uses it, scripted or agent, routine or eventful.
- Q: Who builds what? → A: Code builds every section, table, chart, caption and number; a model (or the scripted template) writes only the prose inside a section, numbers only through claim tokens. The scripted engine and the agent produce the same skeleton.
- Q: What leads the brief? → A: §1 states, in order: projected national TRx this week; the like-for-like change against the four weeks before; brand share of the market basket; and the one number we are least sure of, chosen by rule (an estimated territory if any; else the lead number of the lowest-confidence story; else the change built on the fewest TRx).
- Q: Is national TRx projected? → A: **Yes, by territory stratum** (course Week 2, "projectable to national with stratified factors"): observed TRx ÷ panel coverage per territory, summed. Coverage 0.98–1.0 is observed; 0.5–0.98 is projected and labelled; below 0.5 or no feed, the territory is estimated from its own share of national over its last four weeks that passed the gate and were not holidays, and labelled estimated. Growth stays like-for-like. No story names a driver from a projected or estimated cut (ADR 0001).
- Q: Charts? → A: Yes, code-built from evidence rows, each with a caption (code, with claims) and a one-to-two-line explanation (writer prose with claim tokens): §2 a 13-week TRx trend (projected national and the selected territory; restated weeks dotted; projected and estimated weeks hollow; no forecast line); §3 per story, the territory's weekly TRx against its four-week baseline band, with a second panel for the driver the checks tested; §4 a coverage strip, territory by week, with projected, estimated and restated cells marked.
- Q: Can the analyst see the data? → A: Yes: every section carries its evidence table (the rows behind its claims), the query behind a toggle, and a CSV download. Analysts only.
- Q: What do leaders see? → A: §1, §2 (table and charts, no queries or downloads), §3 without the checks and evidence, and §5.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A brief where code writes every number (Priority: P1)

The writer produces prose around claim tokens. Code fills each token from the closed evidence pack. No digit in the brief comes from the language model.

**Why this priority**: Numeric reconciliation is a hard gate (EV-1.1). Preventing errors beats catching them (Briefing decision 6).

**Independent Test**: Draft the 2026-08-24 brief. Scan for digits outside tokens. Render and compare every number with the pinned snapshot.

**Acceptance Scenarios**:

1. **Given** a closed evidence pack, **When** the writer drafts, **Then** each figure in the prose is a claim token such as `{{c17}}`.
2. **Given** a draft, **When** the renderer fills the tokens, **Then** each value comes from a tool record and is rounded by the metric's rule.
3. **Given** a draft with a digit outside a token, **When** checks run, **Then** the draft is rejected (brief-004).

---

### User Story 2 - The Monday memo, every week (Priority: P1)

The brief is a memo with a fixed outline (Clarifications 2026-11-19): §1 Bottom line; §2 The numbers (KPI table and trend chart); §3 What changed and why, one subsection per story ordered by impact, each with its checks, confidence, driver chart, promotion context where promotion was tested, and owner; §4 What the data can't tell us (data health, restatements, projection and coverage, the coverage strip); §5 Next checks, each with an owner and the decision it unlocks; §6 Appendix (method, the checks run, glossary). When any cut is unreliable, §1 says so first. Routine weeks use the same outline with an empty §3 that says why.

**Why this priority**: The director wants the same short format each week (P3-Q1); P1 wants the team's Monday format (P1-Q6).

**Independent Test**: Draft a routine week (2025-04-21), a week with a withheld cut (2026-05-04) and an eventful week (2026-08-24).

**Acceptance Scenarios**:

1. **Given** the routine week 2025-04-21, **When** the brief is drafted, **Then** it holds the KPI table, at most one line saying territory swings stayed in their normal range, the footnote and the glossary, and no story. It never says "Pacific surged 25%". (User story P1-Q3.)
2. **Given** week 2026-05-04, **When** the brief is drafted, **Then** §1 says first that New England's feed is incomplete; §2 shows a projected national with New England marked projected (coverage 0.66); each like-for-like figure states its territory count (6 of 8 against the four weeks before, because Mid-Atlantic 2026-04-06 is also withheld; 7 of 8 week over week); §4 names New England with its three reasons; and no §3 story is opened for it. It never says "New England BXA fell 34%". (User story P1-Q2; ADR 0001.)
3. **Given** week 2026-08-24, **When** the brief is drafted, **Then** it carries a Southeast story and a continuing Metacora line, and nothing about a national "collapse". (User story P1-Q6.)
4. **Given** any brief, **When** its length is counted, **Then** it is within the semantic-layer limit.

---

### User Story 3 - Plain words and honest confidence (Priority: P1)

Reader-facing text follows ASD-STE100: short sentences, one idea and one number per sentence, one word with one meaning, with business framing. Method terms stay in the evidence, not the prose. Causal wording appears only for High stories; promotion findings are always worded as associations.

**Why this priority**: The director must repeat the explanation upward (P3-Q3). Overclaiming is the costliest error (P2-Q3).

**Independent Test**: Draft the Pacific supply story and a Medium promotion story. Run the plain-language rubric.

**Acceptance Scenarios**:

1. **Given** the Pacific supply story (June 2026), **When** drafted, **Then** it reads like: "For five weeks in June, Pacific pharmacies could fill only about 7 in 10 BXA orders. Pacific BXA prescriptions fell 34% while other territories fell 1%. Supply returned to normal on July 6, and prescriptions recovered." It calls it a supply problem, not a demand problem. (User story P3-Q3.)
2. **Given** any reader-facing sentence, **When** scanned, **Then** it holds no reader-jargon term ("difference-in-differences", "fill-rate elasticity").
3. **Given** a Medium or Low story, **When** drafted, **Then** it uses hedged wording and no causal verb; a Low story appears under "investigate next" with the function to involve.
4. **Given** a supported promotion finding, **When** drafted, **Then** it is worded as an association, names the method and the comparison, and never states a promotion-caused lift. (User story P4-Q1.)

---

### User Story 4 - Continuity, restatements, coverage and next steps (Priority: P2)

For multi-week events, the brief says new or continuing and improving, worsening or flat. When a number reported earlier changed, it states old value, new value and reason. National figures built on fewer territories say so. Each open story names what to investigate next and which function to involve.

**Why this priority**: Repeated alarms erode attention; hidden restatements erode trust (P3-Q4, P3-Q5, P3-Q6).

**Independent Test**: Draft the 2026-09-28 brief (Metacora continuing) and the 2026-07-13 brief (restatement).

**Acceptance Scenarios**:

1. **Given** week 2026-09-28, **When** drafted, **Then** the Metacora story is marked continuing, in its 31st week, worse than at launch and flat for the last 8 weeks, with BXA 32.1% and Metacora 15.2% that week. It never says "New: competitor gaining share". (User story P3-Q4.)
2. **Given** the 2026-07-13 brief, **When** drafted, **Then** it says Mid-Atlantic BXA TRx for 2026-04-06 was restated from 692 to 742 on 2026-07-13 for a late claims adjustment, and every national figure built on 7 territories says so. (User story P3-Q6.)
3. **Given** the Southeast coverage gap (August 2026), **When** next steps are drafted, **Then** they say to involve sales leadership on Southeast coverage, at territory level, and say rep and digital effects cannot be separated. (User stories P3-Q5, P4-Q6.)
4. **Given** the December 2025 holiday weeks, **When** drafted, **Then** the brief labels the drop a calendar effect, cites last year's same weeks, opens no story, and says a rebound is expected. (User story P3-Q2.)

---

### User Story 5 - Promotion context next to performance (Priority: P2)

For each story where promotion was tested, the brief shows promotion activity (aggregated calls, impressions) for the same cut and weeks next to TRx, splits by channel and specialty with small cells flagged, and states what the data cannot show yet.

**Why this priority**: P4 needs activity beside results, and an honest statement of what is missing (P4-Q2, P4-Q3; EV-7.5).

**Independent Test**: Draft the Southeast story.

**Acceptance Scenarios**:

1. **Given** the Southeast story, **When** drafted, **Then** it shows calls and impressions beside TRx for 2026-08-03 to 2026-08-31 (impressions about 870 against a median of about 1,774) and says reach by target segment cannot be shown yet. It never says "the campaign reached its target HCPs". (User story P4-Q3.)
2. **Given** a channel split with cash cells of 36 to 49 TRx a week, **When** drafted, **Then** those cells are marked noisy and no claim generalizes from them. (User story P4-Q2.)

---

### User Story 6 - No individual identified, governed terms (Priority: P1)

No line identifies a rep. "New patients" is used only for NBRx. "Competitive intelligence" is used; "surveillance" never is.

**Why this priority**: The brief is forwarded to sales leadership and marketing. Terminology is a mentor directive.

**Independent Test**: Draft the Southeast brief and scan.

**Acceptance Scenarios**:

1. **Given** a rep-vacancy case, **When** drafted, **Then** the brief mentions only territory-level aggregated activity.
2. **Given** any draft, **When** scanned, **Then** banned terms are absent.

### User Story 7 - A national number every week (Priority: P1)

The brief always states a national TRx level built territory by territory from panel coverage, so the director gets a national figure even in a week with a broken feed, and knows which part of it is projected or estimated.

**Why this priority**: A weekly brand report is "projectable to national with stratified factors" (course Week 2); today the brief shows only like-for-like territories.

**Independent Test**: Draft 2026-05-04 (New England at coverage 0.66) and a routine week (all coverage 1.0).

**Acceptance Scenarios**:

1. **Given** a week where every territory has coverage 1.0, **When** the brief is drafted, **Then** projected national equals the observed sum and nothing is labelled projected.
2. **Given** 2026-05-04, **When** the brief is drafted, **Then** New England's TRx is observed ÷ 0.66, labelled projected, and §1 names it as the number we are least sure of when no territory is estimated.
3. **Given** a territory below 0.5 coverage or with no feed, **When** the brief is drafted, **Then** its TRx is estimated from its share of national over its last four clean weeks and labelled estimated, and no driver is named for it.

---

### User Story 8 - Charts and the data behind every section (Priority: P1)

Each section shows its chart with a caption and one or two lines on what it shows, and an analyst can open the rows behind any claim, see the query, and download them.

**Why this priority**: A brief the analyst cannot check against its data is not trusted (planning session 2026-11-19); the course memos lead with a chart and a caption.

**Independent Test**: Draft 2026-08-24 and open §2 and §3.1 as an analyst and as the director.

**Acceptance Scenarios**:

1. **Given** the 2026-08-24 brief, **When** an analyst opens §3.1, **Then** the Southeast chart shows weekly TRx against its baseline band and the tested driver, with a caption and an explanation whose numbers are claim tokens, and the evidence table, query and CSV are available.
2. **Given** the same brief opened by the director, **When** §2 and §3 are shown, **Then** the charts and captions appear, and no evidence table, query, download or checks list does.

---

### Edge Cases

- All cuts failed: the brief is a data-health notice only (A7 proposal).
- A capped story: listed as unresolved, with its evidence kept.
- Too many stories for the length limit: lower-impact stories move to "investigate next" with a count.
- A revision after a failed check: one revision only (brief-004).
- A story's promotion was not tested (no activity data for the cut): the promotion context section says so.
- No driver is supported for a story: its chart shows the TRx panel only, and the explanation says no driver was supported.
- Every territory's coverage is below 0.5 in the same week: no projected national is given; §1 says the week cannot be reported.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The writer MUST read only the closed evidence pack, the continuity object and the definitions of the metrics in play.
- **FR-002**: The writer MUST emit claim tokens for every figure and MUST NOT emit a digit outside a token.
- **FR-003**: The renderer MUST replace each token with its tool record's value using the metric's rounding rule, and MUST fail on an unresolved token.
- **FR-004**: The brief MUST follow the memo outline in User Story 2 (§1–§6, stories numbered §3.1, §3.2 …) and the semantic-layer length limit. Outline settled 2026-11-19; [NEEDS CLARIFICATION: the length limit a real brand team uses (Evaluation Pack open item 4)]
- **FR-005**: Code MUST fill the KPI table, the data-health section, the coverage labels, the restatement disclosure, the promotion context table and the glossary. The writer does not write them.
- **FR-006**: Stories MUST be ordered by business impact.
- **FR-007**: Routine, warning, failed-validation and eventful runs MUST all use the same template.
- **FR-008**: Causal wording MUST appear only on High stories. Promotion findings MUST use association wording at every level.
- **FR-009**: Reader-facing text MUST follow ASD-STE100 with business framing, and MUST contain no reader-jargon term from the semantic layer.
- **FR-010**: The brief MUST state new or continuing, weeks running, and improving, worsening or flat for multi-week stories.
- **FR-011**: The brief MUST disclose every restatement since the previous brief with old value, new value, date and reason.
- **FR-012**: Every national or regional figure built on fewer than all territories MUST carry its coverage label.
- **FR-013**: Each open story MUST name a next step and a function from the semantic-layer list.
- **FR-014**: For each story where promotion was tested, the brief MUST show promotion activity for the same cut and weeks beside performance, and MUST state what the data cannot show yet. [NEEDS CLARIFICATION: whether reach, channel spend and consumer campaign data enter v1 (Briefing A16, Evaluation Pack open item 19)]
- **FR-015**: Splits below the small-cell floor MUST be marked noisy, and no sentence MAY generalize from them.
- **FR-016**: The brief MUST NOT identify an individual rep. "New patients" MUST be used only for NBRx.
- **FR-017**: The draft MUST store each claim as a `brief_claim` (core-004) with token, text, evidence IDs, metric, rounding, confidence and section.
- **FR-018**: The prompt version MUST be pinned in the run record.
- **FR-019**: The stage MUST accept verifier flags or reviewer comments and redraft only the flagged sections.
- **FR-020**: Code MUST build the section skeleton, every table, chart, caption and claim; the writer MUST write only the prose fields of a section. The scripted engine and the agent MUST emit the same skeleton.
- **FR-021**: §1 MUST state, in order, projected national TRx, the like-for-like change against the four weeks before, brand share of the market basket, and the number least sure of, chosen by the rule in the Clarifications.
- **FR-022**: Projected national MUST be the sum over territories of observed TRx ÷ panel coverage, with the coverage bands and the estimate rule in the Clarifications; each projected or estimated territory MUST be labelled in every table and chart that shows it, and the label MUST say the level is an assumption, not an observed count (Michael, 2026-11-20). A failed cut is projected only when all its faults are completeness faults (missing keys, row-count mismatch, low coverage, late delivery, incomplete source); a cut with duplicate keys, under restatement review or with any other fault is estimated, whatever its coverage (plan research R2, 2026-11-19).
- **FR-023**: No story MAY name a driver for a projected or estimated cut. Growth figures MUST be like-for-like and carry their coverage label (FR-012).
- **FR-024**: §2, each §3 story and §4 MUST carry the charts in the Clarifications, each with a code-built caption and a one-to-two-line explanation whose numbers are claim tokens.
- **FR-025**: Every section MUST carry an evidence table of the rows behind its claims and the query that produced them; the analyst view MUST offer the query and a CSV download.
- **FR-026**: The leadership view MUST carry §1, §2 (no queries or downloads), §3 without checks or evidence, and §5; the server MUST strip the rest.
- **FR-027**: The brief envelope MUST carry the sections as structured data (number, title, prose, claims, chart spec, evidence) and, for the existing scorers, the same content flattened as `answer` text.

### Key Entities

Draft, `brief_claim`, rendered brief, memo outline, section, story, chart spec, evidence table, projected national, estimated territory, glossary (`GLOSSARY.md`), continuity object, promotion context table.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero digits outside claim tokens in any draft (supports EV-1.1).
- **SC-002**: 100% of rendered numbers match the pinned snapshot after stated rounding (EV-1.1, hard gate).
- **SC-003**: 100% of seeded restatement cases are disclosed with old and new values (EV-1.2); the 2026-07-13 brief discloses 692 → 742.
- **SC-004**: Non-numeric claims are checked against the answer key and pinned data (EV-1.3; target to set).
- **SC-005**: Briefs pass format conformance (EV-7.4) and the length limit (EV-8.5).
- **SC-006**: Plain-language score on the rubric (EV-7.1; target to set).
- **SC-007**: Multi-week events carry continuity (EV-7.2); open stories carry next steps (EV-7.3).
- **SC-008**: Every promotion-tested story carries the promotion context table and its limits statement (EV-7.5).
- **SC-009**: Zero individual identifications and zero banned or jargon terms in reader text (EV-9.1, EV-9.2).
- **SC-010**: Every "must not say" phrase in the Briefing user stories is absent from the matching dev brief.
- **SC-011**: Projected national matches the hand calculation (observed ÷ coverage per territory) to the rounding rule in 100% of dev weeks; golden cases P1-Q2 and P3-Q6 are updated for projection and pass.
- **SC-012**: Every §2, §3 and §4 chart's caption and explanation contain no digit outside a claim token, and every claim in them resolves to its evidence table.
- **SC-013**: Zero evidence rows, queries or checks lists in any leadership response.

## Assumptions

- The investigation result is closed before this stage starts.
- Unreliable cuts arrive flagged; the writer does not judge reliability.
- The template starts from Briefing Architecture §5.5 and is replaced if the mentor provides a real one.
- ASD-STE100 is a style target scored by human reviewers.
- The agent's language model is Claude Haiku 5.5 through the Anthropic API (core-007 FR-032); prompts carry only synthetic values and metric definitions (S14).
- The release has territory-level counts and weekly panel coverage per territory, not a pharmacy panel; territories are the projection strata.

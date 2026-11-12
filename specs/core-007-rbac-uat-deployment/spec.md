# Feature Specification: Role-Based Access and UAT Deployment

**Spec ID**: `core-007-rbac-uat-deployment` (shared; owner: Michael. Frontend: Meghna. Forecast roles: Alvin and Sienna confirm)
**Feature Branch**: `speckit-briefing` (spec only; implementation branch to be chosen at plan time)
**Created**: 2026-11-11
**Status**: Draft v2 (clarified 2026-11-11)
**Input**: Course task list (Michael): integrate RBAC, starting from the personas and working outward; set up a Google Cloud deployment of the agent with Keycloak authentication; publish the app for User Acceptance Testing (UAT) with selected users, tracked in MLflow; define user success metrics (time to insight) and agent metrics (approval rate, accuracy, latency, cost). Decisions from Michael, 2026-11-11 (recorded in Context and Clarifications).

## Context

The Briefing UI on `feature/ui-integration` (Meghna) calls a development-only HTTP API over the scripted Briefing baseline. That API has no identity, no roles and no deployment; its own docs (`docs/BRIEFING_UI_INTEGRATION.md`, `frontend/figma-make/FUTURE_ENHANCEMENTS.md` items 4 and 11) list authenticated roles, permission checks and deployment as missing, and the persona switcher was removed until they exist. This spec adds them.

The work goes from the inside out: first who may see what (roles and views, enforced by the server), then sign-in, then the hosted UAT app, then automatic deployment from `main`, then UAT tracking, then agent snapshots.

Each lane gets one analyst role and one leader role, so the two views can be told apart:

| Lane | Analyst view | Leadership view (executive summary only) |
| :- | :- | :- |
| Briefing | P1 Commercial Analyst | P3 Brand Director |
| Forecast | CA Commercial Analytics Analyst | BM Brand Manager |

P2 (Insights Manager), P4 (Marketer) and FM (Forecasting Manager) get no role.

## Clarifications

### Session 2026-11-11

- Q: What do leaders see? → A: The executive summary only, for now.
- Q: Which personas get roles? → A: Briefing P1 and P3; Forecast CA and BM. P2, P4 and FM get none. (P1 and P2 were considered for Briefing; P2's user stories P2-Q2 and P2-Q5 need evidence, so P2 does not fit an executive-summary view, and P3 pairs with BM as the brand leader in each lane.)
- Q: With P2 out of scope, who approves a briefing before a leader sees it? → A: The Commercial Analyst's approval alone publishes it for UAT (core-007 open item 1, closed). brief-005's two-step sign-off stays the target beyond UAT.
- Q: Does a language model run on Google Cloud? → A: No. Agents run locally on Ollama.
- Q: How does locally run agent output reach the hosted app? → A: As versioned briefing snapshots that the owner generates locally (low-code build on `qwen3:4b-instruct-2507-q4_K_M`) for a fixed list of weeks and territories, and commits to `main` (core-007 open item 2, closed). Because the low-code build has not yet passed `eval gate` against the scripted baseline (run `0cd14c5f4266`, 2026-11-05), each snapshot must instead pass its own traceability check and is labelled experimental.
- Q: What may the sign-in service and hosting cost? → A: Nothing beyond Google Cloud usage billing for a basic project; Keycloak is the free open-source edition, and every service stays within the free tiers.

### Session 2026-11-11b

- Q: Can UAT users run the agent live, on the owner's local models? → A: Yes, through a **local worker** (Michael). The app queues an agent job; a worker on the owner's PC polls the app (outbound only, with a worker token), runs the agent on Ollama, and posts the result back. Ollama is never exposed. When no worker has polled recently, the UI says the agent host is offline and the job waits. This widens open item 2: committed snapshots stay possible, and live jobs are added. The app itself still never calls a model (FR-016).

### Session 2026-11-11c

- Q: Who may deploy and operate the Google Cloud project? → A: Every team member, not only the project owner (Michael). Each teammate's own Google account gets a deployer role set on the project: deploy the app and Keycloak, roll back, read status and logs. Creating the project, billing, budgets and granting access stay with the owner.
- Q: May teammates see the UAT passwords and secrets in `deploy/.env.uat`? → A: Yes (Michael), knowingly trading secrecy for a team that can operate the deployment without him. The file is shared through Secret Manager, readable by every teammate granted access, and still never committed (FR-013 unchanged).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Each role sees only its own view, enforced by the server (Priority: P1)

A Commercial Analyst (P1) asks for a weekly briefing and gets the analyst view: the full answer, its claims, every evidence item and the trace. After the analyst approves it, a Brand Director (P3) opens the same briefing and gets the leadership view: an executive summary only. The leadership response that leaves the server holds no evidence items, no queries and no trace, so nothing is hidden only in the browser. An analyst can switch to preview the leadership view; a leader cannot open the analyst view.

**Why this priority**: Every later step (sign-in, hosting, UAT) depends on roles that mean something. Hiding evidence only in the browser would still send it to leaders.

**Independent Test**: With a stand-in identity (no sign-in service yet), request the same briefing as each role and inspect the raw response.

**Acceptance Scenarios**:

1. **Given** a Commercial Analyst, **When** they request the Pacific briefing for the week of 2026-06-08, **Then** the response holds the answer, claims and evidence items, and every claim resolves to an evidence item.
2. **Given** that briefing approved by the analyst, **When** a Brand Director opens it, **Then** the raw response holds the executive summary and no evidence item, query text or trace field.
3. **Given** a Brand Director, **When** they ask for the analyst view (in the UI or by calling the server directly), **Then** the request is refused.
4. **Given** a Commercial Analyst, **When** they switch to the leadership preview, **Then** they see exactly what a Brand Director would see for that run.
5. **Given** the New England week of 2026-05-04 (feed not reportable), **When** a Brand Director reads the executive summary, **Then** the summary still says New England is not reportable and labels national totals "7 of 8" (user story P1-Q2). Removing evidence never removes a data-health caveat or an abstention.
6. **Given** any executive summary, **When** its numbers are compared with the analyst view of the same run, **Then** every number in the summary is one of that run's claims, filled by code.

---

### User Story 2 - The analyst approves before a leader sees a briefing (Priority: P1)

The Commercial Analyst reads a briefing and approves or rejects it, giving a reason when rejecting. Only approved briefings appear for the Brand Director. Approvals survive a restart of the app.

**Why this priority**: Shared Principle II (agents propose, people decide) and the approval-rate metric both depend on it.

**Independent Test**: Approve one briefing and reject another as the analyst; sign in as the Brand Director; restart the app; check again.

**Acceptance Scenarios**:

1. **Given** a briefing the analyst has not approved, **When** a Brand Director looks for it, **Then** it is not listed and cannot be opened.
2. **Given** a briefing the analyst approved, **When** the app restarts and a Brand Director signs in, **Then** the approved briefing is still listed.
3. **Given** a rejected briefing, **When** the analyst rejects it, **Then** the reason is stored with the UAT event and the brief stays hidden from leaders.

---

### User Story 3 - Selected users sign in and get their assigned role (Priority: P1)

A UAT participant opens the app, signs in and lands on the view their role allows. Only invited participants have accounts; nobody can register themselves. The app shows who is signed in and in which role, and offers only the views that role allows.

**Why this priority**: UAT needs real identities so that metrics can be grouped by role and access is limited to the selected users.

**Independent Test**: Sign in as one test user per role; then try with no account, with a wrong password and with an expired session.

**Acceptance Scenarios**:

1. **Given** an invited Brand Director, **When** they sign in, **Then** they land on the leadership view and no analyst control is offered.
2. **Given** a visitor with no account, **When** they open the app or call the server, **Then** they reach only the sign-in page, and every data request is refused.
3. **Given** a signed-in user, **When** the app asks the server who they are, **Then** the server answers with their role and allowed views, never with another user's details.
4. **Given** a user with no role (for example a P2, P4 or FM account created by mistake), **When** they sign in, **Then** they see a "no access" message and no data.

---

### User Story 4 - The UAT app runs on Google Cloud at no cost beyond basic project billing (Priority: P2)

The app (sign-in, frontend and server) is reachable at a stable HTTPS address for the selected users. When nobody is using it, it costs nothing; the first request after an idle period may be slow (cold start). Only the deterministic scripted engine runs live there; agent output appears only as committed snapshots.

**Why this priority**: UAT needs a shared address, but the budget is zero and the agents stay local.

**Independent Test**: Deploy, leave it idle for a day, then run one briefing per role and read the billing report.

**Acceptance Scenarios**:

1. **Given** the deployed app after an idle period, **When** a user requests a briefing, **Then** it appears within the time in SC-004, including the cold start.
2. **Given** the deployed app, **When** its contents are inspected, **Then** they contain no file from the eval package and no ground-truth file.
3. **Given** the deployed app, **When** any request is served, **Then** no language model is called.
4. **Given** a full UAT month, **When** the billing report is read, **Then** the cost meets SC-003, and a budget alert would have fired before any charge above it.

---

### User Story 5 - Merges to main reach the app automatically, only when checks pass (Priority: P2)

When a change merges to `main`, the project's checks run (tests, golden-set validation and the no-model baselines). Only if they pass does a new version of the app go live. If they fail, the live app is unchanged. A bad release can be rolled back to the previous version at once.

**Why this priority**: Keeps the UAT app current with no manual step, without breaking the eval loop (Briefing B-VII).

**Independent Test**: Merge a change that passes the checks and one that fails them; time the first to live and confirm the second never deploys; then roll back.

**Acceptance Scenarios**:

1. **Given** a merge to `main` that passes every check, **When** the pipeline finishes, **Then** the new version is live within the time in SC-005, with no manual step.
2. **Given** a merge whose checks fail, **When** the pipeline runs, **Then** the live app keeps its previous version.
3. **Given** a live version with a defect, **When** an owner rolls back, **Then** the previous version serves all traffic within the time in SC-005.
4. **Given** the pipeline, **When** it authenticates to Google Cloud, **Then** it uses no long-lived key stored in the repository or in GitHub.

---

### User Story 6 - UAT usage is tracked in MLflow (Priority: P2)

Each UAT session records, per briefing: the participant's role, a pseudonymous participant ID, when the question was asked, when the participant marked that they had what they needed (time to insight), how long the server took (latency), whether the analyst approved or rejected the briefing, any claim the participant flagged as wrong, and the engine, engine version and data version used. The owners import these records into the local MLflow store as a UAT experiment, kept apart from the golden-set runs.

**Why this priority**: The course asks for user success and agent metrics from UAT.

**Independent Test**: Run three sessions as different roles, import the records, and read the UAT experiment in the dashboard.

**Acceptance Scenarios**:

1. **Given** a completed session, **When** the records are imported, **Then** the UAT experiment shows time to insight, approval rate, flagged-claim rate, latency and cost, by role and by engine (scripted or agent snapshot).
2. **Given** the UAT records, **When** they are read, **Then** none holds a name, email address or other direct identifier of a participant, and none identifies an individual rep (B-VI).
3. **Given** the hosted app, **When** it records a UAT event, **Then** it does so without using the eval package.

---

### User Story 7 - Locally generated agent snapshots reach the UAT app through main (Priority: P2)

The owner runs the low-code Briefing build locally on Ollama (`qwen3:4b-instruct-2507-q4_K_M`) for a fixed list of weeks and territories, and commits each result as a versioned snapshot: answer, claims, evidence items, engine, engine version, model, and data version. After the merge, the analyst can pick the agent snapshot for a listed week and territory next to the live scripted briefing. Snapshots cannot answer new questions. A snapshot that fails its traceability check is not served.

**Why this priority**: It puts real agent output in front of UAT users at no cloud cost, while the agent itself stays local.

**Independent Test**: Generate two snapshots, one clean and one with a number that has no evidence; merge; check that only the clean one is offered, labelled experimental.

**Acceptance Scenarios**:

1. **Given** a committed snapshot, **When** an analyst opens it, **Then** it is labelled "agent output, experimental" with its engine, model, version and data version.
2. **Given** a snapshot in which a number has no claim, or a claim does not resolve to evidence on the current data version, **When** the app loads snapshots, **Then** that snapshot is not offered, and the pipeline reports it.
3. **Given** a snapshot made on an older data version than the release in the app, **When** the app loads it, **Then** it is not offered.
4. **Given** an approved snapshot, **When** a Brand Director opens it, **Then** they see its executive summary only, as for any briefing.

---

### User Story 8 - Forecast roles are reserved (Priority: P3)

The Forecast lane's roles are defined now so that the Forecast view can plug in later: the Commercial Analytics Analyst (CA) gets the analyst view and the Brand Manager (BM) the leadership view (executive summary only). No Forecast endpoint is exposed until the Forecast lane provides one. **(Forecast lane; Alvin and Sienna confirm the role-to-view mapping and the leadership summary's contents.)**

**Why this priority**: Both lanes share one access model, but the Forecast endpoints are not in this repository yet.

**Independent Test**: Sign in as each Forecast role and check that it sees no Forecast data and no Briefing data.

**Acceptance Scenarios**:

1. **Given** a Forecast role, **When** it signs in before the Forecast endpoint exists, **Then** it sees a "not yet available" message and no data.
2. **Given** a Forecast role, **When** it requests a Briefing, **Then** the request is refused; roles do not cross lanes.

### Edge Cases

- A user has roles in both lanes: each lane uses that lane's role. Within one lane a user holds one role only.
- A briefing abstains or withholds a cut: the executive summary carries the abstention or the "not reportable" notice in place of the number, never a blank or a zero.
- The sign-in service restarts after an idle period: active sessions end and users sign in again; no account, role or password is lost, because they are reloaded at every start.
- A participant tries to change their own password: not offered in UAT (it would be lost at the next restart); an owner resets it.
- A request names a week, territory or brand outside the release: refused with a clear message (existing behavior on `feature/ui-integration`), for every role.
- The UAT event store is unreachable: the briefing is still served, and the missed event is reported in the server log, not silently dropped.
- A leader's response must not carry the data in any other field (error details, debug output, response headers).
- A merge reaches `main` while a pipeline is already running: the later merge deploys after it, and the live app never runs a version whose checks did not pass.
- Usage spikes (for example a link shared beyond the invited group): the instance cap holds, extra requests wait or are refused, and no charge accrues beyond SC-003.

## Requirements *(mandatory)*

### Functional Requirements

**Roles and views**

- **FR-001**: The system MUST define exactly these roles: Briefing Commercial Analyst (P1), Briefing Brand Director (P3), Forecast Commercial Analytics Analyst (CA), Forecast Brand Manager (BM). P2, P4 and FM MUST have no role. The role-to-permission map MUST live in one versioned file in the repository.
- **FR-002**: The system MUST offer two views per lane: the analyst view (answer, claims, evidence items, trace) and the leadership view (executive summary only).
- **FR-003**: The server MUST decide the view from the authenticated role, and MUST remove evidence items, query text and trace data from every leadership response before it leaves the server.
- **FR-004**: Analyst roles MAY request the leadership view of a run. Leadership roles MUST be refused the analyst view.
- **FR-005**: Every number in an executive summary MUST be a claim of the same run, filled by code (shared Principle I). A language model MUST NOT produce or rewrite it.
- **FR-006**: An executive summary MUST keep every abstention, "not reportable" notice and partial-coverage label of the full answer (shared Principle V).
- **FR-007**: A role MUST NOT read the other lane's data. Forecast roles MUST see no data until the Forecast lane exposes its endpoint (Forecast lane; Alvin and Sienna confirm).
- **FR-008**: The server MUST answer "who am I" with the signed-in user's role and allowed views, so the frontend shows only allowed controls.

**Approval**

- **FR-009**: A leader MUST see only briefings that the lane's analyst approved. In UAT the analyst's approval alone publishes a briefing (closes core-007 open item 1; brief-005's two-step sign-off remains the target beyond UAT).
- **FR-010**: The analyst MUST be able to approve or reject a briefing; a rejection MUST carry a reason. Approvals MUST survive a restart of the app.

**Sign-in**

- **FR-011**: Every page and data request MUST require a signed-in user, except the sign-in page and a health check that returns no data.
- **FR-012**: Only accounts created by an owner MAY sign in. Self-registration MUST be off.
- **FR-013**: Accounts, roles and sign-in settings MUST be reloaded from versioned configuration at every start of the sign-in service. Passwords and client secrets MUST come from a secret store, never from the repository.
- **FR-014**: A user with no role, or a role not listed in FR-001, MUST see no data.
- **FR-015**: The sign-in service MUST be the free open-source edition of Keycloak, with no paid subscription or paid add-on.

**Hosting and cost**

- **FR-016**: The hosted app MUST run only the deterministic scripted engine itself, plus committed agent snapshots (FR-027) and agent results posted by the owner's local worker (FR-028). It MUST NOT call a language model.
- **FR-028**: Agent jobs MUST go through a queue the app keeps: only the analyst role may submit; only a caller with the worker token may take or complete a job; the worker connects outbound only; one job runs at a time; a job not finished within its cap is marked failed. A posted result MUST pass the FR-027 traceability check on the app's data version before anyone sees it, and is labelled "agent output, experimental" with its model. The UI MUST show whether the agent host is online.
- **FR-017**: The hosted app MUST serve the frontend and the server from the same address.
- **FR-018**: The hosted app MUST contain no file from the eval package and no ground-truth file (shared Principle III). A check in the pipeline MUST fail if one is present.
- **FR-019**: The hosted app MUST show that its data is synthetic (shared Principle VI).
- **FR-020**: Every service MUST scale to zero when idle and MUST have a capped number of instances. The setup MUST need no always-on machine and no managed database, and MUST use only services and regions covered by Google Cloud's free tiers.
- **FR-021**: The project MUST have a budget alert that fires before any charge above SC-003, and stored build images MUST be pruned to the most recent few versions.

**Automatic deployment**

- **FR-022**: A merge to `main` MUST start the checks (tests, golden-set validation, the no-model baselines and the snapshot traceability check), and MUST deploy a new version only if all of them pass.
- **FR-023**: An owner MUST be able to put the previous version back in service without rebuilding.
- **FR-024**: The pipeline MUST authenticate to Google Cloud without a long-lived key.

**Team operation**

- **FR-029**: The owner MUST be able to grant and revoke, per teammate Google account, a deployer role set that lets the teammate deploy the app and Keycloak, roll back, and read status, logs and the shared environment file (FR-030), with no long-lived key. The role set MUST NOT include billing, budgets, project deletion or granting access to others.
- **FR-030**: The deployment's environment file (UAT passwords, session, client and worker secrets) MUST be shared in the project's secret store, never in the repository. A teammate with the FR-029 role set MUST be able to pull it into their own `deploy/.env.uat` with one command and push a changed one back. A Keycloak deploy MUST refuse to run from a local file that differs from the shared copy, so one teammate's stale file never overwrites another's passwords.

**UAT tracking**

- **FR-025**: The hosted app MUST record one UAT event per briefing: role, pseudonymous participant ID, question time, insight time (when the participant marks that they have what they need), server latency, approve or reject with reason, flagged claims, engine, engine version and data version. UAT events MUST NOT hold names, email addresses or other direct identifiers of participants, and MUST NOT identify an individual rep (B-VI). Recording MUST NOT use the eval package, and a failed recording MUST NOT stop the briefing from being served.
- **FR-026**: The owners MUST be able to import UAT events into the local MLflow store as a UAT experiment, separate from golden-set runs, reporting time to insight, approval rate, flagged-claim rate (the UAT accuracy measure), latency and cost by role and by engine.

**Agent snapshots**

- **FR-027**: Agent output MUST reach the hosted app only as snapshots generated locally and merged to `main`. Each snapshot MUST hold the answer, claims, evidence items, engine, engine version, model and data version. A snapshot MUST be served only if every number in its answer is a claim and every claim resolves to an evidence item on the data version the app serves; otherwise it MUST NOT be offered. Served snapshots MUST be labelled "agent output, experimental".

### Key Entities

- **Role**: a lane, a persona ID (P1, P3, CA, BM), and the views it allows.
- **View**: analyst or leadership; the fields each one may carry.
- **Participant account**: an owner-created sign-in with one role per lane; reloaded from configuration at every start.
- **Briefing**: one run of the scripted engine or one agent snapshot, with its approval state (pending, approved, rejected with reason).
- **Executive summary**: the leadership rendering of one briefing: headline lines, claims filled by code, and every caveat and abstention of the full answer; no evidence or trace.
- **Agent snapshot**: a locally generated low-code briefing for one week and territory, with engine, version, model and data version, committed to the repository.
- **UAT event**: one briefing in one session, with the fields in FR-025.
- **Deployed version**: a build of `main` that passed the checks, with its commit, engine version and data version; the previous version stays available for rollback.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In an automated test over every role and every data request, 100% of leadership responses carry zero evidence items, query text or trace fields, and 100% of leadership requests for the analyst view are refused.
- **SC-002**: 100% of data requests without a signed-in user, or from a user with no listed role, are refused, and 100% of unapproved briefings are hidden from leaders.
- **SC-003**: The sign-in service, app and pipeline cost $0 beyond Google Cloud's basic usage billing; the total bill for a UAT month is under $1 (expected: cents for image storage, or nothing).
- **SC-004**: A participant sees a briefing within 60 seconds of asking, including a cold start after an idle period, and within 10 seconds when the app is already running.
- **SC-005**: A merge that passes the checks is live within 15 minutes with no manual step; a merge that fails them never goes live; a rollback takes effect within 5 minutes.
- **SC-006**: The pipeline's content check finds no eval or ground-truth file in any deployed version.
- **SC-007**: At least 90% of UAT briefings have a complete UAT event in the MLflow UAT experiment.
- **SC-008**: 100% of numbers in executive summaries and in served agent snapshots match a claim with resolvable evidence.
- **SC-009**: Each UAT participant, in their role, reaches their first briefing on their first sign-in without help from an owner.

## Assumptions

- Prerequisite: `main` holds the eval harness, shared tools and low-code build (PR #5) and a cleaned-up version of `feature/ui-integration` before any automatic deployment starts.
- UAT participants are a small invited group (about 5 to 15) for a few weeks; the free tiers cover the load.
- A Google Cloud billing account (with a payment card) is required to create the project even when usage stays within the free tiers.
- Named platforms are constraints set by the course task and by Michael, not design choices left open: Google Cloud (Cloud Run, Secret Manager, Cloud Storage, Artifact Registry) in a US region covered by the free tiers, Keycloak for sign-in, MLflow for tracking. Images are built by GitHub Actions rather than Cloud Build (2026-11-11, build). Keycloak runs scaled to zero with no database; lost sessions and slow first sign-ins after an idle period are accepted for UAT.
- Approvals and UAT events are kept in Cloud Storage (within its free tier), not in a database.
- UAT accuracy is measured as the share of claims participants flag as wrong, plus the approval rate; scored accuracy stays with the golden set in the eval harness (core-006), which the hosted app never touches.
- Time to insight runs from the moment the participant asks to the moment they mark that they have what they need.
- Cost per briefing is the Cloud Run cost for the hosted scripted engine. For agent snapshots generated locally on Ollama, compute time is reported and the dollar cost is reported as not measured, not as zero (core-006 edge case on missing cost data).
- The snapshot list (weeks, territories, questions) is chosen by the owner at plan time. Snapshots answer the questions they were generated for, never new ones.
- Until the low-code build passes `eval gate` against the scripted baseline, its snapshots are labelled experimental; the per-snapshot traceability check (FR-027) is what admits them.
- For UAT, this spec replaces brief-005's assumption that reviewer accounts are local roles with no real identity system, and its two-step sign-off (FR-009). Edit capture and the full publish workflow stay in brief-005.
- The leadership executive summary for the Forecast lane (including Forecast's "dynamic projections") is defined by the Forecast lane.

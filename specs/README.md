# PharmAgentics Spec Index

One Spec Kit feature per component. Specs say WHAT and WHY. Each `plan.md` says HOW. Each `tasks.md` is the work list. Updated 2026-10-23 to the Oct 21–22 sources; the Oct 16 numbering (001 to 010) is retired.

**2026-10-29:** the project moved to eval-driven development. Only the five `brief-###` specs (`brief-001` to `brief-005`, the Briefing lane's own) keep their `spec.md` but have no `plan.md` or `tasks.md`; those were scrapped and will be re-planned against the golden set in [`eval/`](../eval/README.md). The `core-*` specs, which serve both lanes, keep their plans, and so do any future `fcst-*` specs.

**Sources, in order of precedence** (all in [`docs/planning/`](../docs/planning/README.md)): the Proposal; each lane's personas and evaluation pack; the [System Architecture](../docs/planning/system-architecture.md); each lane's architecture doc ([Briefing](../docs/planning/briefing-architecture.md)). The [user stories](../docs/planning/user-stories.md) supply the acceptance scenarios.

**Constitutions:** shared [`.specify/memory/constitution.md`](../.specify/memory/constitution.md) v2.0.0 and Briefing lane [`.specify/memory/constitution-briefing.md`](../.specify/memory/constitution-briefing.md) v1.0.0.

## Namespaces (System Architecture §8, S12 Proposed)

| Prefix | Scope | Owners |
| :- | :- | :- |
| `core-###` | Shared platform both lanes stand on: data world, semantic layer, load-pin-gate, tool and handoff contracts, run orchestrator, eval harness and tracing | Both teams |
| `brief-###` | Briefing lane: stages 3a to 7 | Michael, Meghna |
| `fcst-###` | Forecast lane: stages 3b to 7. `fcst-001` is reserved for Alvin's `001-forecast-explanation-v1` when the `alvin-forecast-explanation` branch merges | Alvin, Sienna |

A `core` spec records what each lane needs from the shared part. It does not specify a lane's internals. Forecast requirements in `core` specs restate the Forecast team's own documents and are marked **(Forecast lane; Alvin and Sienna confirm)**.

## Specs

| Spec | Feature | Stages | Eval items | User stories (acceptance anchors) | Depends on | Replaces (Oct 16) |
| :- | :- | :- | :- | :- | :- | :- |
| [core-001](core-001-data-world/spec.md) | Data world: foundation, generator, injection library | Data | supports all | P1-Q1, P1-Q2, P2-Q1, CA-Q1, CA-Q6 | none | 001-data-generator |
| [core-002](core-002-semantic-layer/spec.md) | Semantic layer | Cross-cutting | EV-9.2 | P1-Q6, P3-Q3 (terms) | core-001 | 002-semantic-layer |
| [core-003](core-003-load-pin-gate/spec.md) | Load, pin and validation gate | 1, 2 | EV-1.2, EV-2.1, EV-2.3, EV-2.4; FE-01 to FE-03 | P1-Q1, P1-Q2, P2-Q1, P2-Q5, P3-Q6, CA-Q1 | core-001, core-002 | 003-validation-gate |
| [core-004](core-004-tool-handoff-contracts/spec.md) | Tool interface and handoff contracts | 4 (tools), all handoffs | EV-4.3, EV-6.1, EV-9.1, EV-9.3; FE-20, FE-30 | P1-Q4, P2-Q4, P3-Q5, P4-Q2 | core-002, core-003 | 005-tool-contracts |
| [core-005](core-005-run-orchestrator/spec.md) | Run orchestrator | 1 to 7, both lanes | EV-8.5; FE-21, FE-26 | P1-Q6, P2-Q6, CA-Q6 | core-002 to core-004 | 009 (orchestrator part) |
| [core-006](core-006-eval-harness-tracing/spec.md) | Eval harness and tracing | Cross-cutting | all EV; FE-30 and the shared harness for FE | all 42 (dev anchor cases) | core-001, then all | 010-eval-harness-tracing |
| [core-007](core-007-rbac-uat-deployment/spec.md) | Role-based access and UAT deployment (Google Cloud, Keycloak, UAT tracking in MLflow) | Cross-cutting (serving) | EV-9.3, EV-9.4; FE-30 | P1-Q2, P1-Q4, P3-Q1, P3-Q6; CA, BM (roles only) | core-006, brief-005 | new (2026-11-11) |
| [brief-001](brief-001-competitive-intelligence/spec.md) | Competitive intelligence | 3a | EV-3.1 to EV-3.4 | P1-Q3, P1-Q5, P3-Q1, P3-Q2 | core-002, core-003 | 004-competitive-intelligence |
| [brief-002](brief-002-triage-investigation/spec.md) | Triage, manager and specialists | 4a | EV-2.2, EV-4.1 to EV-4.5, EV-5.1, EV-5.2, EV-5.4, EV-7.2 | P2-Q1 to P2-Q4, P3-Q4, P4-Q1, P4-Q2, P4-Q4, P4-Q5 | brief-001, core-004 | 006-triage-investigation |
| [brief-003](brief-003-narrative-renderer/spec.md) | Narrative and renderer | 5 | EV-1.1 to EV-1.3, EV-7.1 to EV-7.5, EV-8.5 | P1-Q6, P3-Q3, P3-Q5, P3-Q6, P4-Q3, P4-Q6 | brief-002 | 007-narrative-renderer |
| [brief-004](brief-004-verifier/spec.md) | Verifier | 6 | EV-1.1, EV-5.3, EV-6.1, EV-9.1, EV-9.2 | P1-Q1, P1-Q4, P2-Q5, P3-Q6 | brief-003 | 008-verifier |
| [brief-005](brief-005-review-signoff/spec.md) | Review, sign-off and feedback | 7 | EV-6.2, EV-6.3, EV-8.1 | P1-Q1, P1-Q4, P1-Q6, P2-Q5 | brief-004, core-005 | 009 (review part) |

**Build order** (Briefing Architecture §14, three builds): scripted baseline first (core-001 to core-005, brief-001, a fixed-order brief-002, then brief-003 to brief-005), then low-code, then the Magentic agent. core-006 starts early so every build is scored on the same cases.

## Shared decisions every spec uses

A spec that changes one of these logs it here and in the source doc's decision log.

| Decision | Value | Source |
| :- | :- | :- |
| Data world | The repo's DuckDB foundation (seed 7, `day1-v1`) is the one world for both lanes. Never hard-code its size | System D7; user, 2026-10-16 |
| Answer key | Lives outside the repository. No answer-key, true-data, counterfactual or held-out file is ever committed | System §3.1, §3.7; user, 2026-10-23 |
| Restatement window | **Open (S4).** Briefing proposes 3 weeks; the release restates week 2026-04-06 on 2026-07-13, 14 weeks later. The window is a semantic-layer setting; out-of-window restatements are flagged and disclosed, never applied silently | System S4; Eval item 18 |
| As-of snapshots | The release ships one pull with restated values applied. A run that must show the value as it stood on an earlier date rebuilds it from `restatement_log` prior values (core-003) | user story P2-Q5; data check 2026-10-23 |
| Confidence (Briefing) | High, Medium, Low. Low means abstain. Forecast keeps its own scale until S10 | Briefing Arch §5.4; System §6 |
| Business impact | Absolute change in TRx 30-day equivalents (proposed) | Briefing A4 |
| Investigation requests | One `briefing.investigation_request` per run | Briefing A15 |
| All cuts fail | Publish a data-health notice only (proposed) | Briefing A7 |
| P2 returns a brief | Back to the narrative stage with comments (proposed) | Briefing A8 |
| Orchestration | One run orchestrator for both lanes; each lane keeps its own trigger, states and Magentic loop | System §3.4, S2 |
| Lane names | `briefing.` and `forecast.` prefixes on colliding names | System §6 |
| Inventory driver | **Proposed (S5).** `lookup_inventory` and an inventory catalog entry are kept for the Briefing lane. User stories P1-Q5 and P3-Q3 need it (Pacific supply, June 2026) | User, 2026-10-16 (X3); System S5 |
| Promotion | One tested driver with a verdict either way; stated as an association with its method named; no attribution or ROI model | Briefing decision 20; A16 |
| Comparison group | A territory change is compared with the other territories over the same weeks; territories with their own active event are dropped from the control set | User stories (method note), P4-Q5, FM-Q4 |
| Loop caps | Values live in the semantic layer; starting values in core-002 plan | Eval item 17 |
| Test runner | pytest, which also runs the existing `unittest` suite unchanged (proposed answer to S15) | System S15 |
| Roles and views | One analyst and one leader per lane: P1 and P3 (Briefing), CA and BM (Forecast; Alvin and Sienna confirm). Leaders get the executive summary only, enforced by the server, and see only analyst-approved briefs. P2, P4 and FM have no role | core-007; Michael, 2026-11-11 |
| Hosting | UAT app on Google Cloud within the free tiers; free Keycloak; scripted engine live, no language model in the cloud; agent output only as locally generated, committed snapshots that pass a traceability check | core-007; Michael, 2026-11-11 |

## Open items by spec

Markers `[NEEDS CLARIFICATION: …]` stay in the spec that owns them, at most three per spec, each tied to an open-item ID.

| Spec | Open |
| :- | :- |
| core-001 | Answer-key format for both lanes (S10, Eval 8); held-out seed ownership (Eval 11); calibration class (A12) |
| core-002 | Rep-activity aggregation floor (Eval 5); cap values (Eval 17); restatement window (S4) |
| core-003 | Restatement window and out-of-window handling (S4); all-cuts-fail behavior (A7) |
| core-004 | Agent framework (A3); one tool-record shape (S9). The aggregation floor it applies is held in core-002 |
| core-005 | Proposal amendment (S2); runtime handoff (S1) |
| core-006 | Rerun count (Eval 15); rubric anchors (Eval 13); shared vocabulary (S10) |
| core-007 | Forecast role-to-view mapping, CA analyst and BM leader (Alvin and Sienna confirm). Open items 1 (approval: analyst alone in UAT) and 2 (agent output: committed snapshots) closed 2026-11-11 |
| brief-001 | Business impact (A4); multiple-testing control (A5) |
| brief-002 | Triage junction (A1); plan-review default (A10) |
| brief-003 | Monday template and length (Eval 4); promotion reach and campaign data (A16, Eval 19) |
| brief-004 | Judge agreement bar (Eval 2) |
| brief-005 | Sign-off level (A9); whether reviewers may overwrite a number by hand |

Not tied to one spec: Eval items 1, 6, 7, 14 (mentor or team); S13 (dropped agents' folders); S14 (data-use review per provider); A13 (owner names); A14 and S8 ("surveillance" in the repo README, data README and Proposal).

## Dev anchor cases

Each user story is anchored on a real week of the `day1-v1` release. core-006 turns each anchor into a dev case (`C-###` for Briefing, `TC-##` for Forecast). The story's Given / When / Then is the case; its "must not say" is the case's fail phrase.

| Anchor | Weeks | Briefing stories | Forecast stories | Main spec |
| :- | :- | :- | :- | :- |
| Great Lakes duplicate keys | 2026-07-06 | P1-Q1 | CA-Q1 | core-003 |
| New England incomplete, late, low-coverage feed | 2026-05-04 | P1-Q2 | CA-Q1 | core-003 |
| Mid-Atlantic restatement (692 → 742, recorded 2026-07-13) | 2026-04-06 | P2-Q1, P2-Q5, P3-Q6 | — | core-003 |
| Quiet week, normal territory swings | 2025-04-21 | P1-Q3 | — | brief-001 |
| Holiday and plan-year-reset weeks | 2025-12-22, 2025-12-29 | P3-Q2 | — | brief-001 |
| Mid-Atlantic Part D plan access restriction | 2025-08-04 to 2025-10-27 | P1-Q4, P2-Q2, P2-Q4 | CA-Q5 | brief-002 |
| Mid-Atlantic access restored, seasonal rise | 2025-11-03 to 2025-12-15 | P4-Q4 | — | brief-002 |
| Metacora launch and share gain | 2026-03-02 onward; 2026-04-27; 2026-09-28 | P3-Q1, P3-Q4 | BM-Q2, FM-Q2, FM-Q5 | brief-001, brief-002 |
| Great Lakes promotion lapse | 2026-02-02 to 2026-04-06 | P4-Q1, P4-Q2, P4-Q5 | FM-Q4 | brief-002 |
| Pacific supply shortfall | 2026-06-01 to 2026-06-29; 2026-06-08 | P1-Q5, P3-Q3 | CA-Q4 | brief-002, brief-003 |
| Southeast promotion lapse | 2026-08-03 to 2026-08-31; 2026-08-24 | P1-Q6, P3-Q5, P4-Q2, P4-Q6 | CA-Q2, CA-Q3, BM-Q1, BM-Q3, BM-Q5, BM-Q6, FM-Q1, FM-Q6 | brief-002, brief-003 |
| South Central gap with no visible driver | 2026-08-31 to 2026-09-28 | P2-Q3 | BM-Q4, FM-Q3 | brief-002 |
| Held-out stretch with artifacts and holidays | to be generated | P2-Q6 | — | core-006 |

The release counts 6 seeded business events; 5 show a driver in the context tables. Whether the South Central gap is the sixth event or noise is decided by the answer key, which only core-006 reads.

## Working on a spec in Antigravity or Claude Code

Spec Kit finds the active spec from `.specify/feature.json` (git-ignored) or the `SPECIFY_FEATURE_DIRECTORY` variable, not from the branch name. Before running `/speckit-clarify`, `/speckit-plan`, `/speckit-tasks`, `/speckit-analyze` or `/speckit-implement` on an existing spec, point it at the folder:

```powershell
'{"feature_directory":"specs/brief-002-triage-investigation"}' | Out-File -Encoding ascii .specify/feature.json
```

New specs: run `/speckit-specify` and then rename the created folder into its namespace (`core-`, `brief-` or `fcst-`), and update `feature.json` to match.

## Source layout

```text
data/agent_visible/            the 14-table release; agent tools read only this (via DuckDB)
local/pharmagentics.duckdb     built by the loader; git-ignored
sql/                           reporting views (v0 gate)
semantic_layer/                versioned YAML (core-002)
src/pharmagentics/             shared data layer and orchestration (core-001 to core-005)
  data/          loader and checker (core-001, built)
agents/
  brand-briefing/              Briefing lane (Michael, Meghna)
  forecast-explanation/        Forecast lane (Alvin, Sienna)
eval/                          eval harness, golden set and MLflow store (core-006)
SoT/                           dated Drive exports of the source docs; drops git-ignored
tests/                         data-foundation tests
```

Outside the repository, never committed: the generator, the answer key, the pre-artifact true data, the counterfactual components and the sealed held-out parameters. Only `eval/harness/store.py` reads them, through a path set in an environment variable (core-006).

# Implementation Plan: Narrative and Renderer, slice 1 (memo outline and projected national)

**Branch**: `feature/brief-memo-follow-ups` | **Date**: 2026-11-19 | **Spec**: [spec.md](spec.md) (Draft v3)

**Input**: Feature specification from `specs/brief-003-narrative-renderer/spec.md`, Clarifications 2026-11-19, `GLOSSARY.md`, `docs/adr/0001-projected-national-without-projected-drivers.md`

## Summary

Slice 1 of five turns every Briefing brief, scripted and agent, into the six-section memo the spec settles (§1 Bottom line, §2 The numbers, §3 What changed and why, §4 What the data can't tell us, §5 Next checks, §6 Appendix) and adds a projected national TRx built territory by territory from panel coverage (ADR 0001). Code builds every section and number; the agent's writer still writes only the §1 answer and one sentence per §3 story. Golden cases P1-Q2 and P3-Q6 change to expect the projection. The slice merges only if `eval gate` shows no gated regression for either system against baselines taken at `c15ccde`.

Technical approach (details in [research.md](research.md)):

1. A governed view `reporting.v_rx_projection` exposes, per week, territory and product, the basis (observed, projected, estimated), panel coverage and the observed TRx of cuts whose only faults are completeness faults. Duplicate-key or under-review cuts expose no TRx, so they are estimated.
2. `pharmagentics/tools/projection.py` builds one self-contained SELECT per claim (national, territory, share), so `claims_reconcile` can re-run each one.
3. `pharmagentics/tools/memo.py` composes the memo from parts and returns both the token template (flattened `answer`) and structured `sections`. The scripted pipeline and the MCP server's admin tools both call it, so both engines emit the same skeleton (FR-020).
4. The leadership view keeps §1, §2, §3 without checks, and §5 (FR-026, text level).

Out of scope for slice 1: charts (FR-024), evidence tables, queries and CSV per section (FR-025), the UI's section rendering, the length limit (FR-004, open item 4), promotion context (US5). See "Slices" below.

## Technical Context

**Language/Version**: Python 3.12 (floor 3.11), uv-managed

**Primary Dependencies**: DuckDB (governed views), Microsoft Agent Framework + MCP 2.x (agent), Anthropic Claude Haiku 5.5 (agent writer, core-007 FR-032), MLflow 3.17 (eval)

**Storage**: `local/pharmagentics.duckdb`, rebuilt from `data/agent_visible/` by `src/pharmagentics/data/load_duckdb.py`; the new view lives in `sql/001_reporting_views.sql`. Data version is a hash of the import manifest, so a new view does not change it.

**Testing**: pytest (`tests/`, `eval/tests/`), `python -m eval check`, `python -m eval run`, `python -m eval gate`

**Target Platform**: local Windows dev; Cloud Run image (Dockerfile builds the database with the loader)

**Project Type**: Python library and agents, plus a FastAPI web app (unchanged except the leadership view)

**Performance Goals**: scripted brief under 5 s per case; agent brief cost and latency unchanged within noise (about $0.02 a brief on Haiku)

**Constraints**: no digit outside a claim token (verifier rule); claims re-runnable as single SELECTs over governed relations; agent code never imports `eval/`; another session edits `stages.py`, `registry.py`, `App.tsx` in the main tree, so slice 1 adds new modules and keeps edits to those files to single hunks

**Scale/Scope**: 24 Briefing golden cases, 104 weeks × 8 territories × 4 products

## Constitution Check

*GATE: passes before Phase 0; re-checked after Phase 1 (below).*

| Article | How slice 1 complies |
| :- | :- |
| I Every number from a tool | Projection values, counts and shares are claims from single SELECTs; section headings carry no digits; the writer still types none |
| II Agents explain, people decide | Unchanged: review gate and leadership view stay; §5 names an owner and the decision a check unlocks, never acts |
| III Answer-key isolation | Golden facts recompute through SQL in `eval/` only; agent and tool code never read `eval/` (`eval/tests/test_isolation.py`) |
| IV Typed contracts | `AnswerEnvelope` gains an optional `sections` field (new optional fields are allowed); MCP admin tools are caller-only and keep their names; the new `memo_close` tool is admin-only |
| V Abstain when weak | Estimated and projected cuts never open a story or name a driver (FR-023; stories come only from like-for-like territories); §1 names the number least sure of |
| VI Synthetic data only | Unchanged; the writer prompt still carries only tokens and labels |
| VII Loops end | No loop changes |
| B-I Semantic layer | Partial, as today: projection thresholds (0.98, 0.5) and the completeness-reason list are module constants beside `MATERIAL_CHANGE`; they move when the semantic layer is built (Complexity Tracking) |
| B-II Mode declared | Memo, projection, §1 rule and §5 are code; the writer stays the only model step in stage 5 |
| B-III Pinned data version | Every claim pins the data version; §6 states it; restatements are disclosed in §2 |
| B-IV Traceable | Every new claim is an evidence item with its SQL; spans unchanged |
| B-V Bounded loops | Unchanged |
| B-VI No individual | No rep-level data used |
| B-VII Evaluation gate | Baselines at `c15ccde` for `briefing_scripted` and `briefing_agent` (Haiku); candidate must not regress a gated check |
| Lane constraint: confidence | §1 least-sure rule uses code confidence; causal wording rules unchanged |

Result: **PASS**, one tracked deviation (B-I, pre-existing).

## Project Structure

### Documentation (this feature)

```text
specs/brief-003-narrative-renderer/
├── plan.md              # this file
├── research.md          # Phase 0 decisions R1 to R16
├── data-model.md        # Projection, memo, section entities
├── quickstart.md        # how to prove slice 1 works
├── contracts/
│   ├── v_rx_projection.md      # the governed view
│   ├── memo-envelope.md        # answer text layout + `sections` field
│   └── mcp-admin-tools.md      # brief_sections keys, memo_close
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
sql/001_reporting_views.sql                    # + reporting.v_rx_projection
src/pharmagentics/tools/
├── registry.py                                # + view in ALLOWED (one line)
├── queries.py                                 # + projection SQL builders
├── projection.py                              # NEW: projected national, territory rows, basis labels
├── memo.py                                    # NEW: §1 to §6 composition, least-sure rule, next checks, glossary
└── checks.py                                  # + DECISION map beside OWNER
src/pharmagentics/mcp_server/server.py         # brief_sections gains memo parts; story_section without "Next:"; + memo_close
src/pharmagentics/api/views.py                 # executive_summary by section heading
agents/brand-briefing/briefing_baseline/pipeline.py   # builds the memo through tools/memo.py
agents/brand-briefing/briefing_agent/__init__.py      # calls memo_close, returns sections
agents/brand-briefing/briefing_agent/write.py         # assemble() through tools/memo.py; writer sees the memo
agents/brand-briefing/briefing_agent/prompts/writer.md   # answer = §1 prose, stories = §3 prose
eval/harness/envelope.py                       # + optional sections
eval/golden/briefing/P1-Q2.yaml, P3-Q6.yaml    # projection expectations + facts
eval/golden/CHANGELOG.md                       # one row
tests/test_projection.py                       # NEW: SC-011 hand calculation on every week
tests/test_memo.py                             # NEW: outline, §1 order, leadership cut, digits
tests/*, eval/tests/*                          # updated string expectations
```

**Structure Decision**: new shared modules under `src/pharmagentics/tools/` (the shared data layer), consumed by both Briefing engines, so the manager-off ablation stays exact. No frontend change in slice 1: the hosted app shows the flattened memo text in its existing panel; slice 2 renders sections.

## Slices (proposed; slice 1 is this plan)

| Slice | Scope | Gate |
| :- | :- | :- |
| 1 | Memo outline, projected national, §1 rule, §5, leadership cut; P1-Q2, P3-Q6 | eval gate, scripted and agent |
| 2 | Charts with captions (FR-024), evidence tables, query toggle, CSV (FR-025), UI renders sections, server-side strip (FR-026 full) | eval gate + UI check on the real app |
| 3 | brief-006 follow-ups, scripted engine, threads | eval gate + two-turn cases |
| 4 | brief-006 follow-ups on Haiku; the six two-turn golden cases | eval gate |
| 5 | core-008 FR-019 to FR-022 feedback loop (lessons proposed, people promote) | eval gate |

Confirmed by Michael on 2026-11-20, with slice 2's choices (inline SVG charts, baseline band = min to max of the baseline weeks, first supported driver's panel, CSV built in the browser, a real-app check) and the slice 3 to 5 decisions in brief-006 and core-008 (Session 2026-11-20). The build order and stop rules for an unattended session are in `specs/HANDOFF-memo-slices.md`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
| :- | :- | :- |
| B-I: projection thresholds and the completeness-reason list as module constants | No semantic-layer YAML exists in code yet; every current threshold (`MATERIAL_CHANGE`, `NOISE_Z`) is a module constant | Building the semantic layer is its own spec; blocking slice 1 on it delays the memo |
| A new reporting view that reads `raw.rx_weekly` for failed cuts | The governed views hide a failed cut's TRx entirely, and New England's projected level needs its observed 267 TRx | Reading `raw.rx_weekly` from tools breaks the hard rule; the view exposes TRx only for completeness-only faults, never for duplicate or under-review cuts |

## Post-design Constitution Re-check

Re-checked after data-model and contracts: no new violation. The view is read-only and governed (added to `ALLOWED`); every projection claim is a single re-runnable SELECT; the `sections` field is optional, so older consumers ignore it.

## Slice 2: charts, the data behind each section, sections in the UI (2026-11-20)

Michael's choices: inline SVG, no chart library; baseline band = lowest to highest of the baseline weeks; second panel = the first supported driver's series (none supported: TRx only, and the caption says so); CSV built in the browser from the rows in the response; a real-app check at the end.

- `src/pharmagentics/tools/charts.py`: four builders (§2 trend, §3 story, §3 Metacora shares, §4 coverage). Each reads one governed multi-row SELECT recorded as an evidence item, so every plotted point re-runs (FR-025). Captions are code with claim tokens and name only the marks the chart shows (a smoke run showed the writer reading a generic "dotted points were restated" as a claim). Explanations are code templates; the agent's writer may replace one with its own line, checked like its sentences, and a failing line keeps the template.
- `tools/memo.py`: sections carry `chart`; the flattened answer carries each caption and explanation, so the gated scorers check their numbers (FR-027); `render_sections` adds per-section citations.
- MCP `memo_close` returns the charts built by the same code as the scripted brief (FR-020).
- API: `BriefingResult.sections`; the leadership response carries `views.leadership_sections` (§1, §2, §3 without checks, §5; allow-lists, no claims, citations, tables or queries) (FR-026).
- UI: `frontend/figma-make/src/Memo.tsx` (numbered sections, inline citations, SVG charts, "Data behind this section" with a query toggle and CSV); `App.tsx` changes three lines.
- Checks: `tests/test_charts.py` (chart rows re-run to the same rows, kinds, hollow projected weeks, captions in the answer, leadership leaks); the real app driven in headless Chrome over the DevTools protocol for Pacific 2026-06-08 and New England 2026-05-04, analyst and leadership, with screenshots.

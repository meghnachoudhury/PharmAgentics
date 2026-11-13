# Forecast-Explanation Agent

The Forecast lane (Alvin, Sienna): when the locked weekly TRx forecast differs from the actual, it explains what moved, how much each driver explains, how strong the evidence is, how much stays unexplained, and who should check what. It never changes a forecast and never recommends a commercial action.

The rule it keeps: **V = A − F = Σc + r.** The miss V is the sum of the driver contributions c plus a residual r. The residual is reported, never absorbed into a driver. When the actual is provisional or the controls are weak, the agent pauses attribution instead of guessing. Every number comes from a deterministic query over `data/agent_visible/`; a language model, if one is used, only chooses which tool to call and words the result.

## Built

| Where | What |
| :- | :- |
| `feagent/` | The investigator: five governed tools, a bounded tool loop, the seven-stage pipeline, evidence-based confidence and a verification step |
| `forecast_baseline/` | The **scripted baseline** BL-0, the Forecast system the eval harness runs: `uv run python -m eval run --system forecast_scripted --lane forecast` |
| `tests/` | Unit tests for the tools, the estimators, verification, windows and the pipeline |
| `src/pharmagentics/api/forecast.py` | The browser-facing routes for the lane (below) |

### The seven stages

| # | Stage | Kind | Notes |
| :- | :- | :- | :- |
| 1 | Load and pin | code | Pins brand, territory, week and window to one data release |
| 2 | Validation gate | code | A provisional actual **flags** the run and pauses attribution |
| 3 | Detection | code | The miss against the locked forecast, and whether it is material |
| 4 | Investigation | agent | Scripted (stub) or a model choosing among the five tools; **abstains** when evidence is weak |
| 5 | Drafting | code | Headline, drivers, residual, what to check |
| 6 | Verification | code | Passes, **flags** or **fails** the report (below) |
| 7 | Human review | person | The pipeline result always reads `PENDING`; the decision is stored with the run: the Brand Manager approves, rejects or returns a submitted run (see the API) |

### How a driver is estimated

- **Primary estimate:** the forecast error of the exposed regions beyond what the named control regions' forecast error implies, summed to a total and split by region. The baseline for an event is the week before it starts.
- **Cross-check:** the change in actuals against the same controls. When the two disagree by more than a quarter of the miss, the run is flagged.
- **Confidence** is capped by the evidence, never raised by a model: no named control is inconclusive, fewer than two controls is at most medium, and a small gap relative to the spread across controls lowers it further. The reasons are listed on each driver.
- **Windows:** `window_weeks` (1 to 52) makes the tools explain the sum over that many weeks. A window past the data, or one containing a provisional week, is refused.

### What verification checks

Scope matches the request (week, territory, window); V equals A − F; drivers plus residual equal V; a provisional week is never attributed; every driver cites a real tool result for the right window with a matching number (within 0.5 TRx); confidence is not above its cap. A large residual (over half the miss), a driver against the direction of the miss, or disagreeing estimators raise warnings. Any failed check fails stage 6. The verdict is `PASS`, `WARN` or `FAIL` and shows as stage status `COMPLETE`, `FLAG` or `FAIL`.

## API

Roles come from `src/pharmagentics/api/roles.json`. The server decides the view from the signed-in role.

- The **Commercial Analytics Analyst (CA)** runs the agent, reads the full run, may preview the leadership view, and submits a run for approval.
- The **Brand Manager (BM)** does not run or submit: the persona document does not assume BM operates the agent. BM reads the leadership view of **submitted** runs and approves, rejects or returns them.
- Nothing is approved by the system. No new role was added.

| Route | Who | What |
| :- | :- | :- |
| `GET /api/forecast/status` | any signed-in user | The caller's Forecast role, views and actions; the engine in use; whether the lane is open to the UI |
| `GET /api/forecast/cases` | CA | Three ready-made requests (below) |
| `POST /api/forecast/runs` | CA | Runs the pipeline, stores the run as `not_submitted`, and returns it for the caller's view |
| `POST /api/forecast/runs/{id}/submit` | CA | Sends a `not_submitted` or `returned` run to the Brand Manager (`pending_review`) |
| `GET /api/forecast/runs?status=` | CA, BM | Run summaries. BM sees only submitted runs |
| `GET /api/forecast/runs/{id}?view=` | CA, BM | One run in the caller's view, with its review state. BM gets `404` for a run that was never submitted |
| `POST /api/forecast/runs/{id}/review` | BM | `{"decision": "approved" \| "rejected" \| "returned", "note": "..."}`. A rejection or a return needs a note. Only a `pending_review` run can be decided (`409` otherwise) |

Review states: `not_submitted` → `pending_review` → `approved`, `rejected` or `returned`; a returned run can be submitted again. Running the same request again on the same data release returns the same run and keeps its review state. Every step is kept in `history` with the actor's role and a pseudonym (never a name), so a later evaluation log can read it. Runs are stored as JSON documents under `forecast_runs/` in the app's state folder or bucket, like the Briefing approvals.

Request body (extra fields are refused; the engine and model cannot be chosen by the caller):

```json
{"territory_id": "MID_ATLANTIC", "week_start": "2025-08-04", "window_weeks": 13, "view": "analyst"}
```

`territory_id` is one of the eight territories or `NATIONAL`. `window_weeks` defaults to 1. `view` is optional.

| View | Who may open it | Contains |
| :- | :- | :- |
| `analyst` | CA (the default for CA) | Seven stages with status and summary, the full report, drivers with evidence ids, the verification checks, the review history |
| `leadership` | BM (always); CA (on request, as a preview) | The review state and an executive summary: headline, forecast, actual, miss, drivers (name, impact, confidence), residual, what to check, caveats, the verification verdict. No stages, evidence or tool detail |

Bad input is `422`; an unknown week or a window past the data is `400` with a message. `workflow_status` reads "Processing Complete — Pending Human Approval" even for an abstained run, so decide the banner from `report.abstained` and the stage statuses.

### The three ready-made cases

| Case | Request | Expected |
| :- | :- | :- |
| New England, provisional actual | `NEW_ENGLAND`, `2026-05-04` | Miss −173; stage 2 `FLAG`, stage 4 `ABSTAINED`; no drivers |
| National miss | `NATIONAL`, `2026-08-24` | Miss −1,036; promotion about −212; a large unexplained residual, so stage 6 `FLAG` |
| Mid-Atlantic, 13 weeks | `MID_ATLANTIC`, `2025-08-04`, `window_weeks: 13` | Miss −730; payer access about −679; the two estimators disagree, so stage 6 `FLAG`. Without the window the agent would explain only the first week (−34) |

## Configuration

| Setting | Default | Meaning |
| :- | :- | :- |
| `FEAGENT_MODE` | `stub` | The engine for every request. `stub`: the scripted playbook, no language model. `ollama`: a local model through Ollama. `auto`: a local model if one is running, else stub. Anything else means `stub` |
| `OLLAMA_HOST`, `OLLAMA_MODEL` | `http://localhost:11434`, `gpt-oss:20b` | Used only when the mode is `ollama` or `auto` |
| `PHARMAGENTICS_DATA_DIR` | the repository's `data/agent_visible/` | Where the data release is read from |

**Model: GPT Terra**, fixed for the shared deployment. The model and its credentials are set on the server, outside this repository, and a caller cannot pick or change them. The code in this repository runs the stub (no language model) or a local model. A provisional actual is stopped at the gate before any model is called, and a model's report is verified by stage 6 like any other, so an invented number fails.

## Run and test locally

```powershell
uv sync
uv run python src/pharmagentics/data/load_duckdb.py
uv run pytest agents/forecast-explanation/tests tests/test_forecast_api.py -q
$env:PHARMAGENTICS_AUTH = "dev"; uv run uvicorn pharmagentics.api.app:app --port 8080   # then sign in as a Forecast role
```

The dev sign-in page lists a stand-in Commercial Analytics Analyst (`forecast-analyst`) and Brand Manager (`forecast-manager`). The lane stays "Coming soon" in the UI until `lanes.forecast.available` is set to `true` in `roles.json`; the routes work for the Forecast roles either way. The root `README.md` and `CLAUDE.md` cover the rest of the app.

## Not built yet

- Logging runs and review decisions into the evaluation store (MLflow), a thumbs and comment control in the UI, and any rule beyond the one above (who else may approve, whether a returned run needs a different submitter).
- A pre-period check for a miss that began before the event, and calibration of the confidence and verification thresholds.
- Running `feagent` as an eval system on the Forecast golden cases (today only `forecast_baseline` is). The Forecast golden cases and scorers are drafts until Alvin and Sienna confirm them.
- Retrieval or summarising before the model, to send it less context.

Agent code never imports `eval/`; the harness imports it. Ground truth stays outside this repository.

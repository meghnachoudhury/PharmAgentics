# eval

Eval-driven development for PharmAgentics (spec [core-006](../specs/core-006-eval-harness-tracing/spec.md)). Every system answers the same golden questions, is scored by the same checks, and lands in one MLflow dashboard with its traces and spans.

**Status (2026-11-05):** the golden set, code checks, LLM judge, two controls, **two scripted baselines (one per lane)**, the **Briefing low-code build** and MLflow logging work end to end. The custom Magentic agent (brief-002) plugs in next.

## Commands

All from the repository root, after `uv sync` and building the database (`uv run python src/pharmagentics/data/load_duckdb.py`).

| Command | Does |
| :- | :- |
| `uv run python -m eval check` | Validates the 42 cases and recomputes every fact from the data |
| `uv run python -m eval run --system reference` | Scores the golden answers (positive control) |
| `uv run python -m eval run --system naive_llm` | Scores a local model with no data (negative control); needs Ollama |
| `uv run python -m eval run --system briefing_scripted --lane briefing` | The Briefing scripted baseline (`agents/brand-briefing/briefing_baseline/`) |
| `uv run python -m eval run --system briefing_lowcode --lane briefing` | The Briefing low-code build (`agents/brand-briefing/briefing_lowcode/`): Magentic-One over the MCP server, local model; `--model gemini:` for Gemini |
| `uv run python -m eval run --system forecast_scripted --lane forecast` | The Forecast scripted baseline BL-0 (`agents/forecast-explanation/forecast_baseline/`), a draft for Alvin and Sienna |
| `... --lane briefing` / `--stories P1-Q2,CA-Q1` / `--reruns 3` | Narrows the cases or repeats them; reruns report mean and spread |
| `... --judge` | Adds the LLM judge on `ollama:/gemma3:4b`; `--judge gemini:/<model>` switches provider |
| `uv run python -m eval gate <candidate> <baseline>` | Exits 1 if a gated check scores lower than on the baseline run |
| `uv run python -m eval ui` | MLflow dashboard at http://127.0.0.1:5000 |
| `uv run python -m eval import-stories` | Drafts case files for new user stories; never overwrites an existing case |
| `uv run pytest tests/test_tools.py eval/tests` | The shared-tools and harness tests |

Each `run` is one MLflow parent run with a child run per rerun. Every case becomes a trace with its spans (for the baselines: one per pipeline stage and one per tool call, with the SQL as input), its check results and its expectations, all kept in `eval/mlflow/` (git-ignored).

## Layout

| Path | Holds |
| :- | :- |
| `golden/briefing/` | 24 cases, one per Briefing persona question (C-001 to C-024, P1-Q1 to P4-Q6) |
| `golden/forecast/` | 18 cases, one per Forecast persona question (F-001 to F-018, CA-Q1 to FM-Q6). Drafts until Alvin and Sienna confirm them and map each to TC-01 to TC-12 |
| `golden/CHANGELOG.md` | Every change to a case, and what is still open before freezing |
| `labels/` | Human labels that check the LLM judge (Evaluation Pack open item 2) |
| `harness/` | Case model and importer, fact checks, number matching, scorers, systems, answer contract, runner, isolation scans, the store reader |
| `tests/` | Golden-set integrity, code checks on planted answers, the positive control on all 42 cases, isolation scans, an end-to-end MLflow run |
| `mlflow/` | Runs, traces, spans and scores. Git-ignored |

A case holds the question, the golden answer (the story's "Answer from the data"), the Given / When / Then, the must-not-say rule, its eval items and, where verified, **facts**: numbers with the SQL that recomputes them. Today 69 facts on 14 cases recompute exactly.

## Checks

| Check | Passes when | Eval items | Gated |
| :- | :- | :- | :- |
| `numbers_match_golden` | Every number in the answer matches a golden number at the precision stated. Dates, IDs, years and counts up to 10 are skipped | EV-1.1 proxy for systems without evidence | No: a system with evidence may state correct numbers the golden answer omits |
| `golden_number_recall` | The answer states the golden answer's numbers | Completeness | No |
| `must_not_say` | No literal must-not-say phrase appears, allowing rounding and small rewordings | Case rule | Yes |
| `governed_terms` | No "surveillance"; "new patients" only next to NBRx | EV-9.2 | Yes |
| `no_individual_rep` | No line names or numbers a rep (heuristic) | EV-9.1 | Yes |
| `claims_reconcile` | Each claim's stored SQL, re-run on the data, gives the claimed value at its stated rounding (half up). Systems with evidence only | EV-1.1, FE-04, FE-16 | Yes |
| `numbers_traced` | Every number in the answer text is a claim with evidence. Systems with evidence only | EV-6.1, FE-19 | Yes |
| `links_resolve` | Every claim links to an evidence item pinned to the data version of the run. Systems with evidence only | EV-6.2, FE-20 | Yes |
| `run_errors` | Count of cases where the system crashed; a crash is never scored as zero | Run error tag | Yes (gate) |
| `tool_calls`, `llm_calls`, `seconds`, `hit_cap`, `needed_revision` | Report only: how an agent got its answer (trajectory). Agent systems only | Autonomy ledger evidence; white-box | No |
| `judge_factual_correctness` | RAGAS FactualCorrectness against the golden answer, with `--judge` | EV-1.3 | No: report-only until judge-human agreement clears the bar |

A must-not-say phrase followed by a qualifier ("… without the plan", "… as if the rest were on plan") is context-dependent, so code does not check it; it is kept for the judge.

## Results so far

| System | Cases | Numbers match | Recall | Must not say | Governed terms | No rep | Judge |
| :- | :- | :- | :- | :- | :- | :- | :- |
| `reference` (golden answers) | 42 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 on 3 |
| `naive_llm` (`gemma3:4b`, no data) | 42 | 0.556 | 0.064 | 1.000 | 1.000 | 1.000 | 0.297 on 3 |
| `briefing_scripted` (2026-11-04, with week over week) | 24 | 0.157 | 0.388 | 1.000 | 1.000 | 1.000 | 0.607 on 6 |
| `forecast_scripted` | 18 | 0.189 | 0.293 | 1.000 | 1.000 | 1.000 | n/a |
| `briefing_lowcode` (`qwen3:4b-instruct`, 2026-11-04, mean of 3 reruns) | 24 | 0.378 | 0.201 | 1.000 | 0.972 | 1.000 | 0.618 on 6 |

The baselines also score 1.000 on `claims_reconcile`, `numbers_traced` and `links_resolve`, with 0 run errors. Their low golden-number recall is the finding: they state correct, traced numbers, but only about a third of the numbers each story's answer expects. That gap is what the low-code and agent versions are built to close.

**Shared KPI step gains week over week (2026-11-04).** The scripted baseline now adds a week-over-week line to one-week briefs, summed over reportable cuts and then like for like on the territories that report both weeks (Architecture §5.3). P2-Q1 reads 3,860 against 4,729 (down 18.4%) over every reportable cut, and 4,005 to 3,860 (down 3.6%) like for like. The gate of the new scripted run `c58f99fc6e09` against `6608d416dae8` passes on every gated check, and recall rises from 0.364 to 0.388. `numbers_match_golden` falls (0.184 to 0.157) because the new lines state numbers the golden answers do not list; see Known limits.

**Briefing low-code, three reruns (2026-11-05, run `0cd14c5f4266`, against scripted run `c58f99fc6e09`).** The gate fails on four checks: `claims_reconcile` 0.819, `links_resolve` 0.819, `numbers_traced` 0.980 and `governed_terms` 0.972, against 1.000 for the scripted baseline. There were no run errors: a failed model request now ends as a capped brief, not a crash. Every claim the agent states reconciles to the data; the failures are briefs that state no numbers at all (both claim checks score those 0), stray digits left after the one revision, and two briefs that wrote "no new patients reported", which the agent invented and which breaks the NBRx rule. Four cases fail in every rerun: P4-Q5, P4-Q6 and P2-Q6 (three of the six questions with no period) and P1-Q3, a quiet week where the agent called the right tools but wrote "routine week" without the KPI line. Reruns vary: `claims_reconcile` was 0.792, 0.750 and 0.917 (std 0.071), and 7 of 72 case runs hit a cap. Recall is still about half the baseline's (0.201 against 0.388) because the agent's briefs are shorter. On average a case took 112 seconds, 6.6 tool calls and 14.7 model calls. The first full run (`580635598fec`, before invented tokens were counted and model failures were treated as caps) scored 0.917 on the claim checks with one run error. On the 6-case judged subset (P2-Q1, P2-Q2, P1-Q5, P3-Q3, P4-Q1, P2-Q4) the two systems tie on the report-only judge (0.618 against 0.607); the low-code build passed every gated check there, with lower recall (0.399 against 0.518).

The controls behave as they should: the golden answers pass everything, and a model with no data states almost none of the golden numbers and invents others. The judge separates them too: 1.0 on each golden answer, 0.20 to 0.37 on the no-data answers (P1-Q2, P2-Q1, CA-Q1). That is one sign the judge works, not the calibration open item 2 asks for.

## Known limits

- `numbers_match_golden` is a proxy for EV-1.1 that only suits systems without evidence. Systems with evidence are scored on `claims_reconcile` instead. An answer with no numbers passes it trivially; `golden_number_recall` catches that.
- The baselines are tuned on the dev cases (core-006 allows this; held-out cases will not be). Two analytic bugs the cases exposed: a baseline window that already contained the gap it was meant to detect, and a competitor share that rose mechanically when BXA volume fell.
- The stories' attribution figures (difference-in-differences gaps) are illustrations, so a system with its own valid method may cite different numbers there.
- Item-level checks (driver named, label, abstention, concentration, promotion verdict) need the structured answer that real systems will return (`harness/envelope.py`).
- The judge is slow on a laptop: about 40 seconds per case with `gemma3:4b`, so a full 42-case judged run takes about half an hour. Run it on demand.
- Judged runs answer every case first and then judge that rerun's traces (`_judge_rerun` in `harness/run.py`). MLflow 3.17 would otherwise judge one case while it answers the next, and on a 6 GB GPU the judge and a local agent model then swap every few requests (about 6 seconds per load) while the agent's wall-clock cap absorbs the wait. Now a judged rerun loads each model once. The judged low-code subset run `f1b62f863bf9` predates this, so its timings are pessimistic.
- Runs of an agent on local Ollama tag each rerun with `ollama.size_mb`, `ollama.vram_share` and `ollama.context`. Server settings such as the KV cache type are invisible to clients, so a run records their effect. Runs up to `0cd14c5f4266` used Ollama's f16 KV cache, with 36 of 37 qwen3 layers on the GPU (`vram_share` about 0.90). An 8-bit cache (`OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_FLASH_ATTENTION=1`) fits all 37 layers (3,390 MB, `vram_share` 1.0) and wrote 10% faster on 2 cases (55.9 against 50.6 tokens per second). One of the two briefs came out much shorter, and the setting changes the judge's cache too, so compare quality on a full run before treating 8-bit runs as comparable to f16 ones.
- The wall-clock cap (`wall_seconds`) stops the team, not the case: the brief written from the reports and the revision run after it, so one case took 663 seconds against a 420-second cap.
- 28 cases have no facts yet; six questions still need a period. See `golden/CHANGELOG.md`.
- Held-out cases and the answer key are not here by design; `harness/store.py` will read them from outside the repository.

# Quickstart: prove brief-002 Phase A works

Prerequisites: `uv sync`; the release loaded (`uv run python src/pharmagentics/data/load_duckdb.py`); for the browser steps, `docker compose up --build` (deploy/README.md).

## 1. The baseline did not move (B-VII)

```powershell
uv run python -m eval run --system briefing_scripted --lane briefing
uv run python -m eval gate <new-run-id> c58f99fc6e09
```

Expected: the gate passes, and every gated check equals the baseline run's.

## 2. Code tests

```powershell
uv run pytest tests/test_triage.py tests/test_rbac.py -q
```

They cover: the 2026-06-08 plan (Pacific, then Metacora; quiet territories listed); default decision equals `answer()` on the anchor weeks; dropping and reordering stories; New England withheld on 2026-05-04 and refused if added; no digit outside a claim on any card; triage is analyst-only; the leadership view carries no plan, record or flow.

## 3. In the browser (US7, US8)

1. Sign in as `uat-briefing-analyst`. Choose Mid-Atlantic, week of 2026-07-13, and generate.
2. The triage review shows the candidate cards (Pacific, Mid-Atlantic, Metacora) with Decision, Population, Granularity and Time, and the territories code dropped.
3. Approve unchanged. The brief matches the scripted baseline's for that week. "How this brief was made" lists seven stages; stage 4 shows the triage rules, your plan review, and "fixed order of checks, manager off".
4. Go back, drop Mid-Atlantic, approve. The brief says Mid-Atlantic was left out by the analyst; the triage record shows that call as human.
5. Approve the brief, sign in as `uat-briefing-director`: the executive summary has no stage list and no triage record.

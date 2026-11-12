# PharmAgentics Briefing → Chat integration (development MVP)

**Status:** proposed new code package for the `mwc2150/PharmAgentics` repository, based on `main` as of 2026-11-06. The files are not already merged. This is an API seam plus a runnable **standalone browser demo**; it does **not** contain the unpublished Figma Make project or implement sign-off/history.

## What this package implements

A browser sends `POST /api/briefing/query` with a BXA brand, Monday reporting week, territory, and a weekly-briefing question. The backend calls the repository's existing `agents/brand-briefing/briefing_baseline/pipeline.py::answer` function, which in turn uses the shared governed SQL/Python tools and DuckDB reporting views. The service returns the actual answer, claims, evidence records, data-version hash, and an explicit draft status. The demo UI displays evidence in expandable panels. This is the deterministic **scripted** baseline, not the Magentic-One low-code agent or Gemini Gem.

## Files and exact GitHub upload paths

Upload the extracted ZIP contents **under the repository root**, retaining the full paths:

| Local path (identical in GitHub) | Purpose |
|---|---|
| `src/pharmagentics/api/__init__.py` | New API package |
| `src/pharmagentics/api/app.py` | FastAPI routes, CORS and error handling |
| `src/pharmagentics/api/schemas.py` | Validated API request/response contracts |
| `src/pharmagentics/api/service.py` | Adapter to existing Briefing baseline, evidence checks |
| `frontend/briefing-demo/index.html` | Standalone browser demo page |
| `frontend/briefing-demo/styles.css` | Browser demo styling |
| `frontend/briefing-demo/app.js` | API invocation, claim/evidence display |
| `frontend/figma-make/briefingApi.ts` | Typed `fetch()` adapter for exported Figma Make source |
| `tests/test_briefing_api.py` | API adapter and validation tests, mocked engine |
| `tests/test_briefing_smoke.py` | Real API-to-DuckDB integration smoke test |
| `docs/BRIEFING_UI_INTEGRATION.md` | This implementation and test guide |
| `.github/workflows/briefing-ui-integration.yml` | Optional CI job for new API tests |

No existing repository files are overwritten. This package intentionally does not modify the shared `pyproject.toml`, `uv.lock`, the existing agent, the evaluator, or the source data. **Do not upload the enclosing ZIP folder as a directory**, or your Python imports will not resolve.

## Run locally (macOS/Linux/Windows terminals)

Prerequisites: Python 3.11+, uv, clone of the repository, and the copied files above.

```bash
# In the repository root
uv sync --locked
uv run python src/pharmagentics/data/load_duckdb.py
uv run python src/pharmagentics/data/check_duckdb.py

# API contract + real DuckDB integration tests (the --with options supply API-only dependencies without changing uv.lock)
uv run --with fastapi --with uvicorn --with httpx pytest tests/test_briefing_api.py tests/test_briefing_smoke.py -q

# Run the API in terminal A
uv run --with fastapi --with uvicorn uvicorn pharmagentics.api.app:app --app-dir src --host 127.0.0.1 --port 8000 --reload

# Run the standalone browser UI in terminal B
python -m http.server 5500 --bind 127.0.0.1 --directory frontend/briefing-demo
```

Open `http://127.0.0.1:5500` and select **Cardiovela (BXA)**, **Pacific**, **2026-06-08**. Verify that the chat result appears, the data version is shown, and at least one evidence panel opens.

- Backend interactive API docs: `http://127.0.0.1:8000/docs`
- Readiness check: `GET http://127.0.0.1:8000/api/health`
- Release metadata: `GET http://127.0.0.1:8000/api/briefing/context`
- Data availability ends at `2026-10-05` in the current release: do not use the present date as if there were November data.

### Direct API smoke test

```bash
curl -X POST http://127.0.0.1:8000/api/briefing/query \
  -H 'Content-Type: application/json' \
  -d '{"intent":"weekly_brief","brand_id":"BXA","territory_id":"PACIFIC","week_start":"2026-06-08","question":"What changed this week?"}'
```

The response includes `answer`, `claims`, `evidence`, `data_version`, `abstained`, `engine: scripted` and `review_status: not_submitted`. The code does not manufacture KPI numbers: it calls the existing baseline.

## Figma Make integration — next step after the API works

Your existing Figma Make screens are **not** in this repository and therefore cannot be automatically replaced by these files. Export/copy your existing Make frontend source into an appropriate frontend folder or import the helper `frontend/figma-make/briefingApi.ts` into your current project.

Example from your current React/TypeScript submit handler (adapt to your actual component names):

```ts
import { requestBriefing } from './briefingApi';

const response = await requestBriefing(API_BASE_URL, {
  intent: 'weekly_brief',
  brand_id: 'BXA',
  territory_id: 'PACIFIC',
  week_start: '2026-06-08',
  question: userQuestion,
});

// Use your existing chat message state/rendering:
// addAssistantMessage(response.answer)
// showEvidence(response.claims, response.evidence)
// showReviewBadge('Draft — Requires Analyst Review')
```

Keep `API_BASE_URL` in frontend configuration; never hardcode a publicly accessible tunnel or a secret in Git. From a hosted **HTTPS** Make preview, `localhost` on your own laptop usually will not be reachable. Use a **restricted, HTTPS development backend** or a temporary authenticated/restricted tunnel; the API currently provides no user authentication. Explicitly set `PHARMAGENTICS_ALLOWED_ORIGINS` to your exact browser preview origin (comma-separated if needed). **CORS restrictions are not access control.** Do not use this unauthenticated API with private data or expose it openly on the public internet.

## Important limitations

1. The existing scripted baseline has fixed output structure, not open-ended chat or LLM-powered dialogue. Only `weekly_brief` is currently supported. Other natural-language intents should show "not supported" rather than being interpreted as arbitrary SQL.
2. Figma's Review Queue/History screens remain prototypes. The API returns `draft_requires_review` and `not_submitted`; it does not store/approve briefing records.
3. The UI does not use A2UI yet. It renders validated JSON through ordinary components, with a path to A2UI later.
4. If data quality gates withhold a cut, do not infer its missing values are zero; the existing baseline handles the gated reporting layer.
5. The existing low-code Magentic-One agent has open quality regressions. Switching engines should happen only after this deterministic integration is stable and the evaluation gate is addressed.
6. The requested `week_start` must be a Monday within the loaded synthetic release. Brand is intentionally limited to BXA, the fictional demonstration brand.
7. This package includes mocked API tests; run the **repository's existing integration/evaluation tests** as well, and record an actual browser-to-DuckDB demo before claiming end-to-end readiness.

## Longer-term dependency management

This implementation uses `uv run --with ...` for API-only development dependencies so its files can be uploaded without overwriting the current shared `uv.lock`. When the team approves this API as a permanent runtime component, run `uv add fastapi uvicorn` and `uv add --group dev httpx`, then commit the resulting `pyproject.toml` and `uv.lock` together. Coordinate dependency changes with Michael and Alvin.

## Pull request acceptance criteria

- [ ] New files are at the exact paths listed above.
- [ ] `uv sync --locked` and repository data loader complete.
- [ ] New API tests pass in the local environment and GitHub Actions.
- [ ] Actual request `POST /api/briefing/query` returns traced claims/evidence from DuckDB.
- [ ] Standalone UI displays a real response and expandable evidence.
- [ ] One existing Figma Make chat action is wired to the API (requires your real Make project source).
- [ ] Invalid date/territory/brand returns a clear error.
- [ ] The UI never claims its draft is approved or saved.

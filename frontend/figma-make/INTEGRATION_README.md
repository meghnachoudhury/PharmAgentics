# PharmAgentics — backend-only Figma Make integration

## The two downloadable folders

- `repository_upload/`: **new or modified repository files** with exact destination paths preserved. Add these into a feature branch of `mwc2150/PharmAgentics`. `frontend/figma-make/` is a copy of the pared-down Figma project source. Python files under `src/pharmagentics/api/` are the required new HTTP bridge.
- `figma_make_source/`: import these files into your existing Figma Make project (or open locally as a Vite application). These replace the mock-heavy frontend export while retaining the original visual theme. **Back up your current Figma Make project first.**

### Why we restricted scope

The actual repository has a scripted Briefing baseline, DuckDB, governed SQL, and evidence, but no existing HTTP Briefing API and no persistent review or history service. This package adds the minimum HTTP bridge, then makes *only* the supported weekly briefing and evidence readout available in the UI. It never falls back to mock fixtures.

### Run backend

```sh
uv sync --locked
uv run python src/pharmagentics/data/load_duckdb.py
uv run python src/pharmagentics/data/check_duckdb.py
uv run --with fastapi --with uvicorn uvicorn pharmagentics.api.app:app --app-dir src --host 127.0.0.1 --port 8000 --reload
```

### Run frontend locally

Copy `.env.example` to `.env`, set `VITE_PHARMAGENTICS_API_BASE_URL`, then:

```sh
npm install
npm run dev
```

The original Figma Make `vite.config.ts` defaults to port 8443. Preview the URL printed by Vite.

### Run tests

```sh
uv run --with fastapi --with uvicorn --with httpx pytest tests/test_briefing_api.py tests/test_briefing_smoke.py -q
uv run pytest -q
```

### Hosted Figma Make

A browser hosted at `https://*.figma.site` cannot call a local-only `127.0.0.1` backend. Deploy a restricted HTTPS development service, configure its exact origin in `PHARMAGENTICS_ALLOWED_ORIGINS`, set Figma Make's environment variable to that base URL, and protect the service from public traffic. CORS alone does not secure it.

### Limitations and roadmap

See `docs/FUTURE_ENHANCEMENTS.md`. No offline mock or demo fixture is enabled in this package. The backend method is **fixed scripted**, not Gemini Skills, Gemini Gems, or Magentic-One.

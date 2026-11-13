# PharmAgentics UAT image (core-007): Briefing API + React UI on one origin, scripted engine only.
# No language model, no eval/ package, no ground truth. Build: docker build -t pharmagentics .
# Run: docker run --rm -p 8080:8080 pharmagentics  ->  http://localhost:8080

# ---- 1. Frontend: Vite build of Meghna's UI ----
FROM node:22-slim AS ui
WORKDIR /ui
RUN corepack enable
COPY frontend/figma-make/package.json frontend/figma-make/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/figma-make/ ./
# "." makes the UI call ./api/... on the origin that served it (no CORS, no host baked in).
ENV VITE_PHARMAGENTICS_API_BASE_URL=.
# Type-check first (vite build does not), then build.
RUN pnpm exec tsc --noEmit -p tsconfig.app.json \
 && pnpm exec vite build --config vite.config.standalone.ts

# ---- 2. Runtime: Python 3.12, base deps + api group only ----
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --locked --no-default-groups --group api --no-install-project
COPY src/ src/
COPY sql/ sql/
COPY data/agent_visible/ data/agent_visible/
COPY agents/brand-briefing/briefing_baseline/ agents/brand-briefing/briefing_baseline/
COPY agents/forecast-explanation/feagent/ agents/forecast-explanation/feagent/
RUN uv sync --locked --no-default-groups --group api \
 && uv run --no-sync python src/pharmagentics/data/load_duckdb.py \
 && uv run --no-sync python src/pharmagentics/data/check_duckdb.py
COPY --from=ui /ui/dist /app/ui
ARG PHARMAGENTICS_VERSION=dev
# /state holds approvals and UAT events: a volume locally, a Cloud Storage bucket mount on Cloud Run.
ENV PHARMAGENTICS_STATIC_DIR=/app/ui PHARMAGENTICS_STATE_DIR=/state PHARMAGENTICS_VERSION=${PHARMAGENTICS_VERSION} \
    PORT=8080 PATH="/app/.venv/bin:$PATH"
RUN useradd --uid 10001 app && mkdir /state && chown -R app /app /state
USER app
EXPOSE 8080
# --proxy-headers: behind Cloud Run's HTTPS front end, sign-in callback URLs must use https.
CMD ["sh", "-c", "exec uvicorn pharmagentics.api.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]

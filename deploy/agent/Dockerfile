# Cloud agent host (core-007 FR-031): Ollama on CPU with the qwen3 model baked in, plus the same worker the
# teammates run. It is a Cloud Run *job* the app starts when work waits and nobody is hosting; it drains the
# queue and exits when idle. No ground truth and no eval/ in it. Build from the repository root:
#   docker build -f deploy/agent/Dockerfile -t pharmagentics-agent .
FROM python:3.12-slim

ARG MODEL=qwen3:4b-instruct-2507-q4_K_M
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates zstd procps \
 && rm -rf /var/lib/apt/lists/*

# ---- Ollama, CPU only. The installer brings GPU libraries this host never uses; they are removed in the same
# layer, so they are not stored. These layers come first so a code change never re-uploads them.
RUN curl -fsSL https://ollama.com/install.sh | sh \
 ; find / -xdev -type d \( -name 'cuda_*' -o -name 'rocm' -o -name 'mlx*' \) -path '*ollama*' -prune -exec rm -rf {} + 2>/dev/null \
 ; ollama --version

# ---- The model, pulled once at build time (about 2.5 GB), so a cold start reads it from the image.
ENV OLLAMA_MODELS=/models OLLAMA_HOST=127.0.0.1:11434
RUN mkdir -p /models \
 && (ollama serve >/tmp/ollama-build.log 2>&1 &) \
 && for i in $(seq 1 90); do curl -sf http://127.0.0.1:11434/api/version >/dev/null && break; sleep 1; done \
 && ollama pull "$MODEL" \
 && test -d /models/manifests \
 ; pkill ollama || true
# (No chmod or chown over /models or /app: each would copy the whole tree into a new layer. The files are
# already world-readable, and the worker only reads them.)

# ---- Python: the agent group only (no web server, no eval).
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --locked --no-default-groups --group agent --no-install-project
COPY src/ src/
COPY sql/ sql/
COPY data/agent_visible/ data/agent_visible/
COPY agents/brand-briefing/ agents/brand-briefing/
# The same release as the app: the app refuses an agent brief on another data version.
RUN uv sync --locked --no-default-groups --group agent \
 && uv run --no-sync python src/pharmagentics/data/load_duckdb.py \
 && uv run --no-sync python src/pharmagentics/data/check_duckdb.py
COPY deploy/agent/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && useradd --uid 10001 --create-home app
USER app

# CPU settings: one model, kept loaded, one request at a time; the same cache settings as the evals.
# The wall-clock caps in agents/brand-briefing/briefing_agent/agent.yaml are tuned for a GPU, so scale them.
ENV HOME=/home/app PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app/src:/app/agents/brand-briefing PYTHONUNBUFFERED=1 \
    OLLAMA_KEEP_ALIVE=-1 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 \
    OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 \
    PHARMAGENTICS_OLLAMA_TIMEOUT=1500 PHARMAGENTICS_AGENT_WALL_SCALE=6 \
    PHARMAGENTICS_AGENT_MODEL=ollama:${MODEL}
ENTRYPOINT ["/entrypoint.sh"]

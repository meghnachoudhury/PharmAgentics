#!/bin/sh
# Cloud agent host: start Ollama, load the model while the worker starts polling, drain the queue, exit when idle.
set -e
ollama serve >/tmp/ollama.log 2>&1 &
i=0
until curl -sf http://127.0.0.1:11434/api/version >/dev/null; do
  i=$((i + 1))
  if [ "$i" -gt 90 ]; then echo "Ollama did not start:"; tail -n 20 /tmp/ollama.log; exit 1; fi
  sleep 1
done
echo "Ollama ready; loading ${PHARMAGENTICS_AGENT_MODEL#ollama:}"
# Load the model now, with the same context window the agent asks for, so the first job does not wait for it.
curl -s http://127.0.0.1:11434/api/generate \
  -d "{\"model\":\"${PHARMAGENTICS_AGENT_MODEL#ollama:}\",\"prompt\":\"\",\"keep_alive\":-1,\"options\":{\"num_ctx\":12288}}" \
  >/dev/null 2>&1 &
exec python agents/brand-briefing/run_worker.py --app "$PHARMAGENTICS_APP_URL" --name cloud \
  --idle-exit "${IDLE_EXIT_SECONDS:-150}" --interval 10

"""Chat clients for the agents, chosen by one model string. Shared by both lanes.

    ollama:<model>   local Ollama (default; no API credits, nothing leaves the machine)
    gemini:<model>   Gemini Developer API; `gemini:` alone uses GEMINI_MODEL

The string comes from the caller or PHARMAGENTICS_AGENT_MODEL. GEMINI_API_KEY and GEMINI_MODEL are read
from the environment or the repository's git-ignored .env. The key is never logged. Only synthetic data
and metric definitions may go to Gemini (System Architecture §7).
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AGENT_MODEL = "ollama:qwen3:4b-instruct-2507-q4_K_M"
# Ollama's own default context (4K) truncates the Magentic manager's prompts without an error. 12K keeps
# the 4B model 90% on a 6 GB GPU; at 16K it spilled a fifth onto the CPU and the runner died mid-run.
OLLAMA_NUM_CTX = int(os.environ.get("PHARMAGENTICS_OLLAMA_NUM_CTX", "12288"))
# A dead runner must fail one call, not hang the run.
OLLAMA_TIMEOUT = float(os.environ.get("PHARMAGENTICS_OLLAMA_TIMEOUT", "300"))


def load_env(path: Path = REPO_ROOT / ".env") -> None:
    """Set variables from a KEY=VALUE .env file without overriding ones already set."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def model_spec(spec: str | None = None) -> str:
    load_env()
    spec = spec or os.environ.get("PHARMAGENTICS_AGENT_MODEL") or DEFAULT_AGENT_MODEL
    provider, _, model = spec.partition(":")
    if provider == "gemini" and not model:
        model = os.environ.get("GEMINI_MODEL", "")
        if not model:
            raise ValueError("gemini: needs a model, in the string or in GEMINI_MODEL")
    if provider not in ("ollama", "gemini") or not model:
        raise ValueError(f"model string must be ollama:<model> or gemini:<model>, got {spec!r}")
    return f"{provider}:{model}"


def chat_client(spec: str | None = None):
    """An Agent Framework chat client for the model string."""
    provider, _, model = model_spec(spec).partition(":")
    if provider == "ollama":
        from agent_framework.ollama import OllamaChatClient
        from ollama import AsyncClient

        host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        host = host if host.startswith("http") else "http://" + host
        return OllamaChatClient(model=model, client=AsyncClient(host=host, timeout=OLLAMA_TIMEOUT))
    from agent_framework.gemini import GeminiChatClient

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY is not set (environment or .env)")
    return GeminiChatClient(api_key=key, model=model)


def chat_options(spec: str | None = None, temperature: float = 0.0) -> dict:
    """Default options per provider: deterministic sampling, and a context window Ollama will not truncate."""
    provider = model_spec(spec).partition(":")[0]
    opts: dict = {"temperature": temperature}
    if provider == "ollama":
        opts["num_ctx"] = OLLAMA_NUM_CTX
    return opts

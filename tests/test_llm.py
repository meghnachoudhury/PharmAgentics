"""Model clients: the Ollama runtime record a run logs, without a live server."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

ollama = pytest.importorskip("ollama")

from pharmagentics.llm import ollama_runtime  # noqa: E402

QWEN = "ollama:qwen3:4b-instruct-2507-q4_K_M"


def _server(monkeypatch, models=None, fail=False):
    class FakeClient:
        def __init__(self, host, timeout):
            pass

        def ps(self):
            if fail:
                raise ConnectionError("no server")
            return SimpleNamespace(models=models or [])

    monkeypatch.setattr(ollama, "Client", FakeClient)


def test_runtime_reports_size_vram_share_and_context(monkeypatch):
    m = SimpleNamespace(model="qwen3:4b-instruct-2507-q4_K_M", name="qwen3:4b-instruct-2507-q4_K_M",
                        size=4543 * 2**20, size_vram=int(4543 * 2**20 * 0.902), context_length=12288)
    other = SimpleNamespace(model="gemma3:4b", name="gemma3:4b", size=2900 * 2**20, size_vram=2900 * 2**20,
                            context_length=4096)
    _server(monkeypatch, [other, m])
    assert ollama_runtime(QWEN) == {"ollama.size_mb": 4543, "ollama.vram_share": 0.902, "ollama.context": 12288}


def test_runtime_is_empty_when_not_loaded_unreachable_or_not_ollama(monkeypatch):
    _server(monkeypatch, [])
    assert ollama_runtime(QWEN) == {}
    _server(monkeypatch, fail=True)
    assert ollama_runtime(QWEN) == {}
    assert ollama_runtime("gemini:gemini-flash-latest") == {}

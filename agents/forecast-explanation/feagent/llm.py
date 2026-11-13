"""LLM client seam. v1 talks to Ollama; swap later without touching tools."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Protocol

from feagent.config import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT_SEC


class LLMClient(Protocol):
    name: str
    model: str

    def available(self) -> tuple[bool, str]:
        ...

    def complete(self, messages: list[dict[str, str]]) -> str:
        ...


class OllamaClient:
    name = "ollama"

    def __init__(
        self,
        host: str = OLLAMA_HOST,
        model: str = OLLAMA_MODEL,
        timeout: float = OLLAMA_TIMEOUT_SEC,
    ) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout

    def list_models(self) -> list[str]:
        tags = self._request("/api/tags", None, timeout=3)
        names: list[str] = []
        for item in tags.get("models", []):
            name = item.get("name") or item.get("model") or ""
            if name:
                names.append(name)
        return names

    def available(self) -> tuple[bool, str]:
        try:
            models = self.list_models()
        except Exception as exc:
            return False, f"Ollama not reachable at {self.host}: {exc}"
        if self._model_is_installed(models):
            return True, f"{self.model} is available"
        if models:
            return (
                False,
                f"Ollama is up, but {self.model} is not pulled. Installed: {', '.join(models)}. "
                f"Set the model name to one of these, or run: ollama pull {self.model}",
            )
        return False, f"Ollama is up, but no models are installed. Run: ollama pull {self.model}"

    def _model_is_installed(self, models: list[str]) -> bool:
        wanted = self.model.strip()
        short = wanted.split(":")[0]
        return any(m == wanted or m.startswith(wanted) or m.startswith(short + ":") for m in models)

    def complete(self, messages: list[dict[str, str]]) -> str:
        """Returns the investigator's JSON action, whether the model answered in text or by tool call."""
        payload = {
            "model": self.model,
            "messages": to_native_messages(messages),
            "stream": False,
            "options": {"temperature": 0},
            "tools": native_tools(),
        }
        try:
            data = self._request("/api/chat", payload)
        except urllib.error.HTTPError as exc:
            if exc.code != 400:
                raise
            payload.pop("tools")
            payload["messages"] = messages
            data = self._request("/api/chat", payload)
        message = data.get("message", {})
        calls = message.get("tool_calls") or []
        if calls:
            return action_from_tool_call(calls[0].get("function", {}))
        return message.get("content", "")

    def _request(
        self,
        path: str,
        payload: dict[str, Any] | None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.host + path,
            data=body,
            method="GET" if payload is None else "POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))


SUBMIT_REPORT = "submit_report"

_JSON_TYPES = {"int": "integer", "float": "number", "str": "string", "object": "object"}

_REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "drivers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "driver": {"type": "string"},
                    "impact_trx": {"type": "number"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low", "inconclusive"]},
                    "method": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                },
                "required": ["driver", "impact_trx", "evidence_ids"],
            },
        },
        "what_to_check": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "why": {"type": "string"},
                    "owner": {"type": "string"},
                },
                "required": ["question", "why", "owner"],
            },
        },
        "caveats": {"type": "array", "items": {"type": "string"}},
        "abstained": {"type": "boolean"},
    },
    "required": ["headline", "drivers", "what_to_check", "caveats", "abstained"],
}


def native_tools() -> list[dict[str, Any]]:
    """The investigator's tools plus submit_report, in Ollama's native tool-calling format."""
    from feagent.tools import TOOL_SPECS

    tools = []
    for name, spec in TOOL_SPECS.items():
        properties, required = {}, []
        for param, description in spec["parameters"].items():
            if param in {"case_id", "window_weeks"}:
                continue
            properties[param] = {
                "type": _JSON_TYPES.get(description.split(",")[0].split()[0], "string"),
                "description": description,
            }
            if "optional" not in description:
                required.append(param)
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": spec["description"],
                    "parameters": {"type": "object", "properties": properties, "required": required},
                },
            }
        )
    tools.append(
        {
            "type": "function",
            "function": {
                "name": SUBMIT_REPORT,
                "description": "Finish the investigation by submitting the final report.",
                "parameters": _REPORT_SCHEMA,
            },
        }
    )
    return tools


def action_from_tool_call(function: dict[str, Any]) -> str:
    name, arguments = function.get("name"), function.get("arguments") or {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            arguments = {}
    if name == SUBMIT_REPORT:
        return json.dumps({"action": "final", "report": arguments})
    return json.dumps({"action": "tool", "name": name, "arguments": arguments})


def to_native_messages(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Rewrite the investigator's JSON transcript as a native tool-calling conversation."""
    native: list[dict[str, Any]] = []
    last_call: str | None = None
    for message in messages:
        body = _json_object(message["content"])
        role = message["role"]
        if role == "assistant" and body.get("action") in {"tool", "final"}:
            final = body["action"] == "final"
            last_call = SUBMIT_REPORT if final else body.get("name")
            native.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": last_call,
                                "arguments": (body.get("report") if final else body.get("arguments")) or {},
                            }
                        }
                    ],
                }
            )
            continue
        if role == "user" and last_call and ("tool_result" in body or "error" in body):
            result = body.get("tool_result", body)
            native.append({"role": "tool", "tool_name": last_call, "content": json.dumps(result)})
            last_call = None
            continue
        last_call = None
        native.append(message)
    return native


def _json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def parse_json_message(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in model response: {text[:400]}")
    return json.loads(text[start : end + 1])

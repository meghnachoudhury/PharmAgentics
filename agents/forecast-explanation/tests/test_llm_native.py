import io
import json
import urllib.error

import pytest

from feagent.llm import (
    SUBMIT_REPORT,
    OllamaClient,
    action_from_tool_call,
    native_tools,
    to_native_messages,
)
from feagent.tools import TOOL_SPECS


def by_name():
    return {t["function"]["name"]: t["function"] for t in native_tools()}


def test_every_investigator_tool_is_offered_plus_submit_report():
    assert set(by_name()) == set(TOOL_SPECS) | {SUBMIT_REPORT}


def test_tool_schemas_have_types_and_required_arguments():
    tools = by_name()
    validate = tools["validate_and_quantify"]["parameters"]
    assert validate["properties"]["week"]["type"] == "integer"
    assert validate["properties"]["territory_id"]["type"] == "string"
    assert validate["required"] == ["week"]
    assert "case_id" not in validate["properties"]
    assert "window_weeks" not in validate["properties"]
    compare = tools["compare_exposed_control"]["parameters"]
    assert compare["required"] == ["event_id", "week"]
    reconcile = tools["reconcile_attribution"]["parameters"]
    assert reconcile["properties"]["driver_impacts"]["type"] == "object"


def test_submit_report_schema_requires_evidence_for_every_driver():
    schema = by_name()[SUBMIT_REPORT]["parameters"]
    driver = schema["properties"]["drivers"]["items"]
    assert {"driver", "impact_trx", "evidence_ids"} <= set(driver["required"])
    assert "headline" in schema["required"]


def test_tool_call_becomes_a_tool_action():
    action = json.loads(action_from_tool_call({"name": "get_region_deltas", "arguments": {"week": 18}}))
    assert action == {"action": "tool", "name": "get_region_deltas", "arguments": {"week": 18}}


def test_submit_report_becomes_the_final_action():
    action = json.loads(action_from_tool_call({"name": SUBMIT_REPORT, "arguments": {"headline": "h"}}))
    assert action == {"action": "final", "report": {"headline": "h"}}


def test_arguments_sent_as_a_json_string_are_decoded():
    action = json.loads(action_from_tool_call({"name": "get_region_deltas", "arguments": '{"week": 18}'}))
    assert action["arguments"] == {"week": 18}


def test_arguments_that_are_not_json_become_empty_not_a_crash():
    action = json.loads(action_from_tool_call({"name": "get_region_deltas", "arguments": "week=18"}))
    assert action["arguments"] == {}


def test_transcript_is_rewritten_as_a_native_tool_conversation():
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": json.dumps({"task": "Investigate"})},
        {"role": "assistant", "content": json.dumps({"action": "tool", "name": "validate_and_quantify", "arguments": {"week": 18}})},
        {"role": "user", "content": json.dumps({"tool_result": {"tool_id": "t_1", "name": "validate_and_quantify", "payload": {"ok": True}}})},
        {"role": "assistant", "content": json.dumps({"action": "final", "report": {"headline": "h"}})},
    ]
    native = to_native_messages(messages)
    assert native[0] == messages[0] and native[1] == messages[1]
    assert native[2]["tool_calls"][0]["function"] == {"name": "validate_and_quantify", "arguments": {"week": 18}}
    assert native[3]["role"] == "tool" and native[3]["tool_name"] == "validate_and_quantify"
    assert json.loads(native[3]["content"])["tool_id"] == "t_1"
    assert native[4]["tool_calls"][0]["function"]["name"] == SUBMIT_REPORT


def test_feedback_after_a_tool_call_is_a_tool_message_and_after_plain_text_a_user_message():
    after_call = to_native_messages(
        [
            {"role": "assistant", "content": json.dumps({"action": "final", "report": {}})},
            {"role": "user", "content": json.dumps({"error": "final.report is malformed"})},
        ]
    )
    assert after_call[1]["role"] == "tool" and after_call[1]["tool_name"] == SUBMIT_REPORT
    after_text = to_native_messages(
        [
            {"role": "assistant", "content": "I think it was the payer."},
            {"role": "user", "content": json.dumps({"error": "Reply was not valid JSON"})},
        ]
    )
    assert after_text[1]["role"] == "user"


class StubbedOllama(OllamaClient):
    def __init__(self, responses):
        super().__init__(model="stubbed")
        self.responses = list(responses)
        self.payloads = []

    def _request(self, path, payload, timeout=None):
        self.payloads.append(dict(payload))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_complete_returns_the_action_for_a_native_tool_call():
    client = StubbedOllama(
        [{"message": {"content": "", "tool_calls": [{"function": {"name": "validate_and_quantify", "arguments": {"week": 18}}}]}}]
    )
    action = json.loads(client.complete([{"role": "user", "content": "go"}]))
    assert action["name"] == "validate_and_quantify"
    assert "tools" in client.payloads[0]


def test_complete_returns_plain_content_when_the_model_answers_in_text():
    client = StubbedOllama([{"message": {"content": '{"action":"final","report":{}}'}}])
    assert json.loads(client.complete([{"role": "user", "content": "go"}]))["action"] == "final"


def test_a_model_without_tool_support_is_retried_in_the_json_protocol():
    refused = urllib.error.HTTPError("http://x", 400, "does not support tools", {}, io.BytesIO(b""))
    client = StubbedOllama([refused, {"message": {"content": '{"action":"final","report":{}}'}}])
    messages = [{"role": "user", "content": "go"}]
    client.complete(messages)
    assert "tools" in client.payloads[0]
    assert "tools" not in client.payloads[1]
    assert client.payloads[1]["messages"] == messages


def test_other_http_errors_are_not_swallowed():
    broken = urllib.error.HTTPError("http://x", 500, "server error", {}, io.BytesIO(b""))
    client = StubbedOllama([broken])
    with pytest.raises(urllib.error.HTTPError):
        client.complete([{"role": "user", "content": "go"}])

"""The report writer: the order of models, the fallback, and every check on the prose. No network."""
import io
import json
import urllib.error

import pytest

from feagent import writer
from feagent.pipeline import FORECAST_LANE_CASES, run_forecast_pipeline


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for name in ("FEAGENT_WRITER", "OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL", "OLLAMA_WRITER_MODEL"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="module")
def national():
    return run_forecast_pipeline(FORECAST_LANE_CASES[1]["request"], mode="stub")["report"]


@pytest.fixture(scope="module")
def mid_atlantic():
    return run_forecast_pipeline(FORECAST_LANE_CASES[2]["request"], mode="stub")["report"]


@pytest.fixture(scope="module")
def new_england():
    return run_forecast_pipeline(FORECAST_LANE_CASES[0]["request"], mode="stub")["report"]


def good_prose(report, **override):
    facts = writer.build_facts(report)
    owner = facts["what_to_check"][0]["owner"]
    prose = {
        "summary": f"BXA Cardiovela missed its forecast by {abs(facts['variance_trx']):,} TRx in the week ending {facts['week_ending']}.",
        "miss": f"Actual was {facts['actual_trx']:,} against a forecast of {facts['forecast_trx']:,}.",
        "residual": f"About {facts['residual_share_of_miss_pct']}% of the miss is not explained by any driver.",
        "confidence": "The estimates are associations against comparison regions, not proof of cause.",
        "next_checks": [{"check": "Confirm the event dates with the field team", "why": "The event date drives the estimate", "owner": owner}],
        "analyst_notes": "The event calendar is observable-only.",
    }
    prose.update(override)
    return json.dumps(prose)


def ok(report, **override):
    return lambda messages, cfg: good_prose(report, **override)


def fails(code):
    def call(messages, cfg):
        raise writer.WriterError(code)
    return call


def test_terra_writes_when_it_has_a_key_and_its_prose_passes(national, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    seen = []
    out = writer.write_report(national, terra=lambda m, c: seen.append("terra") or good_prose(national),
                              local=lambda m, c: seen.append("local") or good_prose(national))
    assert out["writer_status"] == "ok" and out["report_model"] == "gpt-6.1-terra"
    assert seen == ["terra"] and out["narrative"]["summary"]
    assert out["writer_attempts"] == [{"model": "gpt-6.1-terra", "outcome": "ok"}]


def test_no_key_goes_straight_to_the_local_qwen_model(national):
    out = writer.write_report(national, terra=writer.call_terra, local=ok(national))
    assert out["report_model"] == "qwen2.5:7b" and out["writer_status"] == "ok"
    assert [a["outcome"] for a in out["writer_attempts"]] == ["no_key", "ok"]


@pytest.mark.parametrize("code", ["http_500", "http_429", "timeout", "unreachable", "bad_response"])
def test_a_terra_failure_falls_back_to_qwen(national, monkeypatch, code):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    out = writer.write_report(national, terra=fails(code), local=ok(national))
    assert out["report_model"] == "qwen2.5:7b" and out["writer_status"] == "ok"
    assert out["writer_attempts"][0] == {"model": "gpt-6.1-terra", "outcome": code}


def test_both_models_failing_keeps_the_scripted_report(national, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    out = writer.write_report(national, terra=fails("http_500"), local=fails("unreachable"))
    assert out["narrative"] is None and out["report_model"] == "none" and out["writer_status"] == "fallback_stub"
    assert [a["outcome"] for a in out["writer_attempts"]] == ["http_500", "unreachable"]


def test_a_crash_inside_a_model_call_is_a_fallback_not_an_error(national):
    def boom(messages, cfg):
        raise RuntimeError("anything")
    out = writer.write_report(national, terra=boom, local=boom)
    assert out["writer_status"] == "fallback_stub"


def test_an_invented_number_is_rejected_and_the_next_model_is_tried(national, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    bad = ok(national, miss="Actual was 9,876 TRx against a forecast of 11,000.")
    out = writer.write_report(national, terra=bad, local=ok(national))
    assert out["report_model"] == "qwen2.5:7b"
    assert out["writer_attempts"][0] == {"model": "gpt-6.1-terra", "outcome": "rejected_invented_number"}


def test_numbers_the_report_holds_pass_in_any_formatting(national):
    facts = writer.build_facts(national)
    for text in (f"{abs(facts['variance_trx']):,} TRx", f"-{abs(facts['variance_trx'])}", f"−{abs(facts['variance_trx']):,}",
                 f"{abs(facts['drivers'][0]['impact_trx'])}", f"{round(abs(facts['drivers'][0]['impact_trx']))}",
                 f"about {facts['residual_share_of_miss_pct']}%", "2026-08-30", f"{facts['window_weeks']} week"):
        prose, problem = writer.check_prose(good_prose(national, miss=f"The figure was {text}."), facts)
        assert problem is None, (text, problem)


def test_a_number_the_report_does_not_hold_is_rejected_even_if_close_in_spirit(national):
    facts = writer.build_facts(national)
    for text in ("1,000 TRx", "about 1.0k", "250 TRx", "15%", "week 98"):
        _prose, problem = writer.check_prose(good_prose(national, miss=f"The figure was {text}."), facts)
        assert problem == "invented_number", text


@pytest.mark.parametrize("sentence", [
    "The team should lower the forecast for next quarter.",
    "We recommend a price cut in the region.",
    "Reallocate budget to the Southeast.",
    "Consider a discount for payers.",
    "Raise the forecast for the next cycle.",
])
def test_a_commercial_action_is_rejected(national, sentence):
    _prose, problem = writer.check_prose(good_prose(national, summary=sentence), writer.build_facts(national))
    assert problem == "commercial_action"


@pytest.mark.parametrize("sentence", [
    "Medium, as the baseline-change cross-check differs from the forecast-error estimate by more than 25% of the miss.",
    "Change in the forecast error was larger than in the comparison regions.",
    "The shift in actuals against the forecast is concentrated in one region.",
    "Forecast error moved against the comparison regions.",
])
def test_describing_the_data_is_not_a_commercial_action(mid_atlantic, sentence):
    prose = good_prose(mid_atlantic, confidence=sentence)
    assert writer.check_prose(prose, writer.build_facts(mid_atlantic))[1] is None, sentence


def test_reviewing_the_forecast_assumptions_is_allowed(national):
    prose = good_prose(national, next_checks=[{"check": "Review the forecast assumptions for the promotion", "why": "To see whether the assumption held", "owner": "Forecasting"}])
    assert writer.check_prose(prose, writer.build_facts(national))[1] is None


def test_a_driver_the_report_does_not_name_is_rejected(national):
    prose = good_prose(national, summary="A competitor launch was the main cause, with a supply shortage as well.")
    assert writer.check_prose(prose, writer.build_facts(national))[1] == "new_driver"


def test_an_owner_the_report_does_not_name_is_rejected(national):
    prose = good_prose(national, next_checks=[{"check": "Look at the data", "why": "To be sure", "owner": "Chief Executive"}])
    assert writer.check_prose(prose, writer.build_facts(national))[1] == "unknown_owner"


@pytest.mark.parametrize("raw,reason", [
    ("not json at all", "bad_json"), ("[1, 2]", "bad_json"), ("{}", "bad_shape"),
    (json.dumps({"summary": "x", "miss": "y", "residual": "z", "confidence": "c", "next_checks": []}), "bad_shape"),
    (json.dumps({"summary": "x" * 800, "miss": "y", "residual": "z", "confidence": "c", "next_checks": [{"check": "a", "why": "b", "owner": "Forecasting"}]}), "bad_shape"),
])
def test_text_that_is_not_the_expected_json_is_rejected(national, raw, reason):
    assert writer.check_prose(raw, writer.build_facts(national))[1] == reason


def test_prose_wrapped_in_a_code_fence_is_still_read(national):
    prose, problem = writer.check_prose("```json\n" + good_prose(national) + "\n```", writer.build_facts(national))
    assert problem is None and prose["summary"]


def test_a_paused_attribution_and_a_disabled_writer_call_no_model(new_england, national, monkeypatch):
    def never(messages, cfg):
        raise AssertionError("no model should be called")
    paused = writer.write_report(new_england, terra=never, local=never)
    assert paused["writer_status"] == "skipped" and paused["writer_attempts"][0]["outcome"] == "attribution_paused"
    monkeypatch.setenv("FEAGENT_WRITER", "off")
    off = writer.write_report(national, terra=never, local=never)
    assert off["writer_status"] == "skipped" and off["writer_attempts"][0]["outcome"] == "disabled"


def test_the_writer_is_given_no_evidence_ids_tool_output_or_internal_week_numbers(national):
    facts = writer.build_facts(national)
    text = json.dumps(facts)
    assert "evidence" not in text and "request_id" not in text and "week" not in facts  # the date week is given, the index is not
    for driver in national["drivers"]:
        for evidence_id in driver["evidence_ids"]:
            assert evidence_id not in text
    assert [d["name"] for d in facts["drivers"]] == [d["driver"] for d in national["drivers"]]


def test_the_scripted_report_is_never_changed_by_the_writer(national):
    before = json.dumps(national, sort_keys=True)
    writer.write_report(national, terra=fails("http_500"), local=ok(national))
    assert json.dumps(national, sort_keys=True) == before


def test_the_model_is_set_on_the_server_not_by_the_caller(monkeypatch):
    assert writer.settings()["terra_model"] == "gpt-6.1-terra" and writer.settings()["local_model"] == "qwen2.5:7b"
    monkeypatch.setenv("OPENAI_MODEL", "gpt-x")
    monkeypatch.setenv("OLLAMA_WRITER_MODEL", "qwen-new")
    assert writer.settings()["terra_model"] == "gpt-x" and writer.settings()["local_model"] == "qwen-new"
    assert writer.describe() == {"enabled": True, "primary": None, "fallback": "qwen-new"}
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    assert writer.describe()["primary"] == "gpt-x" and "sk-test-key" not in json.dumps(writer.describe())


# --- the two HTTP calls, with the network replaced ----------------------------------------------------------

class _Response:
    def __init__(self, body):
        self.body = body

    def read(self):
        return json.dumps(self.body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_terra_sends_the_key_only_in_the_authorization_header(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    seen = {}

    def fake(req, timeout=None):
        seen.update(url=req.full_url, auth=req.get_header("Authorization"), body=json.loads(req.data), timeout=timeout)
        return _Response({"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(writer.urllib.request, "urlopen", fake)
    assert writer.call_terra([{"role": "user", "content": "hi"}], writer.settings()) == "{}"
    assert seen["url"] == "https://api.openai.com/v1/chat/completions" and seen["auth"] == "Bearer sk-test-key"
    assert "sk-test-key" not in json.dumps(seen["body"]) and seen["body"]["model"] == "gpt-6.1-terra"
    assert "temperature" not in seen["body"] and seen["timeout"] == 25


def test_terra_without_a_key_never_touches_the_network(monkeypatch):
    monkeypatch.setattr(writer.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network used"))
    with pytest.raises(writer.WriterError) as caught:
        writer.call_terra([], writer.settings())
    assert caught.value.code == "no_key"


def test_terra_retries_once_without_json_mode_when_the_model_refuses_it(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    bodies = []

    def fake(req, timeout=None):
        body = json.loads(req.data)
        bodies.append("response_format" in body)
        if "response_format" in body:
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b"{}"))
        return _Response({"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(writer.urllib.request, "urlopen", fake)
    assert writer.call_terra([], writer.settings()) == "{}" and bodies == [True, False]


def test_an_error_from_the_server_never_repeats_the_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    def fake(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "bad key sk-test-key", {}, io.BytesIO(b'{"error":{"message":"sk-test-key"}}'))

    monkeypatch.setattr(writer.urllib.request, "urlopen", fake)
    with pytest.raises(writer.WriterError) as caught:
        writer.call_terra([], writer.settings())
    assert caught.value.code == "http_401" and "sk-test-key" not in str(caught.value)


def test_ollama_asks_for_json_and_a_timeout_is_a_code_not_a_crash(monkeypatch):
    seen = {}

    def fake(req, timeout=None):
        seen.update(url=req.full_url, body=json.loads(req.data))
        return _Response({"message": {"content": "{}"}})

    monkeypatch.setattr(writer.urllib.request, "urlopen", fake)
    assert writer.call_ollama([], writer.settings()) == "{}"
    assert seen["url"].endswith("/api/chat") and seen["body"]["format"] == "json" and seen["body"]["model"] == "qwen2.5:7b"

    def slow(req, timeout=None):
        raise TimeoutError()

    monkeypatch.setattr(writer.urllib.request, "urlopen", slow)
    with pytest.raises(writer.WriterError) as caught:
        writer.call_ollama([], writer.settings())
    assert caught.value.code == "timeout"


def test_the_miss_is_given_as_a_percent_not_a_fraction(national, mid_atlantic):
    assert writer.build_facts(national)["variance_pct_of_forecast"] == -20.2
    assert writer.build_facts(mid_atlantic)["variance_pct_of_forecast"] == -7.4


def test_small_figures_must_be_as_given_but_larger_ones_may_be_rounded(mid_atlantic):
    facts = writer.build_facts(mid_atlantic)
    accepted = ("7.4%", "-7%", "51 TRx", "730 TRx", "679 TRx")  # the headline's own -7%, and rounding of a larger figure
    for text in accepted:
        assert writer.check_prose(good_prose(mid_atlantic, miss=f"The figure was {text}."), facts)[1] is None, text
    for text in ("0.42%", "0.3%", "7.9%", "4 TRx", "12%"):
        assert writer.check_prose(good_prose(mid_atlantic, miss=f"The figure was {text}."), facts)[1] == "invented_number", text

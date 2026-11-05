"""The low-code team's defined exits and token checks, without a model (agents/brand-briefing/briefing_lowcode)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("agent_framework_orchestrations")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents" / "brand-briefing"))

from agent_framework.exceptions import ChatClientException  # noqa: E402

from briefing_lowcode.team import _invented, _model_failure  # noqa: E402


def _raised_from(outer: type[BaseException], inner: BaseException) -> BaseException:
    try:
        try:
            raise inner
        except BaseException as e:
            raise outer("wrapped") from e
    except BaseException as e:
        return e


def test_model_failure_direct_wrapped_and_grouped():
    timeout = ChatClientException("Ollama chat request failed : timed out")
    assert _model_failure(timeout)
    assert _model_failure(_raised_from(RuntimeError, timeout))  # __cause__
    assert _model_failure(ExceptionGroup("participants", [ValueError("x"), timeout]))  # grouped
    assert _model_failure(ExceptionGroup("outer", [ExceptionGroup("inner", [_raised_from(RuntimeError, timeout)])]))


def test_other_errors_are_run_errors():
    assert not _model_failure(ValueError("bad tool argument"))
    assert not _model_failure(_raised_from(RuntimeError, KeyError("c9")))
    assert not _model_failure(ExceptionGroup("g", [TypeError("x")]))


def test_model_failure_survives_a_cycle():
    a, b = RuntimeError("a"), RuntimeError("b")
    a.__context__, b.__context__ = b, a
    assert not _model_failure(a)


def test_invented_tokens():
    claims = [{"value": "7"}, {"value": "8"}, {"value": "3.6%"}]
    assert _invented("Down {c3} on {c1} of {c2} territories.", claims) == []
    assert _invented("Up {c8}, flat {c0}, and {c3}.", claims) == ["{c0}", "{c8}"]
    assert _invented("No tokens here.", []) == []
    assert _invented("{c1}", []) == ["{c1}"]

"""Retry + model-fallback policy for Claude calls (pdfdeck/agents/llm.py).

Fully offline: monkeypatches the `_bind` seam so no ChatAnthropic is built and
no network is touched. Verifies that a transient 529 overload on the primary
model falls back to the secondary model, that disabling the fallback re-raises,
and that a non-transient error is never swallowed by the fallback.
"""

import httpx
import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from pdfdeck.agents import llm as llm_mod
from pdfdeck.config import settings


class _Out(BaseModel):
    topic: str


def _overloaded():
    import anthropic

    resp = httpx.Response(
        529, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    return anthropic.OverloadedError("Overloaded", response=resp, body=None)


def _install(monkeypatch, primary_model, exc):
    """Fake `_bind`: the primary model raises `exc` (if any); any other model
    (i.e. the fallback) returns a valid _Out. Records call order in `seen`."""
    seen: list[str] = []

    def fake(model, schema, max_tokens):
        def run(_):
            seen.append(model)
            if model == primary_model and exc is not None:
                raise exc
            return schema(topic="fallback")
        return RunnableLambda(run)

    monkeypatch.setattr(llm_mod, "_bind", fake)
    return seen


def test_falls_back_to_secondary_on_overload(monkeypatch):
    monkeypatch.setattr(settings, "model_fallback_enabled", True)
    monkeypatch.setattr(settings, "fallback_model", "claude-sonnet-5")
    seen = _install(monkeypatch, "claude-opus-4-8", _overloaded())

    chain = llm_mod.structured_llm(_Out, "claude-opus-4-8")
    out = chain.invoke("x")

    assert out.topic == "fallback"                       # secondary model answered
    assert seen == ["claude-opus-4-8", "claude-sonnet-5"]  # primary tried, then fell back


def test_no_fallback_when_disabled(monkeypatch):
    import anthropic

    monkeypatch.setattr(settings, "model_fallback_enabled", False)
    _install(monkeypatch, "claude-opus-4-8", _overloaded())

    chain = llm_mod.structured_llm(_Out, "claude-opus-4-8")
    with pytest.raises(anthropic.OverloadedError):
        chain.invoke("x")


def test_non_transient_error_not_swallowed(monkeypatch):
    monkeypatch.setattr(settings, "model_fallback_enabled", True)
    monkeypatch.setattr(settings, "fallback_model", "claude-sonnet-5")
    seen = _install(monkeypatch, "claude-opus-4-8", ValueError("bad schema"))

    chain = llm_mod.structured_llm(_Out, "claude-opus-4-8")
    with pytest.raises(ValueError):
        chain.invoke("x")
    assert seen == ["claude-opus-4-8"]  # fallback NOT tried on a non-transient error


def test_bind_retries_on_validation_error(monkeypatch):
    """A structured call that omits a required field (pydantic ValidationError)
    is re-sampled once by _bind's retry wrapper, then succeeds."""

    class _Req(BaseModel):
        topic: str  # required -- constructing without it raises ValidationError

    attempts = {"n": 0}

    class _FakeLLM:
        def with_structured_output(self, schema):
            def run(_):
                attempts["n"] += 1
                if attempts["n"] == 1:
                    schema()            # missing 'topic' -> ValidationError
                return schema(topic="ok")
            return RunnableLambda(run)

    monkeypatch.setattr(llm_mod, "_chat", lambda model, max_tokens: _FakeLLM())

    out = llm_mod._bind("m", _Req, 100).invoke("x")
    assert out.topic == "ok"
    assert attempts["n"] == 2  # first attempt failed validation, retried once

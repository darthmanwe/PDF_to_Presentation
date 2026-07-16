"""Shared Claude client factory: SDK retries + model fallback on overload.

Every real LLM call in the pipeline is built here so the reliability policy
lives in one place:

1. **Retries** -- each ChatAnthropic client is configured with `max_retries`
   (`settings.llm_max_retries`); the Anthropic SDK does exponential backoff on
   429 / 5xx / 529 (overloaded).
2. **Model fallback** -- if the primary model is STILL failing with a transient
   server error after its retries, LangChain's `with_fallbacks` retries the same
   call on a secondary model (`settings.fallback_model`). So a 529 storm on Opus
   degrades to Sonnet instead of aborting the whole run.
3. **Validation retry** -- if a model returns a tool call that omits a required
   field (a pydantic ValidationError -- observed live when the Sonnet fallback
   dropped `topic`), the call is re-sampled once before giving up. Different
   models interpret a schema differently, so this guards every structured call.

Other non-transient errors (bad request, auth) are deliberately NOT caught here
-- they should surface, not silently downgrade to another model.
"""

from __future__ import annotations

from typing import Type

from pydantic import BaseModel, ValidationError

from pdfdeck.config import settings


def _transient_errors() -> tuple[type[BaseException], ...]:
    """Anthropic errors worth retrying on a *different* model (server-side, transient)."""
    import anthropic

    return (
        anthropic.OverloadedError,      # 529 -- the "Overloaded" case
        anthropic.InternalServerError,  # 5xx
        anthropic.APITimeoutError,
    )


def _chat(model: str, max_tokens: int):
    from langchain_anthropic import ChatAnthropic

    # No `temperature`: removed on Opus 4.8 / 4.7 (API returns 400).
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "max_retries": settings.llm_max_retries,
    }
    if settings.anthropic_api_key:  # else ChatAnthropic reads ANTHROPIC_API_KEY from the env
        kwargs["api_key"] = settings.anthropic_api_key
    return ChatAnthropic(**kwargs)


def _bind(model: str, schema: Type[BaseModel], max_tokens: int):
    """One structured-output client for `model`. Kept separate as the seam the
    fallback wiring (and its test) compose over.

    Wrapped in a validation retry: models occasionally return a tool call that
    omits a required field (observed live -- a fallback model dropped `topic`),
    which surfaces as a pydantic ValidationError. Retrying re-samples the call;
    the wait is disabled because a schema miss isn't a rate/capacity issue."""
    structured = _chat(model, max_tokens).with_structured_output(schema)
    return structured.with_retry(
        retry_if_exception_type=(ValidationError,),
        stop_after_attempt=2,
        wait_exponential_jitter=False,
    )


def structured_llm(
    schema: Type[BaseModel], model: str | None = None, *, max_tokens: int = 8192
):
    """A structured-output runnable for `schema` on `model` (default the content
    model), with SDK retries and -- when enabled -- a fallback to
    `settings.fallback_model` on transient overload/5xx errors."""
    model = model or settings.content_model
    primary = _bind(model, schema, max_tokens)

    fb = settings.fallback_model
    if settings.model_fallback_enabled and fb and fb != model:
        secondary = _bind(fb, schema, max_tokens)
        return primary.with_fallbacks([secondary], exceptions_to_handle=_transient_errors())
    return primary

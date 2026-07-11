"""Logging and cost accounting for pdfdeck.

ASCII-only log messages by policy: Windows consoles under cp1252 raise
UnicodeEncodeError on emoji, which plagued v1's print-debugging.
LangSmith tracing activates automatically via LANGSMITH_TRACING /
LANGSMITH_API_KEY environment variables (read by langchain-core).
"""

from __future__ import annotations

import logging

# Claude pricing per 1M tokens (input, output), used for the QAReport cost meter.
MODEL_PRICING_USD = {
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logging.getLogger("pdfdeck").handlers:
        root = logging.getLogger("pdfdeck")
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                              datefmt="%H:%M:%S")
        )
        root.addHandler(handler)
        root.setLevel(logging.INFO)
    return logger


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    inp, out = MODEL_PRICING_USD.get(model, (0.0, 0.0))
    return (input_tokens * inp + output_tokens * out) / 1_000_000

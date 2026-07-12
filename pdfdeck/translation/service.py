"""Azure Translator client with rate limiting, retry, and batching.

This is the one part of v1 worth keeping -- it was the best-engineered
module in the old codebase. Ported near-verbatim (chunking, per-minute rate
limiting, exponential backoff with jitter, 429/5xx handling) and cleaned:
ASCII logging, config from pydantic-settings. The pipeline treats it as a
deterministic node; translation was never the failure point.
"""

from __future__ import annotations

import random
import time
import uuid

import requests

from pdfdeck.config import settings
from pdfdeck.telemetry import get_logger

log = get_logger(__name__)


class TranslationService:
    def __init__(self) -> None:
        self.endpoint = settings.azure_translator_endpoint
        self.key = settings.azure_translator_key
        self.region = settings.azure_translator_region

        self.max_chars_per_request = 45000
        self.max_elements_per_request = 900
        self.max_chars_per_minute = 30000
        self.max_requests_per_minute = 20

        self.char_count_this_minute = 0
        self.request_count_this_minute = 0
        self.last_minute_reset = time.time()

        self.max_retries = 5
        self.base_delay = 1.0
        self.max_delay = 60.0

    def is_configured(self) -> bool:
        return bool(self.endpoint and self.key and self.region)

    # -- rate limiting ------------------------------------------------------

    def _reset_rate_limits(self) -> None:
        if time.time() - self.last_minute_reset >= 60:
            self.char_count_this_minute = 0
            self.request_count_this_minute = 0
            self.last_minute_reset = time.time()

    def _wait_for_rate_limit(self, text_length: int) -> None:
        self._reset_rate_limits()
        if (self.char_count_this_minute + text_length > self.max_chars_per_minute
                or self.request_count_this_minute >= self.max_requests_per_minute):
            wait = 60 - (time.time() - self.last_minute_reset)
            if wait > 0:
                log.info("translator rate limit reached; waiting %.1fs", wait)
                time.sleep(wait)
                self._reset_rate_limits()

    # -- chunking -----------------------------------------------------------

    def _chunk(self, texts: list[str]) -> list[list[str]]:
        chunks: list[list[str]] = []
        cur: list[str] = []
        cur_chars = 0
        for t in texts:
            tlen = len(t)
            if (len(cur) >= self.max_elements_per_request
                    or cur_chars + tlen >= self.max_chars_per_request):
                if cur:
                    chunks.append(cur)
                cur, cur_chars = [t], tlen
            else:
                cur.append(t)
                cur_chars += tlen
        if cur:
            chunks.append(cur)
        return chunks

    # -- request with retry -------------------------------------------------

    def _request(self, texts: list[str], target: str, source: str = "en") -> list[str]:
        url = f"{self.endpoint.rstrip('/')}/translate"
        params = {"api-version": "3.0", "from": source, "to": target}
        headers = {
            "Ocp-Apim-Subscription-Key": self.key,
            "Ocp-Apim-Subscription-Region": self.region,
            "Content-type": "application/json",
            "X-ClientTraceId": str(uuid.uuid4()),
        }
        body = [{"text": t} for t in texts]

        for attempt in range(self.max_retries):
            try:
                resp = requests.post(url, params=params, headers=headers, json=body, timeout=30)
                if resp.status_code == 200:
                    result = resp.json()
                    self.char_count_this_minute += sum(len(t) for t in texts)
                    self.request_count_this_minute += 1
                    return [item["translations"][0]["text"] for item in result]
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    wait = (int(retry_after) if retry_after
                            else min(self.base_delay * 2 ** attempt + random.uniform(0, 1), self.max_delay))
                    log.warning("translator 429; waiting %.1fs (retry %d)", wait, attempt + 1)
                    time.sleep(wait)
                    continue
                if resp.status_code in (500, 502, 503, 504):
                    wait = min(self.base_delay * 2 ** attempt + random.uniform(0, 1), self.max_delay)
                    log.warning("translator %d; waiting %.1fs (retry %d)",
                                resp.status_code, wait, attempt + 1)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
            except requests.exceptions.RequestException as exc:
                if attempt == self.max_retries - 1:
                    raise RuntimeError(f"translation failed after {self.max_retries} attempts: {exc}")
                wait = min(self.base_delay * 2 ** attempt + random.uniform(0, 1), self.max_delay)
                log.warning("translator error %s; waiting %.1fs (retry %d)", exc, wait, attempt + 1)
                time.sleep(wait)
        raise RuntimeError(f"translation failed after {self.max_retries} attempts")

    # -- public -------------------------------------------------------------

    def translate_batch(self, texts: list[str], target: str, source: str = "en") -> list[str]:
        """Translate a list of strings, preserving order and empty slots."""
        if not self.is_configured():
            raise RuntimeError("Azure Translator not configured")
        idxs = [i for i, t in enumerate(texts) if t and t.strip()]
        payload = [texts[i] for i in idxs]
        if not payload:
            return list(texts)

        out: list[str] = []
        for chunk in self._chunk(payload):
            self._wait_for_rate_limit(sum(len(t) for t in chunk))
            out.extend(self._request(chunk, target, source))
            time.sleep(0.3)

        result = list(texts)
        for pos, translated in zip(idxs, out):
            result[pos] = translated
        return result

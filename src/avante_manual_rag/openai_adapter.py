"""OpenAI SDK adapter: one retry layer, bounded calls and validated embeddings."""

import os
from pathlib import Path
import time
from typing import Any, Callable
import unicodedata

import numpy as np
from openai import APIConnectionError, APIStatusError, OpenAI
import tiktoken

from .config import Settings
from .contracts import fingerprint
from .errors import RagError, require
from .storage import contained, read_json, write_json


def token_counter(encoding: str) -> Callable[[str], int]:
    tokenizer = tiktoken.get_encoding(encoding)
    return lambda value: len(tokenizer.encode(value, disallowed_special=()))


def validate_vectors(values: Any, count: int, dimensions: int) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=np.float32)
    except (ValueError, TypeError) as error:
        raise RagError("embedding_error", "Invalid embedding array") from error
    if array.shape != (count, dimensions) or not np.isfinite(array).all():
        raise RagError("embedding_error", "Embedding shape or finite-value check failed")
    norms = np.linalg.norm(array.astype(np.float64), axis=1)
    if np.any(norms == 0):
        raise RagError("embedding_error", "Zero embedding vector")
    return array


class OpenAIAdapter:
    def __init__(self, settings: Settings, client: Any = None,
                 count: Callable[[str], int] | None = None) -> None:
        self.settings = settings
        self._client = client
        self.count = count
        self.usage: list[dict] = []

    @property
    def client(self) -> Any:
        if self._client is None:
            key = os.environ.get("OPENAI_API_KEY")
            require(bool(key), "OPENAI_API_KEY is missing; use local .env or environment")
            self._client = OpenAI(api_key=key, max_retries=0, timeout=self.settings.timeout)
        return self._client

    def call(self, operation: Callable, stage: str, **kwargs: Any) -> Any:
        started = time.monotonic()
        for attempt in range(3):
            remaining = self.settings.deadline - (time.monotonic() - started)
            if remaining <= 0:
                raise RagError(f"{stage}_error", "OpenAI operation deadline exceeded")
            try:
                response = operation(timeout=min(self.settings.timeout, remaining), **kwargs)
                if time.monotonic() - started > self.settings.deadline:
                    raise RagError(f"{stage}_error", "OpenAI operation deadline exceeded")
                usage = response.usage.model_dump() if response.usage else {}
                self.usage.append({"stage": stage, "requested_model": kwargs["model"],
                                   "response_model": response.model, "usage": usage})
                return response
            except (APIConnectionError, APIStatusError) as error:
                status = getattr(error, "status_code", None)
                code = getattr(error, "code", None)
                transient = isinstance(error, APIConnectionError) or status in (408, 409, 429)
                transient = transient or (status is not None and status >= 500)
                if code in ("insufficient_quota", "billing_hard_limit_reached"):
                    transient = False
                if not transient or attempt == 2:
                    category = "quota" if code == "insufficient_quota" else str(status or "network")
                    message = f"OpenAI request failed ({category})"
                    raise RagError(f"{stage}_error", message) from None
                delay = min(2 ** attempt, max(0, remaining - self.settings.timeout))
                time.sleep(delay)
        raise AssertionError("Unreachable")

    def embeddings(self, texts: list[str], cache: Path) -> np.ndarray:
        require(bool(texts), "No embedding inputs")
        counter = self.count or token_counter("cl100k_base")
        normalized = [unicodedata.normalize("NFC", value).strip() for value in texts]
        require(all(value and counter(value) <= 8191 for value in normalized),
                "Embedding input is blank or exceeds 8191 tokens; review chunk boundaries")
        keys = [fingerprint([self.settings.embedding_contract(), value]) for value in normalized]
        vectors: dict[str, list] = {}
        missing: dict[str, str] = {}
        for key, value in zip(keys, normalized):
            path = contained(cache, f"{key}.json")
            if path.exists():
                saved = read_json(path)
                require(saved["key"] == key, "Embedding cache key mismatch")
                validate_vectors([saved["vector"]], 1, self.settings.dimensions)
                vectors[key] = saved["vector"]
            else:
                missing[key] = value
        batch: list[tuple[str, str]] = []
        tokens = 0
        for key, value in missing.items():
            size = counter(value)
            if batch and (len(batch) >= 64 or tokens + size > 200000):
                vectors.update(self._embed_batch(batch, cache))
                batch, tokens = [], 0
            batch.append((key, value))
            tokens += size
        if batch:
            vectors.update(self._embed_batch(batch, cache))
        return validate_vectors([vectors[k] for k in keys], len(keys), self.settings.dimensions)

    def _embed_batch(self, batch: list[tuple[str, str]], cache: Path) -> dict[str, list]:
        response = self.call(self.client.embeddings.create, "embedding",
                             model=self.settings.embedding_model,
                             dimensions=self.settings.dimensions,
                             input=[value for _, value in batch], encoding_format="float")
        items = sorted(response.data, key=lambda item: item.index)
        if [item.index for item in items] != list(range(len(batch))):
            raise RagError("embedding_error", "Embedding response indices mismatch")
        matrix = validate_vectors([i.embedding for i in items], len(batch),
                                  self.settings.dimensions)
        results = {}
        for (key, _), vector in zip(batch, matrix):
            results[key] = vector.tolist()
            write_json(contained(cache, f"{key}.json"), {"key": key, "vector": results[key]})
        return results

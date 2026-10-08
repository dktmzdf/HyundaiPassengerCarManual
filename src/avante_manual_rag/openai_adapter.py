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
    """tiktoken 인코딩을 준비하고 문자열의 토큰 개수를 세는 함수를 반환한다.

    처음 쓰는 인코딩의 캐시가 없으면 토크나이저 파일 다운로드가 필요할 수 있다.
    특별 토큰처럼 보이는 문서 내용도 일반 입력으로 세며 API 키는 사용하지 않는다.
    """
    tokenizer = tiktoken.get_encoding(encoding)
    return lambda value: len(tokenizer.encode(value, disallowed_special=()))


def validate_vectors(values: Any, count: int, dimensions: int) -> np.ndarray:
    """벡터를 float32 행렬로 바꾸고 개수·차원·유한값·영벡터 여부를 검사한다.

    반환 모양은 (count, dimensions)이며 잘못된 값은 embedding_error로 거부한다.
    여기서는 L2 정규화하지 않으므로 FAISS 입력 전에 별도 정규화가 필요하다.
    """
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
        """설정과 선택적인 테스트용 클라이언트·토큰 계수기를 보관한다.

        실제 SDK 생성은 지연하며 이 시점에는 키를 읽거나 API를 호출하지 않는다.
        usage 목록은 이번 어댑터에서 성공적으로 받은 호출 응답의 사용량을 누적한다.
        """
        self.settings = settings
        self._client = client
        self.count = count
        self.usage: list[dict] = []

    @property
    def client(self) -> Any:
        """주입된 클라이언트를 쓰거나 환경변수 키로 SDK를 한 번만 생성해 반환한다.

        키가 없으면 configuration_error를 낸다. SDK 재시도를 꺼서 call 함수의
        재시도와 중복되지 않게 하며 클라이언트 생성만으로 모델을 호출하지 않는다.
        """
        if self._client is None:
            key = os.environ.get("OPENAI_API_KEY")
            require(bool(key), "OPENAI_API_KEY is missing; use local .env or environment")
            self._client = OpenAI(api_key=key, max_retries=0, timeout=self.settings.timeout)
        return self._client

    def call(self, operation: Callable, stage: str, **kwargs: Any) -> Any:
        """SDK 작업을 제한 시간 안에서 호출하고 성공 응답 및 usage를 반환·기록한다.

        stage는 embedding/generation 등의 오류 코드 접두사다. 연결·일시적 상태 오류는
        최대 두 번 재시도하고 인증·할당량 소진 등은 즉시 RagError로 변환한다.
        현재 APIResponseValidationError 같은 다른 SDK 예외는 이 경계에서 처리하지 않는다.
        """
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
        """입력 순서와 중복을 유지한 (입력 개수, 차원) 임베딩 행렬을 반환한다.

        NFC 정규화·양끝 공백 제거 후 빈 입력과 8191토큰 초과 입력을 거부한다.
        모델·차원·전처리·본문 해시로 캐시를 찾고 없는 고유 입력만 배치 호출한다.
        같은 텍스트는 배치 내에서도 한 번만 요청하며 API 장애·손상 캐시는 숨기지 않는다.
        """
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
        """(캐시 키, 입력 본문) 배치를 실제 API에 보내고 키별 벡터 목록을 저장·반환한다.

        응답 index로 순서를 복원한 뒤 개수·차원·벡터 값을 검사하므로 잘못된 응답은
        캐시에 쓰지 않는다. 일부 캐시 저장 실패 시 먼저 저장된 항목은 남을 수 있다.
        """
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

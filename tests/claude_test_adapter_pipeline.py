"""Code review reproductions for the OpenAI adapter and ask flow; run by explicit path."""

import httpx2
import pytest
from openai import APIResponseValidationError

from avante_manual_rag.answering import answer
from avante_manual_rag.contracts import SearchResult
from avante_manual_rag.errors import RagError
from avante_manual_rag.openai_adapter import OpenAIAdapter
from avante_manual_rag.pipeline import ask
from helpers import FakeClient, chunk, settings


def no_search(*args, **kwargs):
    """검색 호출을 가로채 AssertionError를 내서 로컬 선행 검사가 빠진 경로를 드러낸다."""
    raise AssertionError("search ran before local checks")


def test_invalid_sdk_response_is_a_generation_error(tmp_path):
    """SDK 응답 검증 예외가 generation_error로 변환돼야 한다는 리뷰의 요구를 재현한다."""
    request = httpx2.Request("POST", "https://test.invalid")
    client = FakeClient()
    client.response_error = APIResponseValidationError(
        httpx2.Response(200, request=request), None, message="invalid body")
    with pytest.raises(RagError) as error:
        answer("질문", [SearchResult(chunk(), .9)], {},
               OpenAIAdapter(settings(tmp_path), client, len))
    assert error.value.code == "generation_error"


def test_ask_rejects_missing_chat_model_before_embedding(tmp_path, monkeypatch):
    """생성 모델 누락을 유료 질문 임베딩 전에 거부해야 한다는 실행 순서 요구를 검사한다."""
    monkeypatch.setattr("avante_manual_rag.pipeline.search", no_search)
    config = settings(tmp_path, chat_model="")
    with pytest.raises(RagError) as error:
        ask(config, "엔진오일 용량은?", OpenAIAdapter(config, FakeClient(), len))
    assert error.value.code == "configuration_error"


def test_ask_profile_conflict_needs_no_search(tmp_path, monkeypatch):
    """명확한 다른 차량 사양은 검색 없이 확인 요청으로 처리해야 한다는 요구를 검사한다."""
    monkeypatch.setattr("avante_manual_rag.pipeline.search", no_search)
    config = settings(tmp_path)
    adapter = OpenAIAdapter(config, FakeClient(), len)
    result = ask(config, "2024년식 수동 아반떼 엔진오일 용량은?", adapter)
    assert result["answer"]["status"] == "needs_clarification"

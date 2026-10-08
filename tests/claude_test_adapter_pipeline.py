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
    raise AssertionError("search ran before local checks")


def test_invalid_sdk_response_is_a_generation_error(tmp_path):
    """grounded-manual-answers spec.md:63-65 reports an invalid response as a service failure."""
    request = httpx2.Request("POST", "https://test.invalid")
    client = FakeClient()
    client.response_error = APIResponseValidationError(
        httpx2.Response(200, request=request), None, message="invalid body")
    with pytest.raises(RagError) as error:
        answer("질문", [SearchResult(chunk(), .9)], {},
               OpenAIAdapter(settings(tmp_path), client, len))
    assert error.value.code == "generation_error"


def test_ask_rejects_missing_chat_model_before_embedding(tmp_path, monkeypatch):
    """A missing chat model must fail before the question is sent for a paid embedding."""
    monkeypatch.setattr("avante_manual_rag.pipeline.search", no_search)
    config = settings(tmp_path, chat_model="")
    with pytest.raises(RagError) as error:
        ask(config, "엔진오일 용량은?", OpenAIAdapter(config, FakeClient(), len))
    assert error.value.code == "configuration_error"


def test_ask_profile_conflict_needs_no_search(tmp_path, monkeypatch):
    """An explicit other-year question is answered locally without retrieval."""
    monkeypatch.setattr("avante_manual_rag.pipeline.search", no_search)
    config = settings(tmp_path)
    adapter = OpenAIAdapter(config, FakeClient(), len)
    result = ask(config, "2024년식 수동 아반떼 엔진오일 용량은?", adapter)
    assert result["answer"]["status"] == "needs_clarification"

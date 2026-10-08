"""Code review reproductions for answering; outside default discovery, so run by path."""

import pytest

from avante_manual_rag.answering import answer, conflicting_vehicle, quote_candidates
from avante_manual_rag.contracts import SearchResult
from avante_manual_rag.openai_adapter import OpenAIAdapter
from helpers import FakeClient, chunk, settings


def test_long_unpunctuated_table_rows_stay_quotable():
    """A short sentence before a long table must not hide the table rows from quote IDs."""
    rows = "\n".join(f"항목 {n:02d} | {n} kg" for n in range(100))
    source = "엔진룸 주의.\n" + rows + "\nDCT 오일 | 3.3 L\n경고문."
    assert len(source) > 1200
    assert any("DCT 오일 | 3.3 L" in value for value in quote_candidates(source))


def test_last_sentence_of_a_long_chunk_stays_quotable():
    """The 32-candidate cap must not make the end of a reviewed chunk uncitable."""
    sentences = [f"항목 {n} 설명이다." for n in range(40)]
    source = " ".join(sentences + ["주행 중 변속 레버를 조작하지 마십시오."])
    assert any("변속 레버" in value for value in quote_candidates(source))


@pytest.mark.parametrize("question", [
    "2030년까지 보증되는 항목이 뭐야?",
    "내 차는 DCT인데 수동 모드로 몇 단까지 올라가?",
])
def test_supported_dct_questions_are_not_profile_conflicts(question):
    """Only an explicit other year, model or transmission conflicts with the 2025 DCT."""
    assert not conflicting_vehicle(question)


def test_context_overflow_is_a_shortage_without_model_call(tmp_path):
    """design.md:243-244 returns a shortage state when no complete evidence bundle fits."""
    client = FakeClient()
    adapter = OpenAIAdapter(settings(tmp_path), client, len)
    result = answer("질문", [SearchResult(chunk(text="가" * 20000), .9)], {}, adapter)
    assert result.status == "insufficient_evidence"
    assert client.calls == []

from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import httpx2
import pytest
from openai import APIStatusError, APITimeoutError

from avante_manual_rag.answering import (
    answer, conflicting_vehicle, numeric_terms, source_quote, validate_answer,
)
from avante_manual_rag.chunking import make_chunks
from avante_manual_rag.contracts import Block, Page, SearchResult
from avante_manual_rag.errors import RagError
from avante_manual_rag.evaluation import evaluate, metrics
from avante_manual_rag.ingestion import register
from avante_manual_rag.openai_adapter import OpenAIAdapter
from avante_manual_rag.parsing import apply_review, printed_number
from avante_manual_rag.pipeline import ingest, index
from avante_manual_rag.retrieval import create_index, search
from avante_manual_rag.storage import GenerationStore, file_hash, read_json, write_json
from helpers import FakeClient, chunk, settings
from test_pipeline import source


def test_line_wrap_quote_returns_source_but_paraphrase_fails():
    assert source_quote("앞 250 kPa", "앞\n250 kPa") == "앞\n250 kPa"
    assert source_quote("앞 251 kPa", "앞\n250 kPa") is None
    assert source_quote("앞 ... kPa", "앞 250 kPa") is None


def test_numbered_steps_unit_alias_and_explicit_vehicle_scope():
    assert numeric_terms("1. 브레이크를 밟아.\n2. D로 바꿔.") == set()
    assert numeric_terms("47 리터") == numeric_terms("47 ℓ") == {"47L"}
    assert conflicting_vehicle("내 차는 2024년식 아반떼 N 수동이야")
    assert conflicting_vehicle("2025 아반떼 하이브리드에 적용해도 돼?")
    assert not conflicting_vehicle("2025년식 DCT의 수동 변속 모드는?")


def test_ambiguous_footer_is_not_invented():
    page = NS(height=600, width=400,
              crop=lambda _: NS(extract_text=lambda: "1-1 2-2"))
    assert printed_number(page) is None


def test_review_separates_columns_and_unknown_scope(tmp_path):
    import pdfplumber
    config, path = source(tmp_path)
    with pdfplumber.open(path) as pdf:
        page = apply_review(pdf.pages[0], Page(1, None, "needs_review", "raw"), {
            "reason": "Synthetic two-column visual layout", "regions": [
                {"id": "left", "bbox": [30, 40, 200, 80], "kind": "text", "section": "L",
                 "applicability": "dct"},
                {"id": "right", "bbox": [210, 40, 390, 80], "kind": "text", "section": "R",
                 "applicability": "unknown"}]})
    assert page.blocks[0].text == "Left column"
    assert page.blocks[1].text == "Right column"
    chunks = make_chunks(register(config)[0], [page], config.profile, "p")
    assert len(chunks) == 1 and "Right" not in chunks[0].text


def test_long_table_is_preserved_and_rejected_when_over_budget(tmp_path):
    config, _ = source(tmp_path)
    document, _ = register(config)
    body = "HEADER kg\n" + "DCT 123 kg\n" * 1000 + "WARNING"
    block = Block("long", 1, [0, 0, 100, 100], "table", body, "table", "dct", True,
                  warnings=["WARNING"])
    result = make_chunks(document, [Page(1, None, "success", body, [block])], config.profile, "p")
    assert result[0].text == body
    with pytest.raises(RagError, match="8191"):
        OpenAIAdapter(config, FakeClient(), len).embeddings([result[0].text], tmp_path / "cache")


@pytest.mark.parametrize("status,code", [(401, "invalid_api_key"), (429, "insufficient_quota")])
def test_generation_auth_quota_errors_are_not_absence(tmp_path, status, code):
    client = FakeClient()
    response = httpx2.Response(status, request=httpx2.Request("POST", "https://test.invalid"))
    client.response_error = APIStatusError("private", response=response, body={"code": code})
    with pytest.raises(RagError) as error:
        answer("question", [SearchResult(chunk(), 1)], {},
               OpenAIAdapter(settings(tmp_path), client, len))
    assert error.value.code == "generation_error" and len(client.calls) == 1


def test_timeout_has_single_retry_layer(tmp_path, monkeypatch):
    monkeypatch.setattr("avante_manual_rag.openai_adapter.time.sleep", lambda _: None)
    client = FakeClient()
    client.embedding_error = APITimeoutError(request=httpx2.Request("POST", "https://test.invalid"))
    with pytest.raises(RagError):
        OpenAIAdapter(settings(tmp_path), client, len).embeddings(["test"], tmp_path / "cache")
    assert len(client.calls) == 3


@pytest.mark.parametrize("status", ["needs_clarification", "conflicting_evidence"])
def test_domain_states_are_not_provider_errors(status):
    assert validate_answer({"status": status, "claims": []}, [], {}).status == status


def test_index_count_mismatch_and_failed_reindex_preserve_active(tmp_path):
    config = settings(tmp_path)
    adapter = OpenAIAdapter(config, FakeClient(), len)
    first = create_index(config, [chunk()], "p", {}, adapter)
    store = GenerationStore(config.data_root)
    with patch("avante_manual_rag.retrieval.faiss.write_index", side_effect=RuntimeError("disk")):
        with pytest.raises(RuntimeError):
            create_index(config, [chunk()], "p", {}, adapter)
    assert store.active("indexes")[0] == first
    _, directory = store.active("indexes")
    metadata = read_json(directory / "metadata.json")
    metadata["build"]["count"] = 2
    write_json(directory / "metadata.json", metadata)
    store.publish("indexes", first, ["vectors.faiss", "metadata.json"])
    with pytest.raises(RagError, match="count"):
        search(config, "question", adapter)


def test_quality_gate_needs_every_judgment_and_zero_errors():
    judgment = {"pass": True, "scope_errors": 0, "citation_errors": 0,
                "numeric_unit_errors": 0, "warning_errors": 0}
    rows = [{"expected_status": "answered", "actual_status": "answered",
             "retrieval_pass": True, "judgment": judgment},
            {"expected_status": "insufficient_evidence", "actual_status": "insufficient_evidence",
             "retrieval_pass": False, "judgment": judgment.copy()}]
    assert metrics(rows)["quality_gate"]
    rows[1]["judgment"]["warning_errors"] = 1
    assert not metrics(rows)["quality_gate"]


def test_full_synthetic_rerun_failure_and_restore(tmp_path):
    from dataclasses import replace
    config, path = source(tmp_path)
    before = file_hash(path)
    review_path = tmp_path / "review.json"
    write_json(review_path, {"document_id": before, "pages": {"1": {
        "reason": "Synthetic review", "regions": [{"id": "a", "bbox": [30, 40, 200, 80],
        "kind": "text", "section": "Test", "applicability": "dct"}]}}})
    config = replace(config, review_file=review_path)
    first_parse = ingest(config)
    adapter = OpenAIAdapter(config, FakeClient(), len)
    first_index = index(config, adapter)
    second_parse = ingest(config)
    second_index = index(config, adapter)
    assert first_parse["processing_id"] == second_parse["processing_id"]
    assert second_index["chunks"] == 1 and len(adapter.client.calls) == 1
    store = GenerationStore(config.data_root)
    store.activate("parsed", first_parse["generation"])
    store.activate("indexes", first_index["generation"])
    assert search(config, "query", adapter)[0]
    assert file_hash(path) == before


def test_local_evaluation_is_offline_and_shared_output_is_redacted(tmp_path):
    config, _ = source(tmp_path)
    registered = ingest(config)
    cases = {"version": "synthetic-v1", "document_id": registered["document_id"],
             "profile": {"project_code": "CN7N", "model_year": 2025, "transmission": "dct"},
             "cases": [{"id": "absent", "category": "absence", "question": "PRIVATE QUERY",
                        "required_bundles": [], "expected_terms": [],
                        "expected_status": "insufficient_evidence"}]}
    cases_path = tmp_path / "cases.json"
    write_json(cases_path, cases)
    client = FakeClient()
    result = evaluate(config, cases_path, "local", OpenAIAdapter(config, client, len))
    assert result["live_status"] == "not_run" and not result["metrics"]["quality_gate"]
    assert client.calls == []
    assert "PRIVATE QUERY" not in str(result)
    assert "raw_text" not in str(result)
    store = GenerationStore(config.data_root)
    _, directory = store.active("reports")
    detail = read_json(directory / "detail.json")
    assert detail["document_id"] == registered["document_id"]
    assert detail["versions"]["openai"] == "3.26.0"


def test_ask_cli_states_failures_and_exit_codes(tmp_path, monkeypatch, capsys):
    import json
    from avante_manual_rag.cli import main
    from avante_manual_rag.retrieval import create_index
    config = settings(tmp_path)
    client = FakeClient()
    adapter = OpenAIAdapter(config, client, len)
    create_index(config, [chunk()], "processing", {}, adapter)
    monkeypatch.setattr("avante_manual_rag.cli.load_settings", lambda _: config)
    monkeypatch.setattr("avante_manual_rag.cli.OpenAIAdapter", lambda _: adapter)
    assert main(["ask", "2024년식 수동 차량이야"]) == 0
    assert json.loads(capsys.readouterr().out)["answer"]["status"] == "needs_clarification"
    client.payload = '{"status":"conflicting_evidence","claims":[]}'
    assert main(["ask", "question"]) == 0
    assert json.loads(capsys.readouterr().out)["answer"]["status"] == "conflicting_evidence"
    client.status = "incomplete"
    assert main(["ask", "question"]) != 0
    assert json.loads(capsys.readouterr().err)["error"] == "generation_error"

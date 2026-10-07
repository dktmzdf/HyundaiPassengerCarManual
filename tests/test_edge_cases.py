import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen.canvas import Canvas

from avante_manual_rag.answering import answer
from avante_manual_rag.cli import execute, main, parser
from avante_manual_rag.config import load_local_env
from avante_manual_rag.contracts import SearchResult
from avante_manual_rag.errors import RagError
from avante_manual_rag.ingestion import register
from avante_manual_rag.openai_adapter import OpenAIAdapter
from avante_manual_rag.parsing import extract_page, parse_manual
from avante_manual_rag.storage import contained, file_hash, read_json, write_json
from helpers import FakeClient, chunk, settings
from test_pipeline import source


def test_env_load_known_keys_no_execution(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_CHAT_MODEL", raising=False)
    path = tmp_path / ".env"
    path.write_text('OPENAI_API_KEY="test-key"\nOPENAI_CHAT_MODEL=gpt-5-mini\n'
                    'UNTRUSTED=$(run-something)\n', encoding="utf-8")
    load_local_env(path)
    import os
    assert os.environ["OPENAI_API_KEY"] == "test-key"
    assert "UNTRUSTED" not in os.environ
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.delenv("OPENAI_CHAT_MODEL")


def test_missing_key_and_model_are_errors(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    adapter = OpenAIAdapter(settings(tmp_path), count=len)
    with pytest.raises(RagError, match="OPENAI_API_KEY"):
        adapter.embeddings(["test"], tmp_path / "cache")
    with pytest.raises(RagError, match="chat_model"):
        answer("question", [SearchResult(chunk(), 1)], {},
               OpenAIAdapter(settings(tmp_path, chat_model=""), FakeClient(), len))


def test_ingest_requires_no_key_search_requires_no_chat_model(tmp_path, monkeypatch):
    config, _ = source(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("avante_manual_rag.cli.load_settings", lambda _: config)
    args = parser().parse_args(["ingest", "--pages", "1"])
    result = execute(args)
    assert result["coverage"]["statuses"] == {"needs_review": 1, "not_processed": 1}
    from avante_manual_rag.retrieval import create_index, search
    config = settings(tmp_path, chat_model="")
    adapter = OpenAIAdapter(config, FakeClient(), len)
    create_index(config, [chunk()], result["processing_id"], {}, adapter)
    assert search(config, "question", adapter)[0]


def test_manifest_wrong_year(tmp_path):
    config, _ = source(tmp_path)
    original = config.manifest.read_text(encoding="utf-8")
    config.manifest.write_text(original.replace("2025", "2024"), encoding="utf-8")
    with pytest.raises(RagError, match="year"):
        register(config)


def test_korean_table_coordinates_and_deduplication(tmp_path):
    import pdfplumber
    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    path = tmp_path / "synthetic.pdf"
    canvas = Canvas(str(path), pagesize=(400, 600))
    canvas.setFont("HYSMyeongJo-Medium", 12)
    canvas.drawString(40, 540, "한글 경고")
    for x in [40, 150, 260]:
        canvas.line(x, 400, x, 500)
    for y in [400, 450, 500]:
        canvas.line(40, y, 260, y)
    for x, y, value in [(50, 470, "종류"), (160, 470, "용량 L"),
                         (50, 420, "DCT"), (160, 420, "3.3")]:
        canvas.drawString(x, y, value)
    canvas.save()
    with pdfplumber.open(path) as pdf:
        page = extract_page(pdf.pages[0], 1)
    assert "한글 경고" in page.raw_text
    tables = [b for b in page.blocks if b.kind == "table"]
    assert tables[0].table == [["종류", "용량 L"], ["DCT", "3.3"]]
    assert "3.3" not in next(b.text for b in page.blocks if b.kind == "text")
    assert page.printed_page is None


def test_extraction_failure_recorded_and_review_hash_rejected(tmp_path):
    config, path = source(tmp_path)
    document, _ = register(config)
    with patch("avante_manual_rag.parsing.extract_page", side_effect=ValueError("bad page")):
        pages, _ = parse_manual(path, document)
    assert all(p.status == "failed" and p.issues for p in pages)
    with pytest.raises(RagError, match="hash"):
        parse_manual(path, document, review={"document_id": "wrong", "pages": {}})


def test_directory_link_escape_is_rejected(tmp_path):
    import os
    import subprocess
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    link = root / "linked"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                       check=True, capture_output=True, timeout=10)
    else:
        link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(RagError, match="escapes"):
        contained(root, "linked/file.json")


def test_invalid_response_indices_fail_before_cache(tmp_path):
    client = FakeClient()
    client.embeddings.create = lambda **_: NS(data=[NS(index=2, embedding=[1.] * 1536)],
                                             model="text-embedding-3-small", usage=None)
    with pytest.raises(RagError, match="indices"):
        OpenAIAdapter(settings(tmp_path), client, len).embeddings(["test"], tmp_path / "cache")
    assert not (tmp_path / "cache").exists()

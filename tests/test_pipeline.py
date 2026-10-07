import csv
from dataclasses import replace
import json
from pathlib import Path

import pytest
from reportlab.pdfgen.canvas import Canvas

from avante_manual_rag.chunking import make_chunks
from avante_manual_rag.cli import main
from avante_manual_rag.contracts import Answer, Block, Document, IndexBuild, Page
from avante_manual_rag.errors import RagError
from avante_manual_rag.evaluation import metrics
from avante_manual_rag.ingestion import register
from avante_manual_rag.parsing import parse_manual
from avante_manual_rag.storage import contained, file_hash
from helpers import settings


def source(tmp_path):
    config = settings(tmp_path)
    config.raw_root.mkdir()
    path = config.raw_root / config.filename
    canvas = Canvas(str(path), pagesize=(400, 600))
    canvas.drawString(40, 540, "Left column")
    canvas.drawString(220, 540, "Right column")
    canvas.drawString(350, 20, "1-1")
    canvas.showPage()
    canvas.showPage()
    canvas.save()
    row = {"filename": path.name, "project_code": "CN7N", "model_year": "2025",
           "sha256": file_hash(path), "size_bytes": path.stat().st_size,
           "model": "Synthetic", "language": "ko_KR", "source_url": "https://test.invalid"}
    with config.manifest.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    return config, path


def test_registration_and_page_status(tmp_path):
    config, path = source(tmp_path)
    before = file_hash(path)
    document, _ = register(config)
    assert register(config)[0] == document
    pages, processing = parse_manual(path, document)
    assert pages[0].printed_page == "1-1"
    assert pages[0].status == "needs_review"
    assert pages[1].status == "needs_ocr"
    assert make_chunks(document, pages, config.profile, processing) == []
    assert file_hash(path) == before
    assert document.source_status == "unverified"
    with pytest.raises(RagError):
        parse_manual(path, document, {3})
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(RagError, match="hash mismatch"):
        register(config)
    path.unlink()
    with pytest.raises(RagError, match="missing"):
        register(config)


def test_linked_warning_cross_page_and_scope(tmp_path):
    config, path = source(tmp_path)
    document, _ = register(config)
    block = Block("dct", 1, [0, 0, 100, 100], "table", "DCT 3.3 L", "Oil",
                  "dct", True, related_ids=["warning"], table=[["type", "L"], ["DCT", "3.3"]])
    warning = Block("warning", 2, [0, 0, 100, 100], "warning", "Check gauge", "Oil",
                    "common", True, warnings=["Check gauge"])
    pages = [Page(1, "1-1", "success", "", [block]), Page(2, "1-2", "success", "", [warning])]
    chunks = make_chunks(document, pages, config.profile, "processing")
    assert chunks[0].pages == [1, 2]
    assert "Check gauge" in chunks[0].text
    assert chunks == make_chunks(document, pages, config.profile, "processing")
    warning.applicability = "manual"
    with pytest.raises(RagError, match="incompatible"):
        make_chunks(document, pages, config.profile, "processing")


def test_contracts_reject_bad_enums_shapes_and_paths(tmp_path):
    for factory in [lambda: Answer("bad", "text"), lambda: Answer("answered", "", claims="bad"),
                    lambda: IndexBuild("g", "p", settings(tmp_path).profile, {}, 1),
                    lambda: Page(1, None, "unknown", ""),
                    lambda: Document("a" * 64, "../file", "title", "CN7N", 2025, "ko", 1, "")]:
        with pytest.raises(RagError):
            factory()


def test_missing_config_nonzero_and_no_input_logging(tmp_path, capsys):
    assert main(["--config", str(tmp_path / "missing.toml"), "ask", "PRIVATE QUESTION"]) != 0
    output = capsys.readouterr()
    assert "PRIVATE QUESTION" not in output.err


def test_metrics_abstention_and_missing_judgment_fail():
    judgment = {"pass": True, "scope_errors": 0, "citation_errors": 0,
                "numeric_unit_errors": 0, "warning_errors": 0}
    rows = [{"expected_status": "answered", "actual_status": "insufficient_evidence",
             "retrieval_pass": True, "judgment": judgment}]
    result = metrics(rows)
    assert result["recall_at_5"] == 1 and result["answer_pass_rate"] == 0
    assert result["quality_gate"] is False
    rows[0].update(actual_status="answered", judgment=None)
    assert metrics(rows)["judgment_status"] == "not_run"

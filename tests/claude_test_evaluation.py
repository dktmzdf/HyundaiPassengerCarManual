"""Code review reproductions for evaluation; outside default discovery, so run by path."""

from avante_manual_rag.contracts import fingerprint
from avante_manual_rag.evaluation import evaluate, metrics
from avante_manual_rag.openai_adapter import OpenAIAdapter
from avante_manual_rag.storage import write_json
from helpers import FakeClient, settings

JUDGMENT = {"pass": True, "scope_errors": 0, "citation_errors": 0,
            "numeric_unit_errors": 0, "warning_errors": 0}


def row(expected: str, actual: str, passed: bool = True) -> dict:
    return {"expected_status": expected, "actual_status": actual, "retrieval_pass": True,
            "judgment": {**JUDGMENT, "pass": passed}}


def test_answer_rate_uses_answerable_cases_only():
    """design.md:269 and rag-quality-evaluation spec.md:56 divide by answerable cases."""
    rows = ([row("answered", "answered")] * 7
            + [row("answered", "insufficient_evidence", passed=False)]
            + [row("insufficient_evidence", "insufficient_evidence")] * 8)
    result = metrics(rows)
    assert not result["quality_gate"]
    assert result["answer_total"] == 8
    assert result["answer_pass_rate"] == 7 / 8


def test_judged_gate_fails_when_a_parsing_check_fails(tmp_path):
    """rag-quality-evaluation spec.md:62 passes a run only when every criterion holds."""
    config = settings(tmp_path)
    cases = {"version": "synthetic-v1", "document_id": "a" * 64,
             "profile": {"project_code": "CN7N", "model_year": 2025, "transmission": "dct"},
             "cases": [{"id": "oil", "category": "table", "question": "DCT 오일 용량은?",
                        "required_bundles": [["oil"]], "expected_terms": ["3.3 L"],
                        "expected_status": "answered"}]}
    report = {"cases_hash": fingerprint(cases), "results": [row("answered", "answered")],
              "parsing_checks": [{"id": "oil", "applicable": True, "pass": False}]}
    write_json(tmp_path / "cases.json", cases)
    write_json(tmp_path / "report.json", report)
    adapter = OpenAIAdapter(config, FakeClient(), len)
    result = evaluate(config, tmp_path / "cases.json", "judge", adapter,
                      tmp_path / "report.json")
    assert not result["metrics"]["quality_gate"]

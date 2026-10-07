"""Separate retrieval measurements, deterministic checks and human semantic judgments."""

from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from .answering import answer
from .config import Settings
from .contracts import fingerprint, to_dict
from .errors import RagError, require
from .openai_adapter import OpenAIAdapter
from .retrieval import search
from .storage import GenerationStore, contained, read_json, write_json


def metrics(rows: list[dict]) -> dict:
    answerable = [r for r in rows if r["expected_status"] == "answered"]
    retrieved = sum(r.get("retrieval_pass") is True for r in answerable)
    fields = {"pass", "scope_errors", "citation_errors", "numeric_unit_errors", "warning_errors"}
    judged = [r for r in rows if isinstance(r.get("judgment"), dict)
              and fields <= r["judgment"].keys()
              and type(r["judgment"]["pass"]) is bool
              and all(type(r["judgment"][f]) is int and r["judgment"][f] >= 0
                      for f in fields - {"pass"})]
    passed = sum(r["judgment"].get("pass") is True and
                 r.get("actual_status") == r["expected_status"] for r in judged)
    absence = [r for r in rows if r["expected_status"] == "insufficient_evidence"]
    errors = {name: sum(r["judgment"].get(name, 0) for r in judged)
              for name in ("scope_errors", "citation_errors", "numeric_unit_errors",
                           "warning_errors")}
    recall = retrieved / len(answerable) if answerable else None
    rate = passed / len(rows) if rows else None
    complete = bool(rows) and len(judged) == len(rows)
    all_absent = all(r.get("actual_status") == "insufficient_evidence" for r in absence)
    return {"retrieval_pass": retrieved, "retrieval_total": len(answerable), "recall_at_5": recall,
            "answer_pass": passed, "answer_total": len(rows), "answer_pass_rate": rate,
            "judgment_status": "complete" if complete else "not_run",
            "errors": errors, "all_absence_abstain": all_absent,
            "quality_gate": complete and recall is not None and recall >= .9 and rate >= .9
            and not any(errors.values()) and all_absent}


def run_case(case: dict, settings: Settings, adapter: OpenAIAdapter) -> dict:
    row = {"id": case["id"], "category": case["category"],
           "expected_status": case["expected_status"], "judgment": None}
    try:
        results, coverage = search(settings, case["question"], adapter)
        ids = {b for r in results[:5] for b in r.chunk.block_ids}
        # Every required bundle needs at least one acceptable evidence block.
        bundles = case["required_bundles"]
        row["retrieval_pass"] = bool(bundles) and all(set(b) & ids for b in bundles)
        row["retrieved_blocks"] = sorted(ids)
        result = answer(case["question"], results, coverage, adapter)
        row["actual_status"] = result.status
        row["answer"] = to_dict(result)
    except RagError as error:
        row.update({"actual_status": "error", "error": error.code, "message": error.message})
    return row


def evaluate(settings: Settings, cases_path: Path, mode: str, adapter: OpenAIAdapter,
             report_path: Path | None = None) -> dict:
    cases_data = read_json(cases_path)
    cases = cases_data["cases"]
    require(bool(cases) and len({c["id"] for c in cases}) == len(cases), "Invalid cases")
    store = GenerationStore(settings.data_root)
    if mode == "judge":
        require(report_path is not None, "--report is required for judge mode")
        report = read_json(report_path)
        require(report["cases_hash"] == fingerprint(cases_data), "Case version mismatch")
        return {"metrics": metrics(report["results"]), "kind": "shared_summary"}
    _, directory = store.active("parsed")
    document = read_json(contained(directory, "document.json"))
    require(document["document_id"] == cases_data["document_id"], "Case document mismatch")
    require(cases_data["profile"] == to_dict(settings.profile), "Case vehicle mismatch")
    summary = read_json(contained(directory, "summary.json"))
    pages = {p["pdf_page"]: p for p in read_json(contained(directory, "pages.json"))}
    available = {b["block_id"]: b for p in pages.values() for b in p["blocks"] if b["reviewed"]}
    checks = []
    for case in cases:
        source = "\n".join(available[b]["text"] for bundle in case["required_bundles"]
                           for b in bundle if b in available)
        preserved = all(term in source for term in case.get("expected_terms", []))
        found = all(any(b in available for b in bundle) for bundle in case["required_bundles"])
        applicable = bool(case["required_bundles"] or case.get("expected_terms"))
        checks.append({"id": case["id"], "applicable": applicable,
                       "pass": found and preserved if applicable else None})
    rows = [run_case(c, settings, adapter) for c in cases] if mode == "live" else []
    index_generation = None
    if mode == "live":
        index_generation, _ = store.active("indexes")
    generation, output = store.begin("reports")
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "mode": mode,
              "cases_hash": fingerprint(cases_data), "processing_id": summary["processing_id"],
              "document_id": document["document_id"], "index_generation": index_generation,
              "command": f"evaluate --mode {mode}", "case_version": cases_data["version"],
              "settings": {"embedding": settings.embedding_contract(), "chat": settings.chat_model,
                           "context_tokens": settings.context_tokens,
                           "output_tokens": settings.output_tokens,
                           "token_encoding": settings.token_encoding, "top_k": settings.top_k,
                           "min_score": settings.min_score},
              "versions": {p: version(p) for p in ["openai", "pdfplumber", "faiss-cpu"]},
              "parsing_checks": checks, "coverage": summary["coverage"], "usage": adapter.usage,
              "results": rows, "metrics": metrics(rows),
              "limits": ["Semantic entailment requires manual judgment",
                         "Unreviewed pages are excluded from answer retrieval"]}
    write_json(contained(output, "detail.json"), report)
    shared = {"generation": generation, "mode": mode, "metrics": report["metrics"],
              "parsing_pass": sum(c["pass"] is True for c in checks),
              "parsing_total": sum(c["applicable"] for c in checks),
              "live_status": ("completed_with_errors" if any(r["actual_status"] == "error"
                                                              for r in rows) else "executed")
              if mode == "live" else "not_run"}
    write_json(contained(output, "summary.json"), shared)
    store.publish("reports", generation, ["detail.json", "summary.json"])
    return shared

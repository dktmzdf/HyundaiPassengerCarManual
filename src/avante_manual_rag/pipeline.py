"""Application operations; adapters never invoke CLI or UI code."""

from pathlib import Path

from .answering import answer
from .chunking import make_chunks
from .config import Settings
from .contracts import Document, page_from_dict, to_dict
from .ingestion import register
from .openai_adapter import OpenAIAdapter
from .parsing import coverage, parse_manual
from .retrieval import create_index, search
from .storage import GenerationStore, contained, read_json, write_json


def ingest(settings: Settings, selected: set[int] | None = None) -> dict:
    document, path = register(settings)
    review = (read_json(settings.review_file)
              if settings.review_file and settings.review_file.is_file() else None)
    pages, processing = parse_manual(path, document, selected, review)
    store = GenerationStore(settings.data_root)
    generation, directory = store.begin("parsed")
    write_json(contained(directory, "document.json"), to_dict(document))
    write_json(contained(directory, "pages.json"), [to_dict(p) for p in pages])
    summary = {"processing_id": processing, "coverage": coverage(pages)}
    write_json(contained(directory, "summary.json"), summary)
    store.publish("parsed", generation, ["document.json", "pages.json", "summary.json"])
    return {"generation": generation, "document_id": document.document_id, **summary}


def index(settings: Settings, adapter: OpenAIAdapter) -> dict:
    _, directory = GenerationStore(settings.data_root).active("parsed")
    document = Document(**read_json(contained(directory, "document.json")))
    pages = [page_from_dict(p) for p in read_json(contained(directory, "pages.json"))]
    summary = read_json(contained(directory, "summary.json"))
    chunks = make_chunks(document, pages, settings.profile, summary["processing_id"])
    generation = create_index(settings, chunks, summary["processing_id"],
                              summary["coverage"], adapter)
    return {"generation": generation, "chunks": len(chunks), "usage": adapter.usage}


def ask(settings: Settings, question: str, adapter: OpenAIAdapter) -> dict:
    results, stats = search(settings, question, adapter)
    result = answer(question, results, stats, adapter)
    return {"answer": to_dict(result), "usage": adapter.usage}

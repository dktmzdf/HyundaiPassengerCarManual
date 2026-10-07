"""JSON CLI output contains requested results; error output never dumps input or secrets."""

import argparse
import json
from pathlib import Path
import sys

from .config import load_settings
from .contracts import to_dict
from .errors import RagError, require
from .openai_adapter import OpenAIAdapter
from . import pipeline
from .retrieval import search
from .storage import GenerationStore


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="avante-rag")
    result.add_argument("--config", type=Path, default=Path("config.example.toml"))
    commands = result.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("--pages", help="PDF page numbers/ranges, e.g. 1,13,16-18")
    commands.add_parser("index")
    for name in ("search", "ask"):
        command = commands.add_parser(name)
        command.add_argument("question")
    rollback = commands.add_parser("rollback")
    rollback.add_argument("kind", choices=["parsed", "indexes"])
    rollback.add_argument("generation")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--cases", type=Path, required=True)
    evaluate.add_argument("--mode", choices=["local", "live", "judge"], default="local")
    evaluate.add_argument("--report", type=Path)
    return result


def page_selection(value: str | None) -> set[int] | None:
    if value is None:
        return None
    numbers = set()
    for part in value.split(","):
        bounds = [int(v) for v in part.split("-")]
        require(1 <= len(bounds) <= 2 and min(bounds) > 0, "Invalid page selection")
        if len(bounds) == 1:
            numbers.add(bounds[0])
        else:
            require(bounds[0] <= bounds[1] <= 100000, "Invalid page range")
            numbers.update(range(bounds[0], bounds[1] + 1))
    return numbers


def execute(args: argparse.Namespace) -> dict:
    settings = load_settings(args.config)
    adapter = OpenAIAdapter(settings)
    if args.command == "ingest":
        return pipeline.ingest(settings, page_selection(args.pages))
    if args.command == "index":
        return pipeline.index(settings, adapter)
    if args.command == "search":
        results, coverage = search(settings, args.question, adapter)
        return {"results": [to_dict(r) for r in results], "coverage": coverage,
                "usage": adapter.usage}
    if args.command == "ask":
        return pipeline.ask(settings, args.question, adapter)
    if args.command == "rollback":
        GenerationStore(settings.data_root).activate(args.kind, args.generation)
        return {"generation": args.generation, "status": "activated"}
    from .evaluation import evaluate
    return evaluate(settings, args.cases, args.mode, adapter, args.report)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        output = execute(args)
        print(json.dumps(output, ensure_ascii=False, allow_nan=False))
        return 0
    except RagError as error:
        print(json.dumps({"error": error.code, "message": error.message}), file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"error": "configuration_or_storage_error",
                          "message": type(error).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

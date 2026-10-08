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
    """설정 경로와 각 하위 명령의 인자를 정의한 파서를 만든다. 작업은 실행하지 않는다."""
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
    """'1,13,16-18' 형태를 중복 없는 PDF 페이지 집합으로 바꾼다.

    None은 전체 페이지를 뜻하며 잘못된 범위는 RagError, 숫자 변환 실패는 ValueError를 낸다.
    선택한 번호가 실제 PDF 범위에 들어가는지는 파서에서 확인한다.
    """
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
    """설정을 읽고 요청된 명령을 실행해 JSON으로 출력할 결과 사전을 반환한다.

    외부 호출 여부는 명령과 캐시에 따라 달라지며 예외는 main에서 처리한다.
    """
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
    """CLI 결과를 stdout, 처리 가능한 오류를 stderr에 JSON으로 쓰고 종료 코드를 반환한다.

    정상 결과는 0, RagError는 1, 설정·저장 관련 일부 예외는 2다.
    argparse 오류는 SystemExit로 종료되며 그 밖의 미처리 예외는 그대로 전달된다.
    """
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

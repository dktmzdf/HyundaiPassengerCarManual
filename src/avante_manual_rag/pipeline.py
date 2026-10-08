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
    """원본을 등록·파싱하고 문서/페이지/요약을 새 파싱 세대로 저장·활성화한다.

    선택 범위 밖의 상태도 보존하며 검토 파일이 없으면 미검토 추출만 만든다.
    API 키나 모델 호출은 필요하지 않고 저장 결과 검증 후 활성 포인터를 교체한다.
    반환 사전에는 세대 ID, 문서 ID, 처리 ID와 처리 현황이 들어 있다.
    """
    document, path = register(settings)
    review = (
        read_json(settings.review_file)
        if settings.review_file and settings.review_file.is_file()
        else None
    )
    # 페이지를 가져옴
    pages, processing = parse_manual(path, document, selected, review)
    store = GenerationStore(settings.data_root)
    generation, directory = store.begin("parsed")
    write_json(contained(directory, "document.json"), to_dict(document))
    # 페이지 저장
    write_json(contained(directory, "pages.json"), [to_dict(p) for p in pages])
    summary = {"processing_id": processing, "coverage": coverage(pages)}
    write_json(contained(directory, "summary.json"), summary)
    store.publish("parsed", generation, ["document.json", "pages.json", "summary.json"])
    return {"generation": generation, "document_id": document.document_id, **summary}


def index(settings: Settings, adapter: OpenAIAdapter) -> dict:
    """활성 파싱 결과에서 적용 가능한 청크를 만들고 새 FAISS 세대를 활성화한다.

    임베딩 캐시에 없는 본문은 adapter를 통해 외부 API로 전송될 수 있다.
    반환 값은 생성한 세대·청크 수·누적 usage이며 처리나 색인 실패는 호출자에게 전달한다.
    """
    _, directory = GenerationStore(settings.data_root).active("parsed")
    document = Document(**read_json(contained(directory, "document.json")))
    pages = [page_from_dict(p) for p in read_json(contained(directory, "pages.json"))]
    summary = read_json(contained(directory, "summary.json"))
    chunks = make_chunks(document, pages, settings.profile, summary["processing_id"])
    generation = create_index(
        settings, chunks, summary["processing_id"], summary["coverage"], adapter
    )
    return {"generation": generation, "chunks": len(chunks), "usage": adapter.usage}


def ask(settings: Settings, question: str, adapter: OpenAIAdapter) -> dict:
    """질문을 검색한 뒤 근거 기반 답변을 생성하고 답변 사전과 usage를 반환한다.

    현재는 검색이 먼저 실행되므로 생성 모델 설정 누락이나 차량 충돌 확인 전에
    질문 임베딩 API가 호출될 수 있다. 검색·생성·인용 실패는 호출자에게 전달한다.
    """
    results, stats = search(settings, question, adapter)
    result = answer(question, results, stats, adapter)
    return {"answer": to_dict(result), "usage": adapter.usage}

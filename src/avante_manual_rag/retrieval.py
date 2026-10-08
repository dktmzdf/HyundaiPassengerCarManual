"""Profile-specific, self-generated FAISS files paired with JSON evidence metadata."""

from pathlib import Path

import faiss
import numpy as np

from .config import Settings
from .chunking import CHUNKER_VERSION
from .contracts import Chunk, IndexBuild, SearchResult, chunk_from_dict, to_dict
from .errors import RagError, require
from .openai_adapter import OpenAIAdapter, validate_vectors
from .storage import GenerationStore, contained, read_json, write_json


def normalized(vectors: np.ndarray) -> np.ndarray:
    """각 벡터를 L2 정규화해 FAISS용 연속 float32 행렬로 반환한다.

    호출자는 차원·유한값·영벡터 여부를 먼저 검증해야 한다. 정규화한 벡터의 내적을
    cosine 유사도로 사용할 수 있지만 정답 확률이 되는 것은 아니다.
    """
    norm = np.linalg.norm(vectors.astype(np.float64), axis=1, keepdims=True)
    return np.ascontiguousarray(vectors / norm, dtype=np.float32)


def create_index(settings: Settings, chunks: list[Chunk], processing_id: str,
                 coverage: dict, adapter: OpenAIAdapter) -> str:
    """프로필·적용 범위를 사전 필터링해 임베딩하고 FAISS/JSON 세대 ID를 반환한다.

    검토 여부는 청크를 만든 단계에서 보장해야 한다. 적용 청크가 없거나 ID가 중복이면
    거부하고, 새 파일의 형식·개수를 검증한 뒤에만 활성 포인터를 교체한다.
    실패한 새 디렉터리나 먼저 생성된 캐시는 남을 수 있지만 원본 PDF는 수정하지 않는다.
    """
    selected = [c for c in chunks if c.profile == settings.profile
                and c.applicability in ("common", settings.profile.transmission)]
    require(bool(selected), "No reviewed applicable chunks; complete local page review first")
    require(len({c.chunk_id for c in selected}) == len(selected), "Duplicate chunks")
    matrix = adapter.embeddings([c.text for c in selected], contained(settings.data_root, "cache"))
    store = GenerationStore(settings.data_root)
    generation, directory = store.begin("indexes")
    index = faiss.IndexFlatIP(settings.dimensions)
    index.add(normalized(matrix))
    faiss.write_index(index, str(contained(directory, "vectors.faiss")))
    build = IndexBuild(generation, processing_id, settings.profile,
                       settings.embedding_contract(), len(selected))
    write_json(contained(directory, "metadata.json"), {
        "build": to_dict(build), "chunker_version": CHUNKER_VERSION,
        "chunks": [to_dict(c) for c in selected],
        "coverage": coverage, "usage": adapter.usage,
    })
    # Validate every file before publishing the active pointer.
    _load(directory, settings)
    store.publish("indexes", generation, ["vectors.faiss", "metadata.json"])
    return generation


def _load(directory: Path, settings: Settings) -> tuple:
    """신뢰 가능한 로컬 세대에서 FAISS, 청크 목록, 메타데이터를 읽어 반환한다.

    청크 버전·임베딩·프로필·벡터 차원/개수의 일치를 검사한다. 생성 직후 검증 또는
    GenerationStore의 무결성 검사 뒤에 호출해야 하며 임의 외부 FAISS 파일에 쓰면 안 된다.
    """
    metadata = read_json(contained(directory, "metadata.json"))
    build = metadata["build"]
    require(metadata["chunker_version"] == CHUNKER_VERSION, "Chunk settings changed; rebuild index")
    require(build["embedding"] == settings.embedding_contract(), "Embedding settings mismatch")
    require(build["profile"] == to_dict(settings.profile), "Index profile mismatch")
    chunks = [chunk_from_dict(data) for data in metadata["chunks"]]
    require(all(c.profile == settings.profile and c.applicability in ("common", "dct")
                for c in chunks), "Index contains incompatible evidence")
    require(len({c.chunk_id for c in chunks}) == len(chunks), "Duplicate index chunks")
    index = faiss.read_index(str(contained(directory, "vectors.faiss")))
    require(isinstance(index, faiss.IndexFlatIP), "Unexpected index type")
    require(index.d == settings.dimensions, "Index dimension mismatch")
    require(index.ntotal == len(chunks) == build["count"], "Index row count mismatch")
    return index, chunks, metadata


def search(settings: Settings, question: str, adapter: OpenAIAdapter) -> tuple[list, dict]:
    """활성 색인과 파싱 설정을 검증하고 질문에 가까운 근거 및 처리 현황을 반환한다.

    새로운 질문은 임베딩 API를 쓸 수 있지만 생성 모델은 호출하지 않는다.
    FAISS의 -1/범위 밖 결과와 최소 점수 미만을 제외한다. 설정 오류는 그대로 전달하고
    저장·질문 임베딩 등 일부 실패는 retrieval_error로 변환한다.
    """
    require(bool(question.strip()), "Empty question")
    try:
        _, directory = GenerationStore(settings.data_root).active("indexes")
        index, chunks, metadata = _load(directory, settings)
        pointer = contained(settings.data_root, "parsed/active.json")
        if pointer.is_file():
            _, parsed = GenerationStore(settings.data_root).active("parsed")
            processing = read_json(contained(parsed, "summary.json"))["processing_id"]
            require(processing == metadata["build"]["processing_id"],
                    "Parsed generation changed; rebuild the index or restore matching generations")
        query = adapter.embeddings([question], contained(settings.data_root, "cache"))
        scores, ids = index.search(normalized(query), settings.top_k)
        results = [SearchResult(chunks[int(i)], float(score))
                   for i, score in zip(ids[0], scores[0])
                   if 0 <= i < len(chunks) and score >= settings.min_score]
        return results, metadata["coverage"]
    except RagError as error:
        if error.code == "configuration_error":
            raise
        raise RagError("retrieval_error", error.message) from None
    except (RuntimeError, ValueError, KeyError, OSError) as error:
        raise RagError("retrieval_error", "Cannot load or query local index") from error

"""Versioned, validated evidence contracts independent of PDF and model providers."""

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import math
import re
from typing import Any

from .errors import require


def fingerprint(value: Any) -> str:
    """JSON 표현을 정규화해 같은 데이터에서 같은 SHA-256 식별자를 만든다.

    value는 JSON으로 표현 가능해야 하며 NaN·무한대는 허용하지 않는다.
    설정·청크·캐시의 변경 감지에 쓰며 원본 파일의 바이트 해시와는 구분한다.
    """
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def text(value: Any, name: str) -> None:
    """name 필드가 공백뿐인 문자열이 아닌지 검사하고 실패하면 RagError를 낸다."""
    require(isinstance(value, str) and bool(value.strip()), f"Invalid {name}")


def positive(value: Any, name: str) -> None:
    """name 필드가 양의 정수인지 검사한다. 정수처럼 취급되는 bool도 거부한다."""
    require(type(value) is int and value > 0, f"Invalid {name}")


def strings(values: Any, name: str) -> None:
    """문자열 목록과 각 항목의 내용을 검증한다. 빈 목록 자체는 허용한다."""
    require(isinstance(values, list), f"Invalid {name}")
    for value in values:
        text(value, name)


@dataclass(frozen=True)
class VehicleProfile:
    project_code: str
    model_year: int
    transmission: str

    def __post_init__(self) -> None:
        """프로젝트 코드·연식 범위·변속기 종류를 검증하고 잘못된 사양을 거부한다."""
        text(self.project_code, "project_code")
        require(type(self.model_year) is int and 1900 < self.model_year < 2200, "Invalid year")
        require(self.transmission in ("dct", "manual"), "Invalid transmission")


@dataclass(frozen=True)
class Document:
    document_id: str
    filename: str
    title: str
    project_code: str
    model_year: int
    language: str
    size_bytes: int
    source_url: str
    source_status: str = "unverified"

    def __post_init__(self) -> None:
        """문서 해시·파일명·크기·차량·출처 상태의 기본 형식을 검증한다.

        실제 파일의 해시 일치 여부나 출처 URL 접근 여부는 여기서 확인하지 않는다.
        """
        require(bool(re.fullmatch(r"[0-9a-f]{64}", self.document_id)), "Invalid document hash")
        for name in ("filename", "title", "project_code", "language"):
            text(getattr(self, name), name)
        require("/" not in self.filename and "\\" not in self.filename, "Invalid filename")
        require(self.filename not in (".", ".."), "Invalid filename")
        positive(self.size_bytes, "size_bytes")
        VehicleProfile(self.project_code, self.model_year, "dct")
        require(self.source_status in ("unverified", "verified", "unavailable"), "Invalid source")
        require(isinstance(self.source_url, str), "Invalid source URL")


@dataclass
class Block:
    block_id: str
    pdf_page: int
    bbox: list[float]
    kind: str
    text: str
    section: str
    applicability: str = "unknown"
    reviewed: bool = False
    conditions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    related_ids: list[str] = field(default_factory=list)
    table: list[list[str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """좌표·페이지·본문·적용 범위와 표/경고 필드의 자료형을 검증한다.

        reviewed 값은 입력된 검토 기록이며 이 함수가 원문 대조를 수행하지는 않는다.
        """
        text(self.block_id, "block_id")
        positive(self.pdf_page, "pdf_page")
        require(len(self.bbox) == 4, "Invalid bounding box")
        require(all(type(n) in (int, float) and math.isfinite(n) for n in self.bbox), "Invalid box")
        valid = 0 <= self.bbox[0] < self.bbox[2] and 0 <= self.bbox[1] < self.bbox[3]
        require(valid, "Invalid box")
        require(self.kind in ("text", "table", "warning", "footnote"), "Invalid block kind")
        text(self.text, "block text")
        require(isinstance(self.section, str), "Invalid section")
        require(self.applicability in ("common", "dct", "manual", "unknown"), "Invalid scope")
        require(type(self.reviewed) is bool, "Invalid review status")
        for name in ("conditions", "warnings", "related_ids"):
            strings(getattr(self, name), name)
        require(isinstance(self.table, list), "Invalid table")
        for row in self.table:
            require(isinstance(row, list) and all(isinstance(c, str) for c in row), "Invalid row")


@dataclass
class Page:
    pdf_page: int
    printed_page: str | None
    status: str
    raw_text: str
    blocks: list[Block] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """페이지 상태와 하위 블록의 PDF 페이지 일치를 검사한다.

        인쇄 번호가 불명확하면 None을 허용하며 실제 PDF의 총 페이지 수는 확인하지 않는다.
        """
        positive(self.pdf_page, "pdf_page")
        require(self.printed_page is None or isinstance(self.printed_page, str), "Invalid label")
        require(self.status in (
            "success", "needs_review", "needs_ocr", "blank", "failed", "not_processed"
        ), "Invalid page status")
        require(isinstance(self.raw_text, str), "Invalid page text")
        require(all(isinstance(b, Block) and b.pdf_page == self.pdf_page for b in self.blocks),
                "Invalid page blocks")
        strings(self.issues, "issues")


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    title: str
    profile: VehicleProfile
    pages: list[int]
    printed_pages: list[str]
    block_ids: list[str]
    section: str
    text: str
    applicability: str
    conditions: list[str]
    warnings: list[str]
    processing_id: str

    def __post_init__(self) -> None:
        """검색용 본문·프로필·원본 페이지·블록 참조의 기본 계약을 검증한다.

        현재는 PDF 페이지와 인쇄 번호 목록의 항목별 대응까지 검증하지 않는다.
        """
        for name in ("chunk_id", "document_id", "title", "text", "processing_id"):
            text(getattr(self, name), name)
        require(isinstance(self.profile, VehicleProfile), "Invalid chunk profile")
        require(isinstance(self.pages, list) and bool(self.pages), "Missing pages")
        for number in self.pages:
            positive(number, "page")
        for name in ("printed_pages", "block_ids", "conditions", "warnings"):
            strings(getattr(self, name), name)
        require(bool(self.block_ids), "Missing block references")
        require(self.applicability in ("common", "dct", "manual", "unknown"), "Invalid scope")


@dataclass
class IndexBuild:
    generation: str
    processing_id: str
    profile: VehicleProfile
    embedding: dict[str, Any]
    count: int

    def __post_init__(self) -> None:
        """색인 세대·프로필·임베딩 설정·벡터 개수의 기본 형식을 검사한다.

        실제 FAISS 파일과 JSON 항목 수의 일치 여부는 검색 어댑터에서 확인한다.
        """
        text(self.generation, "generation")
        text(self.processing_id, "processing_id")
        require(isinstance(self.profile, VehicleProfile), "Invalid index profile")
        require(type(self.count) is int and self.count >= 0, "Invalid vector count")
        require(isinstance(self.embedding, dict), "Invalid embedding settings")
        for name in ("provider", "model", "preprocessing"):
            text(self.embedding.get(name), name)
        positive(self.embedding.get("dimensions"), "dimensions")


@dataclass
class SearchResult:
    chunk: Chunk
    score: float

    def __post_init__(self) -> None:
        """결과가 Chunk를 참조하고 검색 점수가 유한한지 검사한다. 점수는 확률이 아니다."""
        require(isinstance(self.chunk, Chunk) and math.isfinite(self.score), "Invalid result")


@dataclass
class Answer:
    status: str
    message: str
    claims: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """답변 상태와 주장·인용·경고·처리 현황 필드의 기본 형식을 검사한다.

        주장별 참조와 발췌 검사는 answering에서 수행하며 여기서는 의미를 검증하지 않는다.
        """
        require(self.status in (
            "answered", "insufficient_evidence", "needs_clarification", "conflicting_evidence"
        ), "Invalid answer status")
        require(isinstance(self.message, str), "Invalid answer message")
        require(isinstance(self.claims, list) and all(isinstance(c, dict) for c in self.claims),
                "Invalid answer claims")
        require(isinstance(self.citations, list) and
                all(isinstance(c, dict) for c in self.citations), "Invalid citations")
        require(isinstance(self.coverage, dict), "Invalid coverage")
        strings(self.warnings, "answer warnings")


def page_from_dict(data: dict[str, Any]) -> Page:
    """저장된 페이지 사전을 중첩 Block까지 포함한 Page로 복원하고 생성 시 검증한다."""
    return Page(**{**data, "blocks": [Block(**b) for b in data.get("blocks", [])]})


def chunk_from_dict(data: dict[str, Any]) -> Chunk:
    """저장된 청크 사전의 프로필을 VehicleProfile로 복원해 Chunk 계약을 검증한다."""
    return Chunk(**{**data, "profile": VehicleProfile(**data["profile"])})


def to_dict(value: Any) -> dict[str, Any]:
    """데이터클래스와 중첩 데이터를 저장·출력용 사전으로 변환한다. 별도 검증은 하지 않는다."""
    return asdict(value)

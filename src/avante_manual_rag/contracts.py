"""Versioned, validated evidence contracts independent of PDF and model providers."""

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import math
import re
from typing import Any

from .errors import require


def fingerprint(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def text(value: Any, name: str) -> None:
    require(isinstance(value, str) and bool(value.strip()), f"Invalid {name}")


def positive(value: Any, name: str) -> None:
    require(type(value) is int and value > 0, f"Invalid {name}")


def strings(values: Any, name: str) -> None:
    require(isinstance(values, list), f"Invalid {name}")
    for value in values:
        text(value, name)


@dataclass(frozen=True)
class VehicleProfile:
    project_code: str
    model_year: int
    transmission: str

    def __post_init__(self) -> None:
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
    return Page(**{**data, "blocks": [Block(**b) for b in data.get("blocks", [])]})


def chunk_from_dict(data: dict[str, Any]) -> Chunk:
    return Chunk(**{**data, "profile": VehicleProfile(**data["profile"])})


def to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)

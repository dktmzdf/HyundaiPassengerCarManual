"""Register immutable originals using the locally maintained CSV manifest."""

import csv
from pathlib import Path

from .config import Settings
from .contracts import Document
from .errors import RagError, require
from .storage import contained, file_hash


def register(settings: Settings) -> tuple[Document, Path]:
    """manifest의 단일 항목을 원본과 대조하고 문서 메타데이터와 PDF 경로를 반환한다.

    차량·연식·크기·SHA-256 불일치를 거부하며 원본 파일에는 쓰지 않는다.
    파일이 없으면 registration_error를 내고 출처는 접근 검증 없이 unverified로 둔다.
    """
    with settings.manifest.open(encoding="utf-8-sig", newline="") as stream:
        rows = [r for r in csv.DictReader(stream) if r["filename"] == settings.filename]
    require(len(rows) == 1, "Manifest must contain exactly one matching document")
    row = rows[0]
    require(row["project_code"] == settings.profile.project_code, "Wrong document vehicle")
    require(int(row["model_year"]) == settings.profile.model_year, "Wrong document year")
    path = contained(settings.raw_root, row["filename"])
    if not path.is_file():
        raise RagError("registration_error", "Original manual is missing")
    digest = file_hash(path)
    require(digest == row["sha256"], "Original manual hash mismatch")
    require(path.stat().st_size == int(row["size_bytes"]), "Original size mismatch")
    document = Document(
        digest, row["filename"], f'{row["model"]} {row["model_year"]}',
        row["project_code"], int(row["model_year"]), row["language"],
        path.stat().st_size, row["source_url"], "unverified",
    )
    return document, path

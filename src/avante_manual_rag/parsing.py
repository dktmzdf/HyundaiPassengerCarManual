"""Conservative PDF extraction with explicit hash-bound human review regions."""

from collections import Counter
from pathlib import Path
import re
from typing import Any

import pdfplumber

from .contracts import Block, Document, Page, fingerprint
from .errors import require

PARSER_VERSION = "pdfplumber-0.11.10-regions-v1"


def printed_number(page: Any) -> str | None:
    """PDF 하단 7%에서 단일 '장-쪽' 표기를 찾고, 없거나 서로 다르면 None을 반환한다.

    반환 값은 문서에 인쇄된 번호이며 파일 내 페이지 순서와는 별도로 관리한다.
    """
    footer = page.crop((0, page.height * .93, page.width, page.height)).extract_text() or ""
    labels = re.findall(r"(?<!\d)\d{1,2}-\d{1,3}(?!\d)", footer)
    return labels[0] if len(set(labels)) == 1 else None


def extract_page(page: Any, number: int) -> Page:
    """pdfplumber 페이지에서 원문·좌표·표·표 밖 본문을 공통 Page로 추출한다.

    number는 1부터 시작하는 PDF 페이지 번호다. 빈 추출은 needs_ocr로 두며,
    텍스트가 있어도 검토 전 블록의 적용 범위는 unknown, 상태는 needs_review다.
    OCR·그림 해석·다단 읽기 순서 확정은 하지 않고 추출 예외는 호출자에게 전달한다.
    """
    raw = page.extract_text(layout=False) or ""
    if not raw.strip():
        return Page(number, None, "needs_ocr", raw, issues=["empty_extraction_unreviewed"])
    blocks = []
    tables = page.find_tables()
    for index, table in enumerate(tables):
        rows = [[c or "" for c in row] for row in table.extract()]
        body = "\n".join(" | ".join(row) for row in rows)
        if body.strip():
            blocks.append(Block(f"p{number}-table{index}", number, list(table.bbox),
                                "table", body, "", table=rows))
    def outside_tables(obj: dict) -> bool:
        """문자 등 객체의 중심점이 표 밖에 있을 때만 본문 추출에 남겨 중복을 줄인다."""
        x, y = (obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2
        return not any(t.bbox[0] <= x <= t.bbox[2] and t.bbox[1] <= y <= t.bbox[3]
                       for t in tables)
    body = page.filter(outside_tables).extract_text() or ""
    if body.strip():
        blocks.append(Block(f"p{number}-text", number, [0, 0, page.width, page.height],
                            "text", body, ""))
    return Page(number, printed_number(page), "needs_review", raw, blocks,
                ["layout_scope_and_visual_review_required"])


def apply_review(page: Any, result: Page, review: dict) -> Page:
    """기록된 검토 영역·보정 본문·조건·경고를 추출 결과에 적용한 새 Page를 반환한다.

    호출자는 검토 파일의 원본 해시 일치를 먼저 확인해야 한다. 영역 추출이 비거나
    검토 사유가 없으면 거부하며 corrected_text 자체의 의미를 자동 대조하지 않는다.
    success는 지정한 영역의 검토 상태이며 페이지 전체 검토 완료를 뜻하지 않는다.
    """
    require(isinstance(review.get("reason"), str) and bool(review["reason"].strip()),
            "A review requires a recorded reason")
    if review.get("blank"):
        require(not result.raw_text.strip(), "Cannot mark extracted text as blank")
        return Page(result.pdf_page, review.get("printed_page"), "blank", "")
    blocks = []
    for region in review["regions"]:
        bbox = region["bbox"]
        extracted = page.crop(tuple(bbox)).extract_text() or ""
        require(bool(extracted.strip()), "Reviewed region has no extracted text")
        # Corrections are local, tied to the original digest and explicit visual review.
        body = region.get("corrected_text", extracted)
        blocks.append(Block(
            region["id"], result.pdf_page, bbox, region["kind"], body, region["section"],
            region["applicability"], True, region.get("conditions", []),
            region.get("warnings", []), region.get("related_ids", []), region.get("table", []),
        ))
    return Page(result.pdf_page, review.get("printed_page", result.printed_page),
                "success", result.raw_text, blocks, review.get("issues", []))


def parse_manual(path: Path, document: Document, selected: set[int] | None = None,
                 review: dict | None = None) -> tuple[list[Page], str]:
    """원본 PDF의 전체 페이지 상태 목록과 처리 설정의 결정적 식별자를 반환한다.

    selected가 None이면 전부 추출하고, 선택 밖 페이지는 not_processed로 남긴다.
    검토 데이터는 문서 해시에 묶으며 페이지 추출 실패는 failed로 기록해 다음 페이지를
    처리한다. 파일 열기·선택 범위·검토 적용 오류는 숨기지 않으며 원본에는 쓰지 않는다.
    """
    review = review or {"document_id": document.document_id, "pages": {}}
    require(review["document_id"] == document.document_id, "Review hash mismatch")
    processing = fingerprint({"parser": PARSER_VERSION, "document": document.document_id,
                              "review": review, "selected": sorted(selected) if selected else None})
    results = []
    with pdfplumber.open(path) as pdf:
        if selected is not None:
            require(bool(selected) and min(selected) > 0 and max(selected) <= len(pdf.pages),
                    "Page selection outside document")
        for number, page in enumerate(pdf.pages, 1):
            if selected is not None and number not in selected:
                results.append(Page(number, None, "not_processed", ""))
                continue
            try:
                result = extract_page(page, number)
            except Exception:
                result = Page(number, None, "failed", "", issues=["page_extraction_failed"])
            if str(number) in review["pages"] and result.status != "failed":
                result = apply_review(page, result, review["pages"][str(number)])
            results.append(result)
            page.close()
    return results, processing


def coverage(pages: list[Page]) -> dict:
    """페이지 상태별 개수, 미검토/부분 검토 번호, 문제 목록을 요약해 반환한다.

    success와 blank는 미검토 목록에서 제외한다. 부분 검토는 success 중 issues가 있는
    페이지로 집계하므로 전체 문서의 의미적 검토율이나 답변 정확도를 나타내지는 않는다.
    """
    return {"total_pages": len(pages), "statuses": dict(Counter(p.status for p in pages)),
            "unreviewed_pages": [p.pdf_page for p in pages if p.status not in ("success", "blank")],
            "partially_reviewed_pages": [p.pdf_page for p in pages
                                         if p.status == "success" and p.issues],
            "issues": {str(p.pdf_page): p.issues for p in pages if p.issues}}

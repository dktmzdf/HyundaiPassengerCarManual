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
    footer = page.crop((0, page.height * .93, page.width, page.height)).extract_text() or ""
    labels = re.findall(r"(?<!\d)\d{1,2}-\d{1,3}(?!\d)", footer)
    return labels[0] if len(set(labels)) == 1 else None


def extract_page(page: Any, number: int) -> Page:
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
    return {"total_pages": len(pages), "statuses": dict(Counter(p.status for p in pages)),
            "unreviewed_pages": [p.pdf_page for p in pages if p.status not in ("success", "blank")],
            "partially_reviewed_pages": [p.pdf_page for p in pages
                                         if p.status == "success" and p.issues],
            "issues": {str(p.pdf_page): p.issues for p in pages if p.issues}}

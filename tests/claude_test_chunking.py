"""Code review reproductions for chunking; outside default discovery, so run by path."""

from avante_manual_rag.chunking import make_chunks
from avante_manual_rag.contracts import Block, Document, Page, VehicleProfile

PROFILE = VehicleProfile("CN7N", 2025, "dct")
DOCUMENT = Document("a" * 64, "manual.pdf", "Synthetic manual", "CN7N", 2025, "ko", 1, "")


def block(identifier: str, page: int, text: str, scope: str = "dct",
          related: list[str] | None = None) -> Block:
    return Block(identifier, page, [0, 0, 10, 10], "table", text, "Synthetic", scope, True,
                 related_ids=related or [])


def test_printed_labels_stay_attached_to_their_pdf_pages():
    """manual-ingestion spec.md:30-36 keeps each printed label traceable to its PDF page."""
    table = block("tire", 13, "타이어 공기압 표", related=["note"])
    note = block("note", 16, "각주: 적재 시 기준")
    pages = [Page(13, None, "success", "raw", [table]),
             Page(16, "1-10", "success", "raw", [note])]
    linked = next(c for c in make_chunks(DOCUMENT, pages, PROFILE, "p") if c.pages == [13, 16])
    assert dict(zip(linked.pages, linked.printed_pages)).get(16) == "1-10"


def test_manual_only_link_is_left_out_without_failing_index():
    """design.md:125 links a common header to DCT rows and leaves manual-only rows out."""
    header = block("header", 16, "오일 표 제목", "common", related=["dct", "manual"])
    dct = block("dct", 16, "DCT 오일 3.3 L")
    manual = block("manual", 16, "수동 오일 1.9 L", "manual")
    page = Page(16, "1-10", "success", "raw", [header, dct, manual])
    chunks = make_chunks(DOCUMENT, [page], PROFILE, "p")
    assert any({"header", "dct"} <= set(c.block_ids) for c in chunks)
    assert all("수동 오일" not in c.text for c in chunks)

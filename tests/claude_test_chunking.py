"""Code review reproductions for chunking; outside default discovery, so run by path."""

from avante_manual_rag.chunking import make_chunks
from avante_manual_rag.contracts import Block, Document, Page, VehicleProfile

PROFILE = VehicleProfile("CN7N", 2025, "dct")
DOCUMENT = Document("a" * 64, "manual.pdf", "Synthetic manual", "CN7N", 2025, "ko", 1, "")


def block(identifier: str, page: int, text: str, scope: str = "dct",
          related: list[str] | None = None) -> Block:
    """페이지·적용 범위·연결을 지정한 검토 완료 합성 블록을 만들어 청크 재현에 사용한다."""
    return Block(identifier, page, [0, 0, 10, 10], "table", text, "Synthetic", scope, True,
                 related_ids=related or [])


def test_printed_labels_stay_attached_to_their_pdf_pages():
    """인쇄 번호가 없는 페이지와 섞여도 인쇄 번호의 PDF 페이지 대응이 유지돼야 함을 검사한다."""
    table = block("tire", 13, "타이어 공기압 표", related=["note"])
    note = block("note", 16, "각주: 적재 시 기준")
    pages = [Page(13, None, "success", "raw", [table]),
             Page(16, "1-10", "success", "raw", [note])]
    linked = next(c for c in make_chunks(DOCUMENT, pages, PROFILE, "p") if c.pages == [13, 16])
    assert dict(zip(linked.pages, linked.printed_pages)).get(16) == "1-10"


def test_manual_only_link_is_left_out_without_failing_index():
    """공통 표 제목의 수동 전용 링크가 DCT 청크 생성 전체를 실패시키지 않아야 함을 검사한다."""
    header = block("header", 16, "오일 표 제목", "common", related=["dct", "manual"])
    dct = block("dct", 16, "DCT 오일 3.3 L")
    manual = block("manual", 16, "수동 오일 1.9 L", "manual")
    page = Page(16, "1-10", "success", "raw", [header, dct, manual])
    chunks = make_chunks(DOCUMENT, [page], PROFILE, "p")
    assert any({"header", "dct"} <= set(c.block_ids) for c in chunks)
    assert all("수동 오일" not in c.text for c in chunks)

"""Preserve reviewed evidence units with all linked warnings and applicability."""

from .contracts import Chunk, Document, Page, VehicleProfile, fingerprint
from .errors import require

CHUNKER_VERSION = "reviewed-linked-v2"


def make_chunks(document: Document, pages: list[Page], profile: VehicleProfile,
                processing_id: str) -> list[Chunk]:
    """검토된 공통/해당 변속기 블록과 연결된 근거를 묶어 결정적 ID의 청크를 만든다.

    페이지·블록 참조·조건·경고를 함께 보존하고 같은 ID의 결과는 중복 제거한다.
    문서 프로필 불일치·중복 블록·없는 링크 및 수동 전용/미검토 연결은 현재 전체 작업을
    RagError로 중단한다. 인쇄 번호가 없는 페이지는 printed_pages 목록에서 빠진다.
    """
    require((document.project_code, document.model_year) ==
            (profile.project_code, profile.model_year), "Wrong document profile")
    blocks = {b.block_id: b for p in pages for b in p.blocks}
    require(len(blocks) == sum(len(p.blocks) for p in pages), "Duplicate block IDs")
    labels = {p.pdf_page: p.printed_page for p in pages}
    chunks = []
    for block in blocks.values():
        if not block.reviewed or block.applicability not in ("common", profile.transmission):
            continue
        linked = [block]
        visited = {block.block_id}
        for current in linked:
            for reference in current.related_ids:
                require(reference in blocks, "Missing linked evidence")
                other = blocks[reference]
                require(other.reviewed and other.applicability in ("common", profile.transmission),
                        "Linked evidence has incompatible or unreviewed scope")
                if reference not in visited:
                    visited.add(reference)
                    linked.append(other)
        body = "\n\n".join(b.text for b in linked)
        conditions = list(dict.fromkeys(c for b in linked for c in b.conditions))
        warnings = list(dict.fromkeys(w for b in linked for w in b.warnings))
        body += "\n" + "\n".join(value for value in conditions + warnings if value not in body)
        numbers = sorted({b.pdf_page for b in linked})
        identifier = fingerprint([document.document_id, processing_id, CHUNKER_VERSION,
                                  sorted(visited), body])
        chunks.append(Chunk(identifier, document.document_id, document.title, profile, numbers,
                            [labels[n] for n in numbers if labels[n]], sorted(visited),
                            block.section, body.strip(), block.applicability,
                            conditions, warnings, processing_id))
    return list({c.chunk_id: c for c in chunks}.values())

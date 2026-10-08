from pathlib import Path
from unittest.mock import patch

import pytest

from avante_manual_rag.contracts import Block, Page, VehicleProfile
from avante_manual_rag.errors import RagError
from avante_manual_rag.storage import GenerationStore, contained, read_json, write_json


@pytest.mark.parametrize("year,transmission", [(True, "dct"), (2025, "auto"), (0, "dct")])
def test_profile_rejects_invalid_input(year, transmission):
    """bool 연식·지원하지 않는 변속기·범위 밖 연식이 차량 계약에서 거부되는지 확인한다."""
    with pytest.raises(RagError):
        VehicleProfile("CN7N", year, transmission)


def test_page_and_block_boundaries():
    """잘못된 페이지·좌표 및 필수 프로필 필드 누락이 생성 경계에서 거부되는지 확인한다."""
    with pytest.raises(RagError):
        Page(0, None, "success", "text")
    with pytest.raises(RagError):
        Block("id", 1, [10, 0, 0, 10], "text", "text", "section")
    with pytest.raises(TypeError):
        VehicleProfile(**{"project_code": "CN7N"})


def test_escape_rejected(tmp_path):
    """상위 상대 경로와 외부 절대 경로를 데이터 디렉터리 밖 대상으로 허용하지 않는지 검사한다."""
    with pytest.raises(RagError):
        contained(tmp_path, "../outside.json")
    with pytest.raises(RagError):
        contained(tmp_path, tmp_path.parent / "absolute.json")


def test_failed_generation_preserves_active_and_rollback(tmp_path):
    """포인터 교체 실패가 기존 활성 세대를 보존하고 이후 이전 세대 복귀가 되는지 검사한다."""
    store = GenerationStore(tmp_path)
    first, directory = store.begin("parsed")
    write_json(directory / "data.json", {"value": 1})
    store.publish("parsed", first, ["data.json"])
    second, directory2 = store.begin("parsed")
    write_json(directory2 / "data.json", {"value": 2})
    with patch("avante_manual_rag.storage.os.replace", side_effect=OSError("interrupted")):
        with pytest.raises(OSError):
            store.publish("parsed", second, ["data.json"])
    assert store.active("parsed")[0] == first
    store.publish("parsed", second, ["data.json"])
    store.activate("parsed", first)
    assert store.active("parsed")[0] == first


def test_corrupted_generation_is_rejected(tmp_path):
    """공개한 세대의 JSON 내용을 바꾸면 저장된 해시로 손상이 감지되는지 확인한다."""
    store = GenerationStore(tmp_path)
    generation, directory = store.begin("indexes")
    write_json(directory / "metadata.json", {"value": 1})
    store.publish("indexes", generation, ["metadata.json"])
    write_json(directory / "metadata.json", {"value": 2})
    with pytest.raises(RagError):
        store.active("indexes")


def test_json_failure_does_not_replace_file(tmp_path):
    """NaN 직렬화 실패가 기존 정상 JSON 파일을 덮어쓰지 않는지 확인한다."""
    target = tmp_path / "file.json"
    write_json(target, {"value": 1})
    with pytest.raises(ValueError):
        write_json(target, {"value": float("nan")})
    assert read_json(target) == {"value": 1}

from pathlib import Path
from unittest.mock import patch

import pytest

from avante_manual_rag.contracts import Block, Page, VehicleProfile
from avante_manual_rag.errors import RagError
from avante_manual_rag.storage import GenerationStore, contained, read_json, write_json


@pytest.mark.parametrize("year,transmission", [(True, "dct"), (2025, "auto"), (0, "dct")])
def test_profile_rejects_invalid_input(year, transmission):
    with pytest.raises(RagError):
        VehicleProfile("CN7N", year, transmission)


def test_page_and_block_boundaries():
    with pytest.raises(RagError):
        Page(0, None, "success", "text")
    with pytest.raises(RagError):
        Block("id", 1, [10, 0, 0, 10], "text", "text", "section")
    with pytest.raises(TypeError):
        VehicleProfile(**{"project_code": "CN7N"})


def test_escape_rejected(tmp_path):
    with pytest.raises(RagError):
        contained(tmp_path, "../outside.json")
    with pytest.raises(RagError):
        contained(tmp_path, tmp_path.parent / "absolute.json")


def test_failed_generation_preserves_active_and_rollback(tmp_path):
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
    store = GenerationStore(tmp_path)
    generation, directory = store.begin("indexes")
    write_json(directory / "metadata.json", {"value": 1})
    store.publish("indexes", generation, ["metadata.json"])
    write_json(directory / "metadata.json", {"value": 2})
    with pytest.raises(RagError):
        store.active("indexes")


def test_json_failure_does_not_replace_file(tmp_path):
    target = tmp_path / "file.json"
    write_json(target, {"value": 1})
    with pytest.raises(ValueError):
        write_json(target, {"value": float("nan")})
    assert read_json(target) == {"value": 1}

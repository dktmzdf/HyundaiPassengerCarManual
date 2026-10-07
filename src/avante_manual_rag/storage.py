"""Local immutable generations; a single atomic pointer selects a complete generation."""

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from uuid import uuid4

from .errors import RagError, require


def contained(root: Path, relative: str | Path) -> Path:
    base = root.resolve()
    child = (base / relative).resolve()
    require(child.is_relative_to(base) and child != base, "Path escapes data directory")
    return child


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        digest = sha256()
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RagError("storage_error", "Cannot read local JSON data") from error


def write_json(path: Path, value: Any) -> None:
    """Replace one file; callers must validate the target with contained first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".pending-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class GenerationStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def begin(self, kind: str) -> tuple[str, Path]:
        self._kind(kind)
        generation = uuid4().hex
        directory = contained(self.root, f"{kind}/{generation}")
        directory.mkdir(parents=True, exist_ok=False)
        return generation, directory

    def publish(self, kind: str, generation: str, names: list[str]) -> None:
        directory = self.directory(kind, generation)
        files = {}
        for name in names:
            path = contained(directory, name)
            files[name] = {"sha256": file_hash(path), "size": path.stat().st_size}
        write_json(contained(directory, "integrity.json"), files)
        self.activate(kind, generation)

    def directory(self, kind: str, generation: str) -> Path:
        self._kind(kind)
        require(bool(re.fullmatch(r"[0-9a-f]{32}", generation)), "Invalid generation")
        return contained(self.root, f"{kind}/{generation}")

    def validate(self, kind: str, generation: str) -> Path:
        directory = self.directory(kind, generation)
        files = read_json(contained(directory, "integrity.json"))
        require(isinstance(files, dict) and bool(files), "Missing integrity manifest")
        for name, expected in files.items():
            path = contained(directory, name)
            if not path.is_file() or path.stat().st_size != expected["size"]:
                raise RagError("storage_error", "Generation file size mismatch")
            if file_hash(path) != expected["sha256"]:
                raise RagError("storage_error", "Generation file hash mismatch")
        return directory

    def activate(self, kind: str, generation: str) -> None:
        self.validate(kind, generation)
        write_json(contained(self.root, f"{kind}/active.json"), {"generation": generation})

    def active(self, kind: str) -> tuple[str, Path]:
        self._kind(kind)
        pointer = read_json(contained(self.root, f"{kind}/active.json"))
        generation = pointer["generation"]
        return generation, self.validate(kind, generation)

    @staticmethod
    def _kind(kind: str) -> None:
        require(kind in ("parsed", "indexes", "reports"), "Invalid generation kind")

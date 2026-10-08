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
    """root 아래로 해석되는 실제 경로를 반환하고 상위 경로·링크를 통한 탈출을 거부한다.

    root 자체도 파일 대상에서 제외한다. 반환 후 경로가 바뀌는 동시 실행까지 보호하는
    파일 핸들 기반 검증은 아니므로 호출 시점의 경로 검사로 사용한다.
    """
    base = root.resolve()
    child = (base / relative).resolve()
    require(child.is_relative_to(base) and child != base, "Path escapes data directory")
    return child


def file_hash(path: Path) -> str:
    """파일을 1 MiB씩 읽어 원본 바이트의 SHA-256을 반환한다. 읽기 오류는 전달한다."""
    with path.open("rb") as stream:
        digest = sha256()
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    """UTF-8 JSON을 읽고 파싱한 값을 반환하며 접근·해석 실패는 storage_error로 바꾼다.

    반환 자료형과 도메인 필드는 별도 계약 검증이 필요하며 입력 경로도 호출자가 확인한다.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RagError("storage_error", "Cannot read local JSON data") from error


def write_json(path: Path, value: Any) -> None:
    """JSON을 같은 디렉터리의 임시 파일에 쓰고 fsync 후 대상 파일 하나를 교체한다.

    호출자가 contained로 경로를 검증해야 한다. 직렬화·쓰기·교체 오류는 전달하며 임시
    파일은 정리한다. 여러 파일의 일괄 갱신까지 원자적으로 보장하는 함수는 아니다.
    """
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
        """세대를 저장할 기준 경로만 정규화한다. 디렉터리 생성이나 파일 읽기는 하지 않는다."""
        self.root = root.resolve()

    def begin(self, kind: str) -> tuple[str, Path]:
        """허용된 종류 아래에 고유한 새 디렉터리를 만들고 세대 ID와 경로를 반환한다.

        아직 활성화하지 않으므로 생성 도중 실패해도 이전 활성 세대를 선택할 수 있다.
        """
        self._kind(kind)
        generation = uuid4().hex
        directory = contained(self.root, f"{kind}/{generation}")
        directory.mkdir(parents=True, exist_ok=False)
        return generation, directory

    def publish(self, kind: str, generation: str, names: list[str]) -> None:
        """완성된 파일의 크기·해시 목록을 기록하고 검증 후 해당 세대를 활성화한다.

        names는 세대 내부 상대 경로다. 해시 목록 작성과 포인터 교체는 별도 단계이며
        이미 공개된 세대 내용을 덮어쓰지 않는 정책은 호출자가 지켜야 한다.
        """
        directory = self.directory(kind, generation)
        files = {}
        for name in names:
            path = contained(directory, name)
            files[name] = {"sha256": file_hash(path), "size": path.stat().st_size}
        write_json(contained(directory, "integrity.json"), files)
        self.activate(kind, generation)

    def directory(self, kind: str, generation: str) -> Path:
        """종류와 32자리 세대 ID를 검증해 저장 경로를 반환한다. 존재 여부는 확인하지 않는다."""
        self._kind(kind)
        require(bool(re.fullmatch(r"[0-9a-f]{32}", generation)), "Invalid generation")
        return contained(self.root, f"{kind}/{generation}")

    def validate(self, kind: str, generation: str) -> Path:
        """세대의 무결성 목록과 실제 파일 크기·해시를 대조하고 검증된 경로를 반환한다.

        불일치는 storage_error로 거부한다. 해시는 손상 감지용이며 악성 파일의 진위나
        각 파일의 데이터 계약까지 증명하지는 않으므로 신뢰 가능한 로컬 세대만 읽는다.
        """
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
        """완성된 세대를 검증하고 active.json 하나를 교체해 새 세대 선택 또는 복귀를 한다.

        파싱과 색인 등 여러 종류의 포인터를 동시에 바꾸는 트랜잭션은 아니다.
        """
        self.validate(kind, generation)
        write_json(contained(self.root, f"{kind}/active.json"), {"generation": generation})

    def active(self, kind: str) -> tuple[str, Path]:
        """활성 포인터를 읽고 세대 파일을 검증해 ID와 경로를 반환한다. 누락은 오류다."""
        self._kind(kind)
        pointer = read_json(contained(self.root, f"{kind}/active.json"))
        generation = pointer["generation"]
        return generation, self.validate(kind, generation)

    @staticmethod
    def _kind(kind: str) -> None:
        """세대 종류를 parsed/indexes/reports로 제한하고 다른 이름은 RagError로 거부한다."""
        require(kind in ("parsed", "indexes", "reports"), "Invalid generation kind")

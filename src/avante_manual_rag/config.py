"""Configuration is local; API secrets are read only when a real request is needed."""

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib

from .contracts import VehicleProfile, positive, text
from .errors import require


@dataclass(frozen=True)
class Settings:
    data_root: Path
    raw_root: Path
    manifest: Path
    filename: str
    profile: VehicleProfile
    embedding_model: str
    dimensions: int
    chat_model: str
    timeout: float
    deadline: float
    top_k: int
    min_score: float
    context_tokens: int
    output_tokens: int
    token_encoding: str
    review_file: Path | None = None

    def __post_init__(self) -> None:
        """현재 지원 차량·임베딩 모델·경로 분리·실행 한도를 검증한다.

        생성 모델은 빈 문자열도 허용하며 실제 답변을 만들 때 누락 여부를 확인한다.
        """
        require(self.profile == VehicleProfile("CN7N", 2025, "dct"), "Unsupported vehicle")
        require(not self.data_root.is_relative_to(self.raw_root), "Output is inside raw data")
        require(not self.raw_root.is_relative_to(self.data_root), "Output contains raw data")
        for name in ("dimensions", "top_k", "context_tokens", "output_tokens"):
            positive(getattr(self, name), name)
        require(self.timeout > 0 and self.deadline >= self.timeout, "Invalid request limits")
        require(-1 <= self.min_score <= 1, "Invalid minimum score")
        text(self.embedding_model, "embedding model")
        require(isinstance(self.chat_model, str), "Invalid chat model")
        require(self.embedding_model == "text-embedding-3-small" and self.dimensions == 1536,
                "This baseline requires text-embedding-3-small/1536; rebuild for other models")
        require(self.context_tokens > self.output_tokens + 512, "Insufficient context budget")
        require(Path(self.filename).name == self.filename, "Invalid filename")

    def embedding_contract(self) -> dict:
        """색인·캐시 호환성 검사에 쓰는 제공자·모델·차원·전처리 설정을 반환한다."""
        return {"provider": "openai", "model": self.embedding_model,
                "dimensions": self.dimensions, "preprocessing": "nfc-v1"}


def load_settings(path: Path) -> Settings:
    """TOML과 같은 위치의 .env를 읽고 상대 경로를 설정 파일 기준으로 해석한다.

    환경변수의 생성 모델 설정이 우선하며 토크나이저 캐시 경로도 설정한다.
    파일 접근·TOML 해석·필수 키 누락 및 Settings 검증 오류는 호출자에게 전달한다.
    """
    load_local_env(path.resolve().parent / ".env")
    with path.open("rb") as stream:
        data = tomllib.load(stream)
    base = path.resolve().parent
    paths, model = data["paths"], data["models"]
    runtime = data["runtime"]
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str((base / "data/cache/tiktoken").resolve()))
    return Settings(
        data_root=(base / paths["data_root"]).resolve(),
        raw_root=(base / paths["raw_root"]).resolve(),
        manifest=(base / paths["manifest"]).resolve(), filename=paths["filename"],
        profile=VehicleProfile(**data["vehicle"]),
        embedding_model=model["embedding_model"], dimensions=model["embedding_dimensions"],
        chat_model=os.environ.get("OPENAI_CHAT_MODEL", model.get("chat_model", "")),
        timeout=runtime["timeout_seconds"], deadline=runtime["deadline_seconds"],
        top_k=runtime["top_k"], min_score=runtime["min_score"],
        context_tokens=runtime["context_tokens"], output_tokens=runtime["output_tokens"],
        token_encoding=model["token_encoding"],
        review_file=(base / paths["review_file"]).resolve() if paths.get("review_file") else None,
    )


def load_local_env(path: Path) -> None:
    """로컬 파일에서 API 키와 생성 모델만 읽고 기존 환경변수 값은 유지한다.

    파일이 없으면 건너뛰며 변수 치환·코드 실행·값 출력은 하지 않는다.
    따옴표 한 쌍만 제거하므로 인라인 주석은 값에 포함될 수 있다.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        name, separator, value = line.partition("=")
        name = name.strip()
        if separator and name in ("OPENAI_API_KEY", "OPENAI_CHAT_MODEL"):
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if value:
                os.environ.setdefault(name, value)

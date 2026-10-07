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
        return {"provider": "openai", "model": self.embedding_model,
                "dimensions": self.dimensions, "preprocessing": "nfc-v1"}


def load_settings(path: Path) -> Settings:
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
    """Read only two known keys; no interpolation, execution, or secret logging."""
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

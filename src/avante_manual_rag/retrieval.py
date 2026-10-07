"""Profile-specific, self-generated FAISS files paired with JSON evidence metadata."""

from pathlib import Path

import faiss
import numpy as np

from .config import Settings
from .chunking import CHUNKER_VERSION
from .contracts import Chunk, IndexBuild, SearchResult, chunk_from_dict, to_dict
from .errors import RagError, require
from .openai_adapter import OpenAIAdapter, validate_vectors
from .storage import GenerationStore, contained, read_json, write_json


def normalized(vectors: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vectors.astype(np.float64), axis=1, keepdims=True)
    return np.ascontiguousarray(vectors / norm, dtype=np.float32)


def create_index(settings: Settings, chunks: list[Chunk], processing_id: str,
                 coverage: dict, adapter: OpenAIAdapter) -> str:
    selected = [c for c in chunks if c.profile == settings.profile
                and c.applicability in ("common", settings.profile.transmission)]
    require(bool(selected), "No reviewed applicable chunks; complete local page review first")
    require(len({c.chunk_id for c in selected}) == len(selected), "Duplicate chunks")
    matrix = adapter.embeddings([c.text for c in selected], contained(settings.data_root, "cache"))
    store = GenerationStore(settings.data_root)
    generation, directory = store.begin("indexes")
    index = faiss.IndexFlatIP(settings.dimensions)
    index.add(normalized(matrix))
    faiss.write_index(index, str(contained(directory, "vectors.faiss")))
    build = IndexBuild(generation, processing_id, settings.profile,
                       settings.embedding_contract(), len(selected))
    write_json(contained(directory, "metadata.json"), {
        "build": to_dict(build), "chunker_version": CHUNKER_VERSION,
        "chunks": [to_dict(c) for c in selected],
        "coverage": coverage, "usage": adapter.usage,
    })
    # Validate every file before publishing the active pointer.
    _load(directory, settings)
    store.publish("indexes", generation, ["vectors.faiss", "metadata.json"])
    return generation


def _load(directory: Path, settings: Settings) -> tuple:
    metadata = read_json(contained(directory, "metadata.json"))
    build = metadata["build"]
    require(metadata["chunker_version"] == CHUNKER_VERSION, "Chunk settings changed; rebuild index")
    require(build["embedding"] == settings.embedding_contract(), "Embedding settings mismatch")
    require(build["profile"] == to_dict(settings.profile), "Index profile mismatch")
    chunks = [chunk_from_dict(data) for data in metadata["chunks"]]
    require(all(c.profile == settings.profile and c.applicability in ("common", "dct")
                for c in chunks), "Index contains incompatible evidence")
    require(len({c.chunk_id for c in chunks}) == len(chunks), "Duplicate index chunks")
    index = faiss.read_index(str(contained(directory, "vectors.faiss")))
    require(isinstance(index, faiss.IndexFlatIP), "Unexpected index type")
    require(index.d == settings.dimensions, "Index dimension mismatch")
    require(index.ntotal == len(chunks) == build["count"], "Index row count mismatch")
    return index, chunks, metadata


def search(settings: Settings, question: str, adapter: OpenAIAdapter) -> tuple[list, dict]:
    require(bool(question.strip()), "Empty question")
    try:
        _, directory = GenerationStore(settings.data_root).active("indexes")
        index, chunks, metadata = _load(directory, settings)
        pointer = contained(settings.data_root, "parsed/active.json")
        if pointer.is_file():
            _, parsed = GenerationStore(settings.data_root).active("parsed")
            processing = read_json(contained(parsed, "summary.json"))["processing_id"]
            require(processing == metadata["build"]["processing_id"],
                    "Parsed generation changed; rebuild the index or restore matching generations")
        query = adapter.embeddings([question], contained(settings.data_root, "cache"))
        scores, ids = index.search(normalized(query), settings.top_k)
        results = [SearchResult(chunks[int(i)], float(score))
                   for i, score in zip(ids[0], scores[0])
                   if 0 <= i < len(chunks) and score >= settings.min_score]
        return results, metadata["coverage"]
    except RagError as error:
        if error.code == "configuration_error":
            raise
        raise RagError("retrieval_error", error.message) from None
    except (RuntimeError, ValueError, KeyError, OSError) as error:
        raise RagError("retrieval_error", "Cannot load or query local index") from error

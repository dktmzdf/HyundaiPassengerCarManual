from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS

from avante_manual_rag.config import Settings
from avante_manual_rag.contracts import Chunk, VehicleProfile


def settings(tmp_path, **changes):
    base = Settings(tmp_path / "processed", tmp_path / "raw", tmp_path / "manifest.csv",
                    "manual.pdf", VehicleProfile("CN7N", 2025, "dct"),
                    "text-embedding-3-small", 1536, "gpt-5-mini", 1, 5, 5, -1, 16000, 2000,
                    "o200k_base")
    return replace(base, **changes)


def chunk(identifier="chunk", scope="dct", **changes):
    base = Chunk(identifier, "a" * 64, "Synthetic manual", VehicleProfile("CN7N", 2025, "dct"),
                 [1], ["1-1"], [identifier], "Synthetic", "기어오일 용량 3.3 ℓ", scope,
                 ["DCT 차량"], ["용량은 참고만 하고 게이지로 확인"], "processing")
    return replace(base, **changes)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.payload = '{"status":"insufficient_evidence","claims":[]}'
        self.embedding_error = None
        self.response_error = None
        self.status = "completed"
        self.output = []
        self.embeddings = NS(create=self.embed)
        self.responses = NS(create=self.respond)

    def embed(self, **kwargs):
        self.calls.append(kwargs)
        if self.embedding_error:
            raise self.embedding_error
        dims = kwargs["dimensions"]
        items = [NS(index=i, embedding=[float(i + 1)] + [0.] * (dims - 1))
                 for i, _ in enumerate(kwargs["input"])]
        return NS(data=list(reversed(items)), model=kwargs["model"], usage=NS(model_dump=lambda: {
            "prompt_tokens": 5, "total_tokens": 5}))

    def respond(self, **kwargs):
        self.calls.append(kwargs)
        if self.response_error:
            raise self.response_error
        return NS(output_text=self.payload, status=self.status, output=self.output,
                  model=kwargs["model"], usage=NS(model_dump=lambda: {"total_tokens": 10}))

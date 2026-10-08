from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS

from avante_manual_rag.config import Settings
from avante_manual_rag.contracts import Chunk, VehicleProfile


def settings(tmp_path, **changes):
    """임시 디렉터리를 쓰는 기본 Settings를 만들고 changes의 필드만 교체한다."""
    base = Settings(tmp_path / "processed", tmp_path / "raw", tmp_path / "manifest.csv",
                    "manual.pdf", VehicleProfile("CN7N", 2025, "dct"),
                    "text-embedding-3-small", 1536, "gpt-5-mini", 1, 5, 5, -1, 16000, 2000,
                    "o200k_base")
    return replace(base, **changes)


def chunk(identifier="chunk", scope="dct", **changes):
    """원본 PDF 없이 검색·인용 검사에 사용할 합성 청크를 만들고 필요한 필드를 바꾼다."""
    base = Chunk(identifier, "a" * 64, "Synthetic manual", VehicleProfile("CN7N", 2025, "dct"),
                 [1], ["1-1"], [identifier], "Synthetic", "기어오일 용량 3.3 ℓ", scope,
                 ["DCT 차량"], ["용량은 참고만 하고 게이지로 확인"], "processing")
    return replace(base, **changes)


class FakeClient:
    def __init__(self):
        """호출 기록과 주입 가능한 오류·응답을 준비한다. 실제 네트워크는 사용하지 않는다."""
        self.calls = []
        self.payload = '{"status":"insufficient_evidence","claims":[]}'
        self.embedding_error = None
        self.response_error = None
        self.status = "completed"
        self.output = []
        self.embeddings = NS(create=self.embed)
        self.responses = NS(create=self.respond)

    def embed(self, **kwargs):
        """요청을 기록하고 index 역순의 합성 벡터를 돌려줘 응답 순서 복원을 검사하게 한다.

        embedding_error가 설정돼 있으면 해당 예외를 내며 usage는 고정된 테스트 값이다.
        """
        self.calls.append(kwargs)
        if self.embedding_error:
            raise self.embedding_error
        dims = kwargs["dimensions"]
        items = [NS(index=i, embedding=[float(i + 1)] + [0.] * (dims - 1))
                 for i, _ in enumerate(kwargs["input"])]
        return NS(data=list(reversed(items)), model=kwargs["model"], usage=NS(model_dump=lambda: {
            "prompt_tokens": 5, "total_tokens": 5}))

    def respond(self, **kwargs):
        """기록된 payload·상태·출력으로 가짜 생성 응답을 반환하거나 주입된 예외를 낸다."""
        self.calls.append(kwargs)
        if self.response_error:
            raise self.response_error
        return NS(output_text=self.payload, status=self.status, output=self.output,
                  model=kwargs["model"], usage=NS(model_dump=lambda: {"total_tokens": 10}))

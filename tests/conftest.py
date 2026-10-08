"""Default tests forbid network access, including accidental SDK calls."""

import socket
from pathlib import Path
from uuid import uuid4
import pytest


def pytest_configure(config):
    """사용자가 basetemp를 지정하지 않았으면 프로젝트 tmp 아래 고유 테스트 경로를 쓴다."""
    if config.option.basetemp is None:
        root = Path(__file__).resolve().parents[1] / "tmp"
        root.mkdir(exist_ok=True)
        config.option.basetemp = str(root / f"pytest-{uuid4().hex}")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """각 테스트에서 소켓 연결을 막아 실제 API 호출이나 다운로드가 섞이지 않게 한다."""
    def forbidden(*args, **kwargs):
        """연결 시도를 받으면 AssertionError를 내서 뜻하지 않은 외부 접근을 드러낸다."""
        raise AssertionError("Network access is forbidden in default tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)

"""Public errors contain safe summaries, never provider payloads or credentials."""


class RagError(Exception):
    def __init__(self, code: str, message: str) -> None:
        """외부에 노출할 오류 코드와 설명을 담는다. 호출자가 비밀값을 제외해야 한다."""
        super().__init__(message)
        self.code = code
        self.message = message


def require(condition: bool, message: str) -> None:
    """조건이 거짓이면 configuration_error를 낸다. 참이면 추가 처리 없이 반환한다."""
    if not condition:
        raise RagError("configuration_error", message)

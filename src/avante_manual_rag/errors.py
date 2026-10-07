"""Public errors contain safe summaries, never provider payloads or credentials."""


class RagError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RagError("configuration_error", message)

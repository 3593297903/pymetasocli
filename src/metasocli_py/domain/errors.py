class AppError(Exception):
    def __init__(self, code: str, message: str, *, incomplete: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.incomplete = incomplete


def fail(code: str, message: str) -> None:
    raise AppError(code, message)

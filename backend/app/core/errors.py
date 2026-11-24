"""Application errors mapped to HTTP responses by the API layer."""


class AppError(Exception):
    def __init__(self, status_code: int, detail: str, code: str = "error"):
        self.status_code = status_code
        self.detail = detail
        self.code = code
        super().__init__(detail)

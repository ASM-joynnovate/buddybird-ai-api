from typing import Any


class CustomError(Exception):
    code: int = 400
    error_code: str = "COMMON__BAD_REQUEST"
    message: str = "잘못된 요청입니다."
    detail: dict[str, Any] | str | None = None

    def __init__(
        self,
        code: int | None = None,
        message: str | None = None,
        *,
        detail: dict[str, Any] | str | None = None,
    ) -> None:
        super().__init__(message or self.message)
        if code:
            self.code = code
        if message:
            self.message = message
        if detail:
            self.detail = detail


class ResourceNotFoundError(CustomError):
    code = 404
    error_code = "COMMON__RESOURCE_NOT_FOUND"
    message = "요청한 리소스를 찾을 수 없습니다."

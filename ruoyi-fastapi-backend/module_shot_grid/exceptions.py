from typing import Any


class ShotGridDomainException(Exception):
    """Shot Grid 领域异常，携带稳定错误键和真实 HTTP 状态。"""

    def __init__(
        self,
        *,
        http_status: int,
        error_key: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.error_key = error_key
        self.message = message
        self.details = details


def shot_grid_error(
    http_status: int,
    error_key: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> ShotGridDomainException:
    """创建统一的 Shot Grid 领域异常。"""

    return ShotGridDomainException(
        http_status=http_status,
        error_key=error_key,
        message=message,
        details=details,
    )

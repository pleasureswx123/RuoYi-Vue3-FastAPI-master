from typing import Any

from pydantic import Field, field_validator

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel


class ShotGridVersionSubmissionCreateModel(ShotGridApiModel):
    file_id: str = Field(min_length=36, max_length=36)
    idempotency_key: str = Field(min_length=1, max_length=100)
    changelog: str = Field(min_length=1, max_length=5000)
    ai_params: dict[str, Any] | None = None

    @field_validator('file_id', 'idempotency_key', 'changelog')
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ShotGridVersionSubmissionRetryModel(ShotGridApiModel):
    """重试无需新参数，保留原始提交快照。"""

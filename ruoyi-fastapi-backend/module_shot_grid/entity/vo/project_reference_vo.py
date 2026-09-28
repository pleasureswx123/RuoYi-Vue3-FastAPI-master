from uuid import UUID

from pydantic import Field, field_validator

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel


class ShotGridProjectReferenceInput(ShotGridApiModel):
    """项目共享资料；编辑通过 fields_set 区分省略与明确清空。"""

    reference_description: str | None = Field(default=None, max_length=10000)
    reference_file_ids: list[str] = Field(default_factory=list, max_length=5)

    @field_validator('reference_description')
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value else None

    @field_validator('reference_file_ids')
    @classmethod
    def normalize_file_ids(cls, value: list[str]) -> list[str]:
        normalized = [str(UUID(file_id)) for file_id in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError('项目资料文件不能重复')
        return normalized


class ShotGridProjectReferenceFileModel(ShotGridApiModel):
    file_id: str
    original_name: str
    content_type: str | None = None
    file_size: int = Field(ge=0)
    download_url: str

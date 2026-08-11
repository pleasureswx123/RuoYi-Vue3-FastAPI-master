from typing import Literal

from pydantic import Field, field_validator

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel, ShotGridPageQueryModel


class ShotGridDiscoveryQueryModel(ShotGridPageQueryModel):
    """工作台搜索与文件页统一查询参数。"""

    resource_type: Literal['all', 'shot', 'asset', 'task', 'version', 'file'] = 'all'
    project_id: int | None = Field(default=None, gt=0)

    @field_validator('keyword')
    @classmethod
    def normalize_keyword(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None


class ShotGridWorkbenchQueryModel(ShotGridApiModel):
    recent_limit: int = Field(default=8, ge=1, le=20)

from typing import Literal

from pydantic import Field, field_validator

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel

MIN_SEARCH_KEYWORD_LENGTH = 2


class ShotGridSearchQueryModel(ShotGridApiModel):
    """Shot Grid 全局搜索参数。"""

    keyword: str = Field(min_length=2, max_length=100, description='搜索关键字')
    limit: int = Field(default=8, ge=1, le=20, description='每类结果返回上限')

    @field_validator('keyword')
    @classmethod
    def normalize_keyword(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < MIN_SEARCH_KEYWORD_LENGTH:
            raise ValueError('搜索关键字至少需要 2 个字符')
        return normalized


class ShotGridSearchItemModel(ShotGridApiModel):
    """不暴露存储物理路径的统一搜索结果。"""

    result_type: Literal['shot', 'asset', 'file']
    result_id: str
    project_id: int
    project_code: str
    project_name: str
    title: str
    subtitle: str | None = None
    status: str | None = None
    target_path: str


class ShotGridSearchGroupModel(ShotGridApiModel):
    """单一资源类型的搜索结果组。"""

    items: list[ShotGridSearchItemModel] = Field(default_factory=list)
    has_more: bool = False


class ShotGridSearchResultModel(ShotGridApiModel):
    """按资源类型分组的全局搜索响应。"""

    keyword: str
    shots: ShotGridSearchGroupModel = Field(default_factory=ShotGridSearchGroupModel)
    assets: ShotGridSearchGroupModel = Field(default_factory=ShotGridSearchGroupModel)
    files: ShotGridSearchGroupModel = Field(default_factory=ShotGridSearchGroupModel)

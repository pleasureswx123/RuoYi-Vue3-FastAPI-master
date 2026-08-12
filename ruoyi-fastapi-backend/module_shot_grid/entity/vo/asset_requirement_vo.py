from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel, ShotGridPageQueryModel

SQL_BIGINT_MAX = 9_223_372_036_854_775_807


class ShotGridAssetRequirementListQueryModel(ShotGridPageQueryModel):
    """待匹配资产需求分页查询。"""

    resolution_status: Literal['pending', 'conflict', 'matched', 'ignored'] | None = None
    asset_type: Literal['Character', 'Environment', 'Prop'] | None = None
    order_by_column: Literal['createTime', 'rawName', 'resolutionStatus'] = 'createTime'


class ShotGridAssetRequirementResolveModel(ShotGridApiModel):
    """人工选择正式资产完成匹配。"""

    model_config = ConfigDict(extra='forbid')

    asset_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator('reason', mode='before')
    @classmethod
    def normalize_reason(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError('解决原因必须是字符串')
        return value.strip()


class ShotGridAssetRequirementIgnoreModel(ShotGridApiModel):
    """人工忽略待匹配需求。"""

    model_config = ConfigDict(extra='forbid')

    reason: str = Field(min_length=1, max_length=500)

    @field_validator('reason', mode='before')
    @classmethod
    def normalize_reason(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError('忽略原因必须是字符串')
        return value.strip()


class ShotGridAssetRequirementModel(ShotGridApiModel):
    """待匹配资产需求列表项。"""

    requirement_id: int
    project_id: int
    shot_id: int
    episode_no: int
    scene_no: int
    shot_no: int
    asset_type: Literal['Character', 'Environment', 'Prop']
    raw_name: str
    normalized_name: str
    resolution_status: Literal['pending', 'conflict', 'matched', 'ignored']
    asset_id: int | None = None
    asset_name: str | None = None
    resolved_by: int | None = None
    resolved_time: datetime | None = None
    resolution_reason: str | None = None
    create_time: datetime
    update_time: datetime | None = None


class ShotGridAssetRequirementRematchResultModel(ShotGridApiModel):
    """项目级重新匹配结果。"""

    matched_count: int = 0
    pending_count: int = 0
    conflict_count: int = 0


class ShotGridAssetRequirementActionResultModel(ShotGridApiModel):
    """单条需求人工处理结果。"""

    requirement_id: int
    resolution_status: Literal['matched', 'ignored']
    asset_id: int | None = None
    idempotent_replay: bool = False

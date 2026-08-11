from typing import Literal

from pydantic import Field

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel, ShotGridPageQueryModel


class RequirementQueryModel(ShotGridPageQueryModel):
    status: Literal['pending', 'conflict'] | None = None
    asset_type: Literal['Character', 'Environment', 'Prop'] | None = None
    shot_id: int | None = Field(default=None, gt=0)


class CandidateQueryModel(ShotGridApiModel):
    keyword: str | None = Field(default=None, max_length=200)
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class RequirementBindModel(ShotGridApiModel):
    asset_id: int = Field(gt=0)
    lock_version: int = Field(ge=0)


class RequirementCloseModel(ShotGridApiModel):
    lock_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)

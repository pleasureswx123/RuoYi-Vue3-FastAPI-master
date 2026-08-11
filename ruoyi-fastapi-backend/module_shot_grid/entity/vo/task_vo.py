from datetime import date
from typing import Literal

from pydantic import Field

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel, ShotGridPageQueryModel


class ShotGridTaskAssignModel(ShotGridApiModel):
    assignee_user_id: int = Field(gt=0, description='负责人用户ID')
    due_date: date | None = Field(default=None, description='截止日期')
    requirements: str | None = Field(default=None, max_length=10000, description='制作要求')


class ShotGridTaskQueryModel(ShotGridPageQueryModel):
    task_status: Literal['not_started', 'in_progress', 'pending_review', 'revision', 'completed'] | None = None
    task_kind: Literal['shot_video', 'asset_image'] | None = None
    assignee_user_id: int | None = Field(default=None, gt=0)
    shot_id: int | None = Field(default=None, gt=0)
    asset_item_id: int | None = Field(default=None, gt=0)


class ShotGridTaskStartModel(ShotGridApiModel):
    reason: str | None = Field(default=None, max_length=500, description='代操作原因')

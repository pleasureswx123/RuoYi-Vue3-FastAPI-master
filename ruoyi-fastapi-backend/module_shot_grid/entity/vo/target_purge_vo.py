"""永久清理公开状态不包含私有存储路径。"""

from typing import Literal

from pydantic import Field

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel, ShotGridPageQueryModel


class ShotGridTargetPurgeStatusModel(ShotGridApiModel):
    purge_id: int
    target_kind: Literal['shot', 'asset']
    target_id: int
    target_label: str
    purge_status: Literal['pending', 'processing', 'retry_wait', 'succeeded', 'failed']
    last_error_key: str | None = None
    last_error_message: str | None = None
    can_retry: bool = False


class ShotGridTargetPurgeQueryModel(ShotGridPageQueryModel):
    target_kind: Literal['shot', 'asset']
    purge_id: int | None = Field(default=None, gt=0)
    unfinished_only: bool = True

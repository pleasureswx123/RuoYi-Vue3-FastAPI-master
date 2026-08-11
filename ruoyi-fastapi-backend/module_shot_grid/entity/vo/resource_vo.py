# ruff: noqa: ANN201
from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel, ShotGridLockVersionModel, ShotGridPageQueryModel
from module_shot_grid.entity.vo.project_vo import AspectRatio, ProjectPhase

LifecycleStatus = Literal['active', 'archived']
AssetType = Literal['Character', 'Environment', 'Prop']
AggregateStatus = Literal['no_task', 'not_started', 'in_progress', 'pending_review', 'revision', 'completed']


class ShotGridResourceQueryModel(ShotGridPageQueryModel):
    lifecycle_status: LifecycleStatus | None = None
    status: AggregateStatus | None = None


class ShotGridProjectUpdateModel(ShotGridLockVersionModel):
    project_name: str = Field(min_length=1, max_length=200)
    project_description: str | None = None
    aspect_ratio: AspectRatio
    planned_duration_ms: int | None = Field(default=None, ge=0)
    delivery_date: date | None = None
    current_phase: ProjectPhase
    remark: str | None = Field(default=None, max_length=500)


class ShotGridProjectActionModel(ShotGridLockVersionModel):
    action: Literal['activate', 'complete', 'reopen', 'archive']


class ShotGridEpisodeWriteModel(ShotGridLockVersionModel):
    episode_no: int = Field(gt=0)
    episode_name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    sort_order: int = Field(default=0, ge=0)
    remark: str | None = Field(default=None, max_length=500)
    lock_version: int = Field(default=0, ge=0, exclude=True)


class ShotGridSceneWriteModel(ShotGridLockVersionModel):
    episode_id: int | None = Field(default=None, gt=0)
    scene_no: int = Field(ge=0)
    scene_name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    sort_order: int = Field(default=0, ge=0)
    remark: str | None = Field(default=None, max_length=500)
    lock_version: int = Field(default=0, ge=0, exclude=True)

    @model_validator(mode='after')
    def validate_prologue(self):
        if (self.scene_no == 0) != (self.scene_name == '序'):
            raise ValueError('场次号 0 必须且只能使用场次名称“序”')
        return self


class ShotGridShotWriteModel(ShotGridLockVersionModel):
    episode_id: int = Field(gt=0)
    scene_id: int = Field(gt=0)
    shot_no: int = Field(gt=0)
    duration_ms: int = Field(default=0, ge=0)
    shot_size: str | None = Field(default=None, max_length=40)
    camera_position: str | None = Field(default=None, max_length=100)
    camera_movement: str | None = Field(default=None, max_length=100)
    focal_length: str | None = Field(default=None, max_length=50)
    description: str = Field(min_length=1)
    dialogue: str | None = None
    sound_effect: str | None = None
    color_reference: str | None = None
    sort_order: int = Field(default=0, ge=0)
    remark: str | None = Field(default=None, max_length=500)
    lock_version: int = Field(default=0, ge=0, exclude=True)


class ShotGridAssetWriteModel(ShotGridLockVersionModel):
    asset_name: str = Field(min_length=1, max_length=200)
    asset_type: AssetType
    description: str | None = None
    sort_order: int = Field(default=0, ge=0)
    remark: str | None = Field(default=None, max_length=500)
    lock_version: int = Field(default=0, ge=0, exclude=True)

    @field_validator('asset_name', mode='before')
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class ShotGridAssetItemWriteModel(ShotGridLockVersionModel):
    asset_id: int | None = Field(default=None, gt=0)
    production_item: str | None = Field(default=None, max_length=240)
    description: str | None = None
    sort_order: int = Field(default=0, ge=0)
    remark: str | None = Field(default=None, max_length=500)
    lock_version: int = Field(default=0, ge=0, exclude=True)


class ShotGridArchiveModel(ShotGridLockVersionModel):
    pass


class ShotGridResourceModel(ShotGridApiModel):
    id: int
    project_id: int
    lifecycle_status: LifecycleStatus | None = None
    lock_version: int
    create_time: datetime
    update_time: datetime
    data: dict

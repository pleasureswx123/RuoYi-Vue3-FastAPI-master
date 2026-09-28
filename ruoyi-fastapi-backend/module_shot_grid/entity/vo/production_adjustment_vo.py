from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel, ShotGridLockVersionModel
from module_shot_grid.entity.vo.shot_crud_vo import SQL_BIGINT_MAX, _strip_optional_text
from module_shot_grid.entity.vo.task_schedule_vo import BusinessDateTime


class ShotGridProductionChanges(ShotGridApiModel):
    """稀疏变更：省略保持原值，文本 null 表示清空。"""

    model_config = ConfigDict(extra='forbid')
    reference_description: str | None = Field(default=None, max_length=10000)
    reference_file_ids: list[str] = Field(default_factory=list, min_length=1, max_length=5)

    @field_validator('reference_file_ids')
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        ids = [str(UUID(item)) for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError('参考文件不能重复')
        return ids

    assignee_user_id: int | None = Field(default=None, gt=0, le=SQL_BIGINT_MAX)
    priority: Literal['low', 'normal', 'high', 'urgent'] | None = None
    expected_start_time: BusinessDateTime | None = None
    expected_end_time: BusinessDateTime | None = None
    duration_ms: int | None = Field(default=None, ge=0, le=SQL_BIGINT_MAX)
    description: str | None = None
    shot_size: str | None = Field(default=None, max_length=500)
    camera_position: str | None = Field(default=None, max_length=500)
    camera_movement: str | None = Field(default=None, max_length=500)
    focal_length: str | None = Field(default=None, max_length=500)
    dialogue: str | None = None
    sound_effect: str | None = None
    color_reference: str | None = None
    remark: str | None = Field(default=None, max_length=2000)

    @field_validator(
        'reference_description',
        'description',
        'shot_size',
        'camera_position',
        'camera_movement',
        'focal_length',
        'dialogue',
        'sound_effect',
        'color_reference',
        'remark',
        mode='before',
    )
    @classmethod
    def normalize_text(cls, value: object) -> str | None:
        return _strip_optional_text(value)

    @model_validator(mode='after')
    def validate_patch(self) -> 'ShotGridProductionChanges':
        fields = self.model_fields_set
        if not fields:
            raise ValueError('请选择至少一个修改字段')
        required = {'assignee_user_id', 'priority', 'duration_ms', 'expected_start_time', 'expected_end_time'}
        if any(getattr(self, key) is None for key in fields & required):
            raise ValueError('制作人、优先级、时长和排期不能清空')
        if ('expected_start_time' in fields) != ('expected_end_time' in fields):
            raise ValueError('计划起止时间必须成对提交')
        if self.expected_start_time and self.expected_end_time <= self.expected_start_time:
            raise ValueError('计划结束时间必须晚于开始时间')
        return self


class ShotGridProductionAdjustmentItem(ShotGridLockVersionModel):
    model_config = ConfigDict(extra='forbid')
    task_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    shot_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    shot_lock_version: int = Field(ge=0)
    changes: ShotGridProductionChanges


class ShotGridAdjustmentConflict(ShotGridApiModel):
    model_config = ConfigDict(extra='forbid')
    task_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    conflict_task_ids: list[int] = Field(max_length=1000)

    @field_validator('conflict_task_ids')
    @classmethod
    def validate_ids(cls, ids: list[int]) -> list[int]:
        if any(value <= 0 or value > SQL_BIGINT_MAX for value in ids) or len(ids) != len(set(ids)):
            raise ValueError('重叠任务ID必须为不重复的正整数')
        return sorted(ids)


class ShotGridProductionAdjustmentModel(ShotGridApiModel):
    model_config = ConfigDict(extra='forbid')
    reason: str = Field(min_length=1, max_length=500)
    items: list[ShotGridProductionAdjustmentItem] = Field(min_length=1, max_length=100)
    overlap_acknowledged: bool = False
    expected_conflicts: list[ShotGridAdjustmentConflict] = Field(default_factory=list, max_length=100)

    @field_validator('reason', mode='before')
    @classmethod
    def trim_reason(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode='after')
    def validate_unique(self) -> 'ShotGridProductionAdjustmentModel':
        for field in ('task_id', 'shot_id'):
            if len({getattr(item, field) for item in self.items}) != len(self.items):
                raise ValueError('任务及镜头不能重复')
        ids = [item.task_id for item in self.expected_conflicts]
        if len(ids) != len(set(ids)) or not set(ids) <= {item.task_id for item in self.items}:
            raise ValueError('冲突快照必须对应本次任务且不能重复')
        return self

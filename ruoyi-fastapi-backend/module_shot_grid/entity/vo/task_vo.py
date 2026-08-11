from datetime import date, datetime
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from module_shot_grid.entity.vo.common_vo import (
    ShotGridApiModel,
    ShotGridLockVersionModel,
    ShotGridPageQueryModel,
)

TaskKind = Literal['shot_video', 'asset_image']
TaskStatus = Literal['not_started', 'in_progress', 'pending_review', 'revision', 'completed']
TaskPriority = Literal['low', 'normal', 'high', 'urgent']
SQL_BIGINT_MAX = 9_223_372_036_854_775_807


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('任务文本字段必须是字符串')
    normalized = value.strip()
    return normalized or None


class ShotGridTaskFilterModel(ShotGridPageQueryModel):
    """任务列表共用筛选条件。"""

    task_kind: TaskKind | None = Field(default=None, description='任务类型')
    task_status: TaskStatus | None = Field(default=None, description='任务状态')
    due_date_from: date | None = Field(default=None, description='截止日期下界')
    due_date_to: date | None = Field(default=None, description='截止日期上界')
    priority: TaskPriority | None = Field(default=None, description='任务优先级')
    order_by_column: Literal['taskId', 'dueDate', 'priority', 'createTime', 'updateTime'] = Field(
        default='updateTime',
        description='排序字段',
    )

    @model_validator(mode='after')
    def validate_due_date_range(self) -> 'ShotGridTaskFilterModel':
        if self.due_date_from is not None and self.due_date_to is not None and self.due_date_from > self.due_date_to:
            raise ValueError('dueDateFrom 不能晚于 dueDateTo')
        return self


class ShotGridTaskListQueryModel(ShotGridTaskFilterModel):
    """项目内任务分页查询。"""

    assignee_user_id: int | None = Field(
        default=None,
        gt=0,
        le=SQL_BIGINT_MAX,
        description='负责人用户ID',
    )
    scope: Literal['project', 'mine'] = Field(default='project', description='项目范围或本人范围')


class ShotGridMineTaskListQueryModel(ShotGridTaskFilterModel):
    """工作台跨项目“我的任务”查询；负责人范围由服务端强制。"""


class ShotGridTaskUpdateModel(ShotGridLockVersionModel):
    """修改任务要求、优先级和截止日期的完整快照。"""

    model_config = ConfigDict(extra='forbid')

    requirements: str | None = Field(description='制作要求，显式 null 表示清空')
    priority: TaskPriority = Field(description='任务优先级')
    due_date: date | None = Field(description='截止日期，显式 null 表示清空')

    @field_validator('requirements', mode='before')
    @classmethod
    def normalize_requirements(cls, value: object) -> str | None:
        return _normalize_optional_text(value)


class ShotGridTaskAssignModel(ShotGridApiModel):
    """首次分配或受控改派任务。"""

    model_config = ConfigDict(extra='forbid')

    assignee_user_id: int = Field(gt=0, le=SQL_BIGINT_MAX, description='唯一主制作人用户ID')
    task_description: str | None = Field(default=None, description='可选制作要求')
    priority: TaskPriority | None = Field(default=None, description='可选任务优先级；首次分配默认 normal')
    due_date: date | None = Field(default=None, description='可选截止日期')
    task_lock_version: int | None = Field(
        default=None,
        ge=0,
        description='已有任务改派时必填；首次分配时必须为空',
    )

    @field_validator('task_description', mode='before')
    @classmethod
    def normalize_task_description(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode='after')
    def reject_explicit_null_priority(self) -> 'ShotGridTaskAssignModel':
        if 'priority' in self.model_fields_set and self.priority is None:
            raise ValueError('priority 不能显式为空')
        return self


class ShotGridTaskStartModel(ShotGridLockVersionModel):
    """开始任务请求。"""

    model_config = ConfigDict(extra='forbid')


class ShotGridTaskProjectSummaryModel(ShotGridApiModel):
    """任务所属项目摘要。"""

    project_id: int
    project_code: str
    project_name: str
    project_status: Literal['preparing', 'active', 'completed', 'archived']


class ShotGridTaskAssigneeModel(ShotGridApiModel):
    """任务负责人摘要；历史任务的成员缩写允许为空。"""

    user_id: int
    nick_name: str | None = None
    producer_code: str | None = None
    member_status: Literal['active', 'removed'] | None = None


class ShotGridTaskTargetModel(ShotGridApiModel):
    """镜头或资产制作分项目标摘要。"""

    target_type: Literal['shot', 'asset_item']
    target_id: int
    target_name: str
    target_description: str | None = None
    lifecycle_status: Literal['active', 'archived'] | None = None
    episode_id: int | None = None
    episode_no: int | None = None
    episode_code: str | None = None
    scene_id: int | None = None
    scene_no: int | None = None
    scene_code: str | None = None
    scene_name: str | None = None
    shot_id: int | None = None
    shot_no: int | None = None
    shot_code: str | None = None
    asset_id: int | None = None
    asset_type: Literal['Character', 'Environment', 'Prop'] | None = None
    asset_name: str | None = None
    asset_item_id: int | None = None
    production_item: str | None = None


class ShotGridTaskVersionSummaryModel(ShotGridApiModel):
    """任务版本摘要。"""

    version_id: int
    version_no: int
    version_number: str
    version_status: Literal['pending_review', 'rejected', 'final']
    submitted_time: datetime


class ShotGridTaskListItemModel(ShotGridApiModel):
    """任务列表项。"""

    task_id: int
    task_name: str
    task_kind: TaskKind
    task_status: TaskStatus
    priority: TaskPriority
    due_date: date | None = None
    requirements: str | None = None
    project: ShotGridTaskProjectSummaryModel
    assignee: ShotGridTaskAssigneeModel
    target: ShotGridTaskTargetModel
    version_count: int = Field(default=0, ge=0)
    latest_version: ShotGridTaskVersionSummaryModel | None = None
    final_version: ShotGridTaskVersionSummaryModel | None = None
    lock_version: int = Field(ge=0)
    create_time: datetime
    update_time: datetime


class ShotGridTaskDetailModel(ShotGridTaskListItemModel):
    """任务详情；完整版本和意见继续走独立分页接口。"""

    remark: str | None = None
    create_by: str
    update_by: str
    has_uncommitted_submission: bool = False
    allowed_actions: list[str] = Field(default_factory=list)

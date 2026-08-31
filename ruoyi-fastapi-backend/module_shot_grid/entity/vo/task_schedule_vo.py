from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StrictBool,
    field_validator,
    model_validator,
)

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel
from module_shot_grid.entity.vo.task_vo import TaskKind, TaskPriority, TaskStatus

ScheduleTargetKind = Literal['all', 'shot', 'asset_item']
ScheduleRowTargetKind = Literal['shot', 'asset_item']
ScheduleGroupBy = Literal['assignee', 'task_kind', 'status', 'episode', 'scene', 'asset_type']
ScheduleChangeType = Literal['initial', 'move', 'resize_start', 'resize_end', 'dialog']
ScheduleOperationSource = Literal['start', 'swimlane', 'gantt', 'dialog']
ScheduleClientOperationSource = Literal['swimlane', 'gantt', 'dialog']
AssetType = Literal['Character', 'Environment', 'Prop']
SQL_BIGINT_MAX = 9_223_372_036_854_775_807


def _reject_fractional_datetime(value: object) -> object:
    if isinstance(value, str) and '.' in value:
        raise ValueError('排期时间不允许包含小数秒')
    return value


def _validate_business_datetime(value: datetime) -> datetime:
    if value.tzinfo is not None:
        raise ValueError('排期时间请使用业务本地时间，不附加时区')
    if value.microsecond:
        raise ValueError('排期时间最多精确到秒')
    return value


def _serialize_business_datetime(value: datetime) -> str:
    return value.strftime('%Y-%m-%dT%H:%M:%S')


BusinessDateTime = Annotated[
    datetime,
    BeforeValidator(_reject_fractional_datetime),
    AfterValidator(_validate_business_datetime),
    PlainSerializer(_serialize_business_datetime, return_type=str, when_used='json'),
]


class ShotGridScheduleQueryModel(ShotGridApiModel):
    """项目排期窗口查询；日、周、月只改变客户端窗口和刻度。"""

    model_config = ConfigDict(extra='forbid')

    window_start: BusinessDateTime
    window_end: BusinessDateTime
    target_kind: ScheduleTargetKind = 'all'
    group_by: ScheduleGroupBy = 'assignee'
    assignee_user_ids: list[int] = Field(default_factory=list, max_length=100)
    task_kinds: list[TaskKind] = Field(default_factory=list, max_length=10)
    task_statuses: list[TaskStatus] = Field(default_factory=list, max_length=20)
    priorities: list[TaskPriority] = Field(default_factory=list, max_length=10)
    episode_ids: list[int] = Field(default_factory=list, max_length=100)
    scene_ids: list[int] = Field(default_factory=list, max_length=100)
    asset_types: list[AssetType] = Field(default_factory=list, max_length=10)
    keyword: str | None = Field(default=None, max_length=200)
    only_conflicts: bool = False
    only_delayed: bool = False
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=200, ge=1, le=1000)

    @field_validator('keyword', mode='before')
    @classmethod
    def normalize_keyword(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('keyword 必须是字符串')
        normalized = value.strip()
        return normalized or None

    @field_validator('assignee_user_ids', 'episode_ids', 'scene_ids')
    @classmethod
    def validate_positive_ids(cls, value: list[int]) -> list[int]:
        if any(item <= 0 or item > SQL_BIGINT_MAX for item in value):
            raise ValueError('筛选条件包含非法ID')
        if len(value) != len(set(value)):
            raise ValueError('筛选条件不能包含重复ID')
        return value

    @model_validator(mode='after')
    def validate_window(self) -> 'ShotGridScheduleQueryModel':
        if self.window_end <= self.window_start:
            raise ValueError('windowEnd 必须晚于 windowStart')
        return self


class ShotGridScheduleAssigneeModel(ShotGridApiModel):
    """排期行负责人摘要。"""

    user_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    user_name: str
    nick_name: str | None = None


class ShotGridScheduleTargetModel(ShotGridApiModel):
    """排期行所指向的镜头或资产制作分项摘要。"""

    target_kind: ScheduleRowTargetKind
    target_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    parent_id: int | None = Field(default=None, gt=0, le=SQL_BIGINT_MAX)
    code: str | None = None
    name: str
    sort_order: int = Field(ge=0)
    episode_id: int | None = Field(default=None, gt=0, le=SQL_BIGINT_MAX)
    episode_no: int | None = Field(default=None, ge=0)
    scene_id: int | None = Field(default=None, gt=0, le=SQL_BIGINT_MAX)
    scene_no: int | None = Field(default=None, ge=0)
    asset_type: AssetType | None = None


class ShotGridScheduleConflictModel(ShotGridApiModel):
    """与当前任务按半开区间重叠的同人任务摘要。"""

    task_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    target_name: str
    assignee: ShotGridScheduleAssigneeModel
    start_time: BusinessDateTime
    end_time: BusinessDateTime

    @model_validator(mode='after')
    def validate_range(self) -> 'ShotGridScheduleConflictModel':
        if self.end_time <= self.start_time:
            raise ValueError('冲突任务结束时间必须晚于开始时间')
        return self


class ShotGridScheduleTaskModel(ShotGridApiModel):
    """项目排期主列表的一行真实任务。"""

    task_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    project_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    task_kind: TaskKind
    task_status: TaskStatus
    priority: TaskPriority
    lock_version: int = Field(ge=0)
    group_key: str
    group_name: str
    target: ShotGridScheduleTargetModel
    assignee: ShotGridScheduleAssigneeModel
    current_start: BusinessDateTime
    current_end: BusinessDateTime
    baseline_start: BusinessDateTime | None = None
    baseline_end: BusinessDateTime | None = None
    conflicts: list[ShotGridScheduleConflictModel] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_ranges(self) -> 'ShotGridScheduleTaskModel':
        if self.current_end <= self.current_start:
            raise ValueError('当前排期结束时间必须晚于开始时间')
        if (self.baseline_start is None) != (self.baseline_end is None):
            raise ValueError('首版排期必须成对返回')
        if (
            self.baseline_start is not None
            and self.baseline_end is not None
            and self.baseline_end <= self.baseline_start
        ):
            raise ValueError('首版排期结束时间必须晚于开始时间')
        return self


class ShotGridScheduleGroupModel(ShotGridApiModel):
    """稳定分组键及显示摘要。"""

    group_key: str
    group_name: str
    sort_order: int = Field(ge=0)
    task_count: int = Field(ge=0)


class ShotGridSchedulePageModel(ShotGridApiModel):
    """项目排期分页响应。"""

    rows: list[ShotGridScheduleTaskModel]
    groups: list[ShotGridScheduleGroupModel] = Field(default_factory=list)
    page_num: int = Field(ge=1)
    page_size: int = Field(ge=1, le=1000)
    total: int = Field(ge=0)
    has_next: bool
    unscheduled_count: int = Field(ge=0)
    server_time: BusinessDateTime


class ShotGridScheduleUnscheduledTaskModel(ShotGridApiModel):
    """已经存在真实任务、但当前尚未取得排期的任务。"""

    task_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    project_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    task_kind: TaskKind
    task_status: TaskStatus
    priority: TaskPriority
    lock_version: int = Field(ge=0)
    target: ShotGridScheduleTargetModel
    assignee: ShotGridScheduleAssigneeModel
    allowed_actions: list[str] = Field(default_factory=list)


class ShotGridScheduleUnscheduledPageModel(ShotGridApiModel):
    """未排期任务独立分页响应。"""

    rows: list[ShotGridScheduleUnscheduledTaskModel]
    page_num: int = Field(ge=1)
    page_size: int = Field(ge=1, le=1000)
    total: int = Field(ge=0)
    has_next: bool


class ShotGridScheduleUpdateModel(ShotGridApiModel):
    """管理员创建或调整完整任务排期。"""

    model_config = ConfigDict(extra='forbid')

    lock_version: int = Field(ge=0)
    expected_start_time: BusinessDateTime
    expected_end_time: BusinessDateTime
    operation_source: ScheduleClientOperationSource
    change_reason: str = Field(min_length=1, max_length=500)
    overlap_acknowledged: StrictBool = False
    expected_conflict_task_ids: list[int] = Field(default_factory=list, max_length=1000)

    @field_validator('change_reason', mode='before')
    @classmethod
    def normalize_reason(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError('changeReason 必须是字符串')
        normalized = value.strip()
        if not normalized:
            raise ValueError('changeReason 不能为空')
        return normalized

    @field_validator('expected_conflict_task_ids')
    @classmethod
    def validate_conflict_ids(cls, value: list[int]) -> list[int]:
        if any(task_id <= 0 or task_id > SQL_BIGINT_MAX for task_id in value):
            raise ValueError('expectedConflictTaskIds 包含非法任务ID')
        if len(value) != len(set(value)):
            raise ValueError('expectedConflictTaskIds 不能包含重复任务')
        return value

    @model_validator(mode='after')
    def validate_range(self) -> 'ShotGridScheduleUpdateModel':
        if self.expected_end_time <= self.expected_start_time:
            raise ValueError('expectedEndTime 必须晚于 expectedStartTime')
        return self


class ShotGridScheduleChangeModel(ShotGridApiModel):
    """任务排期结构化历史响应。"""

    schedule_change_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    task_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    operator: ShotGridScheduleAssigneeModel
    from_start_time: BusinessDateTime | None = None
    from_end_time: BusinessDateTime | None = None
    to_start_time: BusinessDateTime
    to_end_time: BusinessDateTime
    change_type: ScheduleChangeType
    operation_source: ScheduleOperationSource
    change_reason: str
    overlap_acknowledged: bool
    overlap_task_ids: list[int]
    task_lock_version_before: int = Field(ge=0)
    task_lock_version_after: int = Field(ge=1)
    create_time: BusinessDateTime

    @model_validator(mode='after')
    def validate_ranges_and_versions(self) -> 'ShotGridScheduleChangeModel':
        if (self.from_start_time is None) != (self.from_end_time is None):
            raise ValueError('变更前排期必须成对返回')
        if (
            self.from_start_time is not None
            and self.from_end_time is not None
            and self.from_end_time <= self.from_start_time
        ):
            raise ValueError('变更前排期结束时间必须晚于开始时间')
        if self.to_end_time <= self.to_start_time:
            raise ValueError('变更后排期结束时间必须晚于开始时间')
        if self.task_lock_version_after <= self.task_lock_version_before:
            raise ValueError('变更后任务版本必须递增')
        return self

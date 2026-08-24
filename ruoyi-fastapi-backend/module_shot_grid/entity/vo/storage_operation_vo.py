from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from common.vo import ResponseBaseModel
from module_shot_grid.entity.vo.common_vo import ShotGridApiModel, ShotGridLockVersionModel, ShotGridPageQueryModel

StorageOperationType = Literal[
    'initialize_project',
    'ensure_episode_directory',
    'ensure_shot_directory',
    'ensure_asset_directory',
    'reconcile_directory',
    'renumber_shot_directories',
]
StorageAggregateType = Literal['project', 'episode', 'scene', 'shot', 'asset']
StorageOperationStatus = Literal[
    'pending',
    'processing',
    'succeeded',
    'retry_wait',
    'failed',
    'compensation_pending',
    'compensated',
    'compensation_failed',
]


def normalize_retry_reason(value: Any) -> str:
    """规范化人工重试原因，避免空白审计记录。"""

    if not isinstance(value, str):
        raise ValueError('重试原因必须是字符串')
    normalized = value.strip()
    if not normalized:
        raise ValueError('重试原因不能为空')
    return normalized


class ShotGridProjectStorageRetryModel(ShotGridLockVersionModel):
    """项目初始目录人工重试请求。"""

    reason: str = Field(min_length=1, max_length=500, description='人工重试原因')

    @field_validator('reason', mode='before')
    @classmethod
    def validate_reason(cls, value: Any) -> str:
        return normalize_retry_reason(value)


class ShotGridStorageOperationRetryModel(ShotGridApiModel):
    """动态目录操作人工重试请求。"""

    reason: str = Field(min_length=1, max_length=500, description='人工重试原因')

    @field_validator('reason', mode='before')
    @classmethod
    def validate_reason(cls, value: Any) -> str:
        return normalize_retry_reason(value)


class ShotGridStorageOperationQueryModel(ShotGridPageQueryModel):
    """项目目录操作安全诊断分页查询。"""

    operation_type: StorageOperationType | None = Field(default=None, description='操作类型')
    operation_status: StorageOperationStatus | None = Field(default=None, description='执行状态')
    order_by_column: Literal['operationId', 'createTime', 'updateTime', 'nextRetryTime'] = Field(
        default='createTime',
        description='排序字段',
    )


class ShotGridStorageOperationModel(ShotGridApiModel):
    """不暴露租约、凭据和内部幂等键的目录操作诊断。"""

    operation_id: int = Field(description='目录操作ID')
    project_id: int = Field(description='项目ID')
    operation_type: StorageOperationType = Field(description='操作类型')
    aggregate_type: StorageAggregateType = Field(description='目标业务类型')
    aggregate_id: int = Field(description='目标业务ID')
    target_relative_path: str = Field(description='安全相对路径快照')
    operation_status: StorageOperationStatus = Field(description='执行状态')
    attempt_count: int = Field(ge=0, description='已执行次数')
    next_retry_time: datetime | None = Field(default=None, description='下次自动重试时间')
    started_time: datetime | None = Field(default=None, description='首次开始时间')
    completed_time: datetime | None = Field(default=None, description='完成时间')
    last_error_key: str | None = Field(default=None, description='最近稳定错误键')
    last_error_message: str | None = Field(default=None, description='最近净化错误摘要')
    create_time: datetime = Field(description='创建时间')
    update_time: datetime = Field(description='更新时间')


class ShotGridStorageRetryAcceptedModel(ShotGridApiModel):
    """目录人工重试已受理结果。"""

    operation_id: int = Field(description='新建或重放的对账操作ID')
    project_id: int = Field(description='项目ID')
    operation_status: StorageOperationStatus = Field(description='当前操作状态')
    replayed: bool = Field(default=False, description='是否为同幂等键重放')
    status_url: str = Field(description='目录操作状态查询地址')


class ShotGridStorageRetryAcceptedResponseModel(ResponseBaseModel):
    """真实 HTTP 202 对应的目录重试响应。"""

    code: Literal[202] = Field(default=202, description='响应码')
    msg: str = Field(default='目录重试已受理', description='响应信息')
    data: ShotGridStorageRetryAcceptedModel = Field(description='受理结果')

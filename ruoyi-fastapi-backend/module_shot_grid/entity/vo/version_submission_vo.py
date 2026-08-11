import json
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from common.vo import ResponseBaseModel
from module_shot_grid.entity.vo.common_vo import ShotGridApiModel

VersionSubmissionStatus = Literal['pending', 'publishing', 'published', 'committing', 'committed', 'failed']


class ShotGridVersionSubmissionCreateModel(ShotGridApiModel):
    """创建版本暂存请求。"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
        extra='forbid',
    )

    file_id: str = Field(description='平台受保护源文件ID')
    changelog: str = Field(min_length=1, max_length=5000, description='本轮修改说明')
    ai_params: dict[str, Any] | list[Any] | None = Field(default=None, description='可选AI生成参数快照')

    @field_validator('file_id', mode='before')
    @classmethod
    def normalize_file_id(cls, value: Any) -> str:
        try:
            return str(uuid.UUID(str(value)))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError('fileId 格式不正确') from exc

    @field_validator('changelog', mode='before')
    @classmethod
    def normalize_changelog(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError('修改说明必须是字符串')
        normalized = value.strip()
        if not normalized or not normalized.isprintable():
            raise ValueError('修改说明不能为空且不能包含控制字符')
        return normalized

    @model_validator(mode='after')
    def validate_ai_params_size(self) -> 'ShotGridVersionSubmissionCreateModel':
        if self.ai_params is None:
            return self
        try:
            encoded = json.dumps(self.ai_params, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError('aiParams 必须是可序列化的有限 JSON') from exc
        if len(encoded.encode('utf-8')) > 64 * 1024:
            raise ValueError('aiParams 不能超过 64KiB')
        return self


class ShotGridVersionSubmissionAcceptedModel(ShotGridApiModel):
    """版本提交异步受理结果。"""

    submission_id: int
    submission_status: VersionSubmissionStatus
    reserved_version_number: str
    business_file_name: str
    status_url: str
    task_status: Literal['not_started', 'in_progress', 'revision', 'pending_review', 'completed']
    replayed: bool = False


class ShotGridVersionSubmissionAcceptedResponseModel(ResponseBaseModel):
    """真实 HTTP 202 对应的版本提交响应。"""

    code: Literal[202] = Field(default=202)
    msg: str = Field(default='版本提交已受理')
    data: ShotGridVersionSubmissionAcceptedModel


class ShotGridVersionSubmissionStatusModel(ShotGridApiModel):
    """版本提交状态；不暴露租约、内部路径和幂等键。"""

    submission_id: int
    project_id: int
    task_id: int
    source_file_id: str
    submission_status: VersionSubmissionStatus
    reserved_version_no: int
    reserved_version_number: str
    business_file_name: str
    attempt_count: int = Field(ge=0)
    last_error_key: str | None = None
    last_error_message: str | None = None
    version_id: int | None = None
    review_list_id: int | None = None
    version_status: Literal['pending_review', 'rejected', 'final'] | None = None
    task_status: Literal['not_started', 'in_progress', 'pending_review', 'revision', 'completed']
    create_time: datetime
    update_time: datetime


class ShotGridVersionFileAccessModel(ShotGridApiModel):
    """专用授权下载所需的最小版本文件上下文。"""

    project_id: int
    version_id: int
    file_id: str
    business_file_name: str

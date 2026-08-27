import json
import unicodedata
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from common.vo import ResponseBaseModel
from module_shot_grid.config import SHOT_GRID_VERSION_SUBMISSION_CONFIG
from module_shot_grid.entity.vo.common_vo import ShotGridApiModel

VersionSubmissionStatus = Literal['pending', 'publishing', 'published', 'committing', 'committed', 'failed']
VersionSubmissionTaskKind = Literal['shot_video', 'asset_image']
VersionSubmissionFileExtension = Literal['mp4', 'mov', 'jpg', 'png']
MAX_CLIENT_FILE_KEY_LENGTH = 100


def _normalize_client_file_key(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError('clientFileKey 必须是字符串')
    normalized = value.strip()
    if not normalized or len(normalized) > MAX_CLIENT_FILE_KEY_LENGTH or not normalized.isprintable():
        raise ValueError('clientFileKey 长度必须为1到100个可打印字符')
    return normalized


def _normalize_candidate_note(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('candidateNote 必须是字符串')
    normalized = value.strip()
    if not normalized:
        return None
    if not normalized.isprintable():
        raise ValueError('candidateNote 不能包含控制字符')
    return normalized


def _validate_candidate_order(candidates: list[Any]) -> None:
    client_keys = [item.client_file_key for item in candidates]
    sort_orders = [item.sort_order for item in candidates]
    if len(client_keys) != len(set(client_keys)):
        raise ValueError('candidates 不能包含重复 clientFileKey')
    if sort_orders != list(range(len(candidates))):
        raise ValueError('candidates 必须按 sortOrder 从0开始连续排列')


class ShotGridVersionSubmissionPreflightCandidateModel(ShotGridApiModel):
    """上传前候选文件的浏览器快照。"""

    model_config = ConfigDict(extra='forbid')

    client_file_key: str
    file_name: str = Field(min_length=1, max_length=255)
    file_size: int = Field(gt=0, le=SHOT_GRID_VERSION_SUBMISSION_CONFIG.max_file_size_bytes)
    sort_order: int = Field(ge=0)
    candidate_note: str | None = Field(default=None, max_length=500)

    @field_validator('client_file_key', mode='before')
    @classmethod
    def normalize_client_file_key(cls, value: Any) -> str:
        return _normalize_client_file_key(value)

    @field_validator('file_name', mode='before')
    @classmethod
    def normalize_file_name(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError('fileName 必须是字符串')
        normalized = value.strip()
        if not normalized or not normalized.isprintable() or '/' in normalized or '\\' in normalized:
            raise ValueError('fileName 必须是安全的纯文件名')
        return normalized

    @field_validator('candidate_note', mode='before')
    @classmethod
    def normalize_candidate_note(cls, value: Any) -> str | None:
        return _normalize_candidate_note(value)


class ShotGridVersionSubmissionCandidateCreateModel(ShotGridApiModel):
    """私有上传完成后的候选文件绑定。"""

    model_config = ConfigDict(extra='forbid')

    client_file_key: str
    file_id: str = Field(description='平台受保护源文件ID')
    sort_order: int = Field(ge=0)
    candidate_note: str | None = Field(default=None, max_length=500)

    @field_validator('client_file_key', mode='before')
    @classmethod
    def normalize_client_file_key(cls, value: Any) -> str:
        return _normalize_client_file_key(value)

    @field_validator('file_id', mode='before')
    @classmethod
    def normalize_file_id(cls, value: Any) -> str:
        try:
            return str(uuid.UUID(str(value)))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError('fileId 格式不正确') from exc

    @field_validator('candidate_note', mode='before')
    @classmethod
    def normalize_candidate_note(cls, value: Any) -> str | None:
        return _normalize_candidate_note(value)


class ShotGridIssueResponseInputModel(ShotGridApiModel):
    """制作人对一条未关闭问题的本版处理说明。"""

    model_config = ConfigDict(extra='forbid')

    issue_id: int = Field(gt=0)
    response_text: str = Field(min_length=1, max_length=5000)

    @field_validator('response_text', mode='before')
    @classmethod
    def normalize_response_text(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError('问题处理说明必须是字符串')
        normalized = value.replace('\r\n', '\n').replace('\r', '\n').strip()
        has_forbidden_control = any(
            unicodedata.category(character) == 'Cc' and character != '\n' for character in normalized
        )
        if not normalized or has_forbidden_control:
            raise ValueError('问题处理说明不能为空且不能包含换行以外的控制字符')
        return normalized


class ShotGridVersionSubmissionMetadataModel(ShotGridApiModel):
    """预检与正式提交共用的版本说明。"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
        extra='forbid',
    )

    changelog: str = Field(min_length=1, max_length=5000, description='本轮修改说明')
    ai_params: dict[str, Any] | list[Any] | None = Field(default=None, description='可选AI生成参数快照')
    issue_responses: list[ShotGridIssueResponseInputModel] = Field(default_factory=list, max_length=200)

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
    def validate_ai_params_size(self) -> 'ShotGridVersionSubmissionMetadataModel':
        issue_ids = [item.issue_id for item in self.issue_responses]
        if len(issue_ids) != len(set(issue_ids)):
            raise ValueError('issueResponses 不能包含重复问题')
        if self.ai_params is None:
            return self
        try:
            encoded = json.dumps(self.ai_params, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError('aiParams 必须是可序列化的有限 JSON') from exc
        if len(encoded.encode('utf-8')) > 64 * 1024:
            raise ValueError('aiParams 不能超过 64KiB')
        return self


class ShotGridVersionSubmissionPreflightModel(ShotGridVersionSubmissionMetadataModel):
    """私有文件上传前的无副作用版本提交预检。"""

    candidates: list[ShotGridVersionSubmissionPreflightCandidateModel] = Field(
        min_length=1,
        max_length=SHOT_GRID_VERSION_SUBMISSION_CONFIG.max_candidates,
    )

    @model_validator(mode='after')
    def validate_candidates(self) -> 'ShotGridVersionSubmissionPreflightModel':
        _validate_candidate_order(self.candidates)
        total_size = sum(item.file_size for item in self.candidates)
        if total_size > SHOT_GRID_VERSION_SUBMISSION_CONFIG.max_batch_size_bytes:
            raise ValueError('候选文件总大小超过批次上限')
        return self


class ShotGridVersionSubmissionCreateModel(ShotGridVersionSubmissionMetadataModel):
    """创建版本暂存请求。"""

    candidates: list[ShotGridVersionSubmissionCandidateCreateModel] = Field(
        min_length=1,
        max_length=SHOT_GRID_VERSION_SUBMISSION_CONFIG.max_candidates,
    )
    open_issue_snapshot_hash: str = Field(pattern=r'^[0-9a-f]{64}$', description='预检返回的未关闭问题集合摘要')

    @model_validator(mode='after')
    def validate_candidates(self) -> 'ShotGridVersionSubmissionCreateModel':
        _validate_candidate_order(self.candidates)
        file_ids = [item.file_id for item in self.candidates]
        if len(file_ids) != len(set(file_ids)):
            raise ValueError('candidates 不能包含重复 fileId')
        return self


class ShotGridVersionSubmissionPreflightCandidateResultModel(ShotGridApiModel):
    """预检后的候选编号与文件类型。"""

    client_file_key: str
    candidate_no: int = Field(gt=0)
    candidate_number: str
    file_extension: VersionSubmissionFileExtension


class ShotGridVersionSubmissionPreflightResultModel(ShotGridApiModel):
    """当前上下文允许进入私有上传步骤的稳定证明。"""

    ready: Literal[True] = True
    task_id: int
    task_kind: VersionSubmissionTaskKind
    task_status: Literal['in_progress', 'revision']
    candidates: list[ShotGridVersionSubmissionPreflightCandidateResultModel]
    max_candidates: int = Field(gt=0)
    max_file_size_bytes: int = Field(gt=0)
    max_batch_size_bytes: int = Field(gt=0)
    open_issue_snapshot_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    allowed_actions: list[Literal['version.add']] = Field(default_factory=lambda: ['version.add'])


class ShotGridVersionSubmissionCandidateStatusModel(ShotGridApiModel):
    """候选文件在提交/发布流程中的外部安全状态。"""

    client_file_key: str | None = None
    candidate_no: int = Field(gt=0)
    candidate_number: str
    source_file_id: str
    business_file_name: str
    candidate_note: str | None = None
    sort_order: int = Field(ge=0)
    publish_status: Literal['pending', 'publishing', 'published', 'failed']
    last_error_key: str | None = None
    last_error_message: str | None = None


class ShotGridVersionSubmissionAcceptedModel(ShotGridApiModel):
    """版本提交异步受理结果。"""

    submission_id: int
    submission_status: VersionSubmissionStatus
    reserved_version_number: str
    candidate_count: int = Field(gt=0)
    candidates: list[ShotGridVersionSubmissionCandidateStatusModel]
    # 扩容迁移期保留候选01镜像，旧客户端升级完成后再移除。
    business_file_name: str
    status_url: str
    task_status: Literal['not_started', 'preparing', 'in_progress', 'revision', 'pending_review', 'completed']
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
    candidate_count: int = Field(gt=0)
    candidates: list[ShotGridVersionSubmissionCandidateStatusModel]
    # 扩容迁移期保留候选01镜像，旧客户端升级完成后再移除。
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
    task_status: Literal['not_started', 'preparing', 'in_progress', 'pending_review', 'revision', 'completed']
    create_time: datetime
    update_time: datetime


class ShotGridVersionFileAccessModel(ShotGridApiModel):
    """专用授权下载所需的最小版本文件上下文。"""

    project_id: int
    version_id: int
    file_id: str
    business_file_name: str


class ShotGridPlaybackTicketModel(ShotGridApiModel):
    """浏览器原生媒体元素使用的短期资源绑定票据。"""

    playback_url: str
    expires_in_seconds: int = Field(gt=0)


class ShotGridPlaybackTicketPayloadModel(ShotGridApiModel):
    """仅保存于 Redis 的播放票据载荷。"""

    version_id: int = Field(gt=0)
    file_id: str
    user_id: int = Field(gt=0)
    session_id: str = Field(min_length=1, max_length=200)
    access_token_hash: str = Field(pattern=r'^[0-9a-f]{64}$')

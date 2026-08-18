import json
import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from module_shot_grid.entity.vo.common_vo import (
    ShotGridApiModel,
    ShotGridLockVersionModel,
    ShotGridPageQueryModel,
)

SQL_BIGINT_MAX = 9_223_372_036_854_775_807
SQL_INTEGER_MAX = 2_147_483_647
MAX_ANNOTATION_JSON_BYTES = 64 * 1024
MAX_ANNOTATION_ITEMS = 100
MAX_ANNOTATION_POINTS_PER_ITEM = 512
MAX_ANNOTATION_TOTAL_POINTS = 4096
SAFE_ANNOTATION_TYPE = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,31}$')
SAFE_ANNOTATION_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$')
HTML_TAG = re.compile(r'</?[A-Za-z][^>]*>')

VersionStatus = Literal['pending_review', 'rejected', 'final']
TaskStatus = Literal['not_started', 'in_progress', 'pending_review', 'revision', 'completed']
ReviewActionType = Literal['approve', 'reject', 'defer']
ReviewListStatus = Literal['draft', 'active', 'completed', 'archived']
ReviewListMode = Literal['auto_single', 'manual_batch']
NoteStatus = Literal['open', 'resolved']
IssueVerificationResult = Literal['resolved', 'still_present']


def _reject_embedded_payload(value: str, *, field_name: str) -> str:
    """拒绝批注字段中的 HTML 和可内嵌二进制 URL。"""
    normalized = value.strip()
    lowered = normalized.casefold()
    if lowered.startswith(('data:', 'blob:')) or HTML_TAG.search(normalized):
        raise ValueError(f'{field_name} 不能包含 HTML、Data URL 或 Blob URL')
    return normalized


class ShotGridAnnotationPointModel(ShotGridApiModel):
    """归一化批注坐标。"""

    model_config = ConfigDict(extra='forbid')

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class ShotGridAnnotationItemModel(ShotGridApiModel):
    """单个结构化批注；类型保持安全、可扩展字符串。"""

    model_config = ConfigDict(extra='forbid')

    annotation_id: str = Field(alias='id', min_length=1, max_length=100)
    annotation_type: str = Field(alias='type', min_length=1, max_length=32)
    color: str | None = Field(default=None, max_length=32)
    stroke_width: float | None = Field(default=None, ge=0, le=1)
    points: list[ShotGridAnnotationPointModel] = Field(
        default_factory=list,
        max_length=MAX_ANNOTATION_POINTS_PER_ITEM,
    )
    text: str | None = Field(default=None, max_length=1000)

    @field_validator('annotation_id', mode='before')
    @classmethod
    def validate_annotation_id(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError('批注ID必须是字符串')
        normalized = _reject_embedded_payload(value, field_name='批注ID')
        if not SAFE_ANNOTATION_ID.fullmatch(normalized):
            raise ValueError('批注ID包含不安全字符')
        return normalized

    @field_validator('annotation_type', mode='before')
    @classmethod
    def validate_annotation_type(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError('批注类型必须是字符串')
        normalized = _reject_embedded_payload(value, field_name='批注类型')
        if not SAFE_ANNOTATION_TYPE.fullmatch(normalized):
            raise ValueError('批注类型包含不安全字符')
        return normalized

    @field_validator('color', 'text', mode='before')
    @classmethod
    def validate_optional_safe_text(cls, value: object, info: Any) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f'{info.field_name} 必须是字符串')
        normalized = _reject_embedded_payload(value, field_name=info.field_name)
        return normalized or None


class ShotGridAnnotationsModel(ShotGridApiModel):
    """版本画面批注载荷。"""

    model_config = ConfigDict(extra='forbid')

    schema_version: Literal[1] = Field(default=1)
    source_width: int = Field(gt=0, le=100_000)
    source_height: int = Field(gt=0, le=100_000)
    items: list[ShotGridAnnotationItemModel] = Field(default_factory=list, max_length=MAX_ANNOTATION_ITEMS)

    @model_validator(mode='after')
    def validate_complexity(self) -> 'ShotGridAnnotationsModel':
        total_points = sum(len(item.points) for item in self.items)
        if total_points > MAX_ANNOTATION_TOTAL_POINTS:
            raise ValueError('批注总点数超过限制')
        payload = self.model_dump(mode='json', by_alias=True)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        if len(encoded) > MAX_ANNOTATION_JSON_BYTES:
            raise ValueError('批注JSON超过大小限制')
        return self


class ShotGridVersionListQueryModel(ShotGridPageQueryModel):
    """任务版本分页查询。"""

    version_status: VersionStatus | None = Field(default=None)
    order_by_column: Literal['versionNo', 'submittedTime'] = Field(default='versionNo')


class ShotGridVersionFileModel(ShotGridApiModel):
    """版本文件的安全读取模型。"""

    file_id: str
    original_name: str
    business_file_name: str
    role: str
    is_primary: bool
    sort_order: int
    content_type: str | None = None
    file_size: int
    url: str


class ShotGridAutoReviewListSummaryModel(ShotGridApiModel):
    """自动单版本审核单摘要。"""

    review_list_id: int
    review_list_name: str
    review_status: ReviewListStatus
    lock_version: int


class ShotGridVersionListItemModel(ShotGridApiModel):
    """不可覆盖版本列表项。"""

    version_id: int
    project_id: int
    task_id: int
    version_no: int
    version_number: str
    version_status: VersionStatus
    changelog: str
    submitted_by: int
    submitter_name: str | None = None
    submitted_time: datetime
    generated_at_ms: int
    lock_version: int


class ShotGridVersionDetailModel(ShotGridVersionListItemModel):
    """版本详情；内部存储路径不进入响应。"""

    ai_params: dict[str, Any] | list[Any] | None = None
    files: list[ShotGridVersionFileModel] = Field(default_factory=list)
    media_derivation_status: Literal['pending', 'processing', 'completed', 'failed'] | None = None
    auto_review_list: ShotGridAutoReviewListSummaryModel | None = None


class ShotGridReviewListQueryModel(ShotGridPageQueryModel):
    """项目审核单分页查询。"""

    review_status: ReviewListStatus | None = Field(default=None)
    review_mode: ReviewListMode | None = Field(default=None)
    task_id: int | None = Field(default=None, gt=0, le=SQL_BIGINT_MAX)
    version_id: int | None = Field(default=None, gt=0, le=SQL_BIGINT_MAX)
    order_by_column: Literal['createTime', 'reviewDate'] = Field(default='createTime')


class ShotGridReviewListItemModel(ShotGridApiModel):
    """审核单列表项；人工批量审核单没有单一版本。"""

    review_list_id: int
    project_id: int
    project_code: str | None = None
    project_name: str | None = None
    review_list_name: str
    description: str | None = None
    review_date: date | None = None
    review_mode: ReviewListMode
    review_status: ReviewListStatus
    auto_version_id: int | None = None
    task_id: int | None = None
    version_no: int | None = None
    version_number: str | None = None
    version_status: VersionStatus | None = None
    version_count: int = 0
    thumbnail: dict[str, str] | None = None
    media_derivation_status: Literal['pending', 'processing', 'completed', 'failed'] | None = None
    lock_version: int
    create_time: datetime


class ShotGridReviewListDetailModel(ShotGridReviewListItemModel):
    """审核单详情；自动单保留 version，人工单返回有序 versions。"""

    version: ShotGridVersionListItemModel | None = None
    versions: list[ShotGridVersionListItemModel] = Field(default_factory=list)


class ShotGridManualReviewListCreateModel(ShotGridApiModel):
    """创建人工批量审核单草稿。"""

    model_config = ConfigDict(extra='forbid')

    review_list_name: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=10_000)
    review_date: date | None = None
    version_ids: list[int] = Field(default_factory=list, max_length=200)

    @field_validator('review_list_name', 'description', mode='before')
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('审核单文本字段必须是字符串')
        normalized = value.strip()
        return normalized or None

    @field_validator('version_ids')
    @classmethod
    def validate_initial_version_ids(cls, value: list[int]) -> list[int]:
        if any(item <= 0 or item > SQL_BIGINT_MAX for item in value) or len(set(value)) != len(value):
            raise ValueError('版本ID必须为不重复的正整数')
        return value


class ShotGridManualReviewListUpdateModel(ShotGridManualReviewListCreateModel, ShotGridLockVersionModel):
    """修改人工批量审核单草稿。"""


class ShotGridManualReviewListVersionsModel(ShotGridLockVersionModel):
    """向人工审核单加入版本。"""

    model_config = ConfigDict(extra='forbid')

    version_ids: list[int] = Field(min_length=1, max_length=200)

    @field_validator('version_ids')
    @classmethod
    def validate_version_ids(cls, value: list[int]) -> list[int]:
        if any(item <= 0 or item > SQL_BIGINT_MAX for item in value) or len(set(value)) != len(value):
            raise ValueError('版本ID必须为不重复的正整数')
        return value


class ShotGridManualReviewListOrderItemModel(ShotGridApiModel):
    model_config = ConfigDict(extra='forbid')

    version_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    sort_order: int = Field(ge=0, le=SQL_INTEGER_MAX)


class ShotGridManualReviewListOrderModel(ShotGridLockVersionModel):
    """完整替换人工审核单版本顺序。"""

    model_config = ConfigDict(extra='forbid')

    versions: list[ShotGridManualReviewListOrderItemModel] = Field(min_length=1, max_length=200)

    @field_validator('versions')
    @classmethod
    def validate_versions(
        cls, value: list[ShotGridManualReviewListOrderItemModel]
    ) -> list[ShotGridManualReviewListOrderItemModel]:
        version_ids = [item.version_id for item in value]
        sort_orders = [item.sort_order for item in value]
        if len(set(version_ids)) != len(value) or len(set(sort_orders)) != len(value):
            raise ValueError('版本ID和排序值不能重复')
        if sorted(sort_orders) != list(range(len(value))):
            raise ValueError('排序值必须从 0 开始连续递增')
        return value


class ShotGridNoteCreateModel(ShotGridApiModel):
    """创建绑定当前版本的修改问题。"""

    model_config = ConfigDict(extra='forbid')

    content: str | None = Field(default=None, max_length=10_000)
    media_time_ms: int | None = Field(default=None, ge=0, le=SQL_BIGINT_MAX)
    annotations: ShotGridAnnotationsModel | None = None

    @field_validator('content', mode='before')
    @classmethod
    def normalize_content(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('审核意见必须是字符串')
        return value.strip() or None

    @model_validator(mode='after')
    def require_content_or_annotations(self) -> 'ShotGridNoteCreateModel':
        if self.content or (self.annotations is not None and self.annotations.items):
            return self
        raise ValueError('修改问题必须填写文字内容或至少添加一项画面标注')


class ShotGridNoteModel(ShotGridApiModel):
    """兼容内部命名的跨版本修改问题。"""

    note_id: int
    project_id: int
    version_id: int
    origin_version_number: str
    reviewer_user_id: int
    reviewer_name: str | None = None
    content: str | None = None
    media_time_ms: int | None = None
    annotations: ShotGridAnnotationsModel | None = None
    note_status: NoteStatus
    resolved_in_version_id: int | None = None
    resolved_in_version_number: str | None = None
    create_time: datetime
    update_time: datetime


class ShotGridIssueResponseModel(ShotGridApiModel):
    """某个正式版本随提交保存的问题处理说明。"""

    response_id: int
    submission_id: int
    version_id: int | None = None
    version_number: str | None = None
    response_text: str
    responded_by: int
    responder_name: str | None = None
    create_time: datetime


class ShotGridIssueVerificationModel(ShotGridApiModel):
    """审核人对某版是否修复问题的不可变确认。"""

    verification_id: int
    checked_version_id: int
    checked_version_number: str
    result: IssueVerificationResult
    comment: str | None = None
    reviewer_user_id: int
    reviewer_name: str | None = None
    create_time: datetime


class ShotGridIssueDetailModel(ShotGridApiModel):
    """包含处理说明与确认历史的完整问题。"""

    issue_id: int
    project_id: int
    origin_version_id: int
    origin_version_number: str
    reviewer_user_id: int
    reviewer_name: str | None = None
    content: str | None = None
    media_time_ms: int | None = None
    annotations: ShotGridAnnotationsModel | None = None
    status: NoteStatus
    resolved_in_version_id: int | None = None
    resolved_in_version_number: str | None = None
    pending_version_id: int | None = None
    pending_version_number: str | None = None
    create_time: datetime
    update_time: datetime
    responses: list[ShotGridIssueResponseModel] = Field(default_factory=list)
    verifications: list[ShotGridIssueVerificationModel] = Field(default_factory=list)


class ShotGridReviewVersionSummaryModel(ShotGridApiModel):
    version_id: int
    version_no: int
    version_number: str
    version_status: VersionStatus
    lock_version: int


class ShotGridCarriedIssueModel(ShotGridIssueDetailModel):
    current_version_response: ShotGridIssueResponseModel


class ShotGridReviewContextModel(ShotGridApiModel):
    """审核当前版本所需的历史问题与本版新问题。"""

    current_version: ShotGridReviewVersionSummaryModel
    carried_issues: list[ShotGridCarriedIssueModel] = Field(default_factory=list)
    current_version_issues: list[ShotGridIssueDetailModel] = Field(default_factory=list)


class ShotGridIssueVerificationInputModel(ShotGridApiModel):
    """审核动作中的逐条问题确认。"""

    model_config = ConfigDict(extra='forbid')

    issue_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    result: IssueVerificationResult
    comment: str | None = Field(default=None, max_length=1000)

    @field_validator('comment', mode='before')
    @classmethod
    def normalize_comment(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('问题确认说明必须是字符串')
        return value.strip() or None

    @model_validator(mode='after')
    def validate_comment_for_result(self) -> 'ShotGridIssueVerificationInputModel':
        if self.result == 'resolved':
            self.comment = None
        return self


class ShotGridReviewActionCreateModel(ShotGridLockVersionModel):
    """提交版本审核动作。"""

    model_config = ConfigDict(extra='forbid')

    action_type: ReviewActionType
    reason: str | None = Field(default=None, max_length=1000)
    issue_verifications: list[ShotGridIssueVerificationInputModel] = Field(default_factory=list, max_length=200)

    @field_validator('reason', mode='before')
    @classmethod
    def normalize_reason(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('审核原因必须是字符串')
        normalized = value.strip()
        return normalized or None

    @model_validator(mode='after')
    def validate_issue_verifications(self) -> 'ShotGridReviewActionCreateModel':
        issue_ids = [item.issue_id for item in self.issue_verifications]
        if len(issue_ids) != len(set(issue_ids)):
            raise ValueError('issueVerifications 不能包含重复问题')
        if self.action_type == 'defer' and self.issue_verifications:
            raise ValueError('稍后决定不能提交问题确认结果')
        return self


class ShotGridReviewActionQueryModel(ShotGridPageQueryModel):
    """版本审核动作历史分页查询。"""

    action_type: ReviewActionType | None = None
    order_by_column: Literal['createTime'] = Field(default='createTime')


class ShotGridReviewActionModel(ShotGridApiModel):
    """不可变审核动作历史。"""

    action_id: int
    project_id: int
    version_id: int
    reviewer_user_id: int
    reviewer_name: str | None = None
    action_type: ReviewActionType
    from_status: VersionStatus
    to_status: VersionStatus
    reason: str | None = None
    create_time: datetime


class ShotGridReviewActionResultModel(ShotGridReviewActionModel):
    """审核动作提交结果快照。"""

    task_id: int
    task_status: TaskStatus
    auto_review_list_id: int
    review_status: ReviewListStatus
    lock_version: int
    replayed: bool = False

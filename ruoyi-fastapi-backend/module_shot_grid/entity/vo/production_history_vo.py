from datetime import date, datetime
from typing import Literal

from pydantic import Field

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel

ProductionHistorySubjectType = Literal['shot', 'asset']
ProductionHistoryLaneType = Literal['shot', 'assetItem']
ProductionHistoryStage = Literal['created', 'assigned', 'production', 'review', 'revision', 'final']
ProductionHistoryEvidenceLevel = Literal['confirmed', 'inferred']
ProductionHistoryEventType = Literal[
    'subject_created',
    'subject_imported',
    'lane_created',
    'task_created',
    'version_cycle',
]
ProductionHistoryResourceType = Literal[
    'shot',
    'asset',
    'assetItem',
    'importBatch',
    'task',
    'version',
    'reviewList',
    'issue',
]


class ShotGridProductionHistoryActorModel(ShotGridApiModel):
    """制作履历中的平台账号安全摘要。"""

    user_id: int | None = None
    user_name: str | None = None
    nick_name: str | None = None


class ShotGridProductionHistoryResourceRefModel(ShotGridApiModel):
    """履历事件指向的真实领域资源，不携带前端路由。"""

    resource_type: ProductionHistoryResourceType
    resource_id: int


class ShotGridProductionHistoryFileModel(ShotGridApiModel):
    """版本文件安全摘要；NAS 路径及物理存储信息不得返回。"""

    file_id: str
    business_file_name: str
    file_role: str
    is_primary: bool
    content_type: str | None = None
    file_size: int


class ShotGridProductionHistoryReviewListModel(ShotGridApiModel):
    review_list_id: int
    review_list_name: str
    review_status: Literal['draft', 'active', 'completed', 'archived']


class ShotGridProductionHistoryReviewActionModel(ShotGridApiModel):
    action_id: int
    action_type: Literal['approve', 'reject', 'defer']
    from_status: Literal['pending_review', 'rejected', 'final']
    to_status: Literal['pending_review', 'rejected', 'final']
    reason: str | None = None
    reviewer: ShotGridProductionHistoryActorModel
    create_time: datetime


class ShotGridProductionHistoryIssueModel(ShotGridApiModel):
    issue_id: int
    origin_version_id: int
    origin_version_number: str
    reviewer: ShotGridProductionHistoryActorModel
    content: str | None = None
    media_time_ms: int | None = None
    has_annotations: bool
    annotation_count: int = Field(ge=0)
    status: Literal['open', 'resolved']
    resolved_in_version_id: int | None = None
    resolved_in_version_number: str | None = None
    create_time: datetime
    update_time: datetime


class ShotGridProductionHistoryIssueResponseModel(ShotGridApiModel):
    response_id: int
    issue_id: int
    origin_version_id: int
    origin_version_number: str
    response_text: str
    responder: ShotGridProductionHistoryActorModel
    create_time: datetime


class ShotGridProductionHistoryIssueVerificationModel(ShotGridApiModel):
    verification_id: int
    issue_id: int
    origin_version_id: int
    origin_version_number: str
    checked_version_id: int
    checked_version_number: str
    result: Literal['resolved', 'still_present']
    comment: str | None = None
    reviewer: ShotGridProductionHistoryActorModel
    create_time: datetime


class ShotGridProductionHistoryVersionCycleModel(ShotGridApiModel):
    """一个不可覆盖版本及其审核闭环事实。"""

    version_id: int
    version_no: int
    version_number: str
    version_status: Literal['pending_review', 'rejected', 'final']
    changelog: str
    submitted_time: datetime
    submitter: ShotGridProductionHistoryActorModel
    primary_file: ShotGridProductionHistoryFileModel | None = None
    thumbnail_file: ShotGridProductionHistoryFileModel | None = None
    auto_review_list: ShotGridProductionHistoryReviewListModel | None = None
    review_actions: list[ShotGridProductionHistoryReviewActionModel] = Field(default_factory=list)
    source_issues: list[ShotGridProductionHistoryIssueModel] = Field(default_factory=list)
    issue_responses: list[ShotGridProductionHistoryIssueResponseModel] = Field(default_factory=list)
    issue_verifications: list[ShotGridProductionHistoryIssueVerificationModel] = Field(default_factory=list)


class ShotGridProductionHistoryImportBatchModel(ShotGridApiModel):
    batch_id: int
    original_file_name: str
    import_type: Literal['shot', 'asset']
    batch_status: Literal['previewed', 'committing', 'committed', 'failed', 'expired']
    committed_by: ShotGridProductionHistoryActorModel | None = None
    committed_time: datetime | None = None


class ShotGridProductionHistoryEventModel(ShotGridApiModel):
    """前端可按时间正序渲染的结构化履历事件。"""

    event_id: str
    event_type: ProductionHistoryEventType
    occurred_at: datetime
    evidence_level: ProductionHistoryEvidenceLevel
    title: str
    description: str | None = None
    lane_ids: list[int] = Field(default_factory=list)
    actor: ShotGridProductionHistoryActorModel | None = None
    resource_ref: ShotGridProductionHistoryResourceRefModel
    import_batch: ShotGridProductionHistoryImportBatchModel | None = None
    version_cycle: ShotGridProductionHistoryVersionCycleModel | None = None


class ShotGridProductionHistoryTaskModel(ShotGridApiModel):
    task_id: int
    task_name: str
    task_kind: Literal['shot_video', 'asset_image']
    task_status: Literal['not_started', 'preparing', 'in_progress', 'pending_review', 'revision', 'completed']
    priority: Literal['low', 'normal', 'high', 'urgent']
    due_date: date | None = None
    assignee: ShotGridProductionHistoryActorModel
    create_time: datetime
    update_time: datetime


class ShotGridProductionHistoryVersionRefModel(ShotGridApiModel):
    version_id: int
    version_no: int
    version_number: str
    version_status: Literal['pending_review', 'rejected', 'final']
    submitted_time: datetime


class ShotGridProductionHistoryLaneModel(ShotGridApiModel):
    lane_id: int
    lane_type: ProductionHistoryLaneType
    name: str
    sort_order: int
    lifecycle_status: Literal['active', 'archived']
    source_import_batch_id: int | None = None
    current_stage: ProductionHistoryStage
    active_step: int = Field(ge=0, le=5)
    task: ShotGridProductionHistoryTaskModel | None = None
    latest_version: ShotGridProductionHistoryVersionRefModel | None = None
    final_version: ShotGridProductionHistoryVersionRefModel | None = None
    version_count: int = Field(ge=0)
    review_action_count: int = Field(ge=0)
    rejection_count: int = Field(ge=0)
    issue_count: int = Field(ge=0)
    open_issue_count: int = Field(ge=0)


class ShotGridProductionHistorySubjectModel(ShotGridApiModel):
    subject_type: ProductionHistorySubjectType
    subject_id: int
    project_id: int
    project_code: str
    project_name: str
    code: str | None = None
    name: str
    description: str | None = None
    lifecycle_status: Literal['active', 'archived']
    asset_type: Literal['Character', 'Environment', 'Prop'] | None = None
    thumbnail_file_id: str | None = None
    created_at: datetime


class ShotGridProductionHistorySummaryModel(ShotGridApiModel):
    """当前阶段只聚合活动 lane；其余累计指标包含可追溯的已归档 lane 历史。"""

    current_stage: ProductionHistoryStage
    active_step: int = Field(ge=0, le=5)
    lane_count: int = Field(ge=0)
    task_count: int = Field(ge=0)
    version_count: int = Field(ge=0)
    review_action_count: int = Field(ge=0)
    rejection_count: int = Field(ge=0)
    issue_count: int = Field(ge=0)
    open_issue_count: int = Field(ge=0)
    resolved_issue_count: int = Field(ge=0)
    final_version_count: int = Field(ge=0)


class ShotGridProductionHistoryModel(ShotGridApiModel):
    subject: ShotGridProductionHistorySubjectModel
    summary: ShotGridProductionHistorySummaryModel
    lanes: list[ShotGridProductionHistoryLaneModel] = Field(default_factory=list)
    events: list[ShotGridProductionHistoryEventModel] = Field(default_factory=list)

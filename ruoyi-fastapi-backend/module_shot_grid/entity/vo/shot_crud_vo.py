from datetime import date, datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel, ShotGridLockVersionModel, ShotGridPageQueryModel

ShotStatus = Literal['unassigned', 'not_started', 'preparing', 'in_progress', 'reviewing', 'revision', 'completed']
DirectoryStatus = Literal['not_created', 'pending', 'ready', 'failed']
AssetType = Literal['Character', 'Environment', 'Prop']
SQL_BIGINT_MAX = 9_223_372_036_854_775_807
SQL_INTEGER_MAX = 2_147_483_647


def _strip_required_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError('镜头描述必须是字符串')
    normalized = value.strip()
    if not normalized:
        raise ValueError('镜头描述不能为空')
    return normalized


def _strip_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('镜头文本字段必须是字符串')
    normalized = value.strip()
    return normalized or None


class ShotGridShotListQueryModel(ShotGridPageQueryModel):
    """镜头分页列表筛选与白名单排序。"""

    episode_id: int | None = Field(default=None, gt=0, le=SQL_BIGINT_MAX, description='集ID')
    scene_id: int | None = Field(default=None, gt=0, le=SQL_BIGINT_MAX, description='场次ID')
    shot_status: ShotStatus | None = Field(default=None, description='镜头聚合状态')
    assignee_user_id: int | None = Field(
        default=None,
        gt=0,
        le=SQL_BIGINT_MAX,
        description='制作人用户ID',
    )
    asset_id: int | None = Field(default=None, gt=0, le=SQL_BIGINT_MAX, description='关联资产ID')
    order_by_column: Literal[
        'episodeNo',
        'sceneNo',
        'shotNo',
        'sortOrder',
        'durationMs',
        'updateTime',
    ] = Field(default='sortOrder', description='排序字段')
    is_asc: Literal['ascending', 'descending'] = Field(default='ascending', description='排序方向')


class ShotGridShotWriteFieldsModel(ShotGridApiModel):
    """镜头创建与修改共享的可写字段。"""

    model_config = ConfigDict(extra='forbid')

    scene_id: int = Field(gt=0, le=SQL_BIGINT_MAX, description='所属场次ID')
    shot_no: int | None = Field(
        default=None,
        gt=0,
        le=SQL_INTEGER_MAX,
        description='兼容字段；Sxxx 由服务端按场内位置生成，业务前端不再提交',
    )
    duration_ms: int = Field(default=0, ge=0, le=SQL_BIGINT_MAX, description='镜头时长（毫秒）')
    shot_size: str | None = Field(default=None, max_length=40, description='景别')
    camera_position: str | None = Field(default=None, max_length=100, description='机位')
    camera_movement: str | None = Field(default=None, max_length=100, description='镜头运动')
    focal_length: str | None = Field(default=None, max_length=50, description='焦段原始文本')
    description: str = Field(min_length=1, description='镜头制作内容描述')
    dialogue: str | None = Field(default=None, description='台词或对白')
    sound_effect: str | None = Field(default=None, description='音效说明')
    color_reference: str | None = Field(default=None, description='色调参考说明')
    remark: str | None = Field(default=None, max_length=500, description='备注')
    sort_order: int | None = Field(
        default=None,
        ge=0,
        le=SQL_INTEGER_MAX,
        description='兼容内部排序键；业务前端不直接维护',
    )
    sequence_position: int | None = Field(
        default=None,
        ge=1,
        le=SQL_INTEGER_MAX,
        description='场内镜头位置，从 1 开始；该位置同时决定 Sxxx',
    )
    asset_ids: list[int] = Field(default_factory=list, description='完整关联资产ID集合')

    @model_validator(mode='after')
    def validate_sequence_input(self) -> 'ShotGridShotWriteFieldsModel':
        if self.sort_order is not None and self.sequence_position is not None:
            raise ValueError('sortOrder 与 sequencePosition 不能同时提交')
        if self.shot_no is not None and self.sequence_position is not None and self.shot_no != self.sequence_position:
            raise ValueError('shotNo 已与 sequencePosition 合并，两者同时提交时必须相同')
        return self

    @field_validator('description', mode='before')
    @classmethod
    def normalize_description(cls, value: Any) -> str:
        return _strip_required_text(value)

    @field_validator(
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
    def normalize_optional_text(cls, value: Any) -> str | None:
        return _strip_optional_text(value)

    @field_validator('asset_ids')
    @classmethod
    def validate_asset_ids(cls, value: list[int]) -> list[int]:
        if any(asset_id <= 0 or asset_id > SQL_BIGINT_MAX for asset_id in value):
            raise ValueError('资产ID必须是 PostgreSQL BIGINT 范围内的正整数')
        if len(value) != len(set(value)):
            raise ValueError('关联资产ID不能重复')
        return value


class ShotGridShotCreateModel(ShotGridShotWriteFieldsModel):
    """创建镜头请求。"""


class ShotGridShotUpdateModel(ShotGridShotWriteFieldsModel):
    """修改镜头请求；assetIds 是完整关系快照。"""

    lock_version: int = Field(ge=0, description='镜头乐观锁版本')
    asset_ids: list[int] = Field(description='完整关联资产ID集合')


class ShotGridShotReorderModel(ShotGridLockVersionModel):
    """调整镜头在所属场次中的业务位置。"""

    model_config = ConfigDict(extra='forbid')

    sequence_position: int = Field(ge=1, le=SQL_INTEGER_MAX, description='场内镜头位置，从 1 开始')


class ShotGridShotReorderResultModel(ShotGridApiModel):
    """镜头场内重排结果。"""

    shot_id: int
    shot_no: int | None = Field(default=None, ge=1, description='立即完成时的新场内镜头号')
    shot_code: str | None = Field(default=None, description='立即完成时的新 Sxxx')
    sequence_position: int = Field(ge=1)
    lock_version: int = Field(ge=0)
    operation_id: int | None = None
    operation_status: Literal['succeeded', 'pending'] = 'succeeded'
    storage_status: Literal['ready', 'migrating'] = 'ready'
    status_url: str | None = None


class ShotGridShotRenumberModel(ShotGridApiModel):
    """按当前顺序受理单场镜头连续编号。"""

    model_config = ConfigDict(extra='forbid')

    scene_id: int = Field(gt=0, le=SQL_BIGINT_MAX, description='待连续编号的场次ID')


class ShotGridShotRenumberResultModel(ShotGridApiModel):
    """单场连续编号受理结果；目录迁移成功后才切换数据库编号。"""

    scene_id: int
    shot_count: int = Field(ge=1)
    changed_count: int = Field(ge=0)
    operation_id: int | None = None
    operation_status: Literal['pending', 'succeeded']
    storage_status: Literal['migrating', 'ready']
    status_url: str | None = None


class ShotGridShotArchiveModel(ShotGridLockVersionModel):
    """归档镜头请求。"""

    model_config = ConfigDict(extra='forbid')


class ShotGridShotDeleteItemModel(ShotGridLockVersionModel):
    """批量删除中的镜头标识和乐观锁版本。"""

    shot_id: int = Field(gt=0, le=SQL_BIGINT_MAX)


class ShotGridShotBatchDeleteModel(ShotGridApiModel):
    """批量删除镜头；整个请求在同一事务内完成。"""

    model_config = ConfigDict(extra='forbid')

    items: list[ShotGridShotDeleteItemModel] = Field(min_length=1, max_length=200)

    @model_validator(mode='after')
    def validate_unique_shots(self) -> 'ShotGridShotBatchDeleteModel':
        shot_ids = [item.shot_id for item in self.items]
        if len(shot_ids) != len(set(shot_ids)):
            raise ValueError('批量删除不能包含重复镜头')
        return self


class ShotGridShotBatchDeleteResultModel(ShotGridApiModel):
    """镜头批量删除结果。"""

    deleted_shot_ids: list[int]
    deleted_count: int = Field(ge=1)


class ShotGridShotAssigneeModel(ShotGridApiModel):
    """镜头唯一任务的制作人摘要。"""

    user_id: int
    nick_name: str
    producer_code: str | None = None


class ShotGridShotAssetSummaryModel(ShotGridApiModel):
    """镜头关联资产摘要。"""

    asset_id: int
    asset_name: str
    asset_type: AssetType


class ShotGridShotSceneSummaryModel(ShotGridApiModel):
    """镜头所属集与场次摘要。"""

    episode_id: int
    episode_no: int
    episode_code: str
    scene_id: int
    scene_no: int
    scene_code: str
    scene_name: str | None = None


class ShotGridShotTaskSummaryModel(ShotGridApiModel):
    """镜头唯一视频任务摘要。"""

    task_id: int
    task_kind: Literal['shot_video']
    task_status: Literal['not_started', 'preparing', 'in_progress', 'pending_review', 'revision', 'completed']
    assignee: ShotGridShotAssigneeModel
    priority: Literal['low', 'normal', 'high', 'urgent']
    due_date: date | None = None
    expected_start_time: datetime | None = None
    expected_end_time: datetime | None = None
    lock_version: int


class ShotGridShotThumbnailModel(ShotGridApiModel):
    """镜头最新版本缩略图摘要。"""

    file_id: str
    name: str
    url: str


class ShotGridShotProxyMediaModel(ShotGridApiModel):
    """镜头最新版本代理视频摘要。"""

    file_id: str
    name: str
    url: str


class ShotGridShotLatestVersionModel(ShotGridApiModel):
    """镜头最新版本摘要。"""

    version_id: int
    version_number: str
    status: Literal['pending_review', 'rejected', 'final']
    business_file_name: str


class ShotGridShotLatestFeedbackModel(ShotGridApiModel):
    """镜头最新可见反馈摘要。"""

    note_id: int
    content: str
    note_status: Literal['open', 'resolved']
    create_time: datetime


class ShotGridShotListItemModel(ShotGridApiModel):
    """表格、卡片和故事板共用的镜头列表项。"""

    shot_id: int
    project_id: int
    episode_id: int
    episode_no: int
    episode_code: str
    scene_id: int
    scene_no: int
    scene_code: str
    scene_name: str | None = None
    shot_no: int
    shot_code: str
    storage_dir_name: str | None = None
    directory_status: DirectoryStatus
    duration_ms: int
    shot_size: str | None = None
    camera_position: str | None = None
    camera_movement: str | None = None
    focal_length: str | None = None
    description: str
    environment_assets: list[ShotGridShotAssetSummaryModel] = Field(default_factory=list)
    character_assets: list[ShotGridShotAssetSummaryModel] = Field(default_factory=list)
    dialogue: str | None = None
    sound_effect: str | None = None
    color_reference: str | None = None
    remark: str | None = None
    sort_order: int
    sequence_position: int = Field(ge=1)
    status: ShotStatus
    task_id: int | None = None
    task_lock_version: int | None = Field(default=None, ge=0)
    expected_start_time: datetime | None = None
    expected_end_time: datetime | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    assignee: ShotGridShotAssigneeModel | None = None
    thumbnail: ShotGridShotThumbnailModel | None = None
    proxy_media: ShotGridShotProxyMediaModel | None = None
    latest_version: ShotGridShotLatestVersionModel | None = None
    latest_feedback: ShotGridShotLatestFeedbackModel | None = None
    asset_count: int = Field(ge=0)
    lock_version: int = Field(ge=0)


class ShotGridShotDetailModel(ShotGridShotListItemModel):
    """镜头详情；历史版本和审核意见继续走独立分页接口。"""

    lifecycle_status: Literal['active', 'archived']
    scene: ShotGridShotSceneSummaryModel
    assets: list[ShotGridShotAssetSummaryModel] = Field(default_factory=list)
    task: ShotGridShotTaskSummaryModel | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    create_by: str
    create_time: datetime
    update_by: str
    update_time: datetime


class ShotGridShotArchiveResultModel(ShotGridApiModel):
    """镜头归档结果。"""

    shot_id: int
    lifecycle_status: Literal['archived'] = 'archived'
    lock_version: int = Field(ge=0)

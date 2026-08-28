from datetime import date, datetime
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from module_shot_grid.entity.vo.common_vo import (
    ShotGridApiModel,
    ShotGridLockVersionModel,
    ShotGridPageQueryModel,
)

AssetType = Literal['Character', 'Environment', 'Prop']
AssetWorkStatus = Literal['unassigned', 'not_started', 'preparing', 'in_progress', 'reviewing', 'revision', 'completed']
ASSET_ITEM_STATUSES = get_args(AssetWorkStatus)
DirectoryStatus = Literal['not_created', 'pending', 'ready', 'failed']
LifecycleStatus = Literal['active', 'archived']
TaskStatus = Literal['not_started', 'preparing', 'in_progress', 'pending_review', 'revision', 'completed']
SQL_INTEGER_MAX = 2_147_483_647
SQL_BIGINT_MAX = 9_223_372_036_854_775_807


class ShotGridAssetListQueryModel(ShotGridPageQueryModel):
    """资产分页查询。"""

    asset_type: AssetType | None = Field(default=None, description='资产类型')
    asset_status: AssetWorkStatus | None = Field(default=None, description='聚合制作状态')
    assignee_user_id: int | None = Field(
        default=None,
        gt=0,
        le=SQL_BIGINT_MAX,
        description='制作人用户ID',
    )
    order_by_column: Literal['assetName', 'assetType', 'sortOrder', 'updateTime'] = Field(
        default='sortOrder',
        description='排序字段',
    )


class ShotGridAssetItemWriteModel(ShotGridApiModel):
    """创建资产时携带的制作分项。"""

    model_config = ConfigDict(extra='forbid')

    production_item: str | None = Field(default=None, max_length=240, description='制作分项名称，可后补')
    description: str | None = Field(default=None, description='制作分项描述')
    sort_order: int = Field(default=0, ge=0, le=SQL_INTEGER_MAX, description='资产内排序')
    remark: str | None = Field(default=None, max_length=500, description='备注')

    @field_validator('production_item', 'description', 'remark', mode='before')
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('文本字段必须是字符串')
        normalized = value.strip()
        return normalized or None


class ShotGridAssetCreateModel(ShotGridApiModel):
    """创建资产及其首批制作分项。"""

    model_config = ConfigDict(extra='forbid')

    asset_type: AssetType = Field(description='资产类型')
    asset_name: str = Field(min_length=1, max_length=200, description='资产名称')
    description: str | None = Field(default=None, description='资产说明')
    sort_order: int = Field(default=0, ge=0, le=SQL_INTEGER_MAX, description='项目内排序')
    remark: str | None = Field(default=None, max_length=500, description='备注')
    items: list[ShotGridAssetItemWriteModel] = Field(min_length=1, max_length=200, description='制作分项')

    @field_validator('asset_name', mode='before')
    @classmethod
    def normalize_asset_name(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError('资产名称必须是字符串')
        return value.strip()

    @field_validator('description', 'remark', mode='before')
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('文本字段必须是字符串')
        normalized = value.strip()
        return normalized or None

    @model_validator(mode='after')
    def validate_named_items_unique(self) -> 'ShotGridAssetCreateModel':
        normalized_names = [item.production_item.casefold() for item in self.items if item.production_item is not None]
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError('同一资产内制作分项名称不能重复')
        return self


class ShotGridAssetUpdateModel(ShotGridLockVersionModel):
    """修改资产非身份主数据；类型、名称、目录和聚合状态均不可普通编辑。"""

    model_config = ConfigDict(extra='forbid')

    description: str | None = Field(default=None, description='资产说明')
    sort_order: int = Field(default=0, ge=0, le=SQL_INTEGER_MAX, description='项目内排序')
    remark: str | None = Field(default=None, max_length=500, description='备注')

    @field_validator('description', 'remark', mode='before')
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('文本字段必须是字符串')
        normalized = value.strip()
        return normalized or None


class ShotGridAssetArchiveModel(ShotGridLockVersionModel):
    """归档资产或制作分项。"""

    model_config = ConfigDict(extra='forbid')

    reason: str = Field(min_length=1, max_length=500, description='归档原因')

    @field_validator('reason', mode='before')
    @classmethod
    def normalize_reason(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError('归档原因必须是字符串')
        return value.strip()


class ShotGridAssetItemDeleteModel(ShotGridLockVersionModel):
    """删除尚未开始制作的分项。"""

    model_config = ConfigDict(extra='forbid')
    reason: str = Field(min_length=1, max_length=500, description='删除原因')

    @field_validator('reason', mode='before')
    @classmethod
    def normalize_reason(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError('删除原因必须是字符串')
        return value.strip()


class ShotGridAssetItemDeleteResultModel(ShotGridApiModel):
    """制作分项删除结果，父资产继续保留。"""

    project_id: int
    asset_id: int
    deleted_asset_item_id: int


class ShotGridAssetBatchDeleteItemModel(ShotGridApiModel):
    """批量删除中的资产及其锁版本。"""

    model_config = ConfigDict(extra='forbid')

    asset_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    lock_version: int = Field(ge=0)


class ShotGridAssetBatchDeleteModel(ShotGridApiModel):
    """批量删除未开始制作的资产。"""

    model_config = ConfigDict(extra='forbid')

    items: list[ShotGridAssetBatchDeleteItemModel] = Field(min_length=1, max_length=200)
    reason: str = Field(default='资产列表批量删除', min_length=1, max_length=500)

    @field_validator('reason', mode='before')
    @classmethod
    def normalize_reason(cls, value: object) -> object:
        return ShotGridAssetArchiveModel.normalize_reason(value)

    @model_validator(mode='after')
    def validate_unique_assets(self) -> 'ShotGridAssetBatchDeleteModel':
        asset_ids = [item.asset_id for item in self.items]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError('批量删除不能包含重复资产')
        return self


class ShotGridAssetBatchDeleteResultModel(ShotGridApiModel):
    """资产批量删除结果。"""

    deleted_asset_ids: list[int]
    deleted_count: int = Field(ge=1)


class ShotGridAssetItemCreateModel(ShotGridAssetItemWriteModel):
    """为已有资产新增制作分项。"""


class ShotGridAssetItemUpdateModel(ShotGridLockVersionModel):
    """部分修改制作分项；任务委派和要求只能通过任务接口维护。"""

    model_config = ConfigDict(extra='forbid')

    production_item: str | None = Field(default=None, max_length=240, description='制作分项名称，可显式清空')
    description: str | None = Field(default=None, description='制作分项描述，可显式清空')
    sort_order: int | None = Field(default=None, ge=0, le=SQL_INTEGER_MAX, description='资产内排序')
    remark: str | None = Field(default=None, max_length=500, description='备注，可显式清空')

    @field_validator('production_item', 'description', 'remark', mode='before')
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        return ShotGridAssetItemWriteModel.normalize_optional_text(value)

    @model_validator(mode='after')
    def reject_explicit_null_sort_order(self) -> 'ShotGridAssetItemUpdateModel':
        if 'sort_order' in self.model_fields_set and self.sort_order is None:
            raise ValueError('sortOrder 不能显式为空')
        return self


class ShotGridTaskSummaryModel(ShotGridApiModel):
    """资产制作分项的唯一任务摘要。"""

    task_id: int
    assignee_user_id: int
    assignee_name: str | None = None
    producer_code: str | None = None
    task_status: TaskStatus
    priority: Literal['low', 'normal', 'high', 'urgent']
    due_date: date | None = None
    requirements: str | None = None
    lock_version: int


class ShotGridVersionSummaryModel(ShotGridApiModel):
    """资产详情中的只读版本摘要。"""

    version_id: int
    version_no: int
    version_status: Literal['pending_review', 'rejected', 'final']
    submitted_time: datetime


class ShotGridAssetThumbnailModel(ShotGridApiModel):
    """资产或制作分项代表版本的受保护缩略图摘要。"""

    file_id: str
    name: str
    url: str


class ShotGridAssetItemModel(ShotGridApiModel):
    """资产制作分项详情。"""

    asset_item_id: int
    project_id: int
    asset_id: int
    production_item: str | None = None
    description: str | None = None
    sort_order: int
    remark: str | None = None
    lifecycle_status: LifecycleStatus
    asset_status: AssetWorkStatus
    task: ShotGridTaskSummaryModel | None = None
    latest_version: ShotGridVersionSummaryModel | None = None
    final_version: ShotGridVersionSummaryModel | None = None
    thumbnail: ShotGridAssetThumbnailModel | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    lock_version: int
    create_time: datetime
    update_time: datetime


class ShotGridAssetItemStatusCountsModel(BaseModel):
    """活动制作分项数量；键使用状态字面量，不转换为 camelCase。"""

    unassigned: int = Field(default=0, ge=0)
    not_started: int = Field(default=0, ge=0)
    preparing: int = Field(default=0, ge=0)
    in_progress: int = Field(default=0, ge=0)
    reviewing: int = Field(default=0, ge=0)
    revision: int = Field(default=0, ge=0)
    completed: int = Field(default=0, ge=0)


class ShotGridAssetListItemModel(ShotGridApiModel):
    """资产列表项。"""

    asset_id: int
    project_id: int
    asset_type: AssetType
    asset_name: str
    description: str | None = None
    sort_order: int
    lifecycle_status: LifecycleStatus
    asset_status: AssetWorkStatus
    item_count: int = 0
    item_status_counts: ShotGridAssetItemStatusCountsModel = Field(default_factory=ShotGridAssetItemStatusCountsModel)
    usage_shot_count: int = 0
    assignee_user_ids: list[int] = Field(default_factory=list)
    thumbnail: ShotGridAssetThumbnailModel | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    directory_status: DirectoryStatus
    lock_version: int
    update_time: datetime


class ShotGridAssetDetailModel(ShotGridAssetListItemModel):
    """资产详情。"""

    storage_dir_name: str
    remark: str | None = None
    items: list[ShotGridAssetItemModel] = Field(default_factory=list)
    create_by: str
    create_time: datetime
    update_by: str

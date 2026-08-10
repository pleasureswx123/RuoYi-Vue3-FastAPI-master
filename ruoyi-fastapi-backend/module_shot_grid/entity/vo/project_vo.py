import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from common.vo import ResponseBaseModel
from module_shot_grid.entity.vo.common_vo import ShotGridApiModel, ShotGridPageQueryModel
from module_shot_grid.entity.vo.project_member_vo import ShotGridInitialMemberModel

ProjectStatus = Literal['preparing', 'active', 'completed', 'archived']
ProjectPhase = Literal['planning', 'asset_production', 'shot_production', 'review', 'delivery', 'completed']
AspectRatio = Literal['16:9', '21:9', '2.39:1', '9:16', '1:1']
SQL_BIGINT_MAX = 9_223_372_036_854_775_807


class ShotGridProjectListQueryModel(ShotGridPageQueryModel):
    """项目范围分页查询。"""

    project_status: ProjectStatus | None = Field(default=None, description='项目状态')
    order_by_column: Literal['projectCode', 'projectName', 'deliveryDate', 'createTime'] = Field(
        default='createTime', description='排序字段'
    )
    scope: Literal['all'] | None = Field(default=None, description='显式跨项目范围')


class ShotGridProjectCreateModel(ShotGridApiModel):
    """创建项目请求。"""

    project_code: str = Field(min_length=2, max_length=12, description='项目代号及文件名前缀')
    project_name: str = Field(min_length=1, max_length=200, description='项目名称')
    project_type: Literal['ai_short_film'] = Field(default='ai_short_film', description='项目类型')
    project_description: str | None = Field(default=None, description='项目描述')
    aspect_ratio: AspectRatio = Field(default='16:9', description='画幅')
    planned_duration_ms: int | None = Field(
        default=None,
        ge=0,
        le=SQL_BIGINT_MAX,
        description='计划总时长（毫秒）',
    )
    delivery_date: date | None = Field(default=None, description='交付日期')
    storage_root_id: int = Field(gt=0, description='NAS 根目录ID')
    project_directory_name: str = Field(min_length=1, max_length=240, description='项目目录名称')
    director_user_ids: list[int] = Field(min_length=1, description='初始项目总监用户ID')
    members: list[ShotGridInitialMemberModel] = Field(default_factory=list, description='初始项目成员')
    remark: str | None = Field(default=None, max_length=500, description='备注')

    @field_validator('project_code', mode='before')
    @classmethod
    def normalize_project_code(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError('项目代号必须是字符串')
        normalized = value.strip().upper()
        if not re.fullmatch(r'[A-Z0-9]{2,12}', normalized):
            raise ValueError('项目代号必须为 2—12 位大写英文字母或数字')
        return normalized

    @field_validator('project_name', 'project_directory_name', mode='before')
    @classmethod
    def strip_required_text(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError('项目名称和目录名称必须是字符串')
        return value.strip()

    @field_validator('project_description', 'remark', mode='before')
    @classmethod
    def strip_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('项目描述和备注必须是字符串')
        normalized = value.strip()
        return normalized or None

    @field_validator('director_user_ids')
    @classmethod
    def validate_director_ids(cls, value: list[int]) -> list[int]:
        if any(user_id <= 0 for user_id in value):
            raise ValueError('项目总监用户ID必须为正整数')
        if len(value) != len(set(value)):
            raise ValueError('项目总监用户ID不能重复')
        return value

    @model_validator(mode='after')
    def validate_member_identity(self) -> 'ShotGridProjectCreateModel':
        member_ids = [member.user_id for member in self.members]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError('初始项目成员不能重复')
        overlap = sorted(set(self.director_user_ids).intersection(member_ids))
        if overlap:
            raise ValueError(f'项目总监与初始成员重复：{overlap}')
        producer_codes = [member.producer_code for member in self.members if member.producer_code is not None]
        if len(producer_codes) != len(set(producer_codes)):
            raise ValueError('同一项目内制作人缩写不能重复')
        return self


class ShotGridProjectCreationAcceptedModel(ShotGridApiModel):
    """项目创建已受理结果。"""

    project_id: int = Field(description='项目ID')
    project_status: ProjectStatus = Field(description='项目状态')
    storage_status: Literal['initializing', 'ready', 'failed', 'migrating'] = Field(description='存储状态')
    status_url: str = Field(description='存储状态查询地址')


class ShotGridProjectCreationAcceptedResponseModel(ResponseBaseModel):
    """真实 HTTP 202 对应的响应模型。"""

    code: Literal[202] = Field(default=202, description='响应码')
    msg: str = Field(default='项目目录正在初始化', description='响应信息')
    data: ShotGridProjectCreationAcceptedModel = Field(description='受理结果')


class ShotGridProjectStorageStatusModel(ShotGridApiModel):
    """项目存储初始化状态与安全路径快照。"""

    project_id: int = Field(description='项目ID')
    storage_status: Literal['initializing', 'ready', 'failed', 'migrating'] = Field(description='存储状态')
    project_path_snapshot: str | None = Field(default=None, description='按项目角色安全返回的完整 UNC 项目路径快照')
    initialized_time: datetime | None = Field(default=None, description='初始目录就绪时间')
    last_error_key: str | None = Field(default=None, description='最近稳定错误键')
    last_error_message: str | None = Field(default=None, description='最近净化错误摘要')
    lock_version: int = Field(ge=0, description='乐观锁版本')
    update_time: datetime = Field(description='最近更新时间')


class ShotGridProjectOverviewModel(ShotGridApiModel):
    """项目概览统一聚合结果。"""

    current_phase: ProjectPhase = Field(description='项目当前阶段')
    total_episodes: int = 0
    total_scenes: int = 0
    total_shots: int = 0
    total_assets: int = 0
    total_asset_items: int = 0
    completed_shots: int = 0
    completed_assets: int = 0
    completed_asset_items: int = 0
    pending_review_shots: int = 0
    pending_review_assets: int = 0
    pending_review_asset_items: int = 0
    revision_shots: int = 0
    revision_assets: int = 0
    revision_asset_items: int = 0
    unassigned_shots: int = 0
    unassigned_assets: int = 0
    unassigned_asset_items: int = 0
    overall_progress: float = Field(default=0.0, ge=0, le=100)


class ShotGridProjectListItemModel(ShotGridProjectOverviewModel):
    """项目列表项。"""

    project_id: int
    project_code: str
    project_name: str
    project_type: str
    project_type_name: str
    aspect_ratio: AspectRatio
    planned_duration_ms: int | None = None
    delivery_date: date | None = None
    project_status: ProjectStatus
    storage_status: Literal['initializing', 'ready', 'failed', 'migrating']
    my_project_role: Literal['director', 'creator'] | None = None
    lock_version: int


class ShotGridProjectDetailModel(ShotGridProjectListItemModel):
    """项目详情。"""

    project_description: str | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    create_by: str
    create_time: datetime
    update_by: str
    update_time: datetime
    remark: str | None = None

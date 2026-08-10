from datetime import datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from common.vo import PageModel, ResponseBaseModel
from module_shot_grid.entity.vo.common_vo import ShotGridApiModel, ShotGridLockVersionModel, ShotGridPageQueryModel

LifecycleStatus = Literal['active', 'archived']
DirectoryStatus = Literal['pending', 'ready', 'failed']
SortDirection = Literal['ascending', 'descending']


def _normalize_optional_text(value: Any) -> str | None:
    """把可选文本统一规范为去首尾空白的字符串或空值。"""

    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('文本字段必须是字符串')
    normalized = value.strip()
    return normalized or None


class ShotGridEpisodeQueryModel(ShotGridPageQueryModel):
    """集分页查询。"""

    lifecycle_status: LifecycleStatus | None = Field(default=None, description='生命周期状态')
    order_by_column: Literal['episodeNo', 'episodeName', 'sortOrder', 'createTime'] = Field(
        default='sortOrder',
        description='排序字段',
    )
    is_asc: SortDirection = Field(default='ascending', description='排序方向')


class ShotGridEpisodeCreateModel(ShotGridApiModel):
    """创建集请求。"""

    model_config = ConfigDict(extra='forbid')

    episode_no: int = Field(gt=0, le=2147483647, description='项目内集号')
    episode_name: str | None = Field(default=None, max_length=200, description='集名称')
    description: str | None = Field(default=None, max_length=10000, description='集说明')
    sort_order: int = Field(default=0, ge=0, le=2147483647, description='项目内排序')
    remark: str | None = Field(default=None, max_length=500, description='备注')

    @field_validator('episode_name', 'description', 'remark', mode='before')
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        return _normalize_optional_text(value)


class ShotGridEpisodeUpdateModel(ShotGridLockVersionModel):
    """修改集请求；集号和 NAS 目录快照创建后不可修改。"""

    model_config = ConfigDict(extra='forbid')

    episode_name: str | None = Field(default=None, max_length=200, description='集名称')
    description: str | None = Field(default=None, max_length=10000, description='集说明')
    sort_order: int | None = Field(default=None, ge=0, le=2147483647, description='项目内排序')
    remark: str | None = Field(default=None, max_length=500, description='备注')

    @field_validator('episode_name', 'description', 'remark', mode='before')
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode='after')
    def require_update_field(self) -> 'ShotGridEpisodeUpdateModel':
        if not {'episode_name', 'description', 'sort_order', 'remark'}.intersection(self.model_fields_set):
            raise ValueError('至少提供一个可修改字段')
        if 'sort_order' in self.model_fields_set and self.sort_order is None:
            raise ValueError('sortOrder 不能为 null')
        return self


class ShotGridArchiveModel(ShotGridLockVersionModel):
    """集或场次归档请求。"""

    model_config = ConfigDict(extra='forbid')


class ShotGridEpisodeModel(ShotGridApiModel):
    """集详情和列表项。"""

    episode_id: int = Field(description='集ID')
    project_id: int = Field(description='项目ID')
    episode_no: int = Field(description='集号')
    episode_code: str = Field(description='镜头业务文件名使用的集代码')
    storage_dir_name: str = Field(description='NAS 集目录快照')
    episode_name: str | None = Field(default=None, description='集名称')
    description: str | None = Field(default=None, description='集说明')
    sort_order: int = Field(description='项目内排序')
    lifecycle_status: LifecycleStatus = Field(description='生命周期状态')
    directory_status: DirectoryStatus = Field(description='最新目录操作派生状态')
    scene_count: int = Field(default=0, ge=0, description='场次数量')
    active_scene_count: int = Field(default=0, ge=0, description='活动场次数量')
    shot_count: int = Field(default=0, ge=0, description='镜头数量')
    active_shot_count: int = Field(default=0, ge=0, description='活动镜头数量')
    create_by: str = Field(description='创建者')
    create_time: datetime = Field(description='创建时间')
    update_by: str = Field(description='更新者')
    update_time: datetime = Field(description='更新时间')
    remark: str | None = Field(default=None, description='备注')
    lock_version: int = Field(ge=0, description='乐观锁版本')


class ShotGridSceneQueryModel(ShotGridPageQueryModel):
    """场次分页查询。"""

    lifecycle_status: LifecycleStatus | None = Field(default=None, description='生命周期状态')
    order_by_column: Literal['sceneNo', 'sceneName', 'sortOrder', 'createTime'] = Field(
        default='sortOrder',
        description='排序字段',
    )
    is_asc: SortDirection = Field(default='ascending', description='排序方向')


class ShotGridSceneCreateModel(ShotGridApiModel):
    """创建场次请求。"""

    model_config = ConfigDict(extra='forbid')

    scene_no: int = Field(ge=0, le=2147483647, description='集内场次号；序固定为0')
    scene_name: str | None = Field(default=None, max_length=200, description='场次名称')
    description: str | None = Field(default=None, max_length=10000, description='场次描述')
    sort_order: int = Field(default=0, ge=0, le=2147483647, description='集内排序')
    remark: str | None = Field(default=None, max_length=500, description='备注')

    @field_validator('scene_name', 'description', 'remark', mode='before')
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode='after')
    def validate_prologue(self) -> 'ShotGridSceneCreateModel':
        if self.scene_no == 0 and self.scene_name != '序':
            raise ValueError('序场次的 sceneNo 必须为 0 且 sceneName 必须为“序”')
        if self.scene_no > 0 and self.scene_name == '序':
            raise ValueError('非序场次不能使用“序”作为名称')
        return self


class ShotGridSceneUpdateModel(ShotGridLockVersionModel):
    """修改场次请求；场次号创建后不可修改。"""

    model_config = ConfigDict(extra='forbid')

    scene_name: str | None = Field(default=None, max_length=200, description='场次名称')
    description: str | None = Field(default=None, max_length=10000, description='场次描述')
    sort_order: int | None = Field(default=None, ge=0, le=2147483647, description='集内排序')
    remark: str | None = Field(default=None, max_length=500, description='备注')

    @field_validator('scene_name', 'description', 'remark', mode='before')
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode='after')
    def require_update_field(self) -> 'ShotGridSceneUpdateModel':
        if not {'scene_name', 'description', 'sort_order', 'remark'}.intersection(self.model_fields_set):
            raise ValueError('至少提供一个可修改字段')
        if 'sort_order' in self.model_fields_set and self.sort_order is None:
            raise ValueError('sortOrder 不能为 null')
        return self


class ShotGridEpisodeSummaryModel(ShotGridApiModel):
    """场次列表中的所属集摘要。"""

    episode_id: int = Field(description='集ID')
    episode_no: int = Field(description='集号')
    episode_code: str = Field(description='镜头业务文件名使用的集代码')
    episode_name: str | None = Field(default=None, description='集名称')
    lifecycle_status: LifecycleStatus = Field(description='生命周期状态')


class ShotGridSceneModel(ShotGridApiModel):
    """场次详情和列表项。"""

    scene_id: int = Field(description='场次ID')
    project_id: int = Field(description='项目ID')
    episode_id: int = Field(description='集ID')
    scene_no: int = Field(description='场次号')
    scene_code: str = Field(description='三位起补零的场次代码')
    scene_name: str | None = Field(default=None, description='场次名称')
    description: str | None = Field(default=None, description='场次描述')
    sort_order: int = Field(description='集内排序')
    lifecycle_status: LifecycleStatus = Field(description='生命周期状态')
    shot_count: int = Field(default=0, ge=0, description='镜头数量')
    active_shot_count: int = Field(default=0, ge=0, description='活动镜头数量')
    create_by: str = Field(description='创建者')
    create_time: datetime = Field(description='创建时间')
    update_by: str = Field(description='更新者')
    update_time: datetime = Field(description='更新时间')
    remark: str | None = Field(default=None, description='备注')
    lock_version: int = Field(ge=0, description='乐观锁版本')


class ShotGridScenePageModel(PageModel[ShotGridSceneModel]):
    """带所属集摘要的场次分页结果。"""

    episode: ShotGridEpisodeSummaryModel = Field(description='所属集摘要')


class ShotGridScenePageResponseModel(ShotGridScenePageModel, ResponseBaseModel):
    """场次分页响应。"""

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel

SQL_BIGINT_MAX = 9_223_372_036_854_775_807


class ShotGridStorageRootOptionModel(ShotGridApiModel):
    """创建项目时可选择的健康 NAS 根目录。"""

    storage_root_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    root_code: str
    root_name: str
    protocol: Literal['smb_unc']
    last_probe_status: Literal['healthy']
    last_probe_time: datetime | None = None


class ShotGridProjectPathPreviewRequestModel(ShotGridApiModel):
    """项目路径预览请求；预览不会写库或创建目录。"""

    project_type: Literal['ai_short_film'] = 'ai_short_film'
    project_name: str = Field(min_length=1, max_length=200)
    project_directory_name: str = Field(min_length=1, max_length=240)

    @field_validator('project_name', 'project_directory_name', mode='before')
    @classmethod
    def normalize_required_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError('项目名称和目录名称必须是字符串')
        return value.strip()


class ShotGridProjectPathPreviewModel(ShotGridApiModel):
    """经后端路径规则计算的只读预览。"""

    storage_root_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    root_name: str
    project_directory_name: str
    project_relative_path: str
    project_path_preview: str
    path_conflict: bool


class ShotGridMemberCandidateQueryModel(ShotGridApiModel):
    """业务成员候选分页查询。"""

    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    keyword: str | None = Field(default=None, max_length=100)


class ShotGridMemberCandidateModel(ShotGridApiModel):
    """不含联系方式和认证字段的安全用户投影。"""

    user_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    user_name: str
    nick_name: str
    avatar: str | None = None
    dept_id: int | None = None
    dept_name: str | None = None


class ShotGridShotAssigneeOptionQueryModel(ShotGridApiModel):
    """镜头首位制作人选项分页查询。"""

    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    keyword: str | None = Field(default=None, max_length=100)


class ShotGridShotAssigneeOptionModel(ShotGridApiModel):
    """项目内可承担镜头任务的活动制作人安全投影。"""

    user_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    user_name: str
    nick_name: str
    avatar: str | None = None
    dept_id: int | None = None
    dept_name: str | None = None
    project_role: Literal['director', 'creator']
    producer_code: str


class ShotGridAssetAssigneeOptionQueryModel(ShotGridShotAssigneeOptionQueryModel):
    """资产制作分项主制作人选项分页查询。"""


class ShotGridAssetAssigneeOptionModel(ShotGridShotAssigneeOptionModel):
    """项目内可承担资产图片任务的活动制作人安全投影。"""

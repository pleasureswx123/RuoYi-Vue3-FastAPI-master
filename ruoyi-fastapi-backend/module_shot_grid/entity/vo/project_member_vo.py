import re
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from common.vo import ResponseBaseModel
from module_shot_grid.entity.vo.common_vo import ShotGridApiModel

ProjectRole = Literal['director', 'creator']


def normalize_producer_code(value: Any) -> str | None:
    """规范化可选制作人缩写。"""

    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('制作人缩写必须是字符串')
    normalized = value.strip().upper()
    if not normalized:
        return None
    if not re.fullmatch(r'[A-Z0-9]{2,12}', normalized):
        raise ValueError('制作人缩写必须为 2—12 位大写英文字母或数字')
    return normalized


class ShotGridInitialMemberModel(ShotGridApiModel):
    """创建项目时的初始成员。"""

    user_id: int = Field(gt=0, description='用户ID')
    project_role: ProjectRole = Field(description='项目角色')
    producer_code: str | None = Field(default=None, description='制作人缩写')

    @field_validator('producer_code', mode='before')
    @classmethod
    def validate_producer_code(cls, value: Any) -> str | None:
        return normalize_producer_code(value)


class ShotGridProjectMemberAddModel(ShotGridInitialMemberModel):
    """新增项目成员请求。"""


class ShotGridProjectMemberUpdateModel(ShotGridApiModel):
    """修改项目成员角色或制作人缩写请求。"""

    project_role: ProjectRole | None = Field(default=None, description='项目角色')
    producer_code: str | None = Field(default=None, description='制作人缩写；显式 null 表示清空')

    @field_validator('producer_code', mode='before')
    @classmethod
    def validate_producer_code(cls, value: Any) -> str | None:
        return normalize_producer_code(value)

    @model_validator(mode='after')
    def validate_update_fields(self) -> 'ShotGridProjectMemberUpdateModel':
        if not {'project_role', 'producer_code'}.intersection(self.model_fields_set):
            raise ValueError('projectRole 和 producerCode 至少提供一项')
        if 'project_role' in self.model_fields_set and self.project_role is None:
            raise ValueError('projectRole 不能为 null')
        return self


class ShotGridProjectMemberModel(ShotGridApiModel):
    """项目成员响应。"""

    user_id: int = Field(description='用户ID')
    user_name: str = Field(description='登录账号')
    nick_name: str = Field(description='用户昵称')
    avatar: str | None = Field(default=None, description='头像地址')
    dept_id: int | None = Field(default=None, description='部门ID')
    dept_name: str | None = Field(default=None, description='部门名称')
    project_role: ProjectRole = Field(description='项目角色')
    producer_code: str | None = Field(default=None, description='制作人缩写')
    joined_time: datetime = Field(description='加入时间')
    account_status: str | None = Field(default=None, description='平台账号状态')


class ShotGridProjectMemberListResponseModel(ResponseBaseModel):
    """项目成员非分页列表响应。"""

    rows: list[ShotGridProjectMemberModel] = Field(default_factory=list, description='项目成员')

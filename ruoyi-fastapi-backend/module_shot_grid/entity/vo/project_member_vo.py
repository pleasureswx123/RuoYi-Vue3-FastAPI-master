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


class ShotGridMemberRolesInput(ShotGridApiModel):
    """兼容旧单值请求，内部统一使用非空角色集合。"""

    project_roles: list[ProjectRole] = Field(min_length=1, description='项目角色集合')

    @model_validator(mode='before')
    @classmethod
    def normalize_role_input(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        value = dict(value)
        old_keys = {'projectRole', 'project_role'} & value.keys()
        new_keys = {'projectRoles', 'project_roles'} & value.keys()
        if old_keys and new_keys:
            raise ValueError('projectRole 与 projectRoles 不能同时提供')
        if old_keys:
            value['project_roles'] = [value.pop(next(iter(old_keys)))]
        return value

    @field_validator('project_roles')
    @classmethod
    def normalize_roles(cls, value: list[ProjectRole] | None) -> list[ProjectRole]:
        if not value:
            raise ValueError('至少选择一个项目角色')
        return [role for role in ('director', 'creator') if role in value]

    @property
    def project_role(self) -> ProjectRole | None:
        """仅供兼容投影，不能用于授权判断。"""
        return self.project_roles[0] if self.project_roles else None


class ShotGridInitialMemberModel(ShotGridMemberRolesInput):
    """创建项目时的初始成员。"""

    user_id: int = Field(gt=0, description='用户ID')
    producer_code: str | None = Field(default=None, description='制作人缩写')

    @field_validator('producer_code', mode='before')
    @classmethod
    def validate_producer_code(cls, value: Any) -> str | None:
        return normalize_producer_code(value)


class ShotGridProjectMemberAddModel(ShotGridInitialMemberModel):
    """新增项目成员请求。"""


class ShotGridProjectMemberQueryModel(ShotGridApiModel):
    """项目成员列表查询。"""

    project_role: ProjectRole | None = Field(default=None, description='项目角色；不传返回全部成员')


class ShotGridProjectMemberUpdateModel(ShotGridMemberRolesInput):
    """修改项目成员角色或制作人缩写请求。"""

    project_roles: list[ProjectRole] | None = Field(default=None, min_length=1, description='项目角色集合')
    producer_code: str | None = Field(default=None, description='制作人缩写；显式 null 表示清空')

    @field_validator('producer_code', mode='before')
    @classmethod
    def validate_producer_code(cls, value: Any) -> str | None:
        return normalize_producer_code(value)

    @model_validator(mode='after')
    def validate_update_fields(self) -> 'ShotGridProjectMemberUpdateModel':
        if not {'project_roles', 'producer_code'}.intersection(self.model_fields_set):
            raise ValueError('projectRoles 和 producerCode 至少提供一项')
        if 'project_roles' in self.model_fields_set and self.project_roles is None:
            raise ValueError('projectRole 不能为 null')
        return self


class ShotGridProjectMemberModel(ShotGridApiModel):
    """项目成员响应。"""

    is_project_creator: bool = Field(default=False, description='是否为项目创建者')
    user_id: int = Field(description='用户ID')
    user_name: str = Field(description='登录账号')
    nick_name: str = Field(description='用户昵称')
    avatar: str | None = Field(default=None, description='头像地址')
    dept_id: int | None = Field(default=None, description='部门ID')
    dept_name: str | None = Field(default=None, description='部门名称')
    project_role: ProjectRole = Field(description='兼容单值投影')
    project_roles: list[ProjectRole] = Field(default_factory=list, description='项目角色集合')
    producer_code: str | None = Field(default=None, description='制作人缩写')
    joined_time: datetime = Field(description='加入时间')
    account_status: str | None = Field(default=None, description='平台账号状态')

    @field_validator('project_roles', mode='before')
    @classmethod
    def ordered_roles(cls, value: Any) -> list[str]:
        return [role for role in ('director', 'creator') if role in (value or [])]


class ShotGridProjectMemberListResponseModel(ResponseBaseModel):
    """项目成员非分页列表响应。"""

    rows: list[ShotGridProjectMemberModel] = Field(default_factory=list, description='项目成员')

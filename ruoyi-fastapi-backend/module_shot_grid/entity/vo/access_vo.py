from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class ShotGridProjectAccessModel(BaseModel):
    """已通过校验的项目访问上下文。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    project_id: int = Field(description='项目ID')
    user_id: int = Field(description='当前用户ID')
    project_role: Literal['director', 'creator'] | None = Field(default=None, description='项目内角色')
    has_all_scope: bool = Field(default=False, description='是否拥有跨项目管理范围')

    project_roles: list[Literal['director', 'creator']] = Field(default_factory=list)

    @model_validator(mode='after')
    def normalize_roles(self) -> 'ShotGridProjectAccessModel':
        # 仅兼容内部旧构造调用；数据库入口必须显式传完整集合，包括空集合。
        if 'project_roles' not in self.model_fields_set and self.project_role:
            self.project_roles = [self.project_role]
        return self

    def has_role(self, role: str) -> bool:
        return role in self.project_roles

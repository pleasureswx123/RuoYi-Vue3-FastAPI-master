from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ShotGridProjectAccessModel(BaseModel):
    """已通过校验的项目访问上下文。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    project_id: int = Field(description='项目ID')
    user_id: int = Field(description='当前用户ID')
    project_role: Literal['director', 'creator'] | None = Field(default=None, description='项目内角色')
    has_all_scope: bool = Field(default=False, description='是否拥有跨项目管理范围')

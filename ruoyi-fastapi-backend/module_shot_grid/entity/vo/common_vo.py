from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ShotGridApiModel(BaseModel):
    """Shot Grid camelCase API 模型基类。"""

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)


class ShotGridPageQueryModel(ShotGridApiModel):
    """Shot Grid 列表接口统一分页基类。"""

    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=20, ge=1, le=100, description='每页记录数')
    order_by_column: str | None = Field(default=None, description='排序字段，由资源查询模型限制白名单')
    is_asc: Literal['ascending', 'descending'] = Field(default='descending', description='排序方向')
    keyword: str | None = Field(default=None, max_length=200, description='关键字')


class ShotGridLockVersionModel(ShotGridApiModel):
    """需要乐观锁保护的更新请求基类。"""

    lock_version: int = Field(ge=0, description='期望乐观锁版本')

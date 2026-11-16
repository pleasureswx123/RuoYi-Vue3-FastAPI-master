from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class ShotGridApiModel(BaseModel):
    """Shot Grid camelCase API 模型基类。"""

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)


class ShotGridApprovedVersionModel(ShotGridApiModel):
    """最近一次审核通过记录；重新反馈后仍保留，不代表当前任务已完成。"""

    version_id: int
    version_no: int
    version_status: Literal['pending_review', 'rejected', 'final']
    delivery_status: Literal['pending', 'publishing', 'published', 'failed'] | None = None
    approved_time: datetime | None = None


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


class ShotGridProductionPeriodModel(ShotGridApiModel):
    """按预期制作时间交集筛选；不改变原有权限范围。"""

    production_from: date | None = None
    production_to: date | None = None

    @model_validator(mode='after')
    def validate_production_period(self) -> 'ShotGridProductionPeriodModel':
        if self.production_from and self.production_to and self.production_from > self.production_to:
            raise ValueError('制作周期开始日期不能晚于结束日期')
        return self


class ShotGridProductionQueryModel(ShotGridPageQueryModel, ShotGridProductionPeriodModel):
    """可选制作人与制作周期，始终与原数据范围取交集。"""

    assignee_user_id: int | None = Field(default=None, gt=0, le=9_223_372_036_854_775_807)

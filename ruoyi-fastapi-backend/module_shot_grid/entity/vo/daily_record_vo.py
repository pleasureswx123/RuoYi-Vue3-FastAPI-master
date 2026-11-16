from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel

CONTROL_CHARACTER_LIMIT = 32
MAX_RANGE_DAYS = 365


class DailyLine(ShotGridApiModel):
    model_config = ConfigDict(extra='forbid')
    record_id: UUID
    lock_version: int = Field(default=0, ge=0)
    platform: str = Field(min_length=1, max_length=80)
    account: str = Field(default='', max_length=80)
    model: str = Field(default='', max_length=80)
    media_type: Literal['image', 'video'] = 'image'
    generated_count: int = Field(ge=0, le=1000000)
    actual_points: Decimal | None = Field(default=None, ge=0, le=Decimal('999999999'), decimal_places=4)
    unit_points: Decimal | None = Field(default=None, ge=0, le=Decimal('999999'), decimal_places=4)
    remark: str = Field(default='', max_length=500)
    removed: bool = False

    @field_validator('platform', 'account', 'model', mode='before')
    @classmethod
    def clean_label(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError('请输入文字')
        value = ' '.join(value.split()).casefold()
        if any(ord(c) < CONTROL_CHARACTER_LIMIT for c in value):
            raise ValueError('名称不可含控制字符')
        return value

    @model_validator(mode='after')
    def validate_points(self) -> 'DailyLine':
        if self.actual_points is None and self.unit_points is None and not self.removed:
            raise ValueError('填写实际积分或单次估算积分，免费填写 0')
        if self.unit_points is not None and self.unit_points * self.generated_count >= Decimal('1000000000000'):
            raise ValueError('估算积分超出范围')
        return self


class DailySave(ShotGridApiModel):
    model_config = ConfigDict(extra='forbid')
    task_id: int = Field(gt=0)
    record_date: date
    lines: list[DailyLine] = Field(min_length=1, max_length=30)

    @model_validator(mode='after')
    def distinct_lines(self) -> 'DailySave':
        if self.record_date > date.today():
            raise ValueError('不能填写未来日期')
        ids = [line.record_id for line in self.lines]
        dims = [(line.platform, line.account, line.model, line.media_type) for line in self.lines if not line.removed]
        if len(set(ids)) != len(ids) or len(set(dims)) != len(dims):
            raise ValueError('同平台、账号、模型和类型请合并填写，不能重复添加')
        return self


class DailyQuery(ShotGridApiModel):
    start: date
    end: date
    user_id: int | None = Field(default=None, gt=0)
    platform: str | None = Field(default=None, max_length=80)
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)

    @model_validator(mode='after')
    def date_range(self) -> 'DailyQuery':
        if not 0 <= (self.end - self.start).days <= MAX_RANGE_DAYS:
            raise ValueError('日期范围需为 1 至 366 天')
        return self

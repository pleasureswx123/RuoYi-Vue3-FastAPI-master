import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

MAX_ANNOTATION_PAYLOAD_BYTES = 65_536


class ReviewModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, str_strip_whitespace=True)


class AnnotationPointModel(ReviewModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class AnnotationModel(ReviewModel):
    annotation_type: Literal['freehand', 'arrow', 'rectangle', 'ellipse', 'point']
    color: str = Field(pattern=r'^#[0-9A-Fa-f]{6}$')
    points: list[AnnotationPointModel] = Field(min_length=1, max_length=500)
    natural_width: int = Field(gt=0, le=100_000)
    natural_height: int = Field(gt=0, le=100_000)


class NoteCreateModel(ReviewModel):
    version_id: int = Field(gt=0)
    content: str = Field(min_length=1, max_length=4000)
    media_time_ms: int | None = Field(default=None, ge=0)
    annotations: list[AnnotationModel] = Field(default_factory=list, max_length=20)
    is_mandatory: bool = False

    @field_validator('content')
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError('意见内容不能为空')
        return value

    @model_validator(mode='after')
    def limit_annotation_payload(self) -> 'NoteCreateModel':
        payload = [item.model_dump(mode='json', by_alias=True) for item in self.annotations]
        if len(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()) > MAX_ANNOTATION_PAYLOAD_BYTES:
            raise ValueError('标注有效载荷不能超过64 KiB')
        return self


class NoteReplyCreateModel(ReviewModel):
    content: str = Field(min_length=1, max_length=4000)

    @field_validator('content')
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError('回复内容不能为空')
        return value


class NoteStatusUpdateModel(ReviewModel):
    status: Literal['open', 'resolved']


class ReviewActionModel(ReviewModel):
    lock_version: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator('reason')
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        return value or None


class RejectReviewActionModel(ReviewActionModel):
    reason: str = Field(min_length=1, max_length=1000)

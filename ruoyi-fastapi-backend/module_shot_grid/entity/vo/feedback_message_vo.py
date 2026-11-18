from datetime import datetime
from typing import Any

from pydantic import Field

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel
from module_shot_grid.entity.vo.review_vo import ShotGridIssueReferenceFileModel


class FeedbackUnreadModel(ShotGridApiModel):
    count: int
    latest_id: int | None


class FeedbackIssueModel(ShotGridApiModel):
    issue_id: int | None = None
    content: str | None = None
    comment: str | None = None
    media_time_ms: int | None = None
    candidate_id: int | None = None
    candidate_no: int | None = None
    annotations: dict[str, Any] | None = None
    reference_files: list[ShotGridIssueReferenceFileModel] = Field(default_factory=list)


class FeedbackMessageModel(ShotGridApiModel):
    message_id: int
    project_id: int
    task_id: int
    project_name: str
    task_name: str
    version_number: str
    sender_name: str
    issues: list[FeedbackIssueModel]
    created_at: datetime
    read_at: datetime | None


class FeedbackMessagePageModel(ShotGridApiModel):
    total: int
    page: int
    rows: list[FeedbackMessageModel]

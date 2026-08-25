from datetime import datetime
from typing import Literal

from pydantic import Field

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel, ShotGridPageQueryModel

FileRole = Literal[
    'review_media',
    'thumbnail',
    'proxy_media',
    'source_original',
    'source_repaired',
    'first_frame',
    'last_frame',
    'reference',
]
FileCenterVisibleRole = Literal[
    'review_media',
    'source_original',
    'source_repaired',
    'first_frame',
    'last_frame',
    'reference',
]


class ShotGridProjectFileQueryModel(ShotGridPageQueryModel):
    """项目正式版本文件分页查询。"""

    file_role: FileCenterVisibleRole | None = Field(default=None, description='可见业务文件用途')
    version_status: Literal['pending_review', 'rejected', 'final'] | None = Field(
        default=None,
        description='版本状态',
    )
    task_kind: Literal['shot_video', 'asset_image'] | None = Field(default=None, description='任务类型')
    order_by_column: Literal['submittedTime', 'businessFileName', 'fileSize'] = Field(
        default='submittedTime',
        description='排序字段',
    )


class ShotGridProjectFileThumbnailModel(ShotGridApiModel):
    """同版本受保护缩略图投影。"""

    file_id: str
    url: str


class ShotGridProjectFileProxyMediaModel(ShotGridApiModel):
    """同版本受保护代理媒体投影。"""

    file_id: str
    url: str


class ShotGridProjectFileModel(ShotGridApiModel):
    """文件中心安全读取模型；不暴露平台物理存储位置。"""

    file_id: str
    project_id: int
    version_id: int
    task_id: int
    task_name: str
    task_kind: Literal['shot_video', 'asset_image']
    version_no: int
    version_number: str
    version_status: Literal['pending_review', 'rejected', 'final']
    original_name: str
    business_file_name: str
    role: FileRole
    is_primary: bool
    content_type: str | None = None
    file_size: int = Field(ge=0)
    nas_relative_path: str | None = None
    published_time: datetime | None = None
    submitted_time: datetime
    download_url: str
    thumbnail: ShotGridProjectFileThumbnailModel | None = None
    proxy_media: ShotGridProjectFileProxyMediaModel | None = None

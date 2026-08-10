from datetime import datetime

from pydantic import Field, model_validator

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel
from module_shot_grid.entity.vo.import_common_vo import (
    ImportIssueModel,
    ImportPreviewSummaryModel,
    ImportSelectedRowModel,
)

SQL_INTEGER_MAX = 2_147_483_647
SQL_BIGINT_MAX = 9_223_372_036_854_775_807


class ShotAssetRequirementPreviewModel(ShotGridApiModel):
    """镜头行引用的单个场景资产需求。"""

    asset_type: str = Field(default='Environment')
    raw_name: str = Field(min_length=1, max_length=200)
    normalized_name: str = Field(min_length=1, max_length=200)
    matched_asset_id: int | None = Field(default=None, gt=0)


class ShotImportNormalizedRowModel(ShotGridApiModel):
    """镜头 Excel 行的无数据库主键规范结果。"""

    episode_no: int = Field(gt=0, le=SQL_INTEGER_MAX)
    episode_code: str = Field(pattern=r'^EP\d{3,}$')
    scene_no: int = Field(ge=0, le=SQL_INTEGER_MAX)
    scene_code: str = Field(pattern=r'^\d{3,}$')
    scene_name: str | None = Field(default=None, max_length=200)
    sort_order: int = Field(ge=0, le=SQL_INTEGER_MAX)
    shot_no: int = Field(gt=0, le=SQL_INTEGER_MAX)
    shot_code: str = Field(pattern=r'^S\d{3,}$')
    duration_ms: int = Field(ge=0, le=SQL_BIGINT_MAX)
    assignee_user_name: str | None = Field(default=None, max_length=30)
    assignee_user_id: int | None = Field(default=None, gt=0)
    description: str = Field(min_length=1)
    shot_size: str | None = Field(default=None, max_length=40)
    camera_position: str | None = Field(default=None, max_length=100)
    camera_movement: str | None = Field(default=None, max_length=100)
    focal_length: str | None = Field(default=None, max_length=50)
    asset_requirements: list[ShotAssetRequirementPreviewModel] = Field(default_factory=list)
    dialogue: str | None = None
    sound_effect: str | None = None
    color_reference: str | None = None
    remark: str | None = Field(default=None, max_length=500)


class ShotImportPreviewRowModel(ShotGridApiModel):
    """单条镜头预检查结果。"""

    sheet_name: str = Field(min_length=1, max_length=31)
    row_number: int = Field(ge=2)
    row_key: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    normalized: ShotImportNormalizedRowModel | None = None
    warnings: list[ImportIssueModel] = Field(default_factory=list)
    errors: list[ImportIssueModel] = Field(default_factory=list)
    can_import: bool


class ShotImportPreviewSummaryModel(ImportPreviewSummaryModel):
    distinct_episodes: int = Field(ge=0)
    distinct_scenes: int = Field(ge=0)
    distinct_shots: int = Field(ge=0)


class ShotExcelParseResultModel(ShotGridApiModel):
    """解析器输出；Service 完成成员和资产数据库匹配后才能对外返回。"""

    summary: ShotImportPreviewSummaryModel
    rows: list[ShotImportPreviewRowModel]
    workbook_warnings: list[ImportIssueModel] = Field(default_factory=list)


class ShotImportPreviewResultModel(ShotGridApiModel):
    batch_id: int = Field(gt=0)
    import_token: str = Field(min_length=1)
    expires_at: datetime
    summary: ShotImportPreviewSummaryModel
    rows: list[ShotImportPreviewRowModel]
    workbook_warnings: list[ImportIssueModel] = Field(default_factory=list)


class ShotImportCommitRequestModel(ShotGridApiModel):
    import_token: str = Field(min_length=1, max_length=200)
    selected_rows: list[ImportSelectedRowModel] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_unique_rows(self) -> 'ShotImportCommitRequestModel':
        keys = [row.key() for row in self.selected_rows]
        if len(keys) != len(set(keys)):
            raise ValueError('selectedRows 不能包含重复的 Sheet 与行号')
        return self


class ShotImportCommitResultModel(ShotGridApiModel):
    batch_id: int = Field(gt=0)
    committed_rows: int = Field(ge=0)
    created_episodes: int = Field(ge=0)
    reused_episodes: int = Field(ge=0)
    created_scenes: int = Field(ge=0)
    reused_scenes: int = Field(ge=0)
    created_shots: int = Field(ge=0)
    created_tasks: int = Field(ge=0)
    created_asset_links: int = Field(ge=0)
    created_asset_requirements: int = Field(ge=0)
    created_storage_operations: int = Field(ge=0)
    idempotent_replay: bool = False

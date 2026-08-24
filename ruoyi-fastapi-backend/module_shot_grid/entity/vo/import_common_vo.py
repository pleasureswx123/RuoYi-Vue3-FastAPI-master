from datetime import datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel


class ImportIssueModel(ShotGridApiModel):
    """导入预检查的稳定问题描述。"""

    error_key: str = Field(min_length=1, max_length=100, description='稳定错误键')
    message: str = Field(min_length=1, max_length=500, description='用户可读说明')
    field_name: str | None = Field(default=None, max_length=100, description='规范字段名')
    sheet_name: str | None = Field(default=None, max_length=31, description='Sheet 名称')
    row_number: int | None = Field(default=None, ge=1, description='Excel 物理行号')


class ImportSelectedRowModel(ShotGridApiModel):
    """多 Sheet 工作簿中的唯一行选择。"""

    model_config = ConfigDict(extra='forbid')

    sheet_name: str = Field(min_length=1, max_length=31, description='Sheet 名称')
    row_number: int = Field(ge=2, description='Excel 物理行号')

    def key(self) -> tuple[str, int]:
        return self.sheet_name, self.row_number


class ImportPreviewSummaryModel(ShotGridApiModel):
    """预检查公共统计。警告行仍可同时计入有效行。"""

    total_rows: int = Field(ge=0)
    valid_rows: int = Field(ge=0)
    warning_rows: int = Field(ge=0)
    error_rows: int = Field(ge=0)


class ImportPreviewTokenPayloadModel(ShotGridApiModel):
    """Redis 中短期保存的预检查绑定与规范化行。"""

    batch_id: int = Field(gt=0)
    project_id: int = Field(gt=0)
    import_type: Literal['shot', 'asset']
    previewed_by: int = Field(gt=0)
    file_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    template_version: str = Field(min_length=1, max_length=30)
    expires_at: datetime
    rows: list[dict[str, Any]]

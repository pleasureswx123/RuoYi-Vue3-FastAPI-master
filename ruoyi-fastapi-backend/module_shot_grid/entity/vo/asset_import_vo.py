from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel
from module_shot_grid.entity.vo.import_common_vo import (
    ImportIssueModel,
    ImportPreviewSummaryModel,
    ImportSelectedRowModel,
)

AssetType = Literal['Character', 'Environment', 'Prop']


class AssetImportNormalizedRowModel(ShotGridApiModel):
    """资产 Excel 单行规范化结果。"""

    asset_type: AssetType | None = Field(default=None, description='规范化资产类型')
    asset_name: str | None = Field(default=None, description='清洗后的资产名称')
    asset_name_key: str | None = Field(default=None, description='资产名称精确匹配键')
    asset_group_key: str | None = Field(default=None, description='本次文件内父资产分组键')
    asset_description: str | None = Field(default=None, description='未来模板的资产主数据描述')
    production_item: str | None = Field(default=None, description='制作分项名称')
    production_item_key: str | None = Field(default=None, description='制作分项匹配键')
    item_description: str | None = Field(default=None, description='制作分项描述')
    remark: str | None = Field(default=None, description='制作分项备注')
    import_row_key: str | None = Field(default=None, description='来源文件、Sheet和行号幂等键')


class AssetImportPreviewRowModel(ShotGridApiModel):
    """资产 Excel 预检查行。"""

    sheet_name: str = Field(description='来源 Sheet 名称')
    row_number: int = Field(ge=2, description='来源 Excel 行号')
    row_key: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$', description='规范化行摘要')
    normalized: AssetImportNormalizedRowModel = Field(description='规范化结果')
    warnings: list[ImportIssueModel] = Field(default_factory=list, description='警告列表')
    errors: list[ImportIssueModel] = Field(default_factory=list, description='错误列表')
    can_import: bool = Field(default=True, description='该行是否允许提交')

    def refresh_can_import(self) -> None:
        """在 Service 追加数据库或成员问题后刷新可导入标志。"""
        self.can_import = not self.errors


class AssetImportTypeSummaryModel(ShotGridApiModel):
    """单种资产的预检查统计。"""

    assets: int = Field(default=0, ge=0, description='父资产数量')
    items: int = Field(default=0, ge=0, description='制作分项行数量')
    valid_rows: int = Field(default=0, ge=0, description='可导入行数')
    warning_rows: int = Field(default=0, ge=0, description='含警告行数')
    error_rows: int = Field(default=0, ge=0, description='含错误行数')


class AssetImportPreviewSummaryModel(ImportPreviewSummaryModel):
    """资产预检查汇总。"""

    distinct_assets: int = Field(default=0, ge=0, description='文件内不同父资产数量')
    distinct_asset_items: int = Field(default=0, ge=0, description='文件内制作分项行数量')
    by_type: dict[str, AssetImportTypeSummaryModel] = Field(default_factory=dict, description='按类型统计')
    estimated_auto_matches: int = Field(default=0, ge=0, description='预计可自动匹配的镜头资产需求数')


class AssetExcelParseResultModel(ShotGridApiModel):
    """资产解析器输出；成员和数据库冲突仍需 Service 补充。"""

    summary: AssetImportPreviewSummaryModel
    rows: list[AssetImportPreviewRowModel]
    workbook_warnings: list[ImportIssueModel] = Field(default_factory=list)


class AssetImportPreviewResponseModel(ShotGridApiModel):
    """资产 Excel 预检查响应。"""

    batch_id: int = Field(description='导入批次ID')
    import_token: str = Field(description='短期预览 Token')
    expires_at: datetime = Field(description='预览数据到期时间')
    summary: AssetImportPreviewSummaryModel = Field(description='预检查汇总')
    rows: list[AssetImportPreviewRowModel] = Field(description='逐行结果')
    workbook_warnings: list[ImportIssueModel] = Field(default_factory=list, description='工作簿级警告')


class AssetImportSelectedRowModel(ImportSelectedRowModel):
    """资产导入选择行；导入只创建资产及制作分项，不承载任务委派。"""


class AssetImportCommitRequestModel(ShotGridApiModel):
    """资产 Excel 正式提交请求。"""

    import_token: str = Field(min_length=1, max_length=200, description='预览 Token')
    selected_rows: list[AssetImportSelectedRowModel] = Field(min_length=1, description='选择提交的自包含明细行')

    @model_validator(mode='after')
    def validate_unique_rows(self) -> 'AssetImportCommitRequestModel':
        identities = [(item.sheet_name, item.row_number) for item in self.selected_rows]
        if len(identities) != len(set(identities)):
            raise ValueError('selectedRows 不能包含重复的 Sheet 和行号')
        return self


class AssetImportCommitResultModel(ShotGridApiModel):
    """资产 Excel 正式提交结果及耐久幂等响应。"""

    batch_id: int = Field(description='导入批次ID')
    committed_rows: int = Field(ge=0, description='正式提交行数')
    created_assets_by_type: dict[str, int] = Field(default_factory=dict, description='各类型新增父资产数')
    reused_assets: int = Field(default=0, ge=0, description='复用已有父资产数')
    created_asset_items: int = Field(default=0, ge=0, description='新增制作分项数')
    missing_production_item_warnings: int = Field(default=0, ge=0, description='缺少制作分项警告数')
    auto_matched_requirements: int = Field(default=0, ge=0, description='本次自动匹配需求数')
    pending_requirements: int = Field(default=0, ge=0, description='项目仍待匹配需求数')
    conflict_requirements: int = Field(default=0, ge=0, description='项目冲突需求数')

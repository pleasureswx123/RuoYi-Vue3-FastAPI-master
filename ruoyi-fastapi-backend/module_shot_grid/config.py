from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SHOT_TEMPLATE_VERSION = 'shot-v1'
ASSET_TEMPLATE_VERSION = 'asset-v1'


class ShotGridImportConfig(BaseSettings):
    """Shot Grid Excel 导入安全边界。"""

    model_config = SettingsConfigDict(env_prefix='SHOT_GRID_IMPORT_', extra='ignore')

    max_file_size_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_archive_entries: int = Field(default=256, gt=0)
    max_uncompressed_bytes: int = Field(default=64 * 1024 * 1024, gt=0)
    max_compression_ratio: int = Field(default=200, gt=0)
    max_rows_per_workbook: int = Field(default=10_000, gt=0)
    max_ooxml_rows_per_workbook: int = Field(default=12_000, gt=0)
    max_ooxml_cells_per_workbook: int = Field(default=200_000, gt=0)
    max_ooxml_xml_elements: int = Field(default=1_000_000, gt=0)
    max_ooxml_columns_per_sheet: int = Field(default=128, gt=0)
    max_ooxml_merge_ranges: int = Field(default=20_000, ge=0)
    max_ooxml_merged_cells: int = Field(default=200_000, ge=0)
    max_cell_text_length: int = Field(default=10_000, gt=0)
    max_ooxml_text_characters: int = Field(default=8_000_000, gt=0)
    max_preview_json_bytes: int = Field(default=16 * 1024 * 1024, gt=0)
    preview_ttl_seconds: int = Field(default=30 * 60, gt=0)
    redis_key_prefix: str = Field(default='shotgrid:import:preview', min_length=1)


SHOT_GRID_IMPORT_CONFIG = ShotGridImportConfig()

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


class ShotGridStorageWorkerConfig(BaseSettings):
    """NAS 目录消费者运行参数。每个进程必须使用不同的 worker_id。"""

    model_config = SettingsConfigDict(env_prefix='SHOT_GRID_STORAGE_WORKER_', extra='ignore')

    lease_seconds: int = Field(default=60, ge=10, le=3600)
    max_attempts: int = Field(default=5, ge=1, le=100)
    retry_base_seconds: int = Field(default=30, ge=1, le=3600)
    batch_size: int = Field(default=10, ge=1, le=100)


SHOT_GRID_STORAGE_WORKER_CONFIG = ShotGridStorageWorkerConfig()


class ShotGridVersionSubmissionConfig(BaseSettings):
    """版本审核媒体的上传和 NAS 发布边界。"""

    model_config = SettingsConfigDict(env_prefix='SHOT_GRID_VERSION_', extra='ignore')

    max_video_size_bytes: int = Field(default=2 * 1024 * 1024 * 1024, gt=0)
    max_image_size_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    video_extensions: tuple[str, ...] = ('.mp4', '.mov')
    video_mime_types: tuple[str, ...] = ('video/mp4', 'video/quicktime')
    video_extension_mimes: dict[str, tuple[str, ...]] = {
        '.mp4': ('video/mp4',),
        '.mov': ('video/quicktime',),
    }
    video_codecs: tuple[str, ...] = ('H.264/AVC',)
    max_video_width: int = Field(default=3840, gt=0)
    max_video_height: int = Field(default=2160, gt=0)
    max_video_duration_seconds: int = Field(default=600, gt=0)
    image_extensions: tuple[str, ...] = ('.jpg', '.jpeg', '.png')
    image_mime_types: tuple[str, ...] = ('image/jpeg', 'image/png')
    image_extension_mimes: dict[str, tuple[str, ...]] = {
        '.jpg': ('image/jpeg',),
        '.jpeg': ('image/jpeg',),
        '.png': ('image/png',),
    }
    image_encodings: tuple[str, ...] = ('JPEG', 'PNG')
    max_image_width: int = Field(default=8192, gt=0)
    max_image_height: int = Field(default=8192, gt=0)
    generate_proxy_files: bool = False
    lease_seconds: int = Field(default=300, ge=10, le=3600)

    def upload_policy(self, task_kind: str) -> dict:
        """返回 Service 与公开接口共同使用的媒体策略，Controller 不复制限制。"""
        if task_kind == 'shot_video':
            return {
                'media_type': 'video',
                'extensions': self.video_extensions,
                'mime_types': self.video_mime_types,
                'extension_mimes': self.video_extension_mimes,
                'max_size_bytes': self.max_video_size_bytes,
                'codecs': self.video_codecs,
                'max_width': self.max_video_width,
                'max_height': self.max_video_height,
                'max_duration_seconds': self.max_video_duration_seconds,
                'generate_proxy': self.generate_proxy_files,
            }
        if task_kind == 'asset_image':
            return {
                'media_type': 'image',
                'extensions': self.image_extensions,
                'mime_types': self.image_mime_types,
                'extension_mimes': self.image_extension_mimes,
                'max_size_bytes': self.max_image_size_bytes,
                'encodings': self.image_encodings,
                'max_width': self.max_image_width,
                'max_height': self.max_image_height,
                'generate_proxy': self.generate_proxy_files,
            }
        raise ValueError(f'不支持的 Shot Grid 任务类型: {task_kind}')


SHOT_GRID_VERSION_CONFIG = ShotGridVersionSubmissionConfig()

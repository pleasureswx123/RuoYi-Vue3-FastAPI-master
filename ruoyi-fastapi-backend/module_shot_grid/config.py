from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SHOT_TEMPLATE_VERSION = 'shot-v2'
ASSET_TEMPLATE_VERSION = 'asset-v2'


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


class ShotGridPlaybackConfig(BaseSettings):
    """原生媒体播放器短期访问票据配置。"""

    model_config = SettingsConfigDict(env_prefix='SHOT_GRID_PLAYBACK_', extra='ignore')

    ticket_ttl_seconds: int = Field(default=30 * 60, ge=60, le=60 * 60)
    redis_key_prefix: str = Field(default='shotgrid:playback:ticket', min_length=1, max_length=100)


SHOT_GRID_PLAYBACK_CONFIG = ShotGridPlaybackConfig()


class ShotGridStorageWorkerConfig(BaseSettings):
    """Shot Grid NAS 目录 Outbox Worker 安全与重试边界。"""

    model_config = SettingsConfigDict(env_prefix='SHOT_GRID_STORAGE_WORKER_', extra='ignore')

    enabled: bool = Field(default=False, description='是否显式启用真实 NAS 目录 Worker')
    poll_interval_seconds: float = Field(default=2, gt=0, le=60)
    batch_size: int = Field(default=20, gt=0, le=100)
    lease_seconds: int = Field(default=120, ge=30, le=3600)
    heartbeat_seconds: int = Field(default=30, ge=5, le=600)
    operation_timeout_seconds: int = Field(default=60, ge=5, le=1800)
    max_attempts: int = Field(default=5, ge=1, le=20)
    retry_delays_seconds: tuple[int, ...] = Field(default=(5, 15, 60, 300), min_length=1, max_length=19)

    @model_validator(mode='after')
    def validate_worker_boundaries(self) -> 'ShotGridStorageWorkerConfig':
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError('NAS Worker 心跳间隔必须小于租约时间')
        if self.operation_timeout_seconds >= self.lease_seconds:
            raise ValueError('NAS Worker 单次 I/O 软超时必须小于租约时间')
        if len(self.retry_delays_seconds) < max(self.max_attempts - 1, 1):
            raise ValueError('NAS Worker 退避序列不足以覆盖自动重试次数')
        if any(delay <= 0 for delay in self.retry_delays_seconds):
            raise ValueError('NAS Worker 退避秒数必须为正整数')
        if tuple(sorted(self.retry_delays_seconds)) != self.retry_delays_seconds:
            raise ValueError('NAS Worker 退避秒数必须按非递减顺序配置')
        return self


SHOT_GRID_STORAGE_WORKER_CONFIG = ShotGridStorageWorkerConfig()


class ShotGridVersionWorkerConfig(BaseSettings):
    """Shot Grid 版本文件 NAS 发布 Worker 安全与重试边界。"""

    model_config = SettingsConfigDict(env_prefix='SHOT_GRID_VERSION_WORKER_', extra='ignore')

    enabled: bool = Field(default=False, description='是否显式启用真实版本文件 NAS 发布 Worker')
    poll_interval_seconds: float = Field(default=2, gt=0, le=60)
    batch_size: int = Field(default=5, gt=0, le=20)
    lease_seconds: int = Field(default=900, ge=60, le=7200)
    heartbeat_seconds: int = Field(default=30, ge=5, le=600)
    operation_timeout_seconds: int = Field(default=300, ge=10, le=3600)
    max_attempts: int = Field(default=5, ge=1, le=20)
    retry_delays_seconds: tuple[int, ...] = Field(default=(5, 15, 60, 300), min_length=1, max_length=19)

    @model_validator(mode='after')
    def validate_worker_boundaries(self) -> 'ShotGridVersionWorkerConfig':
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError('版本发布 Worker 心跳间隔必须小于租约时间')
        if self.operation_timeout_seconds >= self.lease_seconds:
            raise ValueError('版本发布 Worker 单次 I/O 软超时必须小于租约时间')
        if len(self.retry_delays_seconds) < max(self.max_attempts - 1, 1):
            raise ValueError('版本发布 Worker 退避序列不足以覆盖自动重试次数')
        if any(delay <= 0 for delay in self.retry_delays_seconds):
            raise ValueError('版本发布 Worker 退避秒数必须为正整数')
        if tuple(sorted(self.retry_delays_seconds)) != self.retry_delays_seconds:
            raise ValueError('版本发布 Worker 退避秒数必须按非递减顺序配置')
        return self


SHOT_GRID_VERSION_WORKER_CONFIG = ShotGridVersionWorkerConfig()


class ShotGridMediaWorkerConfig(BaseSettings):
    """Shot Grid 缩略图与网页代理媒体 Worker 配置。"""

    model_config = SettingsConfigDict(env_prefix='SHOT_GRID_MEDIA_WORKER_', extra='ignore')

    enabled: bool = Field(default=False, description='是否显式启用媒体派生 Worker')
    poll_interval_seconds: float = Field(default=3, gt=0, le=60)
    batch_size: int = Field(default=2, gt=0, le=10)
    lease_seconds: int = Field(default=900, ge=60, le=7200)
    heartbeat_seconds: int = Field(default=30, ge=5, le=600)
    operation_timeout_seconds: int = Field(default=600, ge=10, le=3600)
    max_attempts: int = Field(default=5, ge=1, le=20)
    retry_delays_seconds: tuple[int, ...] = Field(default=(10, 30, 120, 600), min_length=1, max_length=19)
    ffmpeg_path: str = Field(default='ffmpeg', min_length=1, max_length=500)
    thumbnail_max_edge: int = Field(default=480, ge=128, le=2048)
    image_proxy_max_edge: int = Field(default=1920, ge=480, le=8192)
    video_proxy_max_width: int = Field(default=1280, ge=480, le=3840)
    jpeg_quality: int = Field(default=84, ge=40, le=95)

    @model_validator(mode='after')
    def validate_worker_boundaries(self) -> 'ShotGridMediaWorkerConfig':
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError('媒体派生 Worker 心跳间隔必须小于租约时间')
        if self.operation_timeout_seconds >= self.lease_seconds:
            raise ValueError('媒体派生 Worker 软超时必须小于租约时间')
        if len(self.retry_delays_seconds) < max(self.max_attempts - 1, 1):
            raise ValueError('媒体派生 Worker 退避序列不足以覆盖自动重试次数')
        if any(delay <= 0 for delay in self.retry_delays_seconds):
            raise ValueError('媒体派生 Worker 退避秒数必须为正整数')
        if tuple(sorted(self.retry_delays_seconds)) != self.retry_delays_seconds:
            raise ValueError('媒体派生 Worker 退避秒数必须按非递减顺序配置')
        return self


SHOT_GRID_MEDIA_WORKER_CONFIG = ShotGridMediaWorkerConfig()

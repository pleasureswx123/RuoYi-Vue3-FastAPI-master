import re
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel, ShotGridLockVersionModel, ShotGridPageQueryModel

SQL_BIGINT_MAX = 9_223_372_036_854_775_807
ROOT_CODE_PATTERN = re.compile(r'^[A-Z0-9][A-Z0-9_-]{1,49}$')


class ShotGridStorageRootQueryModel(ShotGridPageQueryModel):
    """平台管理端 NAS 根目录分页查询。"""

    root_status: Literal['enabled', 'disabled'] | None = None
    probe_status: Literal['unknown', 'healthy', 'unreachable', 'unwritable'] | None = None


class ShotGridStorageRootBaseModel(ShotGridApiModel):
    """NAS 根目录可维护字段。"""

    root_code: str = Field(min_length=2, max_length=50)
    root_name: str = Field(min_length=1, max_length=120)
    unc_root_path: str = Field(min_length=5, max_length=1000)
    root_status: Literal['enabled', 'disabled'] = 'enabled'
    remark: str | None = Field(default=None, max_length=500)

    @field_validator('root_code', mode='before')
    @classmethod
    def normalize_root_code(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError('根目录编码必须是字符串')
        normalized = value.strip().upper()
        if not ROOT_CODE_PATTERN.fullmatch(normalized):
            raise ValueError('根目录编码只能使用大写字母、数字、下划线或短横线，长度为2到50位')
        return normalized

    @field_validator('root_name', 'unc_root_path', mode='before')
    @classmethod
    def normalize_required_text(cls, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError('根目录名称和 UNC 路径不能为空')
        return value.strip()

    @field_validator('remark', mode='before')
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('备注必须是字符串')
        return value.strip() or None


class ShotGridStorageRootCreateModel(ShotGridStorageRootBaseModel):
    """新增 NAS 根目录。"""


class ShotGridStorageRootUpdateModel(ShotGridStorageRootBaseModel, ShotGridLockVersionModel):
    """修改或启停 NAS 根目录。"""


class ShotGridStorageRootModel(ShotGridApiModel):
    """平台管理端 NAS 根目录详情。"""

    storage_root_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    root_code: str
    root_name: str
    protocol: Literal['smb_unc']
    unc_root_path: str
    root_status: Literal['enabled', 'disabled']
    last_probe_status: Literal['unknown', 'healthy', 'unreachable', 'unwritable']
    last_probe_time: datetime | None = None
    last_error_key: str | None = None
    last_error_message: str | None = None
    lock_version: int = Field(ge=0)
    create_by: str
    create_time: datetime
    update_by: str
    update_time: datetime
    remark: str | None = None


class ShotGridStorageRootProbeModel(ShotGridApiModel):
    """NAS 根目录读写探测结果。"""

    storage_root_id: int = Field(gt=0, le=SQL_BIGINT_MAX)
    last_probe_status: Literal['healthy', 'unreachable', 'unwritable']
    last_probe_time: datetime
    last_error_key: str | None = None
    last_error_message: str | None = None
    lock_version: int = Field(ge=0)

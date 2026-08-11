import asyncio
import hashlib
from pathlib import Path

from module_shot_grid.config import SHOT_TEMPLATE_VERSION
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error


class ShotGridShotImportTemplateService:
    """读取并校验随 Shot Grid 后端部署的镜头导入模板。"""

    TEMPLATE_PATH = Path(__file__).resolve().parents[1] / 'resources' / 'templates' / 'shot-v1.xlsx'
    EXPECTED_SHA256 = 'f6370bbb14548b645782abf0734e930ec10470565821ba6c8fd1b6a2d9d96ee0'
    DOWNLOAD_FILE_NAME = f'镜头导入模板-{SHOT_TEMPLATE_VERSION}.xlsx'

    @classmethod
    async def get_template_bytes(cls) -> bytes:
        try:
            contents = await asyncio.to_thread(cls.TEMPLATE_PATH.read_bytes)
        except OSError as exc:
            raise cls._template_unavailable() from exc
        if hashlib.sha256(contents).hexdigest() != cls.EXPECTED_SHA256:
            raise cls._template_unavailable()
        return contents

    @staticmethod
    def _template_unavailable() -> ShotGridDomainException:
        return shot_grid_error(
            503,
            'SG_IMPORT_TEMPLATE_UNAVAILABLE',
            '镜头导入模板暂不可用，请联系管理员检查部署资源',
        )

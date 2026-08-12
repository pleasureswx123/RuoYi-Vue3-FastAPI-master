import asyncio
import hashlib
from pathlib import Path

from module_shot_grid.config import ASSET_TEMPLATE_VERSION
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error


class ShotGridAssetImportTemplateService:
    """读取并校验随 Shot Grid 后端部署的资产导入模板。"""

    TEMPLATE_PATH = Path(__file__).resolve().parents[1] / 'resources' / 'templates' / 'asset-v1.xlsx'
    EXPECTED_SHA256 = 'bd42856e37ec6b2eaa992cb190390ae09980f81953617e245f0854b955602059'
    DOWNLOAD_FILE_NAME = f'资产导入模板-{ASSET_TEMPLATE_VERSION}.xlsx'

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
            '资产导入模板暂不可用，请联系管理员检查部署资源',
        )

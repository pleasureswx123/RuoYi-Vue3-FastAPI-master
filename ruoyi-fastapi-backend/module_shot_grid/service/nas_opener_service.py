"""本机 NAS 打开凭证：独立 RSA 密钥，仅签发鉴权版本文件的父目录。"""

import asyncio
import base64
import os
import re
import time
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.entity.vo.nas_opener_vo import NasOpenCommand
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.review_service import ShotGridReviewService

MAX_PATH_LENGTH = 2000
MIN_PATH_SEGMENTS = 2
MIN_RSA_BITS = 2048


def validate_folder(path: str) -> str:
    prefix = '\\\\192.168.10.64\\'
    if not isinstance(path, str) or len(path) > MAX_PATH_LENGTH or not path.startswith(prefix):
        raise ValueError('仅支持公司 NAS 目录')
    parts = path[len(prefix) :].split('\\')
    if (
        len(parts) < MIN_PATH_SEGMENTS
        or parts[0].endswith('$')
        or any(
            not part
            or part.endswith(('.', ' '))
            or re.search(r'[\x00-\x1f\x7f<>:"/|?*%]', part)
            or re.match(r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)', part, re.I)
            for part in parts
        )
    ):
        raise ValueError('NAS 目录格式不安全')
    return path


def _key() -> rsa.RSAPrivateKey:
    # 不复用 JWT 或传输加密密钥，不自动生成、不提供不安全默认值。
    try:
        filename = os.environ['SHOT_GRID_NAS_SIGNING_KEY_FILE']
        key = serialization.load_pem_private_key(Path(filename).read_bytes(), password=None)
        if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < MIN_RSA_BITS:
            raise ValueError('RSA 密钥规格不符合要求')
        return key
    except (KeyError, OSError, ValueError, TypeError):
        raise shot_grid_error(
            503, 'SG_NAS_SIGNER_UNAVAILABLE', 'NAS 打开服务尚未配置，请联系管理员；仍可复制目录'
        ) from None


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def public_key_xml() -> str:
    numbers = _key().public_key().public_numbers()

    def encode(number: int) -> str:
        return base64.b64encode(number.to_bytes((number.bit_length() + 7) // 8, 'big')).decode()

    return f'<RSAKeyValue><Modulus>{encode(numbers.n)}</Modulus><Exponent>{encode(numbers.e)}</Exponent></RSAKeyValue>'


def sign_folder(path: str) -> str:
    now = int(time.time())
    payload = f'SGNAS1\n{now}\n{now + 60}\n{uuid.uuid4().hex}\n{validate_folder(path)}'.encode()
    signature = _key().sign(payload, padding.PKCS1v15(), hashes.SHA256())
    return f'shotgrid-nas://open-v1/{_b64(payload)}.{_b64(signature)}'


class ShotGridNasOpenerService:
    @staticmethod
    async def issue(
        db: AsyncSession, version_id: int, current_user: CurrentUserModel, command: NasOpenCommand
    ) -> dict[str, str | int]:
        # 复用版本详情的项目/任务可见性校验；客户端不能提交任意 UNC 路径。
        detail = await ShotGridReviewService.get_version_detail(db, version_id, current_user)
        if detail.project_id != command.project_id or detail.task_id != command.task_id:
            raise shot_grid_error(409, 'SG_NAS_TARGET_CHANGED', '版本归属已变化，请刷新列表')
        file = next((item for item in detail.files if str(item.file_id) == str(command.file_id)), None)
        if file is None or not file.nas_path or file.role in ('thumbnail', 'proxy_media'):
            raise shot_grid_error(404, 'SG_NAS_FILE_NOT_FOUND', '该版本没有可打开的文件目录')
        try:
            validate_folder(file.nas_path)
            folder = validate_folder(file.nas_path.rsplit('\\', 1)[0])
        except ValueError:
            raise shot_grid_error(422, 'SG_NAS_PATH_INVALID', '文件目录不符合安全规则') from None
        uri = await asyncio.to_thread(sign_folder, folder)
        return {'folder': folder, 'uri': uri, 'expiresIn': 60}

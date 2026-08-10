import hashlib
import uuid
from datetime import datetime, timedelta

from pydantic import BaseModel, ValidationError
from redis import asyncio as aioredis
from redis.exceptions import RedisError

from module_shot_grid.config import SHOT_GRID_IMPORT_CONFIG, ShotGridImportConfig
from module_shot_grid.entity.vo.import_common_vo import ImportPreviewTokenPayloadModel
from module_shot_grid.exceptions import shot_grid_error


class ImportPreviewStore:
    """Redis 导入预览载荷存储；Key 和日志均不保留明文 Token。"""

    @classmethod
    def new_token(cls) -> str:
        return str(uuid.uuid4())

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    @staticmethod
    def expires_at(
        config: ShotGridImportConfig = SHOT_GRID_IMPORT_CONFIG,
        *,
        now: datetime | None = None,
    ) -> datetime:
        """生成与 PostgreSQL ``TIMESTAMP(0)`` 一致的预览到期时间。"""
        reference = now or datetime.now()
        return (reference + timedelta(seconds=config.preview_ttl_seconds)).replace(microsecond=0)

    @classmethod
    async def create(
        cls,
        redis: aioredis.Redis,
        payload: ImportPreviewTokenPayloadModel,
        config: ShotGridImportConfig = SHOT_GRID_IMPORT_CONFIG,
    ) -> str:
        token = cls.new_token()
        await cls.save(redis, token, payload, config)
        return token

    @classmethod
    async def save(
        cls,
        redis: aioredis.Redis,
        token: str,
        payload: ImportPreviewTokenPayloadModel,
        config: ShotGridImportConfig = SHOT_GRID_IMPORT_CONFIG,
        *,
        serialized_payload: bytes | None = None,
    ) -> None:
        key = cls._key(token, config)
        value = serialized_payload or cls.serialize_json(payload, config)
        try:
            saved = await redis.set(
                key,
                value,
                ex=config.preview_ttl_seconds,
                nx=True,
            )
        except RedisError as exc:
            raise shot_grid_error(503, 'SG_IMPORT_PREVIEW_STORE_UNAVAILABLE', '导入预览缓存暂不可用') from exc
        if not saved:
            raise shot_grid_error(409, 'SG_IMPORT_TOKEN_CONFLICT', '导入 Token 已存在，请重新预检查')

    @staticmethod
    def serialize_json(model: BaseModel, config: ShotGridImportConfig = SHOT_GRID_IMPORT_CONFIG) -> bytes:
        """序列化并限制 Redis 载荷或 HTTP 预览对象的 UTF-8 JSON 大小。"""
        value = model.model_dump_json(by_alias=True).encode('utf-8')
        if len(value) > config.max_preview_json_bytes:
            raise shot_grid_error(413, 'SG_IMPORT_PREVIEW_TOO_LARGE', '导入预览结果超过大小限制')
        return value

    @classmethod
    async def get(
        cls,
        redis: aioredis.Redis,
        token: str,
        config: ShotGridImportConfig = SHOT_GRID_IMPORT_CONFIG,
    ) -> ImportPreviewTokenPayloadModel | None:
        try:
            value = await redis.get(cls._key(token, config))
        except RedisError as exc:
            raise shot_grid_error(503, 'SG_IMPORT_PREVIEW_STORE_UNAVAILABLE', '导入预览缓存暂不可用') from exc
        if value is None:
            return None
        try:
            return ImportPreviewTokenPayloadModel.model_validate_json(value)
        except ValidationError as exc:
            raise shot_grid_error(409, 'SG_IMPORT_TOKEN_INVALID', '导入预览数据已损坏，请重新预检查') from exc

    @classmethod
    async def delete(
        cls,
        redis: aioredis.Redis,
        token: str,
        config: ShotGridImportConfig = SHOT_GRID_IMPORT_CONFIG,
    ) -> None:
        try:
            await redis.delete(cls._key(token, config))
        except RedisError as exc:
            raise shot_grid_error(503, 'SG_IMPORT_PREVIEW_STORE_UNAVAILABLE', '导入预览缓存暂不可用') from exc

    @classmethod
    def _key(cls, token: str, config: ShotGridImportConfig) -> str:
        return f'{config.redis_key_prefix}:{cls.token_hash(token)}'

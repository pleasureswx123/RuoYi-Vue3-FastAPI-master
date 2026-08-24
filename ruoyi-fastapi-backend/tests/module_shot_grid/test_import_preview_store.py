from datetime import datetime, timedelta

import pytest

from module_shot_grid.config import ShotGridImportConfig
from module_shot_grid.entity.vo.import_common_vo import ImportPreviewTokenPayloadModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.import_preview_store import ImportPreviewStore

TEST_TTL_SECONDS = 90
PAYLOAD_TOO_LARGE_STATUS = 413


class FakeRedis:
    """只覆盖导入预览存储所需的异步 Redis 接口。"""

    def __init__(self) -> None:
        self.values: dict[str, bytes | str] = {}
        self.last_set: tuple[str, int, bool] | None = None

    async def set(self, key: str, value: bytes | str, *, ex: int, nx: bool) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.last_set = (key, ex, nx)
        return True

    async def get(self, key: str) -> bytes | str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)


def _payload() -> ImportPreviewTokenPayloadModel:
    return ImportPreviewTokenPayloadModel(
        batchId=1,
        projectId=2,
        importType='shot',
        previewedBy=3,
        fileSha256='a' * 64,
        templateVersion='shot-v2',
        expiresAt=datetime.now() + timedelta(minutes=5),
        rows=[{'sheetName': 'EP001', 'rowNumber': 2}],
    )


def test_preview_expiry_uses_database_second_precision() -> None:
    config = ShotGridImportConfig(preview_ttl_seconds=TEST_TTL_SECONDS)
    now = datetime(2026, 8, 10, 12, 0, 0, 987654)

    expires_at = ImportPreviewStore.expires_at(config, now=now)

    assert expires_at == datetime(2026, 8, 10, 12, 1, 30)
    assert expires_at.microsecond == 0


@pytest.mark.asyncio
async def test_preview_store_uses_hashed_key_fixed_ttl_and_round_trips_payload() -> None:
    redis = FakeRedis()
    config = ShotGridImportConfig(preview_ttl_seconds=TEST_TTL_SECONDS, redis_key_prefix='test:preview')
    token = 'secret-preview-token'

    await ImportPreviewStore.save(redis, token, _payload(), config)  # type: ignore[arg-type]

    assert redis.last_set is not None
    key, ttl, nx = redis.last_set
    assert token not in key
    assert key == f'test:preview:{ImportPreviewStore.token_hash(token)}'
    assert (ttl, nx) == (TEST_TTL_SECONDS, True)
    loaded = await ImportPreviewStore.get(redis, token, config)  # type: ignore[arg-type]
    assert loaded is not None
    assert loaded.batch_id == 1
    assert loaded.rows == [{'sheetName': 'EP001', 'rowNumber': 2}]


@pytest.mark.asyncio
async def test_preview_store_delete_invalidates_token() -> None:
    redis = FakeRedis()
    config = ShotGridImportConfig(redis_key_prefix='test:preview')
    token = 'token-to-delete'
    await ImportPreviewStore.save(redis, token, _payload(), config)  # type: ignore[arg-type]

    await ImportPreviewStore.delete(redis, token, config)  # type: ignore[arg-type]

    assert await ImportPreviewStore.get(redis, token, config) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_preview_store_enforces_json_byte_limit_before_redis_write() -> None:
    payload = _payload()
    exact_size = len(payload.model_dump_json(by_alias=True).encode('utf-8'))
    accepted = FakeRedis()
    rejected = FakeRedis()

    await ImportPreviewStore.save(  # type: ignore[arg-type]
        accepted,
        'accepted-token',
        payload,
        ShotGridImportConfig(max_preview_json_bytes=exact_size),
    )
    with pytest.raises(ShotGridDomainException) as exc_info:
        await ImportPreviewStore.save(  # type: ignore[arg-type]
            rejected,
            'rejected-token',
            payload,
            ShotGridImportConfig(max_preview_json_bytes=exact_size - 1),
        )

    assert accepted.values
    assert rejected.values == {}
    assert exc_info.value.http_status == PAYLOAD_TOO_LARGE_STATUS
    assert exc_info.value.error_key == 'SG_IMPORT_PREVIEW_TOO_LARGE'

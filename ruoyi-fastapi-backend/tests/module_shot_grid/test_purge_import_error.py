"""PG触发器保留业务提示，不退化为笼统并发冲突。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from module_shot_grid.dao.import_batch_dao import ShotGridImportBatchDao
from module_shot_grid.service.asset_import_service import AssetImportService
from module_shot_grid.service.shot_import_service import ShotGridShotImportService


def _error() -> IntegrityError:
    original = RuntimeError('旧目标文件仍在清理中')
    original.__cause__ = RuntimeError('pg')
    original.__cause__.constraint_name = 'ck_sg_target_purge_reserved'
    return IntegrityError('insert', {}, original)


def test_asset_import_preserves_cleanup_reason() -> None:
    assert AssetImportService._map_integrity_error(_error()).error_key == 'SG_TARGET_PURGE_PATH_RESERVED'


@pytest.mark.asyncio
async def test_shot_failed_batch_preserves_cleanup_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    mark = AsyncMock()
    monkeypatch.setattr(ShotGridImportBatchDao, 'mark_failed', mark)
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    await ShotGridShotImportService._record_failed_batch(
        db, project_id=16, batch_id=1, committed_by=1, idempotency_key='test', selection_hash='test', exc=_error()
    )
    assert mark.await_args.kwargs['error_key'] == 'SG_TARGET_PURGE_PATH_RESERVED'

"""验证交接增量与主线审核、迁移历史的兼容边界。"""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from alembic.script import ScriptDirectory

from module_shot_grid.dao.daily_record_dao import DailyRecordDao
from module_shot_grid.dao.final_delivery_dao import ShotGridFinalDeliveryDao
from module_shot_grid.entity.vo.daily_record_vo import DailyQuery
from module_shot_grid.service.review_service import ShotGridReviewService


def test_merge_head_keeps_both_existing_revision_histories() -> None:
    script = ScriptDirectory(str(Path(__file__).resolve().parents[2] / 'alembic'))
    assert script.get_heads() == ['20261118_46']
    assert script.get_revision('20261118_45').down_revision == '20261116_44'
    assert set(script.get_revision('20261116_44').down_revision) == {'20261026_41', '20261111_43'}
    assert script.get_revision('20261030_41').down_revision == '20261013_40'


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['pending', 'published', 'failed', 'publishing'])
async def test_formal_feedback_preserves_delivery_fencing(monkeypatch: pytest.MonkeyPatch, status: str) -> None:
    delivery = SimpleNamespace(
        project_id=1,
        task_id=2,
        version_id=3,
        candidate_id=4,
        additional_files=[{'candidate_id': 5}],
        source_file_id='file',
        business_file_name='a.mp4',
        source_nas_relative_path='source',
        final_nas_relative_path='final',
        manifest_nas_relative_path='manifest',
        source_sha256='a' * 64,
        source_file_size=5,
        delivery_status=status,
        validity_status='current',
        attempt_count=7,
        lease_owner='worker',
    )
    monkeypatch.setattr(ShotGridFinalDeliveryDao, 'get_for_update', AsyncMock(return_value=delivery))
    add = AsyncMock()
    monkeypatch.setattr(ShotGridFinalDeliveryDao, 'add', add)
    original_attempt = delivery.attempt_count
    db = AsyncMock()
    version = SimpleNamespace(version_id=3, review_cycle=2)
    if status == 'publishing':
        with pytest.raises(Exception, match='最终交付正在执行'):
            await ShotGridReviewService._revoke_feedback_delivery(db, version, 9, datetime.now())
        add.assert_not_awaited()
        assert delivery.validity_status == 'current'
    else:
        await ShotGridReviewService._revoke_feedback_delivery(db, version, 9, datetime.now())
        revoke = add.await_args.args[1]
        assert revoke.operation == 'revoke' and revoke.review_cycle == version.review_cycle
        assert revoke.additional_files == delivery.additional_files
        assert revoke.delivery_status == 'pending'
        assert delivery.validity_status == 'revoked'
        assert delivery.delivery_status == ('cancelled' if status == 'pending' else status)
    assert delivery.attempt_count == original_attempt and delivery.lease_owner == 'worker'
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_daily_approval_count_excludes_revocation_events() -> None:
    db = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = []
    db.execute.return_value = result
    db.scalar.return_value = 0
    await DailyRecordDao.statistics(db, 1, DailyQuery(start='2026-11-01', end='2026-11-16'), None)
    query = db.scalar.await_args_list[-1].args[0]
    compiled = query.compile()
    assert 'sg_final_delivery.operation =' in str(compiled)
    assert 'publish' in compiled.params.values()
    assert 'count(distinct(sg_version.task_id))' in str(compiled)

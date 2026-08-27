from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from module_shot_grid.service.final_delivery_path_adapter import FinalDeliveryPublishResult
from module_shot_grid.service.final_delivery_worker_service import ShotGridFinalDeliveryWorkerService
from module_shot_grid.service.version_publish_path_adapter import VersionPublishPathAdapterError


def _db() -> SimpleNamespace:
    return SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())


def _claimed() -> SimpleNamespace:
    return SimpleNamespace(final_delivery_id=19, attempt_count=1, lease_owner='leader:claim')


def _context_row() -> dict[str, object]:
    return {
        'final_delivery_id': 19,
        'project_id': 3,
        'task_id': 10,
        'version_id': 14,
        'candidate_id': 22,
        'business_file_name': 'final.mp4',
        'source_nas_relative_path': 'VIDEO\\EP01\\001_S001\\final.mp4',
        'final_nas_relative_path': 'VIDEO\\EP01\\001_S001\\FINAL\\final.mp4',
        'manifest_nas_relative_path': 'VIDEO\\EP01\\001_S001\\FINAL\\FINAL.json',
        'source_sha256': 'a' * 64,
        'source_file_size': 9,
        'delivery_status': 'publishing',
        'attempt_count': 1,
        'lease_owner': 'leader:claim',
        'approved_by': 7,
        'approved_time': datetime(2026, 8, 26, 18, 30),
        'version_no': 1,
        'version_status': 'final',
        'selected_candidate_id': 22,
        'candidate_no': 2,
        'task_status': 'completed',
        'storage_status': 'ready',
        'root_path_snapshot': r'\\server\share',
        'project_relative_path': 'AI影视短片\\罗刹夫人',
        'project_path_snapshot': r'\\server\share\AI影视短片\罗刹夫人',
        'protocol': 'smb_unc',
        'configured_root_path': r'\\server\share',
        'root_del_flag': '0',
    }


@pytest.mark.asyncio
async def test_worker_claims_publishes_and_marks_result_with_fencing() -> None:
    db = _db()
    adapter = SimpleNamespace(
        publish=AsyncMock(
            return_value=FinalDeliveryPublishResult(sha256='a' * 64, file_size=9, publish_mode='hardlink')
        )
    )
    with (
        patch(
            'module_shot_grid.service.final_delivery_worker_service.ShotGridFinalDeliveryDao.claim_next',
            AsyncMock(return_value=_claimed()),
        ),
        patch(
            'module_shot_grid.service.final_delivery_worker_service.ShotGridFinalDeliveryDao.get_publish_context',
            AsyncMock(return_value=_context_row()),
        ),
        patch(
            'module_shot_grid.service.final_delivery_worker_service.ShotGridFinalDeliveryDao.mark_published',
            AsyncMock(return_value=True),
        ) as mark_published,
    ):
        result = await ShotGridFinalDeliveryWorkerService.run_once(
            db,
            worker_id='leader',
            adapter=adapter,
            lease_seconds=30,
            heartbeat_seconds=5,
            operation_timeout_seconds=10,
        )

    assert result.outcome == 'published'
    mark_published.assert_awaited_once()
    assert mark_published.await_args.kwargs['worker_id'] == 'leader:claim'
    assert mark_published.await_args.kwargs['attempt_count'] == 1
    assert mark_published.await_args.kwargs['publish_mode'] == 'hardlink'


@pytest.mark.asyncio
async def test_worker_persists_terminal_safe_error_for_changed_source() -> None:
    db = _db()
    adapter = SimpleNamespace(
        publish=AsyncMock(
            side_effect=VersionPublishPathAdapterError(
                error_key='SG_FINAL_SOURCE_CHANGED',
                safe_message='最佳候选 NAS 文件摘要或大小已发生变化',
                retryable=False,
            )
        )
    )
    with (
        patch(
            'module_shot_grid.service.final_delivery_worker_service.ShotGridFinalDeliveryDao.claim_next',
            AsyncMock(return_value=_claimed()),
        ),
        patch(
            'module_shot_grid.service.final_delivery_worker_service.ShotGridFinalDeliveryDao.get_publish_context',
            AsyncMock(return_value=_context_row()),
        ),
        patch(
            'module_shot_grid.service.final_delivery_worker_service.ShotGridFinalDeliveryDao.mark_failed',
            AsyncMock(return_value=True),
        ) as mark_failed,
    ):
        result = await ShotGridFinalDeliveryWorkerService.run_once(
            db,
            worker_id='leader',
            adapter=adapter,
            lease_seconds=30,
            heartbeat_seconds=5,
            operation_timeout_seconds=10,
        )

    assert result.outcome == 'failed'
    assert result.error_key == 'SG_FINAL_SOURCE_CHANGED'
    assert mark_failed.await_args.kwargs['attempt_count'] == 1


@pytest.mark.asyncio
async def test_worker_does_not_write_success_after_lease_is_lost() -> None:
    db = _db()
    adapter = SimpleNamespace(
        publish=AsyncMock(return_value=FinalDeliveryPublishResult(sha256='a' * 64, file_size=9, publish_mode='copied'))
    )
    with (
        patch(
            'module_shot_grid.service.final_delivery_worker_service.ShotGridFinalDeliveryDao.claim_next',
            AsyncMock(return_value=_claimed()),
        ),
        patch(
            'module_shot_grid.service.final_delivery_worker_service.ShotGridFinalDeliveryDao.get_publish_context',
            AsyncMock(return_value=_context_row()),
        ),
        patch(
            'module_shot_grid.service.final_delivery_worker_service.ShotGridFinalDeliveryDao.mark_published',
            AsyncMock(return_value=False),
        ),
    ):
        result = await ShotGridFinalDeliveryWorkerService.run_once(
            db,
            worker_id='leader',
            adapter=adapter,
            lease_seconds=30,
            heartbeat_seconds=5,
            operation_timeout_seconds=10,
        )

    assert result.outcome == 'lease_lost'
    db.rollback.assert_awaited()

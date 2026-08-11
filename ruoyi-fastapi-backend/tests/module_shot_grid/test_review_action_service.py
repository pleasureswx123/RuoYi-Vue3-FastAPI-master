# ruff: noqa: ANN001, ANN201, ANN202, PLR2004, SIM117
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.review_service import ShotGridReviewService


def row(**values):
    defaults = {
        'project_id': 3,
        'task_id': 8,
        'version_id': 21,
        'task_status': 'pending_review',
        'version_status': 'pending_review',
        'lock_version': 4,
        'update_time': None,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


@pytest.fixture(autouse=True)
def _review_transaction_dependencies():
    with (
        patch(
            'module_shot_grid.service.review_service.ShotGridReviewDao.lock_auto_review_lists',
            AsyncMock(return_value=[]),
        ),
        patch('module_shot_grid.service.review_service.ShotGridProjectAuditDao.add_success_log', AsyncMock()),
    ):
        yield


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('action', 'version_status', 'task_status'),
    [
        ('reject', 'rejected', 'revision'),
        ('approve', 'final', 'completed'),
        ('defer', 'pending_review', 'pending_review'),
    ],
)
async def test_named_review_transitions_are_atomic(action, version_status, task_status):
    task, version = row(version_id=None), row()
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(), add=Mock())
    body = SimpleNamespace(lock_version=4, reason='需要修改' if action == 'reject' else None)
    with (
        patch('module_shot_grid.service.review_service.ShotGridReviewDao.lock_task', AsyncMock(return_value=task)),
        patch(
            'module_shot_grid.service.review_service.ShotGridReviewDao.lock_versions', AsyncMock(return_value=[version])
        ),
        patch('module_shot_grid.service.review_service.ShotGridReviewDao.add') as add,
    ):
        result = await ShotGridReviewService.review_action(db, 3, 8, 21, 99, action, body)
    assert (version.version_status, task.task_status) == (version_status, task_status)
    assert result['versionLockVersion'] == 5
    assert add.call_args.args[1].reason == body.reason
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('task_status', 'lock_version', 'error_key'),
    [('completed', 4, 'SG_REVIEW_TASK_COMPLETED'), ('pending_review', 3, 'SG_REVIEW_LOCK_CONFLICT')],
)
async def test_repeated_completed_and_stale_actions_return_stable_conflict(task_status, lock_version, error_key):
    task, version = row(version_id=None, task_status=task_status), row(lock_version=lock_version)
    db = SimpleNamespace()
    with (
        patch('module_shot_grid.service.review_service.ShotGridReviewDao.lock_task', AsyncMock(return_value=task)),
        patch(
            'module_shot_grid.service.review_service.ShotGridReviewDao.lock_versions', AsyncMock(return_value=[version])
        ),
    ):
        with pytest.raises(ShotGridDomainException) as caught:
            await ShotGridReviewService.review_action(
                db, 3, 8, 21, 99, 'approve', SimpleNamespace(lock_version=4, reason=None)
            )
    assert caught.value.http_status == 409
    assert caught.value.error_key == error_key


@pytest.mark.asyncio
async def test_cross_project_version_is_not_accepted():
    db = SimpleNamespace()
    with (
        patch(
            'module_shot_grid.service.review_service.ShotGridReviewDao.lock_task',
            AsyncMock(return_value=row(version_id=None)),
        ),
        patch('module_shot_grid.service.review_service.ShotGridReviewDao.lock_versions', AsyncMock(return_value=[])),
    ):
        with pytest.raises(ShotGridDomainException) as caught:
            await ShotGridReviewService.review_action(
                db, 3, 8, 999, 99, 'approve', SimpleNamespace(lock_version=0, reason=None)
            )
    assert caught.value.http_status == 404
    assert caught.value.error_key == 'SG_VERSION_NOT_FOUND'


@pytest.mark.asyncio
async def test_v001_rejected_then_v002_can_be_final_without_mutating_history():
    task = row(version_id=None)
    v1 = row(version_id=21, version_status='rejected', lock_version=5)
    v2 = row(version_id=22, version_status='pending_review', lock_version=0)
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    with (
        patch('module_shot_grid.service.review_service.ShotGridReviewDao.lock_task', AsyncMock(return_value=task)),
        patch(
            'module_shot_grid.service.review_service.ShotGridReviewDao.lock_versions', AsyncMock(return_value=[v1, v2])
        ),
        patch('module_shot_grid.service.review_service.ShotGridReviewDao.add'),
    ):
        await ShotGridReviewService.review_action(
            db, 3, 8, 22, 99, 'approve', SimpleNamespace(lock_version=0, reason=None)
        )
    assert (v1.version_status, v1.lock_version) == ('rejected', 5)
    assert v2.version_status == 'final'


@pytest.mark.asyncio
async def test_old_v001_cannot_be_approved_while_v002_is_pending():
    task = row(version_id=None)
    v1 = row(version_id=21, version_status='rejected', lock_version=5)
    v2 = row(version_id=22, version_status='pending_review', lock_version=0)
    with (
        patch('module_shot_grid.service.review_service.ShotGridReviewDao.lock_task', AsyncMock(return_value=task)),
        patch(
            'module_shot_grid.service.review_service.ShotGridReviewDao.lock_versions',
            AsyncMock(return_value=[v1, v2]),
        ),
        pytest.raises(ShotGridDomainException) as caught,
    ):
        await ShotGridReviewService.review_action(
            SimpleNamespace(), 3, 8, 21, 99, 'approve', SimpleNamespace(lock_version=5, reason=None)
        )
    assert caught.value.error_key == 'SG_REVIEW_STATUS_CONFLICT'


@pytest.mark.asyncio
async def test_concurrent_approve_integrity_conflict_rolls_back():
    task, version = row(version_id=None), row()
    db = SimpleNamespace(
        commit=AsyncMock(side_effect=IntegrityError('statement', {}, Exception())), rollback=AsyncMock()
    )
    with (
        patch('module_shot_grid.service.review_service.ShotGridReviewDao.lock_task', AsyncMock(return_value=task)),
        patch(
            'module_shot_grid.service.review_service.ShotGridReviewDao.lock_versions',
            AsyncMock(return_value=[version]),
        ),
        patch('module_shot_grid.service.review_service.ShotGridReviewDao.add'),
        pytest.raises(ShotGridDomainException) as caught,
    ):
        await ShotGridReviewService.review_action(
            db, 3, 8, 21, 99, 'approve', SimpleNamespace(lock_version=4, reason=None)
        )
    assert caught.value.error_key == 'SG_REVIEW_CONCURRENT_CONFLICT'
    db.rollback.assert_awaited_once()

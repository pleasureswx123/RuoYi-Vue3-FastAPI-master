# ruff: noqa: ANN001, ANN201, SIM117
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.review_service import ShotGridReviewService


def item(version_id, sort_order=0):
    return SimpleNamespace(version_id=version_id, sort_order=sort_order)


def version(version_id=11, status='pending_review'):
    return SimpleNamespace(version_id=version_id, version_status=status)


def task(project_id=3, status='pending_review'):
    return SimpleNamespace(project_id=project_id, task_status=status)


@pytest.mark.asyncio
async def test_manual_list_rejects_cross_project_version_injection():
    with patch(
        'module_shot_grid.service.review_service.ShotGridReviewDao.versions_by_ids_for_update',
        AsyncMock(return_value=[]),
    ):
        with pytest.raises(ShotGridDomainException) as caught:
            await ShotGridReviewService._validate_eligible_versions(SimpleNamespace(), 3, [item(999)])
    assert caught.value.error_key == 'SG_REVIEW_LIST_VERSION_SCOPE_INVALID'


@pytest.mark.asyncio
async def test_manual_list_rejects_version_whose_review_state_changed():
    with patch(
        'module_shot_grid.service.review_service.ShotGridReviewDao.versions_by_ids_for_update',
        AsyncMock(return_value=[(version(status='final'), task())]),
    ):
        with pytest.raises(ShotGridDomainException) as caught:
            await ShotGridReviewService._validate_eligible_versions(SimpleNamespace(), 3, [item(11)])
    assert caught.value.error_key == 'SG_REVIEW_LIST_VERSION_STATUS_INVALID'


@pytest.mark.asyncio
async def test_reorder_rejects_stale_lock_version_before_writing_order():
    review_list = SimpleNamespace(review_mode='manual_batch', review_status='active', lock_version=5)
    body = SimpleNamespace(lock_version=4, versions=[item(11)])
    with patch(
        'module_shot_grid.service.review_service.ShotGridReviewService._require_review_list',
        AsyncMock(return_value=review_list),
    ):
        with pytest.raises(ShotGridDomainException) as caught:
            await ShotGridReviewService.reorder_review_list(SimpleNamespace(), 3, 7, 9, body)
    assert caught.value.error_key == 'SG_REVIEW_LIST_LOCK_CONFLICT'

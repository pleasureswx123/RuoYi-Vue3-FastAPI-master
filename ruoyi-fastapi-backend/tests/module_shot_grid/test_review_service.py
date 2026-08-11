from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.entity.do.review_do import ShotGridReviewAction
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.review_vo import (
    ShotGridNoteCreateModel,
    ShotGridReviewActionCreateModel,
    ShotGridReviewActionResultModel,
)
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.review_service import ShotGridReviewService

PROJECT_ID = 1001
TASK_ID = 7001
VERSION_ID = 9001
REVIEW_LIST_ID = 8001
DIRECTOR_ID = 1
CONFLICT_STATUS = 409
UNPROCESSABLE_STATUS = 422
FORBIDDEN_STATUS = 403
INITIAL_TASK_LOCK_VERSION = 3
UPDATED_TASK_LOCK_VERSION = 4
IDEMPOTENCY_RACE_QUERY_COUNT = 2


def _current_user(user_id: int = DIRECTOR_ID) -> CurrentUserModel:
    return CurrentUserModel(
        permissions=['shotgrid:version:review', 'shotgrid:note:add'],
        roles=[],
        user=UserInfoModel(userId=user_id, userName='director', nickName='项目总监'),
    )


def _access(role: str = 'director') -> ShotGridProjectAccessModel:
    return ShotGridProjectAccessModel(
        projectId=PROJECT_ID,
        userId=DIRECTOR_ID,
        projectRole=role,
    )


def _version_context(task_kind: str = 'shot_video') -> dict[str, Any]:
    return {
        'version_id': VERSION_ID,
        'project_id': PROJECT_ID,
        'task_id': TASK_ID,
        'version_no': 1,
        'version_status': 'pending_review',
        'lock_version': 0,
        'task_kind': task_kind,
        'task_status': 'pending_review',
        'assignee_user_id': 2,
        'shot_id': 3001 if task_kind == 'shot_video' else None,
        'asset_item_id': 4001 if task_kind == 'asset_image' else None,
        'shot_duration_ms': 6000 if task_kind == 'shot_video' else None,
    }


def _locked_graph() -> tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]:
    task = SimpleNamespace(
        task_id=TASK_ID,
        task_status='pending_review',
        assignee_user_id=2,
        lock_version=INITIAL_TASK_LOCK_VERSION,
        update_by='creator',
        update_time=datetime(2026, 8, 11, 9, 0, 0),
    )
    version = SimpleNamespace(
        version_id=VERSION_ID,
        version_no=1,
        version_status='pending_review',
        lock_version=0,
    )
    review_list = SimpleNamespace(
        review_list_id=REVIEW_LIST_ID,
        review_status='active',
        lock_version=0,
        update_by='creator',
        update_time=datetime(2026, 8, 11, 9, 0, 0),
    )
    return task, version, review_list


def _persisted_approve_action(command: ShotGridReviewActionCreateModel) -> ShotGridReviewAction:
    snapshot = ShotGridReviewActionResultModel(
        actionId=6001,
        projectId=PROJECT_ID,
        versionId=VERSION_ID,
        reviewerUserId=DIRECTOR_ID,
        reviewerName='项目总监',
        actionType='approve',
        fromStatus='pending_review',
        toStatus='final',
        createTime=datetime(2026, 8, 11, 10, 0, 0),
        taskId=TASK_ID,
        taskStatus='completed',
        autoReviewListId=REVIEW_LIST_ID,
        reviewStatus='completed',
        lockVersion=1,
    )
    return ShotGridReviewAction(
        version_id=VERSION_ID,
        reviewer_user_id=DIRECTOR_ID,
        request_hash=ShotGridReviewService._review_action_request_hash(command),
        result_snapshot=snapshot.model_dump(mode='json'),
    )


async def _patch_review_action_graph(
    monkeypatch: pytest.MonkeyPatch,
    *,
    has_open_mandatory: bool = False,
    existing: ShotGridReviewAction | None = None,
) -> tuple[AsyncMock, SimpleNamespace, SimpleNamespace, SimpleNamespace, list[str]]:
    db = AsyncMock()
    task, version, review_list = _locked_graph()
    events: list[str] = []
    monkeypatch.setattr(
        ShotGridReviewService,
        '_resolve_version_access',
        AsyncMock(return_value=(_version_context(), _access())),
    )
    monkeypatch.setattr(
        ShotGridReviewService,
        '_lock_version_graph',
        AsyncMock(return_value=(PROJECT_ID, task, version, _access())),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.find_review_action_by_idempotency',
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.get_latest_version_no',
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.get_auto_review_list_for_update',
        AsyncMock(return_value=review_list),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.get_auto_review_relation_version_ids',
        AsyncMock(return_value=[VERSION_ID]),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.has_open_mandatory_note',
        AsyncMock(return_value=has_open_mandatory),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.has_other_final_version',
        AsyncMock(return_value=False),
    )

    async def add_action(_db: Any, action: ShotGridReviewAction) -> ShotGridReviewAction:
        events.append('action')
        action.action_id = 6001
        action.create_time = datetime(2026, 8, 11, 10, 0, 0)
        return action

    async def audit(*_args: Any, **_kwargs: Any) -> None:
        events.append('audit')

    async def commit() -> None:
        events.append('commit')

    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.add_review_action',
        AsyncMock(side_effect=add_action),
    )
    monkeypatch.setattr(ShotGridReviewService, '_audit', AsyncMock(side_effect=audit))
    db.commit.side_effect = commit
    return db, task, version, review_list, events


@pytest.mark.asyncio
async def test_approve_atomically_completes_version_task_and_auto_review_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, task, version, review_list, events = await _patch_review_action_graph(monkeypatch)

    result = await ShotGridReviewService.create_review_action(
        db,
        VERSION_ID,
        ShotGridReviewActionCreateModel(actionType='approve', lockVersion=0),
        'approve-1',
        _current_user(),
    )

    assert result.version_id == VERSION_ID
    assert result.to_status == 'final'
    assert result.task_status == 'completed'
    assert result.review_status == 'completed'
    assert result.lock_version == 1
    assert version.version_status == 'final'
    assert task.task_status == 'completed'
    assert task.lock_version == UPDATED_TASK_LOCK_VERSION
    assert review_list.review_status == 'completed'
    assert review_list.lock_version == 1
    assert events == ['action', 'audit', 'commit']
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_approve_with_open_mandatory_note_fails_without_partial_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, task, version, review_list, events = await _patch_review_action_graph(
        monkeypatch,
        has_open_mandatory=True,
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridReviewService.create_review_action(
            db,
            VERSION_ID,
            ShotGridReviewActionCreateModel(actionType='approve', lockVersion=0),
            'approve-blocked',
            _current_user(),
        )

    assert exc_info.value.http_status == CONFLICT_STATUS
    assert exc_info.value.error_key == 'SG_REVIEW_MANDATORY_NOTES_OPEN'
    assert version.version_status == 'pending_review'
    assert task.task_status == 'pending_review'
    assert review_list.review_status == 'active'
    assert events == []
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_reject_requires_reason_or_open_mandatory_note(monkeypatch: pytest.MonkeyPatch) -> None:
    db, _, _, _, events = await _patch_review_action_graph(monkeypatch)

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridReviewService.create_review_action(
            db,
            VERSION_ID,
            ShotGridReviewActionCreateModel(actionType='reject', lockVersion=0),
            'reject-no-reason',
            _current_user(),
        )

    assert exc_info.value.http_status == UNPROCESSABLE_STATUS
    assert exc_info.value.error_key == 'SG_REVIEW_REASON_REQUIRED'
    assert events == []


@pytest.mark.asyncio
async def test_defer_only_records_action_and_advances_version_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    db, task, version, review_list, _ = await _patch_review_action_graph(monkeypatch)

    result = await ShotGridReviewService.create_review_action(
        db,
        VERSION_ID,
        ShotGridReviewActionCreateModel(actionType='defer', reason='稍后复核', lockVersion=0),
        'defer-1',
        _current_user(),
    )

    assert result.to_status == 'pending_review'
    assert result.task_status == 'pending_review'
    assert result.review_status == 'active'
    assert version.lock_version == 1
    assert task.lock_version == INITIAL_TASK_LOCK_VERSION
    assert review_list.lock_version == 0


@pytest.mark.asyncio
async def test_review_action_same_idempotency_replays_persisted_result_before_state_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = ShotGridReviewActionCreateModel(actionType='approve', lockVersion=0)
    existing = _persisted_approve_action(command)
    db, _, _, _, events = await _patch_review_action_graph(monkeypatch, existing=existing)

    result = await ShotGridReviewService.create_review_action(
        db,
        VERSION_ID,
        command,
        'approve-replay',
        _current_user(),
    )

    assert result.replayed is True
    assert result.to_status == 'final'
    assert events == []
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_idempotency_unique_race_rolls_back_requeries_and_replays_first_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = ShotGridReviewActionCreateModel(actionType='approve', lockVersion=0)
    existing = _persisted_approve_action(command)
    db, _, _, _, events = await _patch_review_action_graph(monkeypatch)
    find_existing = AsyncMock(side_effect=[None, existing])
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.find_review_action_by_idempotency',
        find_existing,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.add_review_action',
        AsyncMock(side_effect=IntegrityError('INSERT', {}, RuntimeError('duplicate key'))),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridProjectService._constraint_name',
        lambda _exc: 'uk_sg_review_action_idempotency',
    )

    result = await ShotGridReviewService.create_review_action(
        db,
        VERSION_ID,
        command,
        'approve-race',
        _current_user(),
    )

    assert result.replayed is True
    assert result.to_status == 'final'
    assert find_existing.await_count == IDEMPOTENCY_RACE_QUERY_COUNT
    assert db.rollback.await_count == IDEMPOTENCY_RACE_QUERY_COUNT
    db.commit.assert_not_awaited()
    assert events == []


@pytest.mark.asyncio
async def test_idempotency_unique_race_with_different_hash_returns_conflict_and_closes_query_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = ShotGridReviewActionCreateModel(actionType='approve', lockVersion=0)
    existing = _persisted_approve_action(ShotGridReviewActionCreateModel(actionType='reject', lockVersion=0))
    db, _, _, _, _ = await _patch_review_action_graph(monkeypatch)
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.find_review_action_by_idempotency',
        AsyncMock(side_effect=[None, existing]),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.add_review_action',
        AsyncMock(side_effect=IntegrityError('INSERT', {}, RuntimeError('duplicate key'))),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridProjectService._constraint_name',
        lambda _exc: 'uk_sg_review_action_idempotency',
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridReviewService.create_review_action(
            db,
            VERSION_ID,
            command,
            'approve-race-conflict',
            _current_user(),
        )

    assert exc_info.value.error_key == 'SG_IDEMPOTENCY_CONFLICT'
    assert db.rollback.await_count == IDEMPOTENCY_RACE_QUERY_COUNT


@pytest.mark.asyncio
async def test_unknown_integrity_error_is_not_disguised_as_state_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, _, _, _, _ = await _patch_review_action_graph(monkeypatch)
    integrity_error = IntegrityError('INSERT', {}, RuntimeError('foreign key violation'))
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.add_review_action',
        AsyncMock(side_effect=integrity_error),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridProjectService._constraint_name',
        lambda _exc: 'fk_unknown_audit_reference',
    )

    with pytest.raises(IntegrityError) as exc_info:
        await ShotGridReviewService.create_review_action(
            db,
            VERSION_ID,
            ShotGridReviewActionCreateModel(actionType='approve', lockVersion=0),
            'approve-unknown-db-error',
            _current_user(),
        )

    assert exc_info.value is integrity_error
    db.rollback.assert_awaited_once()


def test_note_media_time_uses_shot_duration_and_rejects_asset_timepoint() -> None:
    ShotGridReviewService._validate_note_media(
        _version_context(),
        ShotGridNoteCreateModel(content='尾帧需要调整', mediaTimeMs=6000),
    )

    with pytest.raises(ShotGridDomainException) as shot_error:
        ShotGridReviewService._validate_note_media(
            _version_context(),
            ShotGridNoteCreateModel(content='越界', mediaTimeMs=6001),
        )
    assert shot_error.value.error_key == 'SG_NOTE_MEDIA_TIME_INVALID'

    with pytest.raises(ShotGridDomainException) as asset_error:
        ShotGridReviewService._validate_note_media(
            _version_context('asset_image'),
            ShotGridNoteCreateModel(content='图片意见', mediaTimeMs=0),
        )
    assert asset_error.value.error_key == 'SG_NOTE_MEDIA_TIME_INVALID'


@pytest.mark.asyncio
async def test_add_note_revalidates_media_time_after_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    task, version, _ = _locked_graph()
    stale_context = _version_context()
    locked_context = {**stale_context, 'shot_duration_ms': 1000}
    monkeypatch.setattr(
        ShotGridReviewService,
        '_resolve_version_access',
        AsyncMock(return_value=(stale_context, _access())),
    )
    monkeypatch.setattr(
        ShotGridReviewService,
        '_lock_version_graph',
        AsyncMock(return_value=(PROJECT_ID, task, version, _access())),
    )
    context_query = AsyncMock(return_value=locked_context)
    add_note = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.get_version_context',
        context_query,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.add_note',
        add_note,
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridReviewService.add_note(
            db,
            VERSION_ID,
            ShotGridNoteCreateModel(content='超出锁后镜头时长', mediaTimeMs=2000),
            _current_user(),
        )

    assert exc_info.value.error_key == 'SG_NOTE_MEDIA_TIME_INVALID'
    context_query.assert_awaited_once_with(db, VERSION_ID)
    add_note.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


def test_creator_cannot_execute_director_review_action() -> None:
    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridReviewService._require_director(_access('creator'))

    assert exc_info.value.http_status == FORBIDDEN_STATUS
    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'


@pytest.mark.parametrize('value', [None, '', '   ', 'key\nvalue', 'key\x00value', 'x' * 101])
def test_idempotency_key_missing_control_char_or_overlength_returns_stable_error(value: str | None) -> None:
    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridReviewService._normalize_idempotency_key(value)

    assert exc_info.value.http_status == UNPROCESSABLE_STATUS
    assert exc_info.value.error_key == 'SG_IDEMPOTENCY_KEY_INVALID'


@pytest.mark.asyncio
async def test_version_detail_returns_only_safe_file_fields_and_redacts_ai_params_for_creator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = {
        'version_id': VERSION_ID,
        'project_id': PROJECT_ID,
        'task_id': TASK_ID,
        'version_no': 1,
        'version_status': 'pending_review',
        'changelog': '首次提交',
        'ai_params': {'prompt': 'internal'},
        'submitted_by': 2,
        'submitter_name': '制作人员',
        'submitted_time': datetime(2026, 8, 11, 9, 0, 0),
        'generated_at_ms': 1786094626499,
        'lock_version': 0,
    }
    monkeypatch.setattr(
        ShotGridReviewService,
        '_resolve_version_access',
        AsyncMock(return_value=(_version_context(), _access('creator'))),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.get_version_row',
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.get_version_files',
        AsyncMock(
            return_value=[
                {
                    'file_id': '5ed39e04-2f29-45ab-a58c-4f8168f5131a',
                    'original_name': 'upload.mp4',
                    'business_file_name': 'WGZR_EP001_001_S001_YJF_V001_1786094626499.mp4',
                    'role': 'review_media',
                    'is_primary': '1',
                    'sort_order': 0,
                    'content_type': 'video/mp4',
                    'file_size': 1024,
                    'storage_key': 'must-not-leak',
                }
            ]
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.get_auto_review_summary',
        AsyncMock(return_value=None),
    )

    detail = await ShotGridReviewService.get_version_detail(AsyncMock(), VERSION_ID, _current_user())

    assert detail.ai_params is None
    assert detail.version_number == 'V001'
    assert detail.files[0].url == ('/shot-grid/versions/9001/files/5ed39e04-2f29-45ab-a58c-4f8168f5131a/download')
    assert 'storage_key' not in detail.files[0].model_dump()


@pytest.mark.asyncio
async def test_auto_review_list_relation_must_contain_only_auto_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.review_service.ShotGridReviewDao.get_auto_review_relation_version_ids',
        AsyncMock(return_value=[VERSION_ID, VERSION_ID + 1]),
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridReviewService._ensure_auto_review_relation(AsyncMock(), REVIEW_LIST_ID, VERSION_ID)

    assert exc_info.value.error_key == 'SG_AUTO_REVIEW_LIST_INTEGRITY_CONFLICT'

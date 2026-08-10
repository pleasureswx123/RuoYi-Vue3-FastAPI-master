from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.shot_crud_vo import (
    ShotGridShotArchiveModel,
    ShotGridShotCreateModel,
    ShotGridShotListQueryModel,
    ShotGridShotUpdateModel,
)
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.shot_crud_service import ShotGridShotCrudService

PROJECT_ID = 1001
SHOT_ID = 3001
ASSIGNEE_USER_ID = 2
CONFLICT_STATUS = 409
NOT_FOUND_STATUS = 404
LATEST_FEEDBACK_NOTE_ID = 12003
MAX_AUDIT_METHOD_LENGTH = 100
UNAUTHENTICATED_STATUS = 401


def _current_user() -> CurrentUserModel:
    return CurrentUserModel(
        permissions=['shotgrid:shot:add', 'shotgrid:shot:edit', 'shotgrid:shot:archive'],
        roles=[],
        user=UserInfoModel(userId=1, userName='director'),
    )


def _access() -> ShotGridProjectAccessModel:
    return ShotGridProjectAccessModel(projectId=PROJECT_ID, userId=1, projectRole='director')


def _project_storage(status: str = 'ready') -> tuple[SimpleNamespace, SimpleNamespace]:
    return (
        SimpleNamespace(project_id=PROJECT_ID, project_status='active'),
        SimpleNamespace(storage_status=status),
    )


def test_shot_actor_rejects_missing_user_with_frozen_authentication_error() -> None:
    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridShotCrudService._actor(SimpleNamespace(user=None))

    assert exc_info.value.http_status == UNAUTHENTICATED_STATUS
    assert exc_info.value.error_key == 'SG_CURRENT_USER_INVALID'


def _scene_context() -> tuple[SimpleNamespace, SimpleNamespace]:
    return (
        SimpleNamespace(scene_id=20, scene_no=1),
        SimpleNamespace(episode_id=10, episode_no=1, storage_dir_name='EP001'),
    )


def _shot_projection_row(*, operation_status: str | None = 'succeeded') -> dict[str, Any]:
    return {
        'shot_id': SHOT_ID,
        'project_id': PROJECT_ID,
        'project_status': 'active',
        'storage_status': 'ready',
        'episode_id': 10,
        'episode_no': 1,
        'scene_id': 20,
        'scene_no': 1,
        'scene_name': '舱室惊醒',
        'shot_no': 1,
        'storage_dir_name': 'S001',
        'directory_operation_status': operation_status,
        'duration_ms': 6000,
        'shot_size': '中近景',
        'camera_position': '低机位',
        'camera_movement': '缓慢推进',
        'focal_length': '35/25',
        'description': '舱室内主角惊醒',
        'dialogue': None,
        'sound_effect': None,
        'color_reference': None,
        'remark': None,
        'sort_order': 100,
        'lifecycle_status': 'active',
        'status': 'completed',
        'task_id': 7001,
        'task_kind': 'shot_video',
        'task_status': 'completed',
        'priority': 'normal',
        'due_date': None,
        'task_lock_version': 3,
        'assignee_user_id': ASSIGNEE_USER_ID,
        'assignee_nick_name': '杨景锋',
        'assignee_producer_code': None,
        'create_by': 'director',
        'create_time': datetime(2026, 8, 7, 12, 0, 0),
        'update_by': 'director',
        'update_time': datetime(2026, 8, 7, 16, 0, 0),
        'lock_version': 1,
    }


def _latest_read_projection() -> dict[str, Any]:
    return {
        'shot_id': SHOT_ID,
        'latest_version_id': 9004,
        'latest_version_no': 4,
        'latest_version_status': 'pending_review',
        'latest_business_file_name': 'WGZR_EP001_001_S001_YJF_V004_1786094626499.mp4',
        'thumbnail_file_id': '5ed39e04-2f29-45ab-a58c-4f8168f5131a',
        'thumbnail_business_file_name': 'WGZR_EP001_001_S001_YJF_V004_thumbnail.jpg',
        'latest_feedback_note_id': LATEST_FEEDBACK_NOTE_ID,
        'latest_feedback_content': '人物起身动作需要更快',
        'latest_feedback_status': 'open',
        'latest_feedback_create_time': datetime(2026, 8, 7, 16, 0, 0),
    }


def test_read_projection_maps_latest_version_thumbnail_feedback_and_historical_assignee() -> None:
    item = ShotGridShotCrudService._build_list_item(
        _shot_projection_row(),
        [],
        _latest_read_projection(),
    )

    assert item.assignee is not None
    assert item.assignee.producer_code is None
    assert item.latest_version is not None
    assert item.latest_version.version_number == 'V004'
    assert item.latest_version.business_file_name.endswith('.mp4')
    assert item.thumbnail is not None
    assert item.thumbnail.url == ('/shot-grid/versions/9004/files/5ed39e04-2f29-45ab-a58c-4f8168f5131a/download')
    assert item.latest_feedback is not None
    assert item.latest_feedback.note_id == LATEST_FEEDBACK_NOTE_ID
    assert item.latest_feedback.note_status == 'open'


def test_read_projection_does_not_fall_back_when_latest_version_has_no_thumbnail() -> None:
    projection = _latest_read_projection()
    projection['thumbnail_file_id'] = None
    projection['thumbnail_business_file_name'] = None

    item = ShotGridShotCrudService._build_list_item(_shot_projection_row(), [], projection)

    assert item.latest_version is not None
    assert item.latest_version.version_number == 'V004'
    assert item.thumbnail is None


def test_read_projection_missing_directory_operation_uses_frozen_not_found_error() -> None:
    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridShotCrudService._build_list_item(
            _shot_projection_row(operation_status=None),
            [],
            _latest_read_projection(),
        )

    assert exc_info.value.http_status == NOT_FOUND_STATUS
    assert exc_info.value.error_key == 'SG_STORAGE_OPERATION_NOT_FOUND'


@pytest.mark.asyncio
async def test_list_reads_versions_files_and_feedback_in_one_batch_query(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _shot_projection_row()
    get_page = AsyncMock(return_value=([row], 1))
    list_assets = AsyncMock(return_value=[])
    list_projections = AsyncMock(return_value=[_latest_read_projection()])
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_shot_page',
        get_page,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_assets_for_shots',
        list_assets,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_read_projections_for_shots',
        list_projections,
    )

    page = await ShotGridShotCrudService.get_shot_page(
        AsyncMock(),
        PROJECT_ID,
        ShotGridShotListQueryModel(),
    )

    assert page.total == 1
    assert page.rows[0].latest_version is not None
    list_projections.assert_awaited_once()
    assert list_projections.await_args.args[2] == [SHOT_ID]


@pytest.mark.asyncio
async def test_create_shot_writes_assets_outbox_task_audit_and_freezes_before_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.lock_project_storage',
        AsyncMock(return_value=_project_storage()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_scene_context',
        AsyncMock(return_value=_scene_context()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.shot_no_exists',
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_active_assets',
        AsyncMock(return_value=[SimpleNamespace(asset_id=4001), SimpleNamespace(asset_id=4002)]),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_assignable_member',
        AsyncMock(return_value={'user_id': 2, 'nick_name': '杨景锋', 'producer_code': 'YJF'}),
    )

    async def add_shot(_db: Any, shot: Any) -> Any:
        shot.shot_id = SHOT_ID
        return shot

    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.add_shot',
        AsyncMock(side_effect=add_shot),
    )
    sync_assets = AsyncMock()
    add_operation = AsyncMock()
    add_task = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.sync_shot_assets',
        sync_assets,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.add_storage_operation',
        add_operation,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.add_task',
        add_task,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridProjectAuditDao.add_success_log',
        audit,
    )
    events: list[str] = []

    async def freeze(*_args: Any) -> Any:
        events.append('freeze')
        return SimpleNamespace(shot_id=SHOT_ID)

    async def commit() -> None:
        events.append('commit')

    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudService._freeze_detail',
        freeze,
    )
    db = AsyncMock()
    db.commit = AsyncMock(side_effect=commit)
    command = ShotGridShotCreateModel(
        sceneId=20,
        shotNo=1,
        durationMs=6000,
        description='舱室内主角惊醒',
        assigneeUserId=2,
        assetIds=[4001, 4002],
    )

    result = await ShotGridShotCrudService.create_shot(db, PROJECT_ID, command, _current_user(), _access())

    assert result.shot_id == SHOT_ID
    assert events == ['freeze', 'commit']
    sync_assets.assert_awaited_once()
    operation = add_operation.await_args.args[1]
    assert operation.operation_type == 'ensure_shot_directory'
    assert operation.target_relative_path == r'VIDEO\EP001\S001'
    assert operation.idempotency_key == f'shotgrid:dir:shot:{PROJECT_ID}:{SHOT_ID}'
    task = add_task.await_args.args[1]
    assert task.task_kind == 'shot_video'
    assert task.assignee_user_id == ASSIGNEE_USER_ID
    audit.assert_awaited_once()
    assert len(audit.await_args.kwargs['method']) < MAX_AUDIT_METHOD_LENGTH


@pytest.mark.asyncio
async def test_create_rejects_project_storage_not_ready_and_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.lock_project_storage',
        AsyncMock(return_value=_project_storage('initializing')),
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridShotCrudService.create_shot(
            db,
            PROJECT_ID,
            ShotGridShotCreateModel(sceneId=20, shotNo=1, description='镜头描述'),
            _current_user(),
            _access(),
        )

    assert exc_info.value.error_key == 'SG_PROJECT_NOT_READY'
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_cannot_silently_reassign_existing_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.lock_project_storage',
        AsyncMock(return_value=_project_storage()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_shot_for_update',
        AsyncMock(
            return_value=SimpleNamespace(
                shot_id=SHOT_ID,
                shot_no=1,
                scene_id=20,
                episode_id=10,
                storage_dir_name='S001',
                lifecycle_status='active',
                lock_version=2,
            )
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_scene_context',
        AsyncMock(return_value=_scene_context()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_active_assets',
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_task_for_update',
        AsyncMock(return_value=SimpleNamespace(assignee_user_id=2)),
    )
    update = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.update_shot',
        update,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridShotCrudService.update_shot(
            db,
            PROJECT_ID,
            SHOT_ID,
            ShotGridShotUpdateModel(
                sceneId=20,
                shotNo=1,
                description='修改描述',
                assigneeUserId=3,
                assetIds=[],
                lockVersion=2,
            ),
            _current_user(),
            _access(),
        )

    assert exc_info.value.http_status == CONFLICT_STATUS
    assert exc_info.value.error_key == 'SG_TASK_ALREADY_EXISTS'
    update.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_archive_rejects_active_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.lock_project_storage',
        AsyncMock(return_value=_project_storage()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_shot_for_update',
        AsyncMock(return_value=SimpleNamespace(lifecycle_status='active', lock_version=2)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_task_for_update',
        AsyncMock(return_value=SimpleNamespace(task_status='in_progress')),
    )
    archive = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.archive_shot',
        archive,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridShotCrudService.archive_shot(
            db,
            PROJECT_ID,
            SHOT_ID,
            ShotGridShotArchiveModel(lockVersion=2),
            _current_user(),
            _access(),
        )

    assert exc_info.value.error_key == 'SG_INVALID_STATE_TRANSITION'
    archive.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_service_rechecks_director_access_instead_of_trusting_controller(monkeypatch: pytest.MonkeyPatch) -> None:
    lock_project = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.lock_project_storage',
        lock_project,
    )
    db = AsyncMock()
    creator_access = ShotGridProjectAccessModel(
        projectId=PROJECT_ID,
        userId=1,
        projectRole='creator',
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridShotCrudService.create_shot(
            db,
            PROJECT_ID,
            ShotGridShotCreateModel(sceneId=20, shotNo=1, description='镜头描述'),
            _current_user(),
            creator_access,
        )

    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'
    lock_project.assert_not_awaited()
    db.rollback.assert_awaited_once()

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.dao.shot_crud_dao import ShotGridShotCrudDao
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.shot_crud_vo import (
    ShotGridShotArchiveModel,
    ShotGridShotBatchDeleteModel,
    ShotGridShotCreateModel,
    ShotGridShotListQueryModel,
    ShotGridShotRenumberModel,
    ShotGridShotReorderModel,
    ShotGridShotUpdateModel,
)
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.shot_crud_service import ShotGridShotCrudService

PROJECT_ID = 1001
SHOT_ID = 3001
SECOND_SHOT_ID = 3002
THIRD_SHOT_ID = 3003
SOURCE_SCENE_ID = 20
TARGET_SCENE_ID = 30
SEQUENCE_STEP = 10
NEXT_LOCK_VERSION = 1
ASSIGNEE_USER_ID = 2
CONFLICT_STATUS = 409
NOT_FOUND_STATUS = 404
LATEST_FEEDBACK_NOTE_ID = 12003
MAX_AUDIT_METHOD_LENGTH = 100
UNAUTHENTICATED_STATUS = 401
RENUMBERED_SHOT_COUNT = 2
BATCH_DELETE_COUNT = 2
MANAGER_USER_ID = 3


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
        SimpleNamespace(storage_status=status, lock_version=0),
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
        'storage_dir_name': '001_S001',
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
        'sequence_position': 1,
        'lifecycle_status': 'active',
        'status': 'completed',
        'task_id': 7001,
        'task_kind': 'shot_video',
        'task_status': 'completed',
        'has_uncommitted_submission': False,
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
        'proxy_media_file_id': '5ed39e04-2f29-45ab-a58c-4f8168f5131b',
        'proxy_media_business_file_name': 'WGZR_EP001_001_S001_YJF_V004_proxy.mp4',
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
    assert item.proxy_media is not None
    assert item.proxy_media.url == ('/shot-grid/versions/9004/files/5ed39e04-2f29-45ab-a58c-4f8168f5131b/download')
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


def test_pending_review_projection_can_display_candidate_before_best_selection() -> None:
    projection = _latest_read_projection()
    projection['latest_business_file_name'] = 'WGZR_EP001_001_S001_YJF_V004_01.mp4'

    item = ShotGridShotCrudService._build_list_item(_shot_projection_row(), [], projection)

    assert item.latest_version is not None
    assert item.latest_version.status == 'pending_review'
    assert item.latest_version.business_file_name.endswith('_01.mp4')


def test_read_projection_missing_directory_operation_uses_frozen_not_found_error() -> None:
    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridShotCrudService._build_list_item(
            _shot_projection_row(operation_status=None),
            [],
            _latest_read_projection(),
        )

    assert exc_info.value.http_status == NOT_FOUND_STATUS
    assert exc_info.value.error_key == 'SG_STORAGE_OPERATION_NOT_FOUND'


def test_unstarted_shot_without_directory_is_reported_as_not_created() -> None:
    row = _shot_projection_row(operation_status=None)
    row['storage_dir_name'] = None
    row['task_id'] = None
    row['task_status'] = None
    row['assignee_user_id'] = None
    row['assignee_nick_name'] = None

    item = ShotGridShotCrudService._build_list_item(row, [], None)

    assert item.directory_status == 'not_created'
    assert item.storage_dir_name is None
    assert item.shot_code == 'S001'


@pytest.mark.parametrize('project_status', ['completed', 'archived'])
def test_completed_or_archived_project_hides_all_shot_actions(project_status: str) -> None:
    row = _shot_projection_row()
    row['project_status'] = project_status

    actions = ShotGridShotCrudService._allowed_actions(row, _current_user(), _access())

    assert actions == []


@pytest.mark.parametrize(
    ('task_status', 'can_assign'),
    [
        (None, True),
        ('not_started', True),
        ('preparing', True),
        ('in_progress', True),
        ('pending_review', True),
        ('revision', True),
        ('completed', False),
    ],
)
def test_shot_detail_exposes_assignment_only_for_unfinished_tasks(task_status: str | None, *, can_assign: bool) -> None:
    row = _shot_projection_row()
    row['task_status'] = task_status
    if task_status is None:
        row['task_id'] = None
        row['assignee_user_id'] = None
    current_user = _current_user()
    current_user.permissions.append('shotgrid:task:assign')

    detail = ShotGridShotCrudService._build_detail(row, [], None, current_user, _access())

    assert ('task.assign' in detail.allowed_actions) is can_assign


@pytest.mark.parametrize(
    'blocked_state',
    [
        {'has_uncommitted_submission': True},
        {'project_status': 'completed'},
        {'project_status': 'archived'},
        {'storage_status': 'failed'},
        {'lifecycle_status': 'archived'},
    ],
)
def test_shot_detail_hides_assignment_when_workflow_is_blocked(blocked_state: dict[str, Any]) -> None:
    row = {**_shot_projection_row(), 'task_status': 'in_progress', **blocked_state}
    current_user = _current_user()
    current_user.permissions.append('shotgrid:task:assign')

    detail = ShotGridShotCrudService._build_detail(row, [], None, current_user, _access())

    assert 'task.assign' not in detail.allowed_actions


@pytest.mark.parametrize(
    ('project_role', 'has_all_scope', 'has_permission', 'can_assign'),
    [
        ('director', False, False, False),
        ('creator', False, True, False),
        ('creator', True, False, False),
        ('creator', True, True, True),
    ],
)
def test_shot_assignment_requires_platform_permission_and_project_management_access(
    project_role: str, *, has_all_scope: bool, has_permission: bool, can_assign: bool
) -> None:
    row = {**_shot_projection_row(), 'task_status': 'in_progress'}
    current_user = _current_user()
    current_user.user = UserInfoModel(userId=MANAGER_USER_ID, userName='manager')
    if has_permission:
        current_user.permissions.append('shotgrid:task:assign')
    access = _access().model_copy(
        update={'user_id': MANAGER_USER_ID, 'project_role': project_role, 'has_all_scope': has_all_scope}
    )

    actions = ShotGridShotCrudService._allowed_actions(row, current_user, access)

    assert ('task.assign' in actions) is can_assign


def test_edit_and_delete_actions_are_only_exposed_before_task_starts() -> None:
    row = _shot_projection_row()
    row['task_status'] = 'not_started'
    not_started_actions = ShotGridShotCrudService._allowed_actions(row, _current_user(), _access())
    assert 'shot.edit' in not_started_actions
    assert 'shot.archive' in not_started_actions

    row['task_status'] = 'in_progress'
    in_progress_actions = ShotGridShotCrudService._allowed_actions(row, _current_user(), _access())
    assert 'shot.edit' not in in_progress_actions
    assert 'shot.archive' not in in_progress_actions

    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridShotCrudService._require_deletable_task(SimpleNamespace(task_status='completed'))
    assert exc_info.value.error_key == 'SG_SHOT_TASK_ALREADY_STARTED'


@pytest.mark.asyncio
async def test_update_shot_rejects_after_task_starts_before_locking_shot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudService._lock_writable_project',
        AsyncMock(),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_task_for_update',
        AsyncMock(return_value=SimpleNamespace(task_status='in_progress')),
    )
    shot_lock = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_shot_for_update',
        shot_lock,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridShotCrudService.update_shot(
            db,
            PROJECT_ID,
            SHOT_ID,
            ShotGridShotUpdateModel(
                sceneId=SOURCE_SCENE_ID,
                durationMs=6000,
                description='尝试修改已开工镜头',
                assetIds=[],
                lockVersion=1,
            ),
            _current_user(),
            _access(),
        )

    assert exc_info.value.http_status == CONFLICT_STATUS
    assert exc_info.value.error_key == 'SG_SHOT_EDIT_PRODUCTION_STARTED'
    shot_lock.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('project_status', ['completed', 'archived'])
async def test_completed_or_archived_project_rejects_shot_writes(
    monkeypatch: pytest.MonkeyPatch,
    project_status: str,
) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.lock_project_storage',
        AsyncMock(
            return_value=(
                SimpleNamespace(project_id=PROJECT_ID, project_status=project_status),
                SimpleNamespace(storage_status='ready'),
            )
        ),
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridShotCrudService._lock_writable_project(
            AsyncMock(),
            PROJECT_ID,
            require_storage_ready=False,
        )

    assert exc_info.value.error_key == 'SG_INVALID_STATE_TRANSITION'


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
async def test_create_shot_defers_directory_until_start_and_audits_before_commit(
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
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_shot_order_for_update',
        AsyncMock(return_value=[]),
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
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_shots_for_renumber',
        AsyncMock(
            return_value=[
                {
                    'shot_id': SHOT_ID,
                    'shot_no': 1,
                    'storage_dir_name': None,
                    'sort_order': 10,
                    'lock_version': 0,
                    'directory_operation_status': None,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_renumber_blockers',
        AsyncMock(return_value=[]),
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
        sequencePosition=1,
        durationMs=6000,
        description='舱室内主角惊醒',
        assetIds=[4001, 4002],
    )

    result = await ShotGridShotCrudService.create_shot(db, PROJECT_ID, command, _current_user(), _access())

    assert result.shot_id == SHOT_ID
    assert events == ['freeze', 'commit']
    sync_assets.assert_awaited_once()
    add_operation.assert_not_awaited()
    assert not hasattr(ShotGridShotCrudDao, 'add_task')
    audit.assert_awaited_once()
    assert len(audit.await_args.kwargs['method']) < MAX_AUDIT_METHOD_LENGTH


@pytest.mark.asyncio
async def test_scene_renumber_freezes_directory_mapping_and_audit_before_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _project_storage()[1]
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.lock_project_storage',
        AsyncMock(return_value=(_project_storage()[0], storage)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_scene_for_update',
        AsyncMock(return_value=_scene_context()),
    )
    rows = [
        {
            'shot_id': SHOT_ID,
            'shot_no': 2,
            'storage_dir_name': '001_S002',
            'lock_version': 4,
            'directory_operation_status': 'succeeded',
        },
        {
            'shot_id': SECOND_SHOT_ID,
            'shot_no': 1,
            'storage_dir_name': '001_S001',
            'lock_version': 7,
            'directory_operation_status': 'succeeded',
        },
    ]
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_shots_for_renumber',
        AsyncMock(return_value=rows),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_renumber_blockers',
        AsyncMock(return_value=[]),
    )

    async def add_operation(_db: Any, operation: Any) -> None:
        operation.operation_id = 8801

    add_storage_operation = AsyncMock(side_effect=add_operation)
    audit = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.add_storage_operation',
        add_storage_operation,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridProjectAuditDao.add_success_log',
        audit,
    )
    db = AsyncMock()

    result = await ShotGridShotCrudService.renumber_scene_shots(
        db,
        PROJECT_ID,
        ShotGridShotRenumberModel(sceneId=SOURCE_SCENE_ID),
        _current_user(),
        _access(),
    )

    operation = add_storage_operation.await_args.args[1]
    assert result.scene_id == SOURCE_SCENE_ID
    assert result.changed_count == RENUMBERED_SHOT_COUNT
    assert result.operation_status == 'pending'
    assert operation.aggregate_type == 'scene'
    assert operation.aggregate_id == SOURCE_SCENE_ID
    assert operation.target_relative_path == r'VIDEO\EP001'
    assert operation.operation_payload['sceneId'] == SOURCE_SCENE_ID
    assert [item['targetDirName'] for item in operation.operation_payload['items']] == [
        '001_S001',
        '001_S002',
    ]
    assert storage.storage_status == 'migrating'
    audit.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_position_inserts_and_rewrites_only_shifted_internal_orders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {'shot_id': SHOT_ID, 'sort_order': SEQUENCE_STEP, 'shot_no': 1, 'lock_version': 0},
        {'shot_id': SECOND_SHOT_ID, 'sort_order': SEQUENCE_STEP * 2, 'shot_no': 2, 'lock_version': 0},
    ]
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_shot_order_for_update',
        AsyncMock(return_value=rows),
    )
    update_order = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.update_shot_order',
        update_order,
    )
    command = ShotGridShotCreateModel(
        sceneId=20,
        description='插入中间的镜头',
        sequencePosition=2,
    )

    result = await ShotGridShotCrudService._resolve_create_sort_order(
        AsyncMock(),
        project_id=PROJECT_ID,
        scene_id=20,
        command=command,
        actor_name='director',
        now=datetime(2026, 8, 20, 12, 0, 0),
    )

    assert result == SEQUENCE_STEP * 2
    update_order.assert_awaited_once()
    assert update_order.await_args.kwargs['shot_id'] == SECOND_SHOT_ID
    assert update_order.await_args.kwargs['sort_order'] == SEQUENCE_STEP * 3


@pytest.mark.asyncio
async def test_update_position_moves_target_without_advancing_target_lock_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {'shot_id': SHOT_ID, 'sort_order': SEQUENCE_STEP, 'shot_no': 1, 'lock_version': 0},
        {'shot_id': SECOND_SHOT_ID, 'sort_order': SEQUENCE_STEP * 2, 'shot_no': 2, 'lock_version': 0},
        {'shot_id': THIRD_SHOT_ID, 'sort_order': SEQUENCE_STEP * 3, 'shot_no': 3, 'lock_version': 0},
    ]
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_shot_order_for_update',
        AsyncMock(return_value=rows),
    )
    update_order = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.update_shot_order',
        update_order,
    )
    command = ShotGridShotUpdateModel(
        sceneId=20,
        description='移动到第一镜',
        assetIds=[],
        lockVersion=0,
        sequencePosition=1,
    )

    result = await ShotGridShotCrudService._resolve_update_sort_order(
        AsyncMock(),
        project_id=PROJECT_ID,
        shot_id=SECOND_SHOT_ID,
        current_scene_id=20,
        target_scene_id=20,
        current_sort_order=SEQUENCE_STEP * 2,
        command=command,
        actor_name='director',
        now=datetime(2026, 8, 20, 12, 0, 0),
    )

    assert result == SEQUENCE_STEP
    update_order.assert_awaited_once()
    assert update_order.await_args.kwargs['shot_id'] == SHOT_ID
    assert update_order.await_args.kwargs['sort_order'] == SEQUENCE_STEP * 2


@pytest.mark.asyncio
async def test_update_position_moves_between_scenes_and_rewrites_both_scene_orders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_rows = [
        {'shot_id': SHOT_ID, 'sort_order': SEQUENCE_STEP, 'shot_no': 1, 'lock_version': 0},
        {'shot_id': SECOND_SHOT_ID, 'sort_order': SEQUENCE_STEP * 2, 'shot_no': 2, 'lock_version': 0},
    ]
    target_rows = [
        {'shot_id': THIRD_SHOT_ID, 'sort_order': SEQUENCE_STEP, 'shot_no': 3, 'lock_version': 0},
    ]

    async def list_scene_order(_db: Any, _project_id: int, scene_id: int) -> list[dict[str, Any]]:
        return source_rows if scene_id == SOURCE_SCENE_ID else target_rows

    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_shot_order_for_update',
        AsyncMock(side_effect=list_scene_order),
    )
    update_order = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.update_shot_order',
        update_order,
    )
    command = ShotGridShotUpdateModel(
        sceneId=TARGET_SCENE_ID,
        shotNo=1,
        description='移动到另一场的第一镜',
        assetIds=[],
        lockVersion=0,
        sequencePosition=1,
    )

    result = await ShotGridShotCrudService._resolve_update_sort_order(
        AsyncMock(),
        project_id=PROJECT_ID,
        shot_id=SHOT_ID,
        current_scene_id=SOURCE_SCENE_ID,
        target_scene_id=TARGET_SCENE_ID,
        current_sort_order=SEQUENCE_STEP,
        command=command,
        actor_name='director',
        now=datetime(2026, 8, 20, 12, 0, 0),
    )

    assert result == SEQUENCE_STEP
    assert [call.kwargs['shot_id'] for call in update_order.await_args_list] == [SECOND_SHOT_ID, THIRD_SHOT_ID]
    assert [call.kwargs['sort_order'] for call in update_order.await_args_list] == [SEQUENCE_STEP, SEQUENCE_STEP * 2]


@pytest.mark.asyncio
async def test_reorder_shot_uses_dedicated_transaction_and_returns_new_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.lock_project_storage',
        AsyncMock(return_value=_project_storage()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_shot_for_update',
        AsyncMock(
            return_value=SimpleNamespace(
                episode_id=10,
                scene_id=20,
                lifecycle_status='active',
                lock_version=0,
            )
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_shot_order_for_update',
        AsyncMock(
            return_value=[
                {'shot_id': SHOT_ID, 'sort_order': SEQUENCE_STEP, 'shot_no': 1, 'lock_version': 0},
                {
                    'shot_id': SECOND_SHOT_ID,
                    'sort_order': SEQUENCE_STEP * 2,
                    'shot_no': 2,
                    'lock_version': 0,
                },
            ]
        ),
    )
    audit = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_renumber_blockers',
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_scene_for_update',
        AsyncMock(return_value=_scene_context()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_shots_for_renumber',
        AsyncMock(
            return_value=[
                {'shot_id': SHOT_ID, 'shot_no': 1, 'lock_version': 0},
                {'shot_id': SECOND_SHOT_ID, 'shot_no': 2, 'lock_version': 0},
            ]
        ),
    )
    synchronize = AsyncMock(
        return_value=(
            SimpleNamespace(
                operation_id=None,
                operation_status='succeeded',
                storage_status='ready',
                status_url=None,
            ),
            {SHOT_ID: NEXT_LOCK_VERSION},
        )
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudService._synchronize_scene_numbers',
        synchronize,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridProjectAuditDao.add_success_log',
        audit,
    )
    db = AsyncMock()

    command = ShotGridShotReorderModel(lockVersion=0, sequencePosition=2)
    result = await ShotGridShotCrudService.reorder_shot(
        db,
        PROJECT_ID,
        SHOT_ID,
        command,
        _current_user(),
        _access(),
    )

    assert result.sequence_position == command.sequence_position
    assert result.lock_version == NEXT_LOCK_VERSION
    assert [row['shot_id'] for row in synchronize.await_args.kwargs['rows']] == [SECOND_SHOT_ID, SHOT_ID]
    audit.assert_awaited_once()
    db.commit.assert_awaited_once()


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

    assert exc_info.value.error_key == 'SG_SHOT_TASK_ALREADY_STARTED'
    archive.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_archive_middle_shot_synchronizes_remaining_scene_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.lock_project_storage',
        AsyncMock(return_value=_project_storage()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_shot_for_update',
        AsyncMock(
            return_value=SimpleNamespace(
                scene_id=SOURCE_SCENE_ID,
                lifecycle_status='active',
                lock_version=2,
            )
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_task_for_update',
        AsyncMock(return_value=None),
    )
    rows = [
        {'shot_id': SHOT_ID, 'shot_no': 1, 'storage_dir_name': None, 'lock_version': 4},
        {'shot_id': SECOND_SHOT_ID, 'shot_no': 2, 'storage_dir_name': None, 'lock_version': 2},
        {'shot_id': THIRD_SHOT_ID, 'shot_no': 3, 'storage_dir_name': None, 'lock_version': 6},
    ]
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_shots_for_renumber',
        AsyncMock(return_value=rows),
    )
    blockers = AsyncMock(return_value=[])
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_renumber_blockers',
        blockers,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_scene_for_update',
        AsyncMock(return_value=_scene_context()),
    )
    archive = AsyncMock(return_value=3)
    synchronize = AsyncMock(
        return_value=(
            SimpleNamespace(operation_status='succeeded'),
            {THIRD_SHOT_ID: 7},
        )
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.archive_shot',
        archive,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudService._synchronize_scene_numbers',
        synchronize,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridProjectAuditDao.add_success_log',
        AsyncMock(),
    )
    db = AsyncMock()

    result = await ShotGridShotCrudService.archive_shot(
        db,
        PROJECT_ID,
        SECOND_SHOT_ID,
        ShotGridShotArchiveModel(lockVersion=2),
        _current_user(),
        _access(),
    )

    assert result.shot_id == SECOND_SHOT_ID
    assert blockers.await_args.args[2] == [SECOND_SHOT_ID, THIRD_SHOT_ID]
    assert [row['shot_id'] for row in synchronize.await_args.kwargs['rows']] == [SHOT_ID, THIRD_SHOT_ID]
    archive.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_archive_rejects_when_resequence_would_touch_frozen_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.lock_project_storage',
        AsyncMock(return_value=_project_storage()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_shot_for_update',
        AsyncMock(
            return_value=SimpleNamespace(
                scene_id=SOURCE_SCENE_ID,
                lifecycle_status='active',
                lock_version=2,
            )
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_task_for_update',
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_shots_for_renumber',
        AsyncMock(
            return_value=[
                {'shot_id': SHOT_ID, 'shot_no': 1, 'storage_dir_name': None, 'lock_version': 4},
                {'shot_id': SECOND_SHOT_ID, 'shot_no': 2, 'storage_dir_name': None, 'lock_version': 2},
                {
                    'shot_id': THIRD_SHOT_ID,
                    'shot_no': 3,
                    'storage_dir_name': '001_S003',
                    'lock_version': 6,
                },
            ]
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_renumber_blockers',
        AsyncMock(return_value=[]),
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
            SECOND_SHOT_ID,
            ShotGridShotArchiveModel(lockVersion=2),
            _current_user(),
            _access(),
        )

    assert exc_info.value.error_key == 'SG_SHOT_DELETE_DIRECTORY_EXISTS'
    assert exc_info.value.details == {'shotIds': [THIRD_SHOT_ID]}
    archive.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_batch_delete_resequences_each_scene_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.lock_project_storage',
        AsyncMock(return_value=_project_storage()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_shot_for_update',
        AsyncMock(
            side_effect=[
                SimpleNamespace(scene_id=SOURCE_SCENE_ID, lifecycle_status='active', lock_version=2),
                SimpleNamespace(scene_id=SOURCE_SCENE_ID, lifecycle_status='active', lock_version=6),
            ]
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_task_for_update',
        AsyncMock(side_effect=[None, None]),
    )
    rows = [
        {'shot_id': SHOT_ID, 'shot_no': 1, 'storage_dir_name': None, 'lock_version': 4},
        {'shot_id': SECOND_SHOT_ID, 'shot_no': 2, 'storage_dir_name': None, 'lock_version': 2},
        {'shot_id': THIRD_SHOT_ID, 'shot_no': 3, 'storage_dir_name': None, 'lock_version': 6},
    ]
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_shots_for_renumber',
        AsyncMock(return_value=rows),
    )
    blockers = AsyncMock(return_value=[])
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.list_scene_renumber_blockers',
        blockers,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.get_scene_for_update',
        AsyncMock(return_value=_scene_context()),
    )
    archive = AsyncMock(side_effect=[3, 7])
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudDao.archive_shot',
        archive,
    )
    synchronize = AsyncMock(
        return_value=(
            SimpleNamespace(operation_status='succeeded'),
            {SHOT_ID: 4},
        )
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridShotCrudService._synchronize_scene_numbers',
        synchronize,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.shot_crud_service.ShotGridProjectAuditDao.add_success_log',
        AsyncMock(),
    )
    db = AsyncMock()

    result = await ShotGridShotCrudService.batch_delete_shots(
        db,
        PROJECT_ID,
        ShotGridShotBatchDeleteModel(
            items=[
                {'shotId': SECOND_SHOT_ID, 'lockVersion': 2},
                {'shotId': THIRD_SHOT_ID, 'lockVersion': 6},
            ]
        ),
        _current_user(),
        _access(),
    )

    assert result.deleted_shot_ids == [SECOND_SHOT_ID, THIRD_SHOT_ID]
    assert blockers.await_args.args[2] == [SECOND_SHOT_ID, THIRD_SHOT_ID]
    assert [row['shot_id'] for row in synchronize.await_args.kwargs['rows']] == [SHOT_ID]
    assert archive.await_count == BATCH_DELETE_COUNT
    db.commit.assert_awaited_once()


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

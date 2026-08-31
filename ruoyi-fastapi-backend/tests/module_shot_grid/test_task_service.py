from datetime import date, datetime
from http import HTTPStatus
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.entity.do.task_schedule_change_do import ShotGridTaskScheduleChange
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.task_vo import (
    ShotGridShotTaskBatchAssignModel,
    ShotGridTaskAssignModel,
    ShotGridTaskListQueryModel,
    ShotGridTaskStartModel,
    ShotGridTaskUpdateModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.task_service import ShotGridTaskService

PROJECT_ID = 10
TASK_ID = 20
SHOT_ID = 30
ASSET_ID = 40
ASSET_ITEM_ID = 50
ASSIGNEE_USER_ID = 2
NEW_ASSIGNEE_USER_ID = 3
INITIAL_TASK_LOCK_VERSION = 3
UPDATED_TASK_LOCK_VERSION = 4
SHOT_DURATION_MS = 8000
CONFLICT_STATUS = 409


def _current_user(
    *,
    user_id: int = 1,
    permissions: list[str] | None = None,
) -> CurrentUserModel:
    return CurrentUserModel(
        permissions=permissions
        or [
            'shotgrid:task:list',
            'shotgrid:task:query',
            'shotgrid:task:edit',
            'shotgrid:task:assign',
            'shotgrid:task:start',
            'shotgrid:version:add',
        ],
        roles=[],
        user=UserInfoModel(userId=user_id, userName=f'user-{user_id}'),
    )


def _access(
    *,
    user_id: int = 1,
    role: str = 'director',
    project_id: int = PROJECT_ID,
    all_scope: bool = False,
) -> ShotGridProjectAccessModel:
    return ShotGridProjectAccessModel(
        projectId=project_id,
        userId=user_id,
        projectRole=None if all_scope else role,
        hasAllScope=all_scope,
    )


def _task(
    *,
    assignee_user_id: int = ASSIGNEE_USER_ID,
    lock_version: int = INITIAL_TASK_LOCK_VERSION,
) -> SimpleNamespace:
    return SimpleNamespace(
        task_id=TASK_ID,
        project_id=PROJECT_ID,
        task_kind='shot_video',
        shot_id=SHOT_ID,
        asset_item_id=None,
        assignee_user_id=assignee_user_id,
        task_status='not_started',
        priority='normal',
        due_date=None,
        requirements='原要求',
        update_by='old',
        update_time=None,
        lock_version=lock_version,
    )


def _task_row(**overrides: Any) -> dict[str, Any]:
    now = datetime(2026, 8, 11, 10, 0, 0)
    row: dict[str, Any] = {
        'task_id': TASK_ID,
        'project_id': PROJECT_ID,
        'shot_id': SHOT_ID,
        'asset_item_id': None,
        'task_name': 'EP001-001-0001 镜头视频制作',
        'task_kind': 'shot_video',
        'assignee_user_id': ASSIGNEE_USER_ID,
        'task_status': 'in_progress',
        'priority': 'high',
        'due_date': date(2026, 8, 20),
        'requirements': '完成镜头视频',
        'remark': None,
        'lock_version': 4,
        'create_by': 'director',
        'create_time': now,
        'update_by': 'creator',
        'update_time': now,
        'project_code': 'LCFR',
        'project_name': '罗刹夫人',
        'project_status': 'active',
        'assignee_user_name': '杨景锋',
        'assignee_nick_name': '杨景锋',
        'assignee_producer_code': 'YJF',
        'assignee_member_status': 'active',
        'assignee_valid': True,
        'episode_id': 100,
        'episode_no': 1,
        'scene_id': 200,
        'scene_no': 1,
        'scene_name': '动力舱',
        'shot_no': 1,
        'shot_storage_dir_name': '001_0001',
        'shot_duration_ms': SHOT_DURATION_MS,
        'shot_description': '主角进入动力舱',
        'shot_size': '中景',
        'shot_camera_position': '平视机位',
        'shot_camera_movement': '缓慢推进',
        'shot_focal_length': '35',
        'shot_dialogue': '准备启动。',
        'shot_sound_effect': '轻微电流声',
        'shot_color_reference': '冷蓝色调',
        'shot_remark': '保持画面稳定',
        'shot_lifecycle_status': 'active',
        'asset_id': None,
        'production_item': None,
        'asset_description': None,
        'asset_item_description': None,
        'asset_item_lifecycle_status': None,
        'asset_lifecycle_status': 'active',
        'asset_type': None,
        'asset_name': None,
        'version_count': 1,
        'latest_version_id': 50,
        'latest_version_no': 1,
        'latest_version_status': 'pending_review',
        'latest_submitted_time': now,
        'final_version_id': None,
        'final_version_no': None,
        'final_version_status': None,
        'final_submitted_time': None,
        'has_uncommitted_submission': False,
    }
    row.update(overrides)
    return row


def test_start_schedule_contract_preserves_existing_range_and_requires_new_future_range() -> None:
    now = datetime(2026, 8, 31, 10)
    existing = _task()
    existing.expected_start_time = datetime(2026, 8, 29, 9)
    existing.expected_end_time = datetime(2026, 8, 30, 18)
    existing.baseline_start_time = existing.expected_start_time
    existing.baseline_end_time = existing.expected_end_time

    start, end, is_initial = ShotGridTaskService._resolve_start_schedule(
        existing,
        ShotGridTaskStartModel(lockVersion=INITIAL_TASK_LOCK_VERSION),
        now,
    )

    assert (start, end, is_initial) == (
        existing.expected_start_time,
        existing.expected_end_time,
        False,
    )

    with pytest.raises(ShotGridDomainException) as existing_override:
        ShotGridTaskService._resolve_start_schedule(
            existing,
            ShotGridTaskStartModel(
                lockVersion=INITIAL_TASK_LOCK_VERSION,
                expectedStartTime='2026-09-01T09:00:00',
                expectedEndTime='2026-09-02T18:00:00',
            ),
            now,
        )
    assert existing_override.value.error_key == 'SG_TASK_EXPECTED_TIME_INVALID'

    fresh = _task()
    with pytest.raises(ShotGridDomainException) as missing_range:
        ShotGridTaskService._resolve_start_schedule(
            fresh,
            ShotGridTaskStartModel(lockVersion=INITIAL_TASK_LOCK_VERSION),
            now,
        )
    assert missing_range.value.error_key == 'SG_TASK_EXPECTED_TIME_INVALID'

    with pytest.raises(ShotGridDomainException) as past_range:
        ShotGridTaskService._resolve_start_schedule(
            fresh,
            ShotGridTaskStartModel(
                lockVersion=INITIAL_TASK_LOCK_VERSION,
                expectedStartTime='2026-08-30T09:00:00',
                expectedEndTime='2026-09-01T18:00:00',
            ),
            now,
        )
    assert past_range.value.error_key == 'SG_TASK_EXPECTED_TIME_INVALID'


@pytest.mark.parametrize(
    ('description', 'supplement', 'expected'),
    [
        ('狭小舱室', None, '资产描述：狭小舱室'),
        ('狭小舱室', '门口主视角', '资产描述：狭小舱室\n分项补充要求：门口主视角'),
        ('狭小舱室', '狭小舱室', '资产描述：狭小舱室'),
        (None, '门口主视角', '分项补充要求：门口主视角'),
    ],
)
def test_asset_task_target_contains_asset_description_and_item_requirements(
    description: str | None, supplement: str | None, expected: str
) -> None:
    result = ShotGridTaskService._build_list_item(
        _task_row(
            task_kind='asset_image',
            shot_id=None,
            asset_id=ASSET_ID,
            asset_item_id=ASSET_ITEM_ID,
            asset_type='Environment',
            asset_name='舱室',
            production_item='主视角',
            asset_item_lifecycle_status='active',
            asset_description=description,
            asset_item_description=supplement,
        )
    )
    assert result.target.target_description == expected


def _patch_locked_access(
    monkeypatch: pytest.MonkeyPatch,
    access: ShotGridProjectAccessModel,
) -> AsyncMock:
    refresh = AsyncMock(return_value=access)
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridProjectAccessService.resolve_access',
        refresh,
    )
    return refresh


def test_task_detail_builds_target_version_and_permission_actions() -> None:
    detail = ShotGridTaskService._build_detail(
        _task_row(),
        _current_user(user_id=ASSIGNEE_USER_ID),
        _access(user_id=ASSIGNEE_USER_ID, role='creator'),
    )

    assert detail.target.target_type == 'shot'
    assert detail.target.target_name == 'EP001-001-0001'
    assert detail.assignee.user_name == '杨景锋'
    assert detail.shot_production is not None
    assert detail.shot_production.duration_ms == SHOT_DURATION_MS
    assert detail.shot_production.description == '主角进入动力舱'
    assert detail.shot_production.shot_size == '中景'
    assert detail.shot_production.camera_position == '平视机位'
    assert detail.shot_production.camera_movement == '缓慢推进'
    assert detail.shot_production.focal_length == '35'
    assert detail.shot_production.dialogue == '准备启动。'
    assert detail.shot_production.sound_effect == '轻微电流声'
    assert detail.shot_production.color_reference == '冷蓝色调'
    assert detail.shot_production.remark == '保持画面稳定'
    assert detail.latest_version is not None
    assert detail.latest_version.version_number == 'V001'
    assert detail.allowed_actions == ['version.add']


def test_task_detail_hides_legacy_internal_worker_owner() -> None:
    detail = ShotGridTaskService._build_detail(
        _task_row(update_by=('31412-9d227a:31412:c380be68a38c43aebe690f61258a664f:a58a5b5baeb5')),
        _current_user(user_id=ASSIGNEE_USER_ID),
        _access(user_id=ASSIGNEE_USER_ID, role='creator'),
    )

    assert detail.update_by == '系统目录服务'


@pytest.mark.asyncio
async def test_task_detail_recovers_legacy_worker_owner_from_directory_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_worker_owner = '31412-9d227a:31412:c380be68a38c43aebe690f61258a664f:a58a5b5baeb5'
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_task_detail',
        AsyncMock(return_value=_task_row(update_by=raw_worker_owner)),
    )
    operation_actor = AsyncMock(return_value='曲占锋')
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_latest_succeeded_shot_directory_operation_actor',
        operation_actor,
    )

    db = AsyncMock()
    row = await ShotGridTaskService._require_task_detail(db, TASK_ID)

    assert row['update_by'] == '曲占锋'
    operation_actor.assert_awaited_once_with(db, PROJECT_ID, SHOT_ID)


def test_task_detail_hides_version_add_while_uncommitted_submission_exists() -> None:
    detail = ShotGridTaskService._build_detail(
        _task_row(has_uncommitted_submission=True),
        _current_user(user_id=ASSIGNEE_USER_ID),
        _access(user_id=ASSIGNEE_USER_ID, role='creator'),
    )

    assert detail.has_uncommitted_submission is True
    assert 'version.add' not in detail.allowed_actions


@pytest.mark.parametrize(
    ('task_kind', 'director_can_start', 'creator_can_start'),
    [('shot_video', True, False), ('asset_image', True, False)],
)
def test_task_start_actions_require_manager_for_both_task_kinds(
    task_kind: str,
    director_can_start: bool,
    creator_can_start: bool,
) -> None:
    row = _task_row(
        task_status='not_started',
        assignee_user_id=ASSIGNEE_USER_ID,
        task_kind=task_kind,
        production_item='主视角',
        asset_item_lifecycle_status='active',
    )
    current_user = _current_user(user_id=ASSIGNEE_USER_ID)

    director_actions = ShotGridTaskService._allowed_actions(
        row,
        current_user,
        _access(user_id=ASSIGNEE_USER_ID, role='director'),
    )
    all_scope_actions = ShotGridTaskService._allowed_actions(
        row,
        current_user,
        _access(user_id=ASSIGNEE_USER_ID, all_scope=True),
    )
    creator_actions = ShotGridTaskService._allowed_actions(
        row,
        current_user,
        _access(user_id=ASSIGNEE_USER_ID, role='creator'),
    )

    assert ('task.start' in director_actions) is director_can_start
    assert ('task.start' in all_scope_actions) is director_can_start
    assert ('task.start' in creator_actions) is creator_can_start
    assert 'version.add' not in creator_actions


def test_task_detail_only_offers_edit_before_task_starts() -> None:
    current_user = _current_user()
    access = _access()

    not_started_actions = ShotGridTaskService._allowed_actions(
        _task_row(task_status='not_started'),
        current_user,
        access,
    )
    in_progress_actions = ShotGridTaskService._allowed_actions(
        _task_row(task_status='in_progress'),
        current_user,
        access,
    )

    assert 'task.edit' in not_started_actions
    assert 'task.edit' not in in_progress_actions


@pytest.mark.parametrize('changes', [{'assignee_valid': False}, {'asset_lifecycle_status': 'archived'}])
def test_asset_start_action_hides_invalid_assignee_or_archived_parent(changes: dict[str, Any]) -> None:
    row = _task_row(
        task_kind='asset_image',
        task_status='not_started',
        production_item='主视角',
        asset_item_lifecycle_status='active',
        **changes,
    )
    assert 'task.start' not in ShotGridTaskService._allowed_actions(row, _current_user(), _access())


@pytest.mark.asyncio
async def test_project_mine_scope_cannot_query_another_assignee() -> None:
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridTaskService.get_project_task_page(
            db,
            PROJECT_ID,
            ShotGridTaskListQueryModel(scope='mine', assigneeUserId=9),
            _current_user(user_id=ASSIGNEE_USER_ID),
            _access(user_id=ASSIGNEE_USER_ID, role='creator'),
        )

    assert exc_info.value.error_key == 'SG_TASK_ASSIGNEE_INVALID'


@pytest.mark.asyncio
async def test_assign_shot_locks_project_target_task_then_member_and_audits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    async def lock_project(*_args: Any, **_kwargs: Any) -> None:
        events.append('project')

    async def lock_target(*_args: Any, **_kwargs: Any) -> tuple[Any, Any, Any]:
        events.append('target')
        return (
            SimpleNamespace(shot_no=1, storage_dir_name='001_0001', description='镜头原始制作内容'),
            SimpleNamespace(episode_no=1),
            SimpleNamespace(scene_no=1),
        )

    async def lock_task(*_args: Any, **_kwargs: Any) -> None:
        events.append('task')

    async def lock_member(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        events.append('member')
        return {'user_id': ASSIGNEE_USER_ID, 'producer_code': 'YJF', 'nick_name': '杨景锋'}

    async def add_task(_db: Any, task: Any) -> Any:
        events.append('insert')
        task.task_id = TASK_ID
        return task

    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_mutable_project',
        lock_project,
    )
    _patch_locked_access(monkeypatch, _access())
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.lock_shot_target',
        lock_target,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_task_for_shot_update',
        lock_task,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_assignable_member',
        lock_member,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.add_task',
        add_task,
    )
    audit = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._audit_assignment',
        audit,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._require_task_detail',
        AsyncMock(return_value=_task_row()),
    )
    expected = object()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._build_detail',
        lambda *_args: expected,
    )
    db = AsyncMock()

    result = await ShotGridTaskService.assign_shot(
        db,
        PROJECT_ID,
        SHOT_ID,
        ShotGridTaskAssignModel(
            assigneeUserId=ASSIGNEE_USER_ID,
            taskDescription='客户端尝试篡改制作要求',
            priority='high',
        ),
        _current_user(),
        _access(),
    )

    assert result is expected
    assert events == ['project', 'target', 'task', 'member', 'insert']
    audit.assert_awaited_once()
    assigned_task = audit.await_args.kwargs['task']
    assert assigned_task.task_name == 'EP001-001-0001 镜头视频制作'
    assert assigned_task.task_status == 'not_started'
    assert assigned_task.requirements == '镜头原始制作内容'
    assert assigned_task.lock_version == 0
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_task_assignment_requires_task_lock_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_mutable_project',
        AsyncMock(),
    )
    _patch_locked_access(monkeypatch, _access())
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.lock_shot_target',
        AsyncMock(
            return_value=(
                SimpleNamespace(shot_no=1, storage_dir_name='001_0001', description='镜头原始制作内容'),
                SimpleNamespace(episode_no=1),
                SimpleNamespace(scene_no=1),
            )
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_task_for_shot_update',
        AsyncMock(return_value=_task()),
    )
    member = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_assignable_member',
        member,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridTaskService.assign_shot(
            db,
            PROJECT_ID,
            SHOT_ID,
            ShotGridTaskAssignModel(assigneeUserId=3),
            _current_user(),
            _access(),
        )

    assert exc_info.value.error_key == 'SG_OPTIMISTIC_LOCK_CONFLICT'
    member.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_assign_shot_rechecks_director_after_project_lock_and_rolls_back_when_demoted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_user = _current_user()
    project_lock = AsyncMock()
    target_lock = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_mutable_project',
        project_lock,
    )
    refresh = _patch_locked_access(monkeypatch, _access(role='creator'))
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.lock_shot_target',
        target_lock,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridTaskService.assign_shot(
            db,
            PROJECT_ID,
            SHOT_ID,
            ShotGridTaskAssignModel(assigneeUserId=ASSIGNEE_USER_ID),
            current_user,
            _access(role='director'),
        )

    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'
    project_lock.assert_awaited_once_with(db, PROJECT_ID, require_storage_ready=True)
    refresh.assert_awaited_once_with(db, current_user, PROJECT_ID)
    target_lock.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_batch_assign_shots_assigns_all_selected_shots_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_shot_id = SHOT_ID
    second_shot_id = SHOT_ID + 1
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_mutable_project',
        AsyncMock(),
    )
    _patch_locked_access(monkeypatch, _access())
    target_lock = AsyncMock(
        side_effect=[
            (
                SimpleNamespace(shot_no=1, storage_dir_name='001_0001', description='第一镜制作内容'),
                SimpleNamespace(episode_no=1),
                SimpleNamespace(scene_no=1),
            ),
            (
                SimpleNamespace(shot_no=2, storage_dir_name='001_0002', description='第二镜制作内容'),
                SimpleNamespace(episode_no=1),
                SimpleNamespace(scene_no=1),
            ),
        ]
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.lock_shot_target',
        target_lock,
    )
    existing_task = _task(assignee_user_id=9, lock_version=INITIAL_TASK_LOCK_VERSION)
    task_lock = AsyncMock(side_effect=[None, existing_task])
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_task_for_shot_update',
        task_lock,
    )
    assign_task = AsyncMock(
        side_effect=[
            (_task(assignee_user_id=ASSIGNEE_USER_ID, lock_version=0), None),
            (_task(assignee_user_id=ASSIGNEE_USER_ID, lock_version=UPDATED_TASK_LOCK_VERSION), 9),
        ]
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._assign_task',
        assign_task,
    )
    audit = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._audit',
        audit,
    )
    db = AsyncMock()

    result = await ShotGridTaskService.batch_assign_shots(
        db,
        PROJECT_ID,
        ShotGridShotTaskBatchAssignModel(
            assigneeUserId=ASSIGNEE_USER_ID,
            items=[
                {'shotId': second_shot_id, 'taskLockVersion': INITIAL_TASK_LOCK_VERSION},
                {'shotId': first_shot_id, 'taskLockVersion': None},
            ],
        ),
        _current_user(),
        _access(),
    )

    expected_count = 2
    assert result.assigned_shot_ids == [first_shot_id, second_shot_id]
    assert result.assigned_count == expected_count
    assert result.created_task_count == 1
    assert result.reassigned_task_count == 1
    assert [call.args[2] for call in target_lock.await_args_list] == [first_shot_id, second_shot_id]
    assert assign_task.await_count == expected_count
    assert assign_task.await_args_list[0].kwargs['command'].task_description == '第一镜制作内容'
    assert 'task_description' in assign_task.await_args_list[0].kwargs['command'].model_fields_set
    assert assign_task.await_args_list[1].kwargs['command'].task_description is None
    assert 'task_description' not in assign_task.await_args_list[1].kwargs['command'].model_fields_set
    audit.assert_awaited_once()
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_assign_asset_item_locks_asset_and_item_before_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    async def lock_project(*_args: Any, **_kwargs: Any) -> None:
        events.append('project')

    async def preview_item(*_args: Any, **_kwargs: Any) -> tuple[int, int]:
        events.append('item-preview')
        return ASSET_ID, ASSET_ITEM_ID

    async def lock_asset(*_args: Any, **_kwargs: Any) -> Any:
        events.append('asset')
        return SimpleNamespace(asset_id=ASSET_ID, asset_name='动力舱室内')

    async def lock_item(*_args: Any, **_kwargs: Any) -> Any:
        events.append('item')
        return SimpleNamespace(asset_id=ASSET_ID, production_item='主视角')

    async def lock_task(*_args: Any, **_kwargs: Any) -> None:
        events.append('task')

    async def lock_member(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        events.append('member')
        return {'user_id': ASSIGNEE_USER_ID, 'producer_code': 'YJF', 'nick_name': '杨景锋'}

    async def add_task(_db: Any, task: Any) -> Any:
        events.append('insert')
        task.task_id = TASK_ID
        return task

    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_mutable_project',
        lock_project,
    )
    _patch_locked_access(monkeypatch, _access())
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_asset_item_project_context',
        preview_item,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.lock_asset',
        lock_asset,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.lock_asset_item',
        lock_item,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_task_for_asset_item_update',
        lock_task,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_assignable_member',
        lock_member,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.add_task',
        add_task,
    )
    audit = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._audit_assignment',
        audit,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._require_task_detail',
        AsyncMock(return_value=_task_row()),
    )
    expected = object()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._build_detail',
        lambda *_args: expected,
    )
    db = SimpleNamespace(add=MagicMock(), commit=AsyncMock(), rollback=AsyncMock())

    result = await ShotGridTaskService.assign_asset_item(
        db,
        PROJECT_ID,
        ASSET_ITEM_ID,
        ShotGridTaskAssignModel(assigneeUserId=ASSIGNEE_USER_ID),
        _current_user(),
        _access(),
    )

    assert result is expected
    assert events == ['project', 'item-preview', 'asset', 'item', 'task', 'member', 'insert']
    assigned_task = audit.await_args.kwargs['task']
    assert assigned_task.task_name == '动力舱室内 - 主视角'
    assert assigned_task.asset_item_id == ASSET_ITEM_ID
    assert assigned_task.shot_id is None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_assign_asset_item_rechecks_director_after_project_lock_and_rolls_back_when_demoted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_user = _current_user()
    project_lock = AsyncMock()
    item_preview = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_mutable_project',
        project_lock,
    )
    refresh = _patch_locked_access(monkeypatch, _access(role='creator'))
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_asset_item_project_context',
        item_preview,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridTaskService.assign_asset_item(
            db,
            PROJECT_ID,
            ASSET_ITEM_ID,
            ShotGridTaskAssignModel(assigneeUserId=ASSIGNEE_USER_ID),
            current_user,
            _access(role='director'),
        )

    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'
    project_lock.assert_awaited_once_with(db, PROJECT_ID, require_storage_ready=True)
    refresh.assert_awaited_once_with(db, current_user, PROJECT_ID)
    item_preview.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.parametrize('task_kind', ['shot_video', 'asset_image'])
@pytest.mark.parametrize(
    ('task_status', 'can_assign'),
    [
        ('not_started', True),
        ('preparing', False),
        ('in_progress', False),
        ('pending_review', False),
        ('revision', False),
        ('completed', False),
    ],
)
def test_task_assignment_action_is_only_available_before_start(
    task_kind: str, task_status: str, *, can_assign: bool
) -> None:
    row = _task_row(
        task_kind=task_kind,
        task_status=task_status,
        production_item='主视角',
        asset_item_lifecycle_status='active',
    )
    assert ('task.assign' in ShotGridTaskService._allowed_actions(row, _current_user(), _access())) is can_assign


@pytest.mark.parametrize('task_kind', ['shot_video', 'asset_image'])
@pytest.mark.asyncio
async def test_reassignment_before_start_preserves_task_identity_and_requirements(
    monkeypatch: pytest.MonkeyPatch, task_kind: str
) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_uncommitted_submission_for_update',
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_assignable_member',
        AsyncMock(return_value={'producer_code': 'NEW'}),
    )
    task = _task()
    assigned, old_assignee = await ShotGridTaskService._assign_task(
        AsyncMock(),
        project_id=PROJECT_ID,
        command=ShotGridTaskAssignModel(assigneeUserId=NEW_ASSIGNEE_USER_ID, taskLockVersion=INITIAL_TASK_LOCK_VERSION),
        current_task=task,
        task_kind=task_kind,
        task_name='改派前的任务',
        shot_id=SHOT_ID if task_kind == 'shot_video' else None,
        asset_item_id=ASSET_ITEM_ID if task_kind == 'asset_image' else None,
        actor_name='director',
    )
    assert assigned is task
    assert assigned.task_id == TASK_ID
    assert old_assignee == ASSIGNEE_USER_ID
    assert assigned.assignee_user_id == NEW_ASSIGNEE_USER_ID
    assert assigned.task_status == 'not_started'
    assert assigned.requirements == '原要求'
    assert assigned.lock_version == UPDATED_TASK_LOCK_VERSION


@pytest.mark.parametrize(
    ('task_status', 'error_key'),
    [
        ('not_started', 'SG_TASK_REASSIGN_SUBMISSION_CONFLICT'),
        ('preparing', 'SG_INVALID_STATE_TRANSITION'),
        ('in_progress', 'SG_INVALID_STATE_TRANSITION'),
        ('pending_review', 'SG_INVALID_STATE_TRANSITION'),
        ('revision', 'SG_INVALID_STATE_TRANSITION'),
        ('completed', 'SG_INVALID_STATE_TRANSITION'),
    ],
)
@pytest.mark.parametrize('task_kind', ['shot_video', 'asset_image'])
@pytest.mark.asyncio
async def test_reassignment_is_blocked_after_start_or_by_uncommitted_submission(
    monkeypatch: pytest.MonkeyPatch,
    task_status: str,
    error_key: str,
    task_kind: str,
) -> None:
    uncommitted = AsyncMock(return_value=901 if task_status == 'not_started' else None)
    member = AsyncMock(return_value={'producer_code': 'NEW'})
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_uncommitted_submission_for_update',
        uncommitted,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_assignable_member',
        member,
    )
    db = AsyncMock()
    task = _task()
    task.task_status = task_status

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridTaskService._assign_task(
            db,
            project_id=PROJECT_ID,
            command=ShotGridTaskAssignModel(
                assigneeUserId=3,
                taskLockVersion=INITIAL_TASK_LOCK_VERSION,
            ),
            current_task=task,
            task_kind=task_kind,
            task_name='镜头任务',
            shot_id=SHOT_ID if task_kind == 'shot_video' else None,
            asset_item_id=ASSET_ITEM_ID if task_kind == 'asset_image' else None,
            actor_name='director',
        )

    assert exc_info.value.error_key == error_key
    assert exc_info.value.http_status == CONFLICT_STATUS
    assert task.assignee_user_id == ASSIGNEE_USER_ID
    assert task.lock_version == INITIAL_TASK_LOCK_VERSION
    if task_status != 'not_started':
        uncommitted.assert_not_awaited()
    else:
        uncommitted.assert_awaited_once_with(db, TASK_ID)
    member.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('all_scope', [False, True])
@pytest.mark.parametrize('existing_directory', [None, '001_S001'])
async def test_start_shot_allows_manager_and_increments_lock_in_same_transaction(
    monkeypatch: pytest.MonkeyPatch,
    all_scope: bool,
    existing_directory: str | None,
) -> None:
    monkeypatch.setattr(ShotGridTaskService, '_now', staticmethod(lambda: datetime(2026, 8, 28, 10)))
    task = _task(assignee_user_id=ASSIGNEE_USER_ID, lock_version=INITIAL_TASK_LOCK_VERSION)
    access = _access(user_id=3, all_scope=all_scope)
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._resolve_task_access',
        AsyncMock(return_value=(PROJECT_ID, access)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_mutable_project',
        AsyncMock(return_value=(SimpleNamespace(), SimpleNamespace(storage_status='ready'))),
    )
    _patch_locked_access(monkeypatch, access)
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_task',
        AsyncMock(return_value=task),
    )
    shot = SimpleNamespace(
        shot_id=SHOT_ID,
        shot_no=1,
        storage_dir_name=existing_directory,
        update_by='old',
        update_time=None,
        lock_version=0,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.lock_shot_target',
        AsyncMock(
            return_value=(
                shot,
                SimpleNamespace(storage_dir_name='EP001'),
                SimpleNamespace(scene_no=1),
            )
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_latest_shot_directory_operation_status',
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.flush',
        AsyncMock(),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_assignable_member',
        AsyncMock(return_value={'user_id': ASSIGNEE_USER_ID, 'producer_code': 'YJF'}),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskScheduleDao.find_overlap_task_ids',
        AsyncMock(return_value=[]),
    )
    audit = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._audit',
        audit,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._require_task_detail',
        AsyncMock(return_value=_task_row(task_status='preparing', lock_version=4)),
    )
    expected = object()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._build_detail',
        lambda *_args: expected,
    )
    db = SimpleNamespace(
        add=MagicMock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )

    result = await ShotGridTaskService.start_task(
        db,
        TASK_ID,
        ShotGridTaskStartModel(
            lockVersion=INITIAL_TASK_LOCK_VERSION,
            shotLockVersion=0,
            assetsConfirmed=True,
            priority='urgent',
            expectedStartTime='2026-08-29T09:00:00',
            expectedEndTime='2026-08-30T18:00:00',
        ),
        _current_user(user_id=3),
    )

    assert result is expected
    assert task.task_status == 'preparing'
    assert task.expected_start_time == datetime(2026, 8, 29, 9)
    assert task.expected_end_time == datetime(2026, 8, 30, 18)
    assert task.baseline_start_time == datetime(2026, 8, 29, 9)
    assert task.baseline_end_time == datetime(2026, 8, 30, 18)
    assert task.due_date == date(2026, 8, 30)
    assert task.priority == 'urgent'
    assert shot.storage_dir_name == (existing_directory or '001_0001')
    assert db.add.call_args.args[0].target_relative_path == f'VIDEO\\EP001\\{shot.storage_dir_name}'
    assert task.lock_version == UPDATED_TASK_LOCK_VERSION
    audit.assert_awaited_once()
    assert audit.await_args.kwargs['payload']['assetsConfirmed'] is True
    assert audit.await_args.kwargs['payload']['expectedStartTime'] == '2026-08-29T09:00:00'
    assert audit.await_args.kwargs['payload']['expectedEndTime'] == '2026-08-30T18:00:00'
    assert audit.await_args.kwargs['payload']['confirmationMethod'] == 'manual'
    assert audit.await_args.kwargs['result']['operatedBy'] == access.user_id
    assert task.assignee_user_id == ASSIGNEE_USER_ID
    history = next(
        call.args[0] for call in db.add.call_args_list if isinstance(call.args[0], ShotGridTaskScheduleChange)
    )
    assert history.change_type == 'initial'
    assert history.operation_source == 'start'
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_asset_task_creates_shared_directory_outbox_and_enters_preparing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ShotGridTaskService, '_now', staticmethod(lambda: datetime(2026, 8, 28, 10)))
    task = _task(assignee_user_id=ASSIGNEE_USER_ID, lock_version=INITIAL_TASK_LOCK_VERSION)
    task.task_kind = 'asset_image'
    task.shot_id = None
    task.asset_item_id = ASSET_ITEM_ID
    access = _access(user_id=ASSIGNEE_USER_ID, role='director')
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._resolve_task_access',
        AsyncMock(return_value=(PROJECT_ID, access)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_mutable_project',
        AsyncMock(return_value=(SimpleNamespace(), SimpleNamespace(storage_status='ready'))),
    )
    _patch_locked_access(monkeypatch, access)
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_assignable_member',
        AsyncMock(return_value={'producer_code': 'YJF'}),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_task',
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_asset_item_project_context',
        AsyncMock(return_value=(ASSET_ID, ASSET_ITEM_ID)),
    )
    lock_asset = AsyncMock(
        return_value=SimpleNamespace(
            asset_id=ASSET_ID,
            asset_type='Environment',
            storage_dir_name='动力舱室内',
            lock_version=4,
        )
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.lock_asset',
        lock_asset,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.lock_asset_item',
        AsyncMock(return_value=SimpleNamespace(production_item='主视角', lock_version=5)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_latest_asset_directory_operation_status',
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskScheduleDao.find_overlap_task_ids',
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.flush',
        AsyncMock(),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._audit',
        AsyncMock(),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._require_task_detail',
        AsyncMock(return_value=_task_row(task_kind='asset_image', task_status='preparing', lock_version=4)),
    )
    expected = object()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._build_detail',
        lambda *_args: expected,
    )
    db = SimpleNamespace(
        add=MagicMock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )

    result = await ShotGridTaskService.start_task(
        db,
        TASK_ID,
        ShotGridTaskStartModel(
            lockVersion=INITIAL_TASK_LOCK_VERSION,
            assetLockVersion=4,
            assetItemLockVersion=5,
            startConfirmed=True,
            priority='high',
            expectedStartTime='2026-08-29T09:00:00',
            expectedEndTime='2026-08-30T18:00:00',
        ),
        _current_user(user_id=ASSIGNEE_USER_ID),
    )

    assert result is expected
    assert task.task_status == 'preparing'
    operation = db.add.call_args.args[0]
    assert operation.operation_type == 'ensure_asset_directory'
    assert operation.aggregate_id == ASSET_ID
    assert operation.target_relative_path == 'ASSET\\Environment\\动力舱室内'
    assert operation.idempotency_key == f'asset-directory:{PROJECT_ID}:{ASSET_ID}'
    assert task.expected_start_time == datetime(2026, 8, 29, 9)
    assert task.expected_end_time == datetime(2026, 8, 30, 18)
    assert task.baseline_start_time == datetime(2026, 8, 29, 9)
    assert task.baseline_end_time == datetime(2026, 8, 30, 18)
    assert task.priority == 'high'
    lock_asset.assert_awaited_once_with(db, PROJECT_ID, ASSET_ID)
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'access',
    [
        _access(user_id=1, role='creator'),
        _access(user_id=ASSIGNEE_USER_ID, role='creator'),
    ],
)
async def test_start_asset_task_rejects_creators(
    monkeypatch: pytest.MonkeyPatch,
    access: ShotGridProjectAccessModel,
) -> None:
    task = _task()
    task.task_kind = 'asset_image'
    task.shot_id = None
    task.asset_item_id = ASSET_ITEM_ID
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._resolve_task_access',
        AsyncMock(return_value=(PROJECT_ID, access)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_mutable_project',
        AsyncMock(return_value=(SimpleNamespace(), SimpleNamespace(storage_status='ready'))),
    )
    _patch_locked_access(monkeypatch, access)
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_task',
        AsyncMock(return_value=task),
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridTaskService.start_task(
            db,
            TASK_ID,
            ShotGridTaskStartModel(lockVersion=INITIAL_TASK_LOCK_VERSION),
            _current_user(user_id=access.user_id),
        )

    assert exc_info.value.error_key == 'SG_TASK_ACTION_DENIED'
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('case', 'error_key'),
    [
        ('unconfirmed', 'SG_ASSET_START_CONFIRMATION_REQUIRED'),
        ('missing_asset_version', 'SG_ASSET_START_CONFIRMATION_REQUIRED'),
        ('missing_item_version', 'SG_ASSET_START_CONFIRMATION_REQUIRED'),
        ('stale_task', 'SG_OPTIMISTIC_LOCK_CONFLICT'),
        ('stale_asset', 'SG_OPTIMISTIC_LOCK_CONFLICT'),
        ('stale_item', 'SG_OPTIMISTIC_LOCK_CONFLICT'),
        ('inactive_assignee', 'SG_TASK_ASSIGNEE_INVALID'),
        ('archived_asset', 'SG_ASSET_NOT_FOUND'),
        ('archived_item', 'SG_ASSET_ITEM_NOT_FOUND'),
        ('blank_item', 'SG_ASSET_PRODUCTION_ITEM_REQUIRED'),
        ('already_started', 'SG_INVALID_STATE_TRANSITION'),
        ('missing_permission', 'SG_TASK_ACTION_DENIED'),
    ],
)
async def test_asset_manager_start_rejects_invalid_snapshot_without_writes(
    monkeypatch: pytest.MonkeyPatch, case: str, error_key: str
) -> None:
    task = _task(lock_version=4 if case == 'stale_task' else 3)
    task.task_kind, task.shot_id, task.asset_item_id = 'asset_image', None, ASSET_ITEM_ID
    if case == 'already_started':
        task.task_status = 'preparing'
    access = _access(user_id=9)
    prefix = 'module_shot_grid.service.task_service.'
    patches = {
        'ShotGridTaskService._resolve_task_access': (PROJECT_ID, access),
        'ShotGridTaskService._lock_mutable_project': (SimpleNamespace(), SimpleNamespace(storage_status='ready')),
        'ShotGridTaskService._lock_task': task,
        'ShotGridTaskDao.get_asset_item_project_context': (ASSET_ID, ASSET_ITEM_ID),
        'ShotGridTaskDao.lock_asset': None
        if case == 'archived_asset'
        else SimpleNamespace(lock_version=1 if case == 'stale_asset' else 0),
        'ShotGridTaskDao.lock_asset_item': None
        if case == 'archived_item'
        else SimpleNamespace(
            lock_version=1 if case == 'stale_item' else 0,
            production_item=' ' if case == 'blank_item' else '主视角',
        ),
        'ShotGridTaskDao.get_assignable_member': None if case == 'inactive_assignee' else {'producer_code': 'YJF'},
    }
    for target, value in patches.items():
        monkeypatch.setattr(prefix + target, AsyncMock(return_value=value))
    _patch_locked_access(monkeypatch, access)
    payload = {'lockVersion': 3, 'assetLockVersion': 0, 'assetItemLockVersion': 0, 'startConfirmed': True}
    if case == 'unconfirmed':
        payload['startConfirmed'] = False
    if case == 'missing_asset_version':
        del payload['assetLockVersion']
    if case == 'missing_item_version':
        del payload['assetItemLockVersion']
    user = _current_user(user_id=9)
    if case == 'missing_permission':
        user.permissions = ['shotgrid:task:query']
    db = SimpleNamespace(add=MagicMock(), commit=AsyncMock(), rollback=AsyncMock())
    with pytest.raises(ShotGridDomainException) as error:
        await ShotGridTaskService.start_task(db, TASK_ID, ShotGridTaskStartModel(**payload), user)
    assert error.value.error_key == error_key
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_task_rechecks_active_membership_after_project_lock_and_rolls_back_when_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_user = _current_user(user_id=ASSIGNEE_USER_ID)
    pre_access = _access(user_id=ASSIGNEE_USER_ID, role='creator')
    project_lock = AsyncMock(return_value=(SimpleNamespace(), SimpleNamespace(storage_status='ready')))
    task_lock = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._resolve_task_access',
        AsyncMock(return_value=(PROJECT_ID, pre_access)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_mutable_project',
        project_lock,
    )
    refresh = AsyncMock(side_effect=shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '无权访问该项目'))
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridProjectAccessService.resolve_access',
        refresh,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_task',
        task_lock,
    )
    audit = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._audit',
        audit,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridTaskService.start_task(
            db,
            TASK_ID,
            ShotGridTaskStartModel(lockVersion=INITIAL_TASK_LOCK_VERSION),
            current_user,
        )

    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'
    project_lock.assert_awaited_once_with(db, PROJECT_ID, require_storage_ready=False)
    refresh.assert_awaited_once_with(db, current_user, PROJECT_ID)
    task_lock.assert_not_awaited()
    audit.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_task_rejects_stale_lock_version_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(assignee_user_id=ASSIGNEE_USER_ID, lock_version=UPDATED_TASK_LOCK_VERSION)
    access = _access()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._resolve_task_access',
        AsyncMock(return_value=(PROJECT_ID, access)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_mutable_project',
        AsyncMock(return_value=(SimpleNamespace(), SimpleNamespace(storage_status='ready'))),
    )
    _patch_locked_access(monkeypatch, access)
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_task',
        AsyncMock(return_value=task),
    )
    audit = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._audit',
        audit,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridTaskService.start_task(
            db,
            TASK_ID,
            ShotGridTaskStartModel(lockVersion=INITIAL_TASK_LOCK_VERSION),
            _current_user(),
        )

    assert exc_info.value.error_key == 'SG_OPTIMISTIC_LOCK_CONFLICT'
    assert task.task_status == 'not_started'
    audit.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_task_applies_full_snapshot_and_audits_before_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(lock_version=INITIAL_TASK_LOCK_VERSION)
    access = _access()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._resolve_task_access',
        AsyncMock(return_value=(PROJECT_ID, access)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_mutable_project',
        AsyncMock(),
    )
    _patch_locked_access(monkeypatch, access)
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_task',
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.flush',
        AsyncMock(),
    )
    audit = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._audit',
        audit,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._require_task_detail',
        AsyncMock(return_value=_task_row(requirements=None, priority='urgent', due_date=None, lock_version=4)),
    )
    expected = object()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._build_detail',
        lambda *_args: expected,
    )
    db = AsyncMock()

    result = await ShotGridTaskService.update_task(
        db,
        TASK_ID,
        ShotGridTaskUpdateModel(
            requirements=None,
            priority='urgent',
            dueDate=None,
            lockVersion=INITIAL_TASK_LOCK_VERSION,
        ),
        _current_user(),
    )

    assert result is expected
    assert task.requirements is None
    assert task.priority == 'urgent'
    assert task.due_date is None
    assert task.lock_version == UPDATED_TASK_LOCK_VERSION
    audit.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_task_rejects_task_after_production_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(lock_version=INITIAL_TASK_LOCK_VERSION)
    task.task_status = 'in_progress'
    access = _access()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._resolve_task_access',
        AsyncMock(return_value=(PROJECT_ID, access)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_mutable_project',
        AsyncMock(),
    )
    _patch_locked_access(monkeypatch, access)
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_task',
        AsyncMock(return_value=task),
    )
    flush = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.flush',
        flush,
    )
    audit = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._audit',
        audit,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridTaskService.update_task(
            db,
            TASK_ID,
            ShotGridTaskUpdateModel(
                requirements='新要求',
                priority='high',
                dueDate=date(2026, 8, 30),
                lockVersion=INITIAL_TASK_LOCK_VERSION,
            ),
            _current_user(),
        )

    assert exc_info.value.http_status == HTTPStatus.CONFLICT
    assert exc_info.value.error_key == 'SG_INVALID_STATE_TRANSITION'
    assert exc_info.value.message == '任务开始制作后不可编辑'
    assert task.requirements == '原要求'
    assert task.priority == 'normal'
    assert task.due_date is None
    assert task.lock_version == INITIAL_TASK_LOCK_VERSION
    flush.assert_not_awaited()
    audit.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_task_rechecks_director_after_project_lock_and_rolls_back_when_demoted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_user = _current_user()
    pre_access = _access(role='director')
    project_lock = AsyncMock()
    task_lock = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._resolve_task_access',
        AsyncMock(return_value=(PROJECT_ID, pre_access)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_mutable_project',
        project_lock,
    )
    refresh = _patch_locked_access(monkeypatch, _access(role='creator'))
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_task',
        task_lock,
    )
    audit = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._audit',
        audit,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridTaskService.update_task(
            db,
            TASK_ID,
            ShotGridTaskUpdateModel(
                requirements='新要求',
                priority='high',
                dueDate=None,
                lockVersion=INITIAL_TASK_LOCK_VERSION,
            ),
            current_user,
        )

    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'
    project_lock.assert_awaited_once_with(db, PROJECT_ID, require_storage_ready=False)
    refresh.assert_awaited_once_with(db, current_user, PROJECT_ID)
    task_lock.assert_not_awaited()
    audit.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_integrity_error_is_rolled_back_and_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task()
    access = _access()
    database_error = IntegrityError('UPDATE sg_task', {}, RuntimeError('database failure'))
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._resolve_task_access',
        AsyncMock(return_value=(PROJECT_ID, access)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_mutable_project',
        AsyncMock(),
    )
    _patch_locked_access(monkeypatch, access)
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskService._lock_task',
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.flush',
        AsyncMock(side_effect=database_error),
    )
    db = AsyncMock()

    with pytest.raises(IntegrityError) as exc_info:
        await ShotGridTaskService.update_task(
            db,
            TASK_ID,
            ShotGridTaskUpdateModel(
                requirements=None,
                priority='normal',
                dueDate=None,
                lockVersion=INITIAL_TASK_LOCK_VERSION,
            ),
            _current_user(),
        )

    assert exc_info.value is database_error
    assert ShotGridTaskService._map_integrity_error(database_error) is None
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('case', 'error_key'),
    [
        ('unconfirmed', 'SG_SHOT_START_CONFIRMATION_REQUIRED'),
        ('missing_shot_version', 'SG_SHOT_START_CONFIRMATION_REQUIRED'),
        ('changed_shot', 'SG_OPTIMISTIC_LOCK_CONFLICT'),
        ('already_started', 'SG_INVALID_STATE_TRANSITION'),
        ('inactive_assignee', 'SG_TASK_ASSIGNEE_INVALID'),
        ('missing_permission', 'SG_TASK_ACTION_DENIED'),
        ('all_scope_missing_permission', 'SG_TASK_ACTION_DENIED'),
        ('creator_owner', 'SG_TASK_ACTION_DENIED'),
        ('creator_other', 'SG_TASK_ACTION_DENIED'),
    ],
)
async def test_shot_start_blocks_stale_unconfirmed_and_unauthorized_requests(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    error_key: str,
) -> None:
    access = _access(user_id=3 if 'missing_permission' in case else 1, all_scope=case == 'all_scope_missing_permission')
    if case.startswith('creator_'):
        access = _access(user_id=ASSIGNEE_USER_ID if case == 'creator_owner' else 8, role='creator')
    task = _task()
    if case == 'already_started':
        task.task_status = 'preparing'
    prefix = 'module_shot_grid.service.task_service.'
    monkeypatch.setattr(
        prefix + 'ShotGridTaskService._resolve_task_access', AsyncMock(return_value=(PROJECT_ID, access))
    )
    monkeypatch.setattr(
        prefix + 'ShotGridTaskService._lock_mutable_project',
        AsyncMock(return_value=(SimpleNamespace(), SimpleNamespace(storage_status='ready'))),
    )
    _patch_locked_access(monkeypatch, access)
    monkeypatch.setattr(prefix + 'ShotGridTaskService._lock_task', AsyncMock(return_value=task))
    monkeypatch.setattr(
        prefix + 'ShotGridTaskDao.get_assignable_member',
        AsyncMock(return_value=None if case == 'inactive_assignee' else {'producer_code': 'YJF'}),
    )
    shot = SimpleNamespace(shot_id=SHOT_ID, lock_version=1 if case == 'changed_shot' else 0, storage_dir_name=None)
    monkeypatch.setattr(
        prefix + 'ShotGridTaskDao.lock_shot_target',
        AsyncMock(return_value=(shot, SimpleNamespace(), SimpleNamespace())),
    )
    audit = AsyncMock()
    monkeypatch.setattr(prefix + 'ShotGridTaskService._audit', audit)
    db = AsyncMock()
    payload = {
        'lockVersion': 3,
        'shotLockVersion': 0,
        'assetsConfirmed': True,
        'expectedStartTime': '2026-09-01T09:00:00',
        'expectedEndTime': '2026-09-02T18:00:00',
    }
    if case == 'unconfirmed':
        payload['assetsConfirmed'] = False
    if case == 'missing_shot_version':
        del payload['shotLockVersion']
    user = _current_user(user_id=access.user_id)
    if 'missing_permission' in case:
        user.permissions = ['shotgrid:task:query']
    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridTaskService.start_task(db, TASK_ID, ShotGridTaskStartModel(**payload), user)
    assert exc_info.value.error_key == error_key
    assert shot.storage_dir_name is None
    audit.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()

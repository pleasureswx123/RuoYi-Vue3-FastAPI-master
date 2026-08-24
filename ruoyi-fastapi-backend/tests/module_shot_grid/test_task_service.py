from datetime import date, datetime
from http import HTTPStatus
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
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
INITIAL_TASK_LOCK_VERSION = 3
UPDATED_TASK_LOCK_VERSION = 4
SHOT_DURATION_MS = 8000


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
        'task_name': 'EP001-001-S001 镜头视频制作',
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
        'episode_id': 100,
        'episode_no': 1,
        'scene_id': 200,
        'scene_no': 1,
        'scene_name': '动力舱',
        'shot_no': 1,
        'shot_storage_dir_name': '001_S001',
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
        'asset_item_description': None,
        'asset_item_lifecycle_status': None,
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
    assert detail.target.target_name == 'EP001-001-S001'
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
        _task_row(
            update_by=(
                '31412-9d227a:31412:c380be68a38c43aebe690f61258a664f:'
                'a58a5b5baeb5'
            )
        ),
        _current_user(user_id=ASSIGNEE_USER_ID),
        _access(user_id=ASSIGNEE_USER_ID, role='creator'),
    )

    assert detail.update_by == '系统目录服务'


@pytest.mark.asyncio
async def test_task_detail_recovers_legacy_worker_owner_from_directory_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_worker_owner = (
        '31412-9d227a:31412:c380be68a38c43aebe690f61258a664f:'
        'a58a5b5baeb5'
    )
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


def test_task_detail_does_not_offer_production_actions_to_director_or_all_scope() -> None:
    row = _task_row(task_status='not_started', assignee_user_id=ASSIGNEE_USER_ID)
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

    assert 'task.start' not in director_actions
    assert 'task.start' not in all_scope_actions
    assert 'task.start' in creator_actions


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
            SimpleNamespace(shot_no=1, storage_dir_name='001_S001', description='镜头原始制作内容'),
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
    assert assigned_task.task_name == 'EP001-001-S001 镜头视频制作'
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
                SimpleNamespace(shot_no=1, storage_dir_name='001_S001', description='镜头原始制作内容'),
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
                SimpleNamespace(shot_no=1, storage_dir_name='001_S001', description='第一镜制作内容'),
                SimpleNamespace(episode_no=1),
                SimpleNamespace(scene_no=1),
            ),
            (
                SimpleNamespace(shot_no=2, storage_dir_name='001_S002', description='第二镜制作内容'),
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


@pytest.mark.asyncio
async def test_reassignment_is_blocked_by_any_uncommitted_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uncommitted = AsyncMock(return_value=901)
    member = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_uncommitted_submission_for_update',
        uncommitted,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.get_assignable_member',
        member,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridTaskService._assign_task(
            db,
            project_id=PROJECT_ID,
            command=ShotGridTaskAssignModel(
                assigneeUserId=3,
                taskLockVersion=INITIAL_TASK_LOCK_VERSION,
            ),
            current_task=_task(),
            task_kind='shot_video',
            task_name='镜头任务',
            shot_id=SHOT_ID,
            asset_item_id=None,
            actor_name='director',
        )

    assert exc_info.value.error_key == 'SG_TASK_REASSIGN_SUBMISSION_CONFLICT'
    uncommitted.assert_awaited_once_with(db, TASK_ID)
    member.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_task_allows_owner_and_increments_lock_in_same_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(assignee_user_id=ASSIGNEE_USER_ID, lock_version=INITIAL_TASK_LOCK_VERSION)
    access = _access(user_id=ASSIGNEE_USER_ID, role='creator')
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
        storage_dir_name=None,
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
        ShotGridTaskStartModel(lockVersion=INITIAL_TASK_LOCK_VERSION),
        _current_user(user_id=ASSIGNEE_USER_ID),
    )

    assert result is expected
    assert task.task_status == 'preparing'
    assert shot.storage_dir_name == '001_S001'
    assert task.lock_version == UPDATED_TASK_LOCK_VERSION
    audit.assert_awaited_once()
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'access',
    [
        _access(user_id=1, role='creator'),
        _access(user_id=ASSIGNEE_USER_ID, role='director'),
        _access(user_id=ASSIGNEE_USER_ID, all_scope=True),
    ],
)
async def test_start_task_rejects_non_owner_creator_director_and_all_scope(
    monkeypatch: pytest.MonkeyPatch,
    access: ShotGridProjectAccessModel,
) -> None:
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
        AsyncMock(return_value=_task(assignee_user_id=ASSIGNEE_USER_ID)),
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
    access = _access(user_id=ASSIGNEE_USER_ID, role='creator')
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
            _current_user(user_id=ASSIGNEE_USER_ID),
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

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.task_schedule_vo import ShotGridScheduleQueryModel, ShotGridScheduleUpdateModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.task_schedule_service import ShotGridTaskScheduleService

PROJECT_ID = 11
TASK_ID = 31
ACTOR_ID = 3
ASSIGNEE_ID = 7
LOCK_VERSION = 4
CONFLICT_TASK_ID = 99
EXPECTED_UNSCHEDULED_COUNT = 2
START_TIME = datetime(2026, 9, 1, 9)
END_TIME = datetime(2026, 9, 3, 18)
BASELINE_START = datetime(2026, 8, 31, 9)
BASELINE_END = datetime(2026, 9, 2, 18)


def _current_user(*, permissions: list[str] | None = None, user_id: int = ACTOR_ID) -> CurrentUserModel:
    return CurrentUserModel(
        permissions=permissions or ['shotgrid:task:schedule', 'shotgrid:task:list', 'shotgrid:task:query'],
        roles=[],
        user=UserInfoModel(userId=user_id, userName='director'),
    )


def _access(*, role: str = 'director', all_scope: bool = False, user_id: int = ACTOR_ID) -> ShotGridProjectAccessModel:
    return ShotGridProjectAccessModel(
        projectId=PROJECT_ID,
        userId=user_id,
        projectRole=None if all_scope else role,
        hasAllScope=all_scope,
    )


def _task(
    *,
    lock_version: int = LOCK_VERSION,
    current_start: datetime | None = None,
    current_end: datetime | None = None,
    baseline_start: datetime | None = None,
    baseline_end: datetime | None = None,
    task_status: str = 'not_started',
) -> SimpleNamespace:
    return SimpleNamespace(
        task_id=TASK_ID,
        project_id=PROJECT_ID,
        task_name='EP001-001-0010 镜头视频制作',
        task_kind='shot_video',
        task_status=task_status,
        priority='high',
        assignee_user_id=ASSIGNEE_ID,
        shot_id=21,
        asset_item_id=None,
        expected_start_time=current_start,
        expected_end_time=current_end,
        baseline_start_time=baseline_start,
        baseline_end_time=baseline_end,
        due_date=current_end.date() if current_end else None,
        lock_version=lock_version,
        update_by='old',
        update_time=None,
        del_flag='0',
    )


def _row(task: SimpleNamespace, *, task_id: int = TASK_ID) -> dict[str, object]:
    return {
        'task_id': task_id,
        'project_id': PROJECT_ID,
        'task_name': task.task_name,
        'task_kind': task.task_kind,
        'task_status': task.task_status,
        'priority': task.priority,
        'assignee_user_id': task.assignee_user_id,
        'assignee_user_name': 'creator',
        'assignee_nick_name': '制作人',
        'expected_start_time': task.expected_start_time,
        'expected_end_time': task.expected_end_time,
        'baseline_start_time': task.baseline_start_time,
        'baseline_end_time': task.baseline_end_time,
        'lock_version': task.lock_version,
        'target_id': 21,
        'target_parent_id': 12,
        'target_sort_order': 10,
        'shot_id': 21,
        'shot_no': 10,
        'episode_id': 2,
        'episode_no': 1,
        'episode_sort_order': 1,
        'scene_id': 12,
        'scene_no': 1,
        'scene_name': '动力舱',
        'scene_sort_order': 1,
        'asset_id': None,
        'asset_name': None,
        'asset_type': None,
        'asset_sort_order': None,
        'asset_item_id': None,
        'production_item': None,
        'asset_item_sort_order': None,
        'group_key': f'assignee:{ASSIGNEE_ID}',
        'group_name': 'creator',
        'group_sort_order': 'creator',
        'project_status': 'active',
    }


def _command(
    *,
    lock_version: int = LOCK_VERSION,
    overlap_acknowledged: bool = False,
    expected_conflicts: list[int] | None = None,
) -> ShotGridScheduleUpdateModel:
    return ShotGridScheduleUpdateModel(
        lockVersion=lock_version,
        expectedStartTime=START_TIME,
        expectedEndTime=END_TIME,
        operationSource='dialog',
        changeReason='客户反馈调整',
        overlapAcknowledged=overlap_acknowledged,
        expectedConflictTaskIds=expected_conflicts or [],
    )


def _wire_success(monkeypatch: pytest.MonkeyPatch, task: SimpleNamespace, *, overlaps: list[int] | None = None) -> dict:
    project = SimpleNamespace(project_id=PROJECT_ID, project_status='active', del_flag='0')
    member = SimpleNamespace(project_role='director', member_status='active')
    conflict_task = _task(
        current_start=datetime(2026, 9, 2, 9),
        current_end=datetime(2026, 9, 4, 18),
        baseline_start=datetime(2026, 9, 2, 9),
        baseline_end=datetime(2026, 9, 4, 18),
    )
    conflict_task.task_id = CONFLICT_TASK_ID
    conflict_row = _row(conflict_task, task_id=CONFLICT_TASK_ID)
    mocks = {
        'resolve_access': AsyncMock(return_value=_access()),
        'lock_project': AsyncMock(return_value=project),
        'lock_actor_member': AsyncMock(return_value=member),
        'lock_task': AsyncMock(return_value=task),
        'idempotency': AsyncMock(return_value=None),
        'assignee': AsyncMock(return_value={'user_id': ASSIGNEE_ID}),
        'target': AsyncMock(return_value=(SimpleNamespace(), SimpleNamespace(), SimpleNamespace())),
        'overlaps': AsyncMock(return_value=overlaps or []),
        'rows': AsyncMock(
            side_effect=lambda _db, _project_id, ids: [_row(task)] if ids == [TASK_ID] else [conflict_row]
        ),
        'add_change': AsyncMock(side_effect=lambda _db, change: change),
        'audit': AsyncMock(),
    }
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskDao.get_task_project_id',
        AsyncMock(return_value=PROJECT_ID),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridProjectAccessService.resolve_access',
        mocks['resolve_access'],
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskScheduleDao.lock_project', mocks['lock_project']
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskScheduleDao.lock_actor_member',
        mocks['lock_actor_member'],
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskScheduleDao.lock_task', mocks['lock_task']
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskScheduleDao.get_idempotency_result',
        mocks['idempotency'],
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskDao.get_assignable_member', mocks['assignee']
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskDao.lock_shot_target', mocks['target']
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskScheduleDao.find_overlap_task_ids',
        mocks['overlaps'],
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskScheduleDao.get_task_rows_by_ids', mocks['rows']
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskScheduleDao.add_schedule_change',
        mocks['add_change'],
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridProjectAuditDao.add_success_log', mocks['audit']
    )
    return mocks


@pytest.mark.asyncio
async def test_initial_schedule_freezes_baseline_updates_due_and_appends_audited_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task()
    mocks = _wire_success(monkeypatch, task)
    db = AsyncMock()
    db.add = Mock()

    result = await ShotGridTaskScheduleService.update_schedule(
        db,
        TASK_ID,
        _command(),
        'schedule-command-1',
        _current_user(),
    )

    assert (task.expected_start_time, task.expected_end_time) == (START_TIME, END_TIME)
    assert (task.baseline_start_time, task.baseline_end_time) == (START_TIME, END_TIME)
    assert task.due_date == date(2026, 9, 3)
    assert task.lock_version == LOCK_VERSION + 1
    change = mocks['add_change'].await_args.args[1]
    assert change.change_type == 'initial'
    assert change.task_lock_version_before == LOCK_VERSION
    assert change.task_lock_version_after == LOCK_VERSION + 1
    assert change.result_snapshot['baselineStart'] == '2026-09-01T09:00:00'
    assert result.baseline_start == START_TIME
    mocks['audit'].assert_awaited_once()
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_reschedule_preserves_frozen_baseline_and_derives_move(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task(
        current_start=BASELINE_START,
        current_end=BASELINE_END,
        baseline_start=BASELINE_START,
        baseline_end=BASELINE_END,
    )
    mocks = _wire_success(monkeypatch, task)
    db = AsyncMock()
    db.add = Mock()

    await ShotGridTaskScheduleService.update_schedule(db, TASK_ID, _command(), 'schedule-command-2', _current_user())

    assert (task.baseline_start_time, task.baseline_end_time) == (BASELINE_START, BASELINE_END)
    assert mocks['add_change'].await_args.args[1].change_type == 'move'


@pytest.mark.asyncio
async def test_overlap_requires_current_exact_snapshot_before_save(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task()
    mocks = _wire_success(monkeypatch, task, overlaps=[CONFLICT_TASK_ID])
    db = AsyncMock()
    db.add = Mock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridTaskScheduleService.update_schedule(
            db, TASK_ID, _command(), 'schedule-command-3', _current_user()
        )

    assert exc_info.value.error_key == 'SG_TASK_SCHEDULE_OVERLAP'
    assert exc_info.value.details == {'conflictTaskIds': [CONFLICT_TASK_ID]}
    assert task.expected_start_time is None
    mocks['add_change'].assert_not_awaited()
    db.rollback.assert_awaited_once()

    db.reset_mock()
    result = await ShotGridTaskScheduleService.update_schedule(
        db,
        TASK_ID,
        _command(overlap_acknowledged=True, expected_conflicts=[CONFLICT_TASK_ID]),
        'schedule-command-4',
        _current_user(),
    )
    assert result.conflicts[0].task_id == CONFLICT_TASK_ID
    assert mocks['add_change'].await_args.args[1].overlap_task_ids == [CONFLICT_TASK_ID]


@pytest.mark.asyncio
async def test_overlap_snapshot_change_and_lock_conflict_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task()
    _wire_success(monkeypatch, task, overlaps=[99, 100])
    db = AsyncMock()
    db.add = Mock()

    with pytest.raises(ShotGridDomainException) as overlap_error:
        await ShotGridTaskScheduleService.update_schedule(
            db,
            TASK_ID,
            _command(overlap_acknowledged=True, expected_conflicts=[99]),
            'schedule-command-5',
            _current_user(),
        )
    assert overlap_error.value.error_key == 'SG_TASK_SCHEDULE_OVERLAP'
    assert overlap_error.value.details == {'conflictTaskIds': [99, 100]}

    task.lock_version = LOCK_VERSION + 1
    with pytest.raises(ShotGridDomainException) as lock_error:
        await ShotGridTaskScheduleService.update_schedule(
            db,
            TASK_ID,
            _command(),
            'schedule-command-6',
            _current_user(),
        )
    assert lock_error.value.error_key == 'SG_OPTIMISTIC_LOCK_CONFLICT'


@pytest.mark.asyncio
async def test_creator_or_missing_schedule_permission_cannot_mutate(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task()
    mocks = _wire_success(monkeypatch, task)
    mocks['resolve_access'].return_value = _access(role='creator')
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as role_error:
        await ShotGridTaskScheduleService.update_schedule(
            db, TASK_ID, _command(), 'schedule-command-7', _current_user()
        )
    assert role_error.value.error_key == 'SG_TASK_SCHEDULE_READ_ONLY'

    mocks['resolve_access'].return_value = _access()
    with pytest.raises(ShotGridDomainException) as permission_error:
        await ShotGridTaskScheduleService.update_schedule(
            db,
            TASK_ID,
            _command(),
            'schedule-command-8',
            _current_user(permissions=['shotgrid:task:list']),
        )
    assert permission_error.value.error_key == 'SG_TASK_SCHEDULE_READ_ONLY'


@pytest.mark.asyncio
async def test_same_idempotency_key_replays_snapshot_and_rejects_other_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task()
    mocks = _wire_success(monkeypatch, task)
    snapshot_task = _task(
        lock_version=LOCK_VERSION + 1,
        current_start=START_TIME,
        current_end=END_TIME,
        baseline_start=START_TIME,
        baseline_end=END_TIME,
    )
    snapshot = ShotGridTaskScheduleService._build_task_model(_row(snapshot_task), conflicts=[], can_schedule=True)
    command = _command()
    request_hash = ShotGridTaskScheduleService._request_hash(command)
    mocks['idempotency'].return_value = SimpleNamespace(
        request_hash=request_hash,
        result_snapshot=snapshot.model_dump(by_alias=True, mode='json'),
    )
    db = AsyncMock()

    replay = await ShotGridTaskScheduleService.update_schedule(
        db, TASK_ID, command, 'schedule-command-9', _current_user()
    )
    assert replay.lock_version == LOCK_VERSION + 1
    mocks['add_change'].assert_not_awaited()
    db.rollback.assert_awaited_once()

    mocks['idempotency'].return_value.request_hash = 'f' * 64
    with pytest.raises(ShotGridDomainException) as conflict:
        await ShotGridTaskScheduleService.update_schedule(db, TASK_ID, command, 'schedule-command-9', _current_user())
    assert conflict.value.error_key == 'SG_IDEMPOTENCY_CONFLICT'


@pytest.mark.asyncio
async def test_project_schedule_batches_conflicts_and_keeps_creator_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task(
        lock_version=LOCK_VERSION,
        current_start=START_TIME,
        current_end=END_TIME,
        baseline_start=START_TIME,
        baseline_end=END_TIME,
    )
    conflict_task = _task(
        current_start=datetime(2026, 9, 2, 9),
        current_end=datetime(2026, 9, 4, 18),
        baseline_start=datetime(2026, 9, 2, 9),
        baseline_end=datetime(2026, 9, 4, 18),
    )
    conflict_task.task_id = CONFLICT_TASK_ID
    schedule_page = AsyncMock(return_value=([_row(task)], 1, 2))
    overlap_pairs = AsyncMock(return_value=[(TASK_ID, CONFLICT_TASK_ID)])
    conflict_rows = AsyncMock(return_value=[_row(conflict_task, task_id=CONFLICT_TASK_ID)])
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridProjectAccessService.resolve_access',
        AsyncMock(return_value=_access(role='creator')),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskScheduleDao.get_schedule_page', schedule_page
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskScheduleDao.get_overlap_pairs', overlap_pairs
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskScheduleDao.get_task_rows_by_ids', conflict_rows
    )

    result = await ShotGridTaskScheduleService.get_project_schedule(
        AsyncMock(),
        PROJECT_ID,
        ShotGridScheduleQueryModel(windowStart=START_TIME, windowEnd=datetime(2026, 10, 1)),
        _current_user(),
    )

    assert result.total == 1
    assert result.unscheduled_count == EXPECTED_UNSCHEDULED_COUNT
    assert result.rows[0].conflicts[0].task_id == CONFLICT_TASK_ID
    assert result.rows[0].allowed_actions == []
    assert result.groups[0].task_count == 1
    overlap_pairs.assert_awaited_once()


@pytest.mark.asyncio
async def test_unscheduled_page_only_offers_schedule_to_authorized_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task()
    row = _row(task)
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridProjectAccessService.resolve_access',
        AsyncMock(return_value=_access()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskScheduleDao.get_unscheduled_page',
        AsyncMock(return_value=([row], 1)),
    )

    result = await ShotGridTaskScheduleService.get_unscheduled_tasks(
        AsyncMock(),
        PROJECT_ID,
        ShotGridScheduleQueryModel(windowStart=START_TIME, windowEnd=datetime(2026, 10, 1)),
        _current_user(),
    )

    assert result.rows[0].allowed_actions == ['schedule']
    assert result.rows[0].task_id == TASK_ID


@pytest.mark.asyncio
async def test_schedule_changes_returns_structured_page_for_director(monkeypatch: pytest.MonkeyPatch) -> None:
    history_row = {
        'schedule_change_id': 501,
        'task_id': TASK_ID,
        'operator_user_id': ACTOR_ID,
        'operator_user_name': 'director',
        'operator_nick_name': '导演',
        'from_start_time': None,
        'from_end_time': None,
        'to_start_time': START_TIME,
        'to_end_time': END_TIME,
        'change_type': 'initial',
        'operation_source': 'dialog',
        'change_reason': '首次排期',
        'overlap_acknowledged': False,
        'overlap_task_ids': [],
        'task_lock_version_before': LOCK_VERSION,
        'task_lock_version_after': LOCK_VERSION + 1,
        'create_time': datetime(2026, 8, 31, 10),
    }
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskDao.get_task_project_id',
        AsyncMock(return_value=PROJECT_ID),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridProjectAccessService.resolve_access',
        AsyncMock(return_value=_access()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskDao.get_task_detail',
        AsyncMock(return_value={'task_id': TASK_ID, 'assignee_user_id': ASSIGNEE_ID}),
    )
    changes = AsyncMock(return_value=([history_row], 1))
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskScheduleDao.get_schedule_changes',
        changes,
    )

    result = await ShotGridTaskScheduleService.get_schedule_changes(
        AsyncMock(), TASK_ID, page_num=1, page_size=20, current_user=_current_user()
    )

    assert result.total == 1
    assert result.rows[0].operator.user_name == 'director'
    assert result.rows[0].overlap_task_ids == []
    changes.assert_awaited_once()


@pytest.mark.asyncio
async def test_schedule_changes_creator_can_only_read_own_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskDao.get_task_project_id',
        AsyncMock(return_value=PROJECT_ID),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridProjectAccessService.resolve_access',
        AsyncMock(return_value=_access(role='creator', user_id=ASSIGNEE_ID)),
    )
    detail = AsyncMock(return_value={'task_id': TASK_ID, 'assignee_user_id': ACTOR_ID})
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskDao.get_task_detail',
        detail,
    )
    changes = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(
        'module_shot_grid.service.task_schedule_service.ShotGridTaskScheduleDao.get_schedule_changes',
        changes,
    )

    with pytest.raises(ShotGridDomainException) as denied:
        await ShotGridTaskScheduleService.get_schedule_changes(
            AsyncMock(),
            TASK_ID,
            page_num=1,
            page_size=20,
            current_user=_current_user(user_id=ASSIGNEE_ID),
        )

    assert denied.value.error_key == 'SG_PROJECT_ACCESS_DENIED'
    changes.assert_not_awaited()

    detail.return_value = {'task_id': TASK_ID, 'assignee_user_id': ASSIGNEE_ID}
    result = await ShotGridTaskScheduleService.get_schedule_changes(
        AsyncMock(),
        TASK_ID,
        page_num=1,
        page_size=20,
        current_user=_current_user(user_id=ASSIGNEE_ID),
    )
    assert result.total == 0

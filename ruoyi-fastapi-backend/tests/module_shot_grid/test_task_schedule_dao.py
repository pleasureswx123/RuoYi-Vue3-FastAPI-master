from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.task_schedule_dao import ShotGridTaskScheduleDao
from module_shot_grid.entity.do.task_schedule_change_do import ShotGridTaskScheduleChange
from module_shot_grid.entity.vo.task_schedule_vo import ShotGridScheduleQueryModel

PROJECT_ID = 11
TASK_ID = 31
ASSIGNEE_ID = 7
WINDOW_START = datetime(2026, 9, 1)
WINDOW_END = datetime(2026, 10, 1)


def _sql(statement: object) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={'literal_binds': True},
        )
    ).lower()


def _query(**overrides: object) -> ShotGridScheduleQueryModel:
    return ShotGridScheduleQueryModel(
        windowStart=WINDOW_START,
        windowEnd=WINDOW_END,
        **overrides,
    )


def test_schedule_statement_uses_current_or_baseline_window_and_stable_group_order() -> None:
    statement = ShotGridTaskScheduleDao.build_schedule_statement(
        PROJECT_ID,
        _query(
            targetKind='shot',
            groupBy='scene',
            assigneeUserId=ASSIGNEE_ID,
            taskStatus='in_progress',
            priority='high',
            episodeId=3,
            sceneId=5,
            keyword='SH010',
        ),
    )
    sql = _sql(statement)

    assert 'sg_task.project_id = 11' in sql
    assert 'sg_task.expected_start_time <' in sql
    assert 'sg_task.expected_end_time >' in sql
    assert 'sg_task.baseline_start_time <' in sql
    assert 'sg_task.baseline_end_time >' in sql
    assert "sg_task.task_kind = 'shot_video'" in sql
    assert 'sg_task.assignee_user_id = 7' in sql
    assert "sg_task.task_status = 'in_progress'" in sql
    assert "sg_task.priority = 'high'" in sql
    assert 'sg_shot.episode_id = 3' in sql
    assert 'sg_shot.scene_id = 5' in sql
    assert 'order by' in sql
    assert 'sg_scene.sort_order' in sql
    assert 'sg_task.expected_start_time' in sql
    assert 'sg_task.task_id' in sql


def test_schedule_statement_can_filter_conflicts_and_baseline_delay_without_narrowing_overlap_scope() -> None:
    sql = _sql(
        ShotGridTaskScheduleDao.build_schedule_statement(
            PROJECT_ID,
            _query(onlyConflicts=True, onlyDelayed=True, targetKind='asset_item', assetType='Character'),
        )
    )

    assert "sg_task.task_kind = 'asset_image'" in sql
    assert "sg_asset.asset_type = 'character'" in sql
    assert 'sg_task.expected_end_time > sg_task.baseline_end_time' in sql
    assert 'exists (select schedule_overlap_task.task_id' in sql
    assert 'schedule_overlap_task.expected_start_time < sg_task.expected_end_time' in sql
    assert 'schedule_overlap_task.expected_end_time > sg_task.expected_start_time' in sql


def test_unscheduled_statement_only_returns_real_active_unfinished_tasks_with_valid_assignee() -> None:
    sql = _sql(ShotGridTaskScheduleDao.build_unscheduled_statement(PROJECT_ID, _query(groupBy='assignee')))

    assert 'sg_task.expected_start_time is null' in sql
    assert 'sg_task.expected_end_time is null' in sql
    assert "sg_task.task_status != 'completed'" in sql
    assert "schedule_assignee_member.member_status = 'active'" in sql
    assert "schedule_assignee_member.project_role = 'creator'" in sql
    assert "schedule_assignee.status = '0'" in sql
    assert "sg_shot.lifecycle_status = 'active'" in sql
    assert "sg_asset_item.lifecycle_status = 'active'" in sql
    assert "sg_asset.lifecycle_status = 'active'" in sql


def test_overlap_statement_uses_half_open_intervals_and_ignores_ui_filters() -> None:
    sql = _sql(
        ShotGridTaskScheduleDao.build_overlap_statement(
            project_id=PROJECT_ID,
            task_id=TASK_ID,
            assignee_user_id=ASSIGNEE_ID,
            start_time=datetime(2026, 9, 5, 9),
            end_time=datetime(2026, 9, 7, 18),
        )
    )

    assert 'schedule_overlap_task.project_id = 11' in sql
    assert 'schedule_overlap_task.assignee_user_id = 7' in sql
    assert 'schedule_overlap_task.task_id != 31' in sql
    assert "schedule_overlap_task.task_status != 'completed'" in sql
    assert "schedule_overlap_task.del_flag = '0'" in sql
    assert 'schedule_overlap_task.expected_start_time <' in sql
    assert 'schedule_overlap_task.expected_end_time >' in sql
    assert 'order by schedule_overlap_task.task_id' in sql
    assert 'keyword' not in sql
    assert 'priority' not in sql


def test_history_idempotency_and_lock_statements_keep_stable_scope() -> None:
    history_sql = _sql(ShotGridTaskScheduleDao.build_history_statement(TASK_ID))
    idempotency_sql = _sql(
        ShotGridTaskScheduleDao.build_idempotency_statement(TASK_ID, ASSIGNEE_ID, 'schedule-command-1')
    )
    project_lock_sql = _sql(ShotGridTaskScheduleDao.build_project_lock_statement(PROJECT_ID))
    task_lock_sql = _sql(ShotGridTaskScheduleDao.build_task_lock_statement(PROJECT_ID, TASK_ID))

    assert 'sg_task_schedule_change.task_id = 31' in history_sql
    assert (
        'order by sg_task_schedule_change.create_time desc, sg_task_schedule_change.schedule_change_id desc'
        in history_sql
    )
    assert 'sg_task_schedule_change.operator_user_id = 7' in idempotency_sql
    assert "sg_task_schedule_change.idempotency_key = 'schedule-command-1'" in idempotency_sql
    assert 'for update' in project_lock_sql
    assert 'for update' in task_lock_sql


@pytest.mark.asyncio
async def test_add_schedule_change_flushes_without_committing() -> None:
    db = AsyncMock()
    db.add = Mock()
    change = ShotGridTaskScheduleChange(
        project_id=PROJECT_ID,
        task_id=TASK_ID,
        operator_user_id=ASSIGNEE_ID,
        to_start_time=datetime(2026, 9, 1),
        to_end_time=datetime(2026, 9, 2),
        change_type='initial',
        operation_source='dialog',
        change_reason='首次排期',
        overlap_acknowledged=False,
        overlap_task_ids=[],
        task_lock_version_before=0,
        task_lock_version_after=1,
        idempotency_key='schedule-command-1',
        request_hash='a' * 64,
        result_snapshot={},
        create_by='admin',
    )

    result = await ShotGridTaskScheduleDao.add_schedule_change(db, change)

    assert result is change
    db.add.assert_called_once_with(change)
    db.flush.assert_awaited_once()
    assert not hasattr(db, 'commit') or db.commit.await_count == 0


@pytest.mark.asyncio
async def test_find_overlap_task_ids_returns_stable_integer_list() -> None:
    db = AsyncMock()
    db.scalars.return_value = [9, 12]

    result = await ShotGridTaskScheduleDao.find_overlap_task_ids(
        db,
        project_id=PROJECT_ID,
        task_id=TASK_ID,
        assignee_user_id=ASSIGNEE_ID,
        start_time=datetime(2026, 9, 5, 9),
        end_time=datetime(2026, 9, 7, 18),
    )

    assert result == [9, 12]
    statement = db.scalars.await_args.args[0]
    assert 'order by schedule_overlap_task.task_id' in _sql(statement)

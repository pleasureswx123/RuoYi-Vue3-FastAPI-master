import os

import pytest
from pydantic import ValidationError
from sqlalchemy import DateTime, Integer, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from module_shot_grid.dao.schedule_phase import production_period_conditions
from module_shot_grid.dao.task_dao import ShotGridTaskDao
from module_shot_grid.entity.vo.task_vo import (
    ShotGridMineTaskListQueryModel,
    ShotGridTaskListQueryModel,
)
from tests.module_shot_grid.test_asset_manager_start_pg import isolated_pg_url  # noqa: F401


def _compile(statement: object) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={'literal_binds': True},
        )
    ).lower()


def test_project_task_statement_applies_project_filters_and_stable_order() -> None:
    statement = ShotGridTaskDao.build_task_statement(
        ShotGridTaskListQueryModel(
            assigneeUserId=8,
            taskKind='shot_video',
            taskStatus='in_progress',
            priority='high',
            orderByColumn='dueDate',
            isAsc='ascending',
        ),
        project_id=10,
    )
    sql = _compile(statement)

    assert 'sg_task.project_id = 10' in sql
    assert 'sg_task.assignee_user_id = 8' in sql
    assert "sg_task.task_kind = 'shot_video'" in sql
    assert "sg_task.task_status = 'in_progress'" in sql
    assert "sg_task.priority = 'high'" in sql
    assert 'sg_task.baseline_start_time' in sql
    assert 'sg_task.baseline_end_time' in sql
    assert 'order by sg_task.due_date asc nulls last, sg_task.task_id desc' in sql


def test_global_mine_statement_forces_current_assignee_and_active_membership() -> None:
    statement = ShotGridTaskDao.build_task_statement(
        ShotGridMineTaskListQueryModel(pageNum=1, pageSize=20),
        mine_user_id=9,
    )
    sql = _compile(statement)

    assert 'sg_task.assignee_user_id = 9' in sql
    assert 'task_assignee_member.user_id = 9' in sql
    assert "task_assignee_member.member_status = 'active'" in sql
    assert 'sg_task.project_id =' not in sql
    assert 'row_number() over (partition by sg_version.task_id' in sql
    assert "sg_version_submission.submission_status != 'committed'" in sql


def test_project_mine_scope_requires_server_supplied_actor_scope() -> None:
    query = ShotGridTaskListQueryModel(scope='mine')

    try:
        ShotGridTaskDao.build_task_statement(query, project_id=10)
    except ValueError as exc:
        assert str(exc) == 'scope=mine 必须由服务端提供当前用户范围'
    else:
        raise AssertionError('scope=mine 未强制服务端注入当前用户范围')


def test_mine_tasks_sort_by_numeric_shot_hierarchy() -> None:
    sql = _compile(
        ShotGridTaskDao.build_task_statement(
            ShotGridMineTaskListQueryModel(orderByColumn='shotNo', isAsc='ascending'), mine_user_id=8
        )
    )
    assert 'sg_task.assignee_user_id = 8' in sql
    assert (
        'order by sg_task.project_id asc, sg_episode.episode_no asc nulls last, sg_scene.scene_no asc nulls last, sg_shot.shot_no asc nulls last, sg_task.task_id asc'
        in sql
    )


def test_workbench_filters_unfinished_before_paging_without_expanding_scope() -> None:
    sql = _compile(
        ShotGridTaskDao.build_task_statement(
            ShotGridMineTaskListQueryModel(unfinishedOnly=True, orderByColumn='workbench'), mine_user_id=9
        )
    )
    assert "sg_task.task_status != 'completed'" in sql
    assert 'sg_task.assignee_user_id = 9' in sql
    assert "task_assignee_member.member_status = 'active'" in sql
    order = sql.rsplit('order by ', 1)[1]
    assert order.index("'revision'") < order.index("'in_progress'") < order.index("'pending_review'")
    assert (
        'coalesce(sg_task.expected_end_time, cast(sg_task.due_date as timestamp without time zone)) asc nulls last'
        in order
    )
    assert order.endswith('sg_task.task_id asc')


def test_unfinished_filter_is_optional_and_intersects_explicit_status() -> None:
    sql = _compile(ShotGridTaskDao.build_task_statement(ShotGridMineTaskListQueryModel(), mine_user_id=9))
    assert "sg_task.task_status != 'completed'" not in sql
    sql = _compile(
        ShotGridTaskDao.build_task_statement(
            ShotGridMineTaskListQueryModel(unfinishedOnly=True, taskStatus='completed'), mine_user_id=9
        )
    )
    assert "sg_task.task_status != 'completed'" in sql
    assert "sg_task.task_status = 'completed'" in sql


def test_schedule_phases_filter_before_pagination_without_mutating_task_status() -> None:
    for phase in ('pending_schedule', 'not_started'):
        sql = _compile(
            ShotGridTaskDao.build_task_statement(
                ShotGridTaskListQueryModel(taskStatus=phase),
                project_id=10,
            )
        )
        assert 'sg_task.expected_start_time is null' in sql
        assert 'sg_task.expected_end_time is null' in sql
        assert f"else sg_task.task_status end = '{phase}'" in sql


def test_workspace_filters_intersect_mine_scope_and_planned_period() -> None:
    query = ShotGridMineTaskListQueryModel(
        projectId=10, assigneeUserId=8, productionFrom='2026-10-01', productionTo='2026-10-31'
    )
    sql = _compile(ShotGridTaskDao.build_task_statement(query, mine_user_id=9))
    assert 'sg_task.project_id = 10' in sql
    assert 'sg_task.assignee_user_id = 8' in sql
    assert 'sg_task.assignee_user_id = 9' in sql
    assert 'task_assignee_member.user_id = 9' in sql
    assert "sg_task.expected_end_time >= '2026-10-01 00:00:00'" in sql
    assert "sg_task.expected_start_time <= '2026-10-31 23:59:59.999999'" in sql
    assert 'sg_task.expected_start_time is not null' in sql


def test_planned_period_rejects_reversed_dates() -> None:

    with pytest.raises(ValidationError, match='制作周期开始日期不能晚于结束日期'):
        ShotGridMineTaskListQueryModel(productionFrom='2026-11-01', productionTo='2026-10-01')


async def _verify_period_on_postgresql(async_engine: AsyncEngine) -> None:

    tasks = (
        text("""SELECT * FROM (VALUES
        (1, TIMESTAMP '2026-09-30', TIMESTAMP '2026-10-01'),
        (2, TIMESTAMP '2026-10-31 23:59:59', TIMESTAMP '2026-11-01'),
        (3, TIMESTAMP '2026-09-01', TIMESTAMP '2026-09-30 23:59:59'),
        (4, NULL::timestamp, NULL::timestamp),
        (5, TIMESTAMP '2026-09-01', TIMESTAMP '2026-11-30'),
        (6, TIMESTAMP '2026-11-01', TIMESTAMP '2026-11-30')
    ) AS fixture(task_id, expected_start_time, expected_end_time)""")
        .columns(task_id=Integer, expected_start_time=DateTime, expected_end_time=DateTime)
        .subquery('task')
    )
    query = ShotGridMineTaskListQueryModel(productionFrom='2026-10-01', productionTo='2026-10-31')
    statement = select(tasks.c.task_id).where(*production_period_conditions(tasks.c, query)).order_by(tasks.c.task_id)
    async with async_engine.connect() as connection:
        assert list((await connection.execute(statement)).scalars()) == [1, 2, 5]


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='显式开启才创建随机隔离 PostgreSQL')
async def test_period_boundaries_on_real_postgresql(isolated_pg_url: URL) -> None:  # noqa: F811
    # 不复用应用全局连接，确保不会因本地环境配置而连接原业务库。
    engine = create_async_engine(isolated_pg_url)
    try:
        await _verify_period_on_postgresql(engine)
    finally:
        await engine.dispose()

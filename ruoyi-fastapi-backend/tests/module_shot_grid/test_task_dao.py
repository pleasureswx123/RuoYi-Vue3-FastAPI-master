from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.task_dao import ShotGridTaskDao
from module_shot_grid.entity.vo.task_vo import (
    ShotGridMineTaskListQueryModel,
    ShotGridTaskListQueryModel,
)


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

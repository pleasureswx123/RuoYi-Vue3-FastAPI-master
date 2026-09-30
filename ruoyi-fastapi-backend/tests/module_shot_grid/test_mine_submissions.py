from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.review_dao import ShotGridReviewDao
from module_shot_grid.entity.vo.review_vo import (
    ShotGridMineReviewQueryModel,
    ShotGridMineVersionQueryModel,
    ShotGridReviewListQueryModel,
)
from module_shot_grid.service.review_service import ShotGridReviewService

PAGE_NUMBER = 2
PAGE_SIZE = 10
TOTAL = 21
USER_ID = 7
REVIEW_ID = 87
FILE_COUNT = 4
PROJECT_ID = 13
SUBMITTER_ID = 23


def test_submission_date_range_and_length_validation() -> None:
    with pytest.raises(ValidationError):
        ShotGridMineVersionQueryModel(submittedFrom='2026-09-24', submittedTo='2026-09-23')
    with pytest.raises(ValidationError):
        ShotGridMineVersionQueryModel(taskKeyword='a' * 241)
    query = ShotGridMineVersionQueryModel(submittedFrom='2026-09-23', submittedTo='2026-09-23', pageNum=2)
    assert query.page_num == PAGE_NUMBER


@pytest.mark.asyncio
async def test_mine_submissions_filters_before_count_and_page_preserving_owner_scope() -> None:
    query = ShotGridMineVersionQueryModel(
        projectId=13,
        projectKeyword='罗刹',
        taskKeyword='0010',
        versionStatus='rejected',
        submittedFrom='2026-09-01',
        submittedTo='2026-09-23',
        pageNum=2,
        pageSize=10,
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one=Mock(return_value=21)),
                SimpleNamespace(mappings=Mock(return_value=[])),
            ]
        )
    )
    rows, total = await ShotGridReviewDao.get_recent_mine_versions(db, 7, query)
    assert rows == [] and total == TOTAL
    count, page = [call.args[0].compile(dialect=postgresql.dialect()) for call in db.execute.await_args_list]
    for statement in (count, page):
        sql = str(statement)
        assert 'sg_version.project_id =' in sql
        assert PROJECT_ID in statement.params.values()
        assert 'sg_version.submitted_by =' in sql
        assert 'sg_project_member.user_id =' in sql
        assert 'sg_project_member.member_status =' in sql
        assert 'sg_project.del_flag =' in sql
        assert 'sg_task.del_flag =' in sql
        assert 'sg_task.assignee_user_id' not in sql
        assert 'sg_project.project_status !=' not in sql
        assert '%罗刹%' in statement.params.values()
        assert '%0010%' in statement.params.values()
        assert 'rejected' in statement.params.values()
        assert datetime(2026, 9, 23, 23, 59, 59, 999999) in statement.params.values()
        assert USER_ID in statement.params.values()
    assert 'LIMIT' not in str(count)
    assert page.params['param_1'] == PAGE_SIZE
    assert page.params['param_2'] == PAGE_SIZE
    assert 'sg_version.submitted_time DESC, sg_version.version_id DESC' in str(page)
    assert 'auto_review_list_id' in str(page)


def test_submission_row_preserves_project_task_and_actual_review_id() -> None:
    item = ShotGridReviewService._version_list_item(
        {
            'version_id': 29,
            'project_id': 13,
            'task_id': 69,
            'version_no': 1,
            'version_status': 'rejected',
            'changelog': '首版',
            'submitted_by': 7,
            'submitted_time': datetime(2026, 9, 23),
            'generated_at_ms': 1,
            'lock_version': 0,
            'project_name': '罗刹夫人',
            'project_code': 'LCFR',
            'task_name': '镜头视频制作',
            'auto_review_list_id': 87,
            'candidate_count': 4,
        }
    ).model_dump(by_alias=True)
    assert item['autoReviewListId'] == REVIEW_ID
    assert item['taskName'] == '镜头视频制作'
    assert item['versionNumber'] == 'V001'
    assert item['candidateCount'] == FILE_COUNT


@pytest.mark.asyncio
@pytest.mark.parametrize('mine', [True, False])
@pytest.mark.parametrize('shot_order', [False, True])
async def test_task_group_paging_keeps_scope_and_returns_unpaged_children(mine: bool, shot_order: bool) -> None:
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one=Mock(return_value=2)),
                SimpleNamespace(mappings=Mock(return_value=[])),
            ]
        )
    )
    order = {'orderByColumn': 'shotNo', 'isAsc': 'ascending'} if shot_order else {}
    if mine:
        await ShotGridReviewDao.get_recent_mine_versions(
            db,
            USER_ID,
            ShotGridMineVersionQueryModel(groupByTask=True, pageNum=2, pageSize=10, versionStatus='rejected', **order),
        )
    else:
        await ShotGridReviewDao.get_review_lists(
            db,
            13,
            ShotGridReviewListQueryModel(groupByTask=True, pageNum=2, pageSize=10, reviewStatus='active', **order),
        )
    count, page = [call.args[0] for call in db.execute.await_args_list]
    count_sql, page_sql = [
        str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))
        for stmt in (count, page)
    ]
    assert 'GROUP BY' in count_sql
    assert 'LIMIT' not in count_sql
    if shot_order:
        assert (
            'sg_episode.episode_no ASC NULLS LAST, sg_scene.scene_no ASC NULLS LAST, sg_shot.shot_no ASC NULLS LAST'
            in page_sql
        )
        assert 'min(anon_1.shot_order_1) ASC NULLS LAST' in page_sql
    assert page._limit_clause is None
    assert 'LIMIT 10 OFFSET 10' in page_sql
    if mine:
        assert 'sg_version.submitted_by = 7' in count_sql and 'sg_version.submitted_by = 7' in page_sql
        assert 'sg_project_member.member_status' in page_sql
        assert "sg_version.version_status = 'rejected'" in count_sql
    else:
        assert 'sg_review_list.project_id = 13' in count_sql and 'sg_review_list.project_id = 13' in page_sql
        assert "sg_review_list.review_status = 'active'" in count_sql
        assert 'coalesce' in count_sql and '.review_list_id)' in count_sql


@pytest.mark.asyncio
async def test_submission_project_options_keep_history_scope_and_archived_projects() -> None:
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(mappings=Mock(return_value=[]))))
    assert await ShotGridReviewDao.get_mine_submission_projects(db, USER_ID) == []
    statement = db.execute.await_args.args[0].compile(
        dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}
    )
    sql = str(statement)
    assert 'SELECT DISTINCT' in sql
    assert 'sg_version.submitted_by = 7' in sql
    assert 'sg_project_member.user_id = 7' in sql
    assert "sg_project_member.member_status = 'active'" in sql
    assert "sg_project.del_flag = '0'" in sql
    assert "sg_task.del_flag = '0'" in sql
    assert 'assignee_user_id' not in sql
    assert 'project_status =' not in sql


def test_submission_project_filter_rejects_invalid_ids() -> None:
    for value in [0, -1, 9_223_372_036_854_775_808]:
        with pytest.raises(ValidationError):
            ShotGridMineVersionQueryModel(projectId=value)


@pytest.mark.asyncio
@pytest.mark.parametrize('has_all_scope', [False, True])
async def test_review_queue_project_filter_preserves_scope_and_pagination(has_all_scope: bool) -> None:
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one=Mock(return_value=21)),
                SimpleNamespace(mappings=Mock(return_value=[])),
            ]
        )
    )
    query = ShotGridMineReviewQueryModel(
        projectId=13,
        projectKeyword=' 罗刹 ',
        keyword='首版',
        reviewMode='auto_single',
        pageNum=2,
        pageSize=10,
        isAsc='ascending',
    )
    await ShotGridReviewDao.get_mine_review_lists(db, USER_ID, query, has_all_scope)
    count, page = [call.args[0].compile(dialect=postgresql.dialect()) for call in db.execute.await_args_list]
    for statement in (count, page):
        sql = str(statement)
        assert 'sg_project.project_name ILIKE' in sql
        assert 'sg_project.project_code ILIKE' in sql
        assert PROJECT_ID in statement.params.values()
        assert 'sg_review_list.project_id =' in sql
        assert '%罗刹%' in statement.params.values()
        assert '%首版%' in statement.params.values()
        assert 'auto_single' in statement.params.values()
        assert 'active' in statement.params.values()
        assert 'archived' in statement.params.values()
        assert 'sg_review_list.del_flag =' in sql
        assert 'sg_project.del_flag =' in sql
        if not has_all_scope:
            assert 'sg_project_member.user_id =' in sql
            assert USER_ID in statement.params.values()
            assert 'director' in statement.params.values()
            assert 'sg_project_member.member_status =' in sql
        else:
            assert 'sg_project_member' not in sql
    assert 'OFFSET' not in str(count)
    page_query = db.execute.await_args_list[1].args[0]
    assert page_query._limit_clause.value == PAGE_SIZE
    assert page_query._offset_clause.value == PAGE_SIZE

    assert 'sg_review_list.create_time ASC, sg_review_list.review_list_id ASC' in str(page)


@pytest.mark.asyncio
@pytest.mark.parametrize('has_all_scope', [False, True])
async def test_review_project_options_use_same_active_director_scope(has_all_scope: bool) -> None:
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(mappings=Mock(return_value=[]))))
    await ShotGridReviewDao.get_mine_review_projects(db, USER_ID, has_all_scope)
    statement = db.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    sql = str(statement)
    assert 'SELECT DISTINCT' in sql
    assert 'LIMIT' not in sql
    assert 'active' in statement.params.values()
    assert 'archived' in statement.params.values()
    assert 'sg_review_list.del_flag =' in sql
    assert 'sg_project.del_flag =' in sql
    if not has_all_scope:
        assert USER_ID in statement.params.values()
        assert 'director' in statement.params.values()
        assert 'sg_project_member.member_status =' in sql
    else:
        assert 'sg_project_member' not in sql


@pytest.mark.asyncio
@pytest.mark.parametrize('order_column', ['shotNo', 'submittedTime'])
async def test_review_content_filters_and_stable_sort_before_pagination(order_column: str) -> None:
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one=Mock(return_value=21)),
                SimpleNamespace(mappings=Mock(return_value=[])),
            ]
        )
    )
    query = ShotGridMineReviewQueryModel(
        keyword='0010',
        taskKind='shot_video',
        submitterKeyword='制作人甲',
        submittedFrom='2026-09-01',
        submittedTo='2026-09-29',
        orderByColumn=order_column,
        isAsc='ascending',
        pageNum=2,
        pageSize=10,
    )
    await ShotGridReviewDao.get_mine_review_lists(db, USER_ID, query, False)
    count, page = [call.args[0].compile(dialect=postgresql.dialect()) for call in db.execute.await_args_list]
    for statement in (count, page):
        sql = str(statement)
        assert 'EXISTS' in sql
        assert 'sg_review_list_version AS' in sql
        assert 'sg_task_1.task_kind =' in sql
        assert 'sg_task_1.task_name ILIKE' in sql
        assert 'CAST(sg_shot_1.shot_no AS VARCHAR)' in sql
        assert 'sys_user_1.user_name ILIKE' in sql
        assert 'sys_user_1.nick_name ILIKE' in sql
        assert 'sg_version_1.project_id = sg_review_list.project_id' in sql
        assert 'sg_review_list_version_1.review_list_id = sg_review_list.review_list_id' in sql
        assert '%0010%' in statement.params.values()
        assert '%制作人甲%' in statement.params.values()
        assert datetime(2026, 9, 29, 23, 59, 59, 999999) in statement.params.values()
        assert 'director' in statement.params.values()
    if order_column == 'shotNo':
        assert 'sg_episode.episode_no ASC NULLS LAST' in str(page)
        assert 'sg_scene.scene_no ASC NULLS LAST' in str(page)
        assert 'sg_shot.shot_no ASC NULLS LAST' in str(page)
        assert 'CASE WHEN' in str(page)
        assert 'sg_review_list.review_list_id ASC' in str(page)
    else:
        assert 'coalesce(sg_version.submitted_time, sg_review_list.create_time) ASC' in str(page)
    assert db.execute.await_args_list[1].args[0]._offset_clause.value == PAGE_SIZE


def test_review_queue_date_range_validation() -> None:
    with pytest.raises(ValidationError):
        ShotGridMineReviewQueryModel(submittedFrom='2026-09-29', submittedTo='2026-09-01')
    with pytest.raises(ValidationError):
        ShotGridMineReviewQueryModel(taskKind='unsupported')


@pytest.mark.asyncio
@pytest.mark.parametrize('has_all_scope', [False, True])
async def test_review_producers_come_from_scoped_active_project_members(has_all_scope: bool) -> None:
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(mappings=Mock(return_value=[]))))
    await ShotGridReviewDao.get_mine_review_producers(db, USER_ID, has_all_scope, PROJECT_ID)
    statement = db.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    sql = str(statement)
    assert 'SELECT DISTINCT sys_user.user_id' in sql
    assert 'sg_project_member.project_id IN (SELECT' in sql
    assert 'sys_user.del_flag =' in sql
    assert 'creator' in statement.params.values()
    assert PROJECT_ID in statement.params.values()
    assert 'active' in statement.params.values()
    assert 'archived' in statement.params.values()
    if not has_all_scope:
        assert 'director' in statement.params.values()
        assert USER_ID in statement.params.values()
        assert 'JOIN sg_project_member ON sg_project_member.project_id = sg_review_list.project_id' in sql
    assert 'LIMIT' not in sql


@pytest.mark.asyncio
async def test_review_filter_by_submitter_id_uses_version_owner() -> None:
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one=Mock(return_value=0)),
                SimpleNamespace(mappings=Mock(return_value=[])),
            ]
        )
    )
    await ShotGridReviewDao.get_mine_review_lists(db, USER_ID, ShotGridMineReviewQueryModel(submittedBy=SUBMITTER_ID), False)
    for call in db.execute.await_args_list:
        statement = call.args[0].compile(dialect=postgresql.dialect())
        assert 'sg_version_1.submitted_by =' in str(statement)
        assert 'assignee_user_id' not in str(statement)
        assert SUBMITTER_ID in statement.params.values()

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.review_dao import ShotGridReviewDao
from module_shot_grid.entity.vo.review_vo import ShotGridMineVersionQueryModel, ShotGridReviewListQueryModel
from module_shot_grid.service.review_service import ShotGridReviewService

PAGE_NUMBER = 2
PAGE_SIZE = 10
TOTAL = 21
USER_ID = 7
REVIEW_ID = 87
FILE_COUNT = 4


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
            db, 13, ShotGridReviewListQueryModel(groupByTask=True, pageNum=2, pageSize=10, reviewStatus='active', **order)
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

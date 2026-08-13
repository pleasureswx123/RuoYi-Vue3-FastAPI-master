from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from module_admin.entity.do.user_do import SysUser
from module_shot_grid.dao.project_option_dao import ShotGridProjectOptionDao
from module_shot_grid.entity.vo.project_option_vo import (
    ShotGridAssetAssigneeOptionQueryModel,
    ShotGridMemberCandidateQueryModel,
    ShotGridShotAssigneeOptionQueryModel,
)

VISIBLE_USER_ID = 77


def _postgresql_sql(statement: object) -> str:
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))


@pytest.mark.asyncio
async def test_member_candidate_count_and_rows_apply_user_data_scope() -> None:
    page_result = MagicMock()
    page_result.mappings.return_value = []
    db = AsyncMock()
    db.scalar.return_value = 0
    db.execute.return_value = page_result
    data_scope_sql = SysUser.user_id == VISIBLE_USER_ID

    await ShotGridProjectOptionDao.get_member_candidate_page(
        db,
        ShotGridMemberCandidateQueryModel(pageNum=1, pageSize=20),
        data_scope_sql,
    )

    count_sql = _postgresql_sql(db.scalar.await_args.args[0])
    rows_sql = _postgresql_sql(db.execute.await_args.args[0])
    assert 'sys_user.user_id = 77' in count_sql
    assert 'sys_user.user_id = 77' in rows_sql


@pytest.mark.asyncio
async def test_member_candidates_can_be_limited_to_one_department() -> None:
    page_result = MagicMock()
    page_result.mappings.return_value = []
    db = AsyncMock()
    db.scalar.return_value = 0
    db.execute.return_value = page_result

    await ShotGridProjectOptionDao.get_member_candidate_page(
        db,
        ShotGridMemberCandidateQueryModel(pageNum=1, pageSize=20, deptId=100),
        SysUser.user_id > 0,
    )

    count_sql = _postgresql_sql(db.scalar.await_args.args[0])
    rows_sql = _postgresql_sql(db.execute.await_args.args[0])
    assert 'sys_user.dept_id = 100' in count_sql
    assert 'sys_user.dept_id = 100' in rows_sql


@pytest.mark.asyncio
async def test_shot_assignee_options_apply_membership_account_and_producer_guards() -> None:
    page_result = MagicMock()
    page_result.mappings.return_value = []
    db = AsyncMock()
    db.scalar.return_value = 0
    db.execute.return_value = page_result

    await ShotGridProjectOptionDao.get_shot_assignee_option_page(
        db,
        1001,
        ShotGridShotAssigneeOptionQueryModel(pageNum=2, pageSize=10, keyword='YJF'),
    )

    count_sql = _postgresql_sql(db.scalar.await_args.args[0])
    rows_sql = _postgresql_sql(db.execute.await_args.args[0])
    for sql in (count_sql, rows_sql):
        assert 'sg_project_member.project_id = 1001' in sql
        assert "sg_project_member.member_status = 'active'" in sql
        assert 'sg_project_member.producer_code IS NOT NULL' in sql
        assert "sys_user.status = '0'" in sql
        assert "sys_user.del_flag = '0'" in sql
        assert "sg_project_member.producer_code ILIKE '%%YJF%%'" in sql
    assert 'ORDER BY sys_user.nick_name, sys_user.user_name, sys_user.user_id' in rows_sql
    assert 'LIMIT 10 OFFSET 10' in rows_sql


@pytest.mark.asyncio
async def test_asset_assignee_options_reuse_the_same_safe_project_member_guards() -> None:
    page_result = MagicMock()
    page_result.mappings.return_value = []
    db = AsyncMock()
    db.scalar.return_value = 0
    db.execute.return_value = page_result

    await ShotGridProjectOptionDao.get_asset_assignee_option_page(
        db,
        1001,
        ShotGridAssetAssigneeOptionQueryModel(pageNum=1, pageSize=20, keyword='creator'),
    )

    rows_sql = _postgresql_sql(db.execute.await_args.args[0])
    assert 'sg_project_member.project_id = 1001' in rows_sql
    assert "sg_project_member.member_status = 'active'" in rows_sql
    assert 'sg_project_member.producer_code IS NOT NULL' in rows_sql
    assert "sys_user.status = '0'" in rows_sql
    assert "sys_user.del_flag = '0'" in rows_sql

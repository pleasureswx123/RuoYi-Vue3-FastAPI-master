from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from module_admin.entity.do.user_do import SysUser
from module_shot_grid.dao.project_dao import ShotGridProjectDao
from module_shot_grid.dao.project_member_dao import ShotGridProjectMemberDao
from module_shot_grid.entity.vo.project_vo import ShotGridProjectListQueryModel

VISIBLE_USER_ID = 2


def _postgresql_sql(statement: object) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={'literal_binds': True},
        )
    )


@pytest.mark.asyncio
async def test_member_access_query_only_recognizes_active_membership() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = result

    await ShotGridProjectMemberDao.get_member(db, 10, 2)

    sql = _postgresql_sql(db.execute.await_args.args[0])
    assert "sg_project_member.member_status = 'active'" in sql


@pytest.mark.asyncio
async def test_active_member_candidate_validation_applies_user_data_scope() -> None:
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db = AsyncMock()
    db.execute.return_value = result

    await ShotGridProjectMemberDao.get_active_users(db, {VISIBLE_USER_ID, 3}, SysUser.user_id == VISIBLE_USER_ID)

    sql = _postgresql_sql(db.execute.await_args.args[0])
    assert 'sys_user.user_id = 2' in sql


@pytest.mark.asyncio
async def test_default_project_scope_joins_only_active_membership() -> None:
    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    rows_result = MagicMock()
    rows_result.mappings.return_value.all.return_value = []
    db = AsyncMock()
    db.execute.side_effect = [count_result, rows_result]

    await ShotGridProjectDao.get_project_page(
        db,
        ShotGridProjectListQueryModel(),
        current_user_id=2,
        include_all=False,
    )

    page_sql = _postgresql_sql(db.execute.await_args_list[1].args[0])
    assert "current_project_member.member_status = 'active'" in page_sql


@pytest.mark.asyncio
async def test_producer_code_conflict_only_counts_active_membership() -> None:
    result = MagicMock()
    result.scalar_one.return_value = 0
    db = AsyncMock()
    db.execute.return_value = result

    exists = await ShotGridProjectMemberDao.producer_code_exists(db, 10, 'YJF')

    assert exists is False
    sql = _postgresql_sql(db.execute.await_args.args[0])
    assert "sg_project_member.member_status = 'active'" in sql

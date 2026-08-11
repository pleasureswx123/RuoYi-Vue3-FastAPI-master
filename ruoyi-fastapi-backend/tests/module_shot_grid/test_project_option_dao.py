from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from module_admin.entity.do.user_do import SysUser
from module_shot_grid.dao.project_option_dao import ShotGridProjectOptionDao
from module_shot_grid.entity.vo.project_option_vo import ShotGridMemberCandidateQueryModel

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

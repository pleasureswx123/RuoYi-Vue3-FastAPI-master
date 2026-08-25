from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.file_center_dao import ShotGridFileCenterDao
from module_shot_grid.entity.vo.file_center_vo import ShotGridProjectFileQueryModel


@pytest.mark.asyncio
async def test_file_center_query_excludes_internal_derived_files() -> None:
    db = AsyncMock()
    db.scalar.return_value = 0
    execute_result = MagicMock()
    execute_result.mappings.return_value.all.return_value = []
    db.execute.return_value = execute_result

    await ShotGridFileCenterDao.get_project_files(db, 8, ShotGridProjectFileQueryModel())

    count_statement = db.scalar.await_args.args[0]
    sql = str(
        count_statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={'literal_binds': True},
        )
    )
    assert "sg_version_file.file_role NOT IN ('thumbnail', 'proxy_media')" in sql


@pytest.mark.parametrize('file_role', ['thumbnail', 'proxy_media'])
def test_file_center_rejects_internal_derived_role_filter(file_role: str) -> None:
    with pytest.raises(ValidationError):
        ShotGridProjectFileQueryModel(fileRole=file_role)

from collections.abc import Iterator
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.project_purge_dao import ShotGridProjectPurgeDao


class _ScalarRows:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def __iter__(self) -> Iterator[object]:
        return iter(self._values)

    def all(self) -> list[object]:
        return self._values


def _sql(statement: object) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={'literal_binds': True},
        )
    )


@pytest.mark.asyncio
async def test_prepare_exclusive_files_removes_every_candidate_temporary_reference_before_ownership_check() -> None:
    db = AsyncMock()
    db.scalars.side_effect = [
        _ScalarRows([101]),
        _ScalarRows([201]),
        _ScalarRows(['file-a', 'file-b']),
        _ScalarRows([]),
        _ScalarRows([]),
        _ScalarRows([]),
        _ScalarRows([]),
        _ScalarRows(
            [
                SimpleNamespace(
                    file_id='file-a', storage_type='local', access_type='private', storage_key='private/file-a'
                ),
                SimpleNamespace(
                    file_id='file-b', storage_type='local', access_type='private', storage_key='private/file-b'
                ),
            ]
        ),
    ]

    result = await ShotGridProjectPurgeDao.prepare_exclusive_files(
        db,
        project_id=9,
        actor_name='admin',
        now=datetime(2026, 8, 26, 15, 0, 0),
    )

    statements = [_sql(call.args[0]) for call in db.execute.await_args_list]
    reference_deletes = [
        statement for statement in statements if statement.startswith('DELETE FROM sys_file_reference')
    ]
    expected_reference_delete_count = 2

    assert len(reference_deletes) == expected_reference_delete_count
    assert "business_type = 'shotgrid_version'" in reference_deletes[0]
    assert "business_type = 'shotgrid_version_submission'" in reference_deletes[1]
    assert "business_id IN ('201')" in reference_deletes[1]
    assert 'file_id IN (' in reference_deletes[1]
    assert "'file-a'" in reference_deletes[1]
    assert "'file-b'" in reference_deletes[1]
    assert [item['fileId'] for item in result] == ['file-a', 'file-b']

from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.version_submission_dao import ShotGridVersionSubmissionDao


class _EmptyMappingResult:
    def mappings(self) -> '_EmptyMappingResult':
        return self

    @staticmethod
    def first() -> None:
        return None


class _CaptureDb:
    def __init__(self) -> None:
        self.statement: Any = None

    async def execute(self, statement: Any) -> _EmptyMappingResult:
        self.statement = statement
        return _EmptyMappingResult()


@pytest.mark.asyncio
async def test_task_creation_context_compiles_for_postgresql_with_latest_directory_subquery() -> None:
    db = _CaptureDb()

    result = await ShotGridVersionSubmissionDao.get_task_creation_context(db, 1)  # type: ignore[arg-type]
    compiled = str(
        db.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={'literal_binds': True},
        )
    )

    assert result is None
    assert 'sg_storage_operation' in compiled
    assert 'ORDER BY sg_storage_operation.operation_id DESC' in compiled
    assert 'LIMIT 1' in compiled
    assert 'sg_task.task_kind' in compiled

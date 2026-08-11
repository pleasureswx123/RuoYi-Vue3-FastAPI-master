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


class _ScalarCaptureDb:
    def __init__(self, result: bool) -> None:
        self.statement: Any = None
        self.result = result

    async def scalar(self, statement: Any) -> bool:
        self.statement = statement
        return self.result


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


@pytest.mark.asyncio
async def test_current_submission_status_query_is_task_scoped_and_only_unresolved() -> None:
    db = _CaptureDb()

    result = await ShotGridVersionSubmissionDao.get_current_submission_status_row(db, 7)  # type: ignore[arg-type]
    compiled = str(
        db.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={'literal_binds': True},
        )
    )

    assert result is None
    assert 'sg_version_submission.task_id = 7' in compiled
    for status in ('pending', 'publishing', 'published', 'committing', 'failed'):
        assert status in compiled
    assert 'committed' not in compiled


@pytest.mark.asyncio
async def test_submit_preflight_unresolved_check_is_read_only_exists_query() -> None:
    db = _ScalarCaptureDb(True)

    result = await ShotGridVersionSubmissionDao.has_unresolved_submission(db, 7)  # type: ignore[arg-type]
    compiled = str(
        db.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={'literal_binds': True},
        )
    )

    assert result is True
    assert 'EXISTS' in compiled
    assert 'sg_version_submission.task_id = 7' in compiled
    for status in ('pending', 'publishing', 'published', 'committing', 'failed'):
        assert status in compiled
    assert 'FOR UPDATE' not in compiled

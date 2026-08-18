from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.import_batch_dao import ShotGridImportBatchDao

PREVIEW_VALID_ROWS = 2
COMMITTED_ROWS = 24


def test_mark_committed_expands_final_valid_rows_after_preview_correction() -> None:
    batch = SimpleNamespace(valid_rows=PREVIEW_VALID_ROWS)

    ShotGridImportBatchDao.mark_committed(
        batch,
        committed_rows=COMMITTED_ROWS,
        selection_hash='a' * 64,
        result_summary={'committedRows': COMMITTED_ROWS},
    )

    assert batch.batch_status == 'committed'
    assert batch.valid_rows == COMMITTED_ROWS
    assert batch.committed_rows == COMMITTED_ROWS


@pytest.mark.asyncio
async def test_mark_failed_writes_sql_null_for_jsonb_result_summary() -> None:
    statements: list[Any] = []

    class FakeDb:
        async def execute(self, statement: Any) -> None:
            statements.append(statement)

    await ShotGridImportBatchDao.mark_failed(
        FakeDb(),  # type: ignore[arg-type]
        project_id=1,
        batch_id=2,
        committed_by=3,
        idempotency_key='request-1',
        selection_hash='a' * 64,
        error_key='SG_IMPORT_HAS_ERRORS',
        error_message='导入失败',
    )

    compiled = str(statements[0].compile(dialect=postgresql.dialect()))
    assert 'result_summary=NULL' in compiled

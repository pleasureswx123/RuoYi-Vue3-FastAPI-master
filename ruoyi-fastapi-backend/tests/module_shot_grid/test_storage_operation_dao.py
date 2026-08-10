from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.storage_operation_dao import ShotGridStorageOperationDao
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageOperation

MAX_ATTEMPT_COUNT = 5


class _ScalarResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object:
        return self.value


class _EmptyMappingResult:
    def mappings(self) -> '_EmptyMappingResult':
        return self

    @staticmethod
    def one_or_none() -> None:
        return None


class _RowCountResult:
    rowcount = 1


def test_claim_statement_uses_postgresql_skip_locked_and_recovers_expired_processing() -> None:
    now = datetime(2026, 8, 10, 12, 0, 0)

    statement = ShotGridStorageOperationDao.build_claim_statement(now)
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))

    assert 'FOR UPDATE SKIP LOCKED' in sql
    assert "operation_status = 'pending'" in sql
    assert "operation_status = 'retry_wait'" in sql
    assert "operation_status = 'processing'" in sql
    assert 'lease_until <=' in sql
    assert 'attempt_count' not in str(statement.whereclause)


@pytest.mark.asyncio
async def test_execution_context_freezes_root_status_and_both_path_scopes() -> None:
    class FakeDb:
        statement: object | None = None

        async def execute(self, statement: object) -> _EmptyMappingResult:
            self.statement = statement
            return _EmptyMappingResult()

    db = FakeDb()

    await ShotGridStorageOperationDao.get_execution_context(db, 1)  # type: ignore[arg-type]

    selected_columns = {column.key for column in db.statement.selected_columns}  # type: ignore[union-attr]
    assert {
        'root_status',
        'root_del_flag',
        'configured_root_path',
        'root_path_snapshot',
        'project_relative_path',
        'project_path_snapshot',
        'target_relative_path',
    } <= selected_columns


@pytest.mark.asyncio
async def test_claim_increments_attempt_and_replaces_expired_lease_even_after_max_attempts() -> None:
    now = datetime(2026, 8, 10, 12, 0, 0)
    operation = SimpleNamespace(
        operation_status='processing',
        attempt_count=MAX_ATTEMPT_COUNT,
        next_retry_time=None,
        lease_owner='dead-worker',
        lease_until=now - timedelta(seconds=1),
        started_time=now - timedelta(minutes=10),
        completed_time=None,
        update_time=now - timedelta(minutes=10),
    )
    db = AsyncMock()
    db.execute.return_value = _ScalarResult(operation)

    claimed = await ShotGridStorageOperationDao.claim_next_operation(
        db,
        worker_id='worker-new',
        now=now,
        lease_until=now + timedelta(minutes=5),
    )

    assert claimed is operation
    assert operation.operation_status == 'processing'
    assert operation.attempt_count == MAX_ATTEMPT_COUNT + 1
    assert operation.lease_owner == 'worker-new'
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_lease_renewal_is_fenced_by_owner_and_attempt_count() -> None:
    class FakeDb:
        statement: object | None = None

        async def execute(self, statement: object) -> _RowCountResult:
            self.statement = statement
            return _RowCountResult()

    now = datetime(2026, 8, 10, 12, 0, 0)
    db = FakeDb()

    renewed = await ShotGridStorageOperationDao.renew_lease(
        db,  # type: ignore[arg-type]
        operation_id=1,
        worker_id='worker-1',
        expected_attempt_count=3,
        now=now,
        lease_until=now + timedelta(minutes=5),
    )

    sql = str(db.statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))  # type: ignore[union-attr]
    assert renewed
    assert "lease_owner = 'worker-1'" in sql
    assert 'attempt_count = 3' in sql
    assert 'lease_until >' in sql


@pytest.mark.asyncio
async def test_initialize_success_updates_operation_and_project_storage_atomically() -> None:
    now = datetime(2026, 8, 10, 12, 0, 0)
    operation = ShotGridStorageOperation(
        operation_id=1,
        project_id=10,
        operation_type='initialize_project',
        aggregate_type='project',
        aggregate_id=10,
        target_relative_path='AI影视短片\\罗刹夫人',
        operation_status='processing',
        idempotency_key='initialize:10',
        attempt_count=1,
        lease_owner='worker-1',
        lease_until=now + timedelta(minutes=5),
    )
    storage = ShotGridProjectStorage(
        project_id=10,
        storage_root_id=2,
        root_path_snapshot=r'\\server\share',
        project_type_dir_snapshot='AI影视短片',
        project_dir_name_snapshot='罗刹夫人',
        project_relative_path='AI影视短片\\罗刹夫人',
        project_path_snapshot=r'\\server\share\AI影视短片\罗刹夫人',
        project_path_key='path-key',
        storage_status='initializing',
        lock_version=0,
    )
    db = AsyncMock()
    db.execute.side_effect = [_ScalarResult(operation), _ScalarResult(storage)]

    updated = await ShotGridStorageOperationDao.mark_succeeded(
        db,
        operation_id=1,
        worker_id='worker-1',
        expected_attempt_count=1,
        now=now,
    )

    assert updated
    assert operation.operation_status == 'succeeded'
    assert operation.lease_owner is None
    assert operation.completed_time == now
    assert storage.storage_status == 'ready'
    assert storage.initialized_time == now
    assert storage.lock_version == 1
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_initialize_retry_records_safe_error_without_marking_storage_ready() -> None:
    now = datetime(2026, 8, 10, 12, 0, 0)
    retry_at = now + timedelta(seconds=15)
    operation = ShotGridStorageOperation(
        operation_id=1,
        project_id=10,
        operation_type='initialize_project',
        aggregate_type='project',
        aggregate_id=10,
        target_relative_path='AI影视短片\\罗刹夫人',
        operation_status='processing',
        idempotency_key='initialize:10',
        attempt_count=1,
        lease_owner='worker-1',
        lease_until=now + timedelta(minutes=5),
    )
    storage = ShotGridProjectStorage(
        project_id=10,
        storage_root_id=2,
        root_path_snapshot=r'\\server\share',
        project_type_dir_snapshot='AI影视短片',
        project_dir_name_snapshot='罗刹夫人',
        project_relative_path='AI影视短片\\罗刹夫人',
        project_path_snapshot=r'\\server\share\AI影视短片\罗刹夫人',
        project_path_key='path-key',
        storage_status='initializing',
        lock_version=0,
    )
    db = AsyncMock()
    db.execute.side_effect = [_ScalarResult(operation), _ScalarResult(storage)]

    updated = await ShotGridStorageOperationDao.mark_retry_wait(
        db,
        operation_id=1,
        worker_id='worker-1',
        expected_attempt_count=1,
        now=now,
        next_retry_time=retry_at,
        error_key='SG_STORAGE_ROOT_UNAVAILABLE',
        error_message='NAS 根目录暂时不可访问或不可写',
    )

    assert updated
    assert operation.operation_status == 'retry_wait'
    assert operation.next_retry_time == retry_at
    assert operation.lease_owner is None
    assert storage.storage_status == 'initializing'
    assert storage.last_error_key == 'SG_STORAGE_ROOT_UNAVAILABLE'
    assert storage.lock_version == 1


@pytest.mark.asyncio
async def test_success_only_keeps_errors_from_each_aggregate_latest_operation() -> None:
    class FakeDb:
        statement: object | None = None

        async def scalar(self, statement: object) -> int:
            self.statement = statement
            return 0

    db = FakeDb()
    operation = SimpleNamespace(project_id=10)

    has_errors = await ShotGridStorageOperationDao._has_other_unresolved_errors(
        db,  # type: ignore[arg-type]
        operation,
    )

    sql = str(db.statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))  # type: ignore[union-attr]
    assert has_errors is False
    assert 'max(sg_storage_operation.operation_id)' in sql
    assert 'GROUP BY sg_storage_operation.aggregate_type, sg_storage_operation.aggregate_id' in sql

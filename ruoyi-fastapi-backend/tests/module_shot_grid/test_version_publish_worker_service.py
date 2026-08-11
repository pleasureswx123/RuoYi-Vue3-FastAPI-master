import asyncio
import inspect
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from module_shot_grid.service.version_publish_path_adapter import VersionPublishResult
from module_shot_grid.service.version_publish_worker_service import (
    ShotGridVersionPublishWorkerService,
    _ClaimedSubmission,
)

SUBMISSION_ID = 11
ATTEMPT_COUNT = 2
NEXT_ATTEMPT_COUNT = 3
PUBLISHED_FILE_SIZE = 10


def _claimed(*, attempt_count: int = ATTEMPT_COUNT) -> _ClaimedSubmission:
    return _ClaimedSubmission(
        submission_id=SUBMISSION_ID,
        attempt_count=attempt_count,
        lease_owner='leader:claim',
        execution_status='committing',
        temporary_relative_path=f'VIDEO\\EP01\\S001\\.sgtmp-11-a{attempt_count}-old.part',
    )


def test_scheduler_wrapper_signature_matches_leader_job_contract() -> None:
    parameters = inspect.signature(ShotGridVersionPublishWorkerService.run_scheduled_batch).parameters

    assert {
        'db',
        'worker_id',
        'max_operations',
        'leader_predicate',
        'lease_seconds',
        'max_attempts',
        'retry_delays_seconds',
        'operation_timeout_seconds',
        'heartbeat_seconds',
    }.issubset(parameters)


@pytest.mark.asyncio
async def test_scheduler_cancellation_waits_for_publish_guardian_to_drain() -> None:
    db = AsyncMock()
    io_started = asyncio.Event()
    allow_finish = asyncio.Event()

    async def controlled_publish(_context: object) -> VersionPublishResult:
        io_started.set()
        await allow_finish.wait()
        return VersionPublishResult(sha256='a' * 64, file_size=PUBLISHED_FILE_SIZE, reused_target=False)

    adapter = SimpleNamespace(publish=controlled_publish)
    guardian = asyncio.create_task(
        ShotGridVersionPublishWorkerService._execute_with_heartbeat(
            db,
            adapter=adapter,  # type: ignore[arg-type]
            context=SimpleNamespace(),  # type: ignore[arg-type]
            claimed=_claimed(),
            lease_seconds=10,
            heartbeat_seconds=5,
            operation_timeout_seconds=5,
        )
    )
    await io_started.wait()

    guardian.cancel()
    await asyncio.sleep(0)
    assert not guardian.done()
    allow_finish.set()
    result, soft_timeout = await guardian

    assert result.file_size == PUBLISHED_FILE_SIZE
    assert not soft_timeout


@pytest.mark.asyncio
async def test_unknown_commit_failure_consumes_attempt_and_rotates_temp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = AsyncMock()
    reset = AsyncMock(return_value=True)
    monkeypatch.setattr(
        'module_shot_grid.service.version_publish_worker_service.ShotGridVersionSubmissionDao.reset_committing_to_published',
        reset,
    )

    result = await ShotGridVersionPublishWorkerService._record_commit_failure(
        db,
        claimed=_claimed(attempt_count=2),
        error=RuntimeError('database unavailable with secret details'),
        now=datetime(2026, 8, 11, 12, 0, 0),
        max_attempts=5,
        retry_delays_seconds=(5, 15, 60, 300),
    )

    assert result.outcome == 'retry_wait'
    kwargs = reset.await_args.kwargs
    assert kwargs['attempt_count'] == ATTEMPT_COUNT
    assert kwargs['next_attempt_count'] == NEXT_ATTEMPT_COUNT
    assert '.sgtmp-11-a3-' in kwargs['temporary_relative_path']
    assert 'secret' not in (result.error_key or '')


@pytest.mark.asyncio
async def test_persistent_unknown_commit_failure_becomes_failed_at_attempt_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = AsyncMock()
    mark_failed = AsyncMock(return_value=True)
    reset = AsyncMock(return_value=True)
    monkeypatch.setattr(
        'module_shot_grid.service.version_publish_worker_service.ShotGridVersionSubmissionDao.mark_failed',
        mark_failed,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_publish_worker_service.ShotGridVersionSubmissionDao.reset_committing_to_published',
        reset,
    )

    result = await ShotGridVersionPublishWorkerService._record_commit_failure(
        db,
        claimed=_claimed(attempt_count=5),
        error=RuntimeError('persistent database failure'),
        now=datetime(2026, 8, 11, 12, 0, 0),
        max_attempts=5,
        retry_delays_seconds=(5, 15, 60, 300),
    )

    assert result.outcome == 'failed'
    mark_failed.assert_awaited_once()
    reset.assert_not_awaited()
    assert mark_failed.await_args.kwargs['error_key'] == 'SG_VERSION_SUBMISSION_FAILED'
    assert mark_failed.await_args.kwargs['error_message'] == '版本发布或正式提交执行失败'

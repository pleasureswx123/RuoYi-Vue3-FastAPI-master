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
        temporary_relative_path=f'VIDEO\\EP01\\001_S001\\.sgtmp-11-a{attempt_count}-old.part',
    )


def _publish_context(submission_file_id: int, publish_status: str) -> dict[str, object]:
    return {
        'submission_id': SUBMISSION_ID,
        'submission_file_id': submission_file_id,
        'candidate_no': submission_file_id,
        'submission_status': 'publishing',
        'publish_status': publish_status,
        'lease_owner': 'leader:claim',
        'attempt_count': ATTEMPT_COUNT,
        'task_kind': 'shot_video',
        'source_storage_type': 'local',
        'source_access_type': 'private',
        'source_status': 'active',
        'source_del_flag': '0',
        'source_storage_key': f'private/{submission_file_id}.mov',
        'source_sha256': 'a' * 64,
        'current_source_sha256': 'a' * 64,
        'source_file_size': PUBLISHED_FILE_SIZE,
        'current_source_file_size': PUBLISHED_FILE_SIZE,
        'business_file_name': f'V001_{submission_file_id:02d}.mov',
        'target_relative_path': f'VIDEO\\V001_{submission_file_id:02d}.mov',
        'temporary_relative_path': f'VIDEO\\.sgtmp-{submission_file_id}.part',
        'storage_status': 'ready',
        'protocol': 'SMB',
        'configured_root_path': r'\\server\share\project',
        'root_path_snapshot': r'\\server\share',
        'project_relative_path': 'project',
        'project_path_snapshot': r'\\server\share\project',
        'root_del_flag': '0',
    }


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
async def test_run_once_publishes_each_unfinished_candidate_and_skips_completed_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = AsyncMock()
    claim = SimpleNamespace(
        submission_id=SUBMISSION_ID,
        attempt_count=ATTEMPT_COUNT,
        lease_owner='leader:claim',
        submission_status='publishing',
        temporary_relative_path='VIDEO\\.legacy.part',
    )
    contexts = [
        _publish_context(1, 'published'),
        _publish_context(2, 'publishing'),
        _publish_context(3, 'publishing'),
    ]
    publish = AsyncMock(
        side_effect=[
            (VersionPublishResult(sha256='a' * 64, file_size=PUBLISHED_FILE_SIZE, reused_target=False), False),
            (VersionPublishResult(sha256='a' * 64, file_size=PUBLISHED_FILE_SIZE, reused_target=False), False),
        ]
    )
    mark_child = AsyncMock(return_value=True)
    mark_parent = AsyncMock(return_value=True)
    monkeypatch.setattr(
        'module_shot_grid.service.version_publish_worker_service.ShotGridVersionSubmissionDao.claim_next',
        AsyncMock(return_value=claim),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_publish_worker_service.ShotGridVersionSubmissionDao.get_publish_contexts',
        AsyncMock(return_value=contexts),
    )
    monkeypatch.setattr(ShotGridVersionPublishWorkerService, '_execute_with_heartbeat', publish)
    monkeypatch.setattr(
        'module_shot_grid.service.version_publish_worker_service.ShotGridVersionSubmissionDao.mark_submission_file_published',
        mark_child,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_publish_worker_service.ShotGridVersionSubmissionDao.mark_published',
        mark_parent,
    )

    result = await ShotGridVersionPublishWorkerService.run_once(
        db,
        worker_id='leader',
        adapter=SimpleNamespace(),
        lease_seconds=10,
        heartbeat_seconds=2,
        operation_timeout_seconds=5,
    )

    assert result.outcome == 'published'
    expected_publish_count = 2
    assert publish.await_count == expected_publish_count
    assert [item.kwargs['context'].business_file_name for item in publish.await_args_list] == [
        'V001_02.mov',
        'V001_03.mov',
    ]
    assert [item.kwargs['submission_file_id'] for item in mark_child.await_args_list] == [2, 3]
    mark_parent.assert_awaited_once()
    db.rollback.assert_not_awaited()


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

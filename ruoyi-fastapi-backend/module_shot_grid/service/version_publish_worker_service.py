import asyncio
import inspect
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PureWindowsPath
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.dao.version_submission_dao import ShotGridVersionSubmissionDao
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.version_publish_path_adapter import (
    ShotGridVersionPublishPathAdapter,
    VersionPublishPathAdapterError,
    VersionPublishPathContext,
    VersionPublishResult,
)
from module_shot_grid.service.version_submission_service import ShotGridVersionSubmissionService

VersionWorkerOutcome = Literal['idle', 'published', 'committed', 'retry_wait', 'failed', 'lease_lost']
LeaderPredicate = Callable[[], bool | Awaitable[bool]]


@dataclass(frozen=True)
class VersionWorkerRunResult:
    """一次版本发布 Worker 消费的安全摘要。"""

    outcome: VersionWorkerOutcome
    submission_id: int | None = None
    attempt_count: int = 0
    error_key: str | None = None
    soft_timeout_exceeded: bool = False


@dataclass(frozen=True)
class _ClaimedSubmission:
    submission_id: int
    attempt_count: int
    lease_owner: str
    execution_status: Literal['publishing', 'committing']
    temporary_relative_path: str


class _LeaseLostDuringExecution(Exception):
    """心跳续租发现 owner + attempt fencing 已失效。"""


class ShotGridVersionPublishWorkerService:
    """以短事务和有期限租约驱动版本源文件到 NAS 的发布。"""

    DEFAULT_LEASE_SECONDS = 900
    MAX_ATTEMPTS = 5
    DEFAULT_RETRY_DELAYS_SECONDS = (5, 15, 60, 300)
    DEFAULT_OPERATION_TIMEOUT_SECONDS = 300
    DEFAULT_HEARTBEAT_SECONDS = 30
    MAX_WORKER_ID_LENGTH = 100
    CONTROL_CHARACTER_LIMIT = 32
    MAX_BATCH_SIZE = 20

    @classmethod
    async def run_scheduled_batch(
        cls,
        db: AsyncSession,
        *,
        worker_id: str,
        adapter: ShotGridVersionPublishPathAdapter | None = None,
        max_operations: int = 5,
        leader_predicate: LeaderPredicate | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
        retry_delays_seconds: tuple[int, ...] = DEFAULT_RETRY_DELAYS_SECONDS,
        operation_timeout_seconds: float = DEFAULT_OPERATION_TIMEOUT_SECONDS,
        heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    ) -> tuple[VersionWorkerRunResult, ...]:
        """Leader 专属调度入口；每条提交前重新确认 Leader 身份。"""

        if max_operations <= 0 or max_operations > cls.MAX_BATCH_SIZE:
            raise ValueError('max_operations 超出允许范围')
        results: list[VersionWorkerRunResult] = []
        for _index in range(max_operations):
            if leader_predicate is not None and not await cls._is_leader(leader_predicate):
                break
            result = await cls.run_once(
                db,
                worker_id=worker_id,
                adapter=adapter,
                lease_seconds=lease_seconds,
                max_attempts=max_attempts,
                retry_delays_seconds=retry_delays_seconds,
                operation_timeout_seconds=operation_timeout_seconds,
                heartbeat_seconds=heartbeat_seconds,
            )
            results.append(result)
            if result.outcome in {'idle', 'retry_wait'}:
                break
        return tuple(results)

    @classmethod
    async def run_once(
        cls,
        db: AsyncSession,
        *,
        worker_id: str,
        adapter: ShotGridVersionPublishPathAdapter | None = None,
        now: datetime | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
        retry_delays_seconds: tuple[int, ...] = DEFAULT_RETRY_DELAYS_SECONDS,
        operation_timeout_seconds: float = DEFAULT_OPERATION_TIMEOUT_SECONDS,
        heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    ) -> VersionWorkerRunResult:
        normalized_worker_id = cls._validate_worker_id(worker_id)
        cls._validate_boundaries(
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
            retry_delays_seconds=retry_delays_seconds,
            operation_timeout_seconds=operation_timeout_seconds,
            heartbeat_seconds=heartbeat_seconds,
        )
        claimed_at = cls._second_precision(now or datetime.now())
        claim_owner = cls._new_claim_owner(normalized_worker_id)
        try:
            submission = await ShotGridVersionSubmissionDao.claim_next(
                db,
                worker_id=claim_owner,
                now=claimed_at,
                lease_seconds=lease_seconds,
            )
            if submission is None:
                await db.commit()
                return VersionWorkerRunResult(outcome='idle')
            claimed = _ClaimedSubmission(
                submission_id=submission.submission_id,
                attempt_count=submission.attempt_count,
                lease_owner=submission.lease_owner,
                execution_status=submission.submission_status,
                temporary_relative_path=submission.temporary_relative_path,
            )
            context_row = await ShotGridVersionSubmissionDao.get_publish_context(db, claimed.submission_id)
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        if claimed.execution_status == 'publishing' and claimed.attempt_count > max_attempts:
            return await cls._record_publish_failure(
                db,
                claimed=claimed,
                error=VersionPublishPathAdapterError(
                    error_key='SG_VERSION_SUBMISSION_FAILED',
                    safe_message='版本发布已达到最大自动尝试次数',
                    retryable=False,
                ),
                now=cls._second_precision(datetime.now()),
                max_attempts=max_attempts,
                retry_delays_seconds=retry_delays_seconds,
            )

        path_adapter = adapter or ShotGridVersionPublishPathAdapter()
        soft_timeout_exceeded = False
        try:
            if context_row is None:
                raise VersionPublishPathAdapterError(
                    error_key='SG_VERSION_SUBMISSION_FAILED',
                    safe_message='版本提交缺少有效的源文件或项目存储绑定',
                    retryable=False,
                )
            context = cls._build_context(context_row, claimed)
            publish_result, soft_timeout_exceeded = await cls._execute_with_heartbeat(
                db,
                adapter=path_adapter,
                context=context,
                claimed=claimed,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                operation_timeout_seconds=operation_timeout_seconds,
            )
        except _LeaseLostDuringExecution:
            return VersionWorkerRunResult(
                outcome='lease_lost',
                submission_id=claimed.submission_id,
                attempt_count=claimed.attempt_count,
                soft_timeout_exceeded=soft_timeout_exceeded,
            )
        except Exception as exc:
            if claimed.execution_status == 'publishing':
                return await cls._record_publish_failure(
                    db,
                    claimed=claimed,
                    error=exc,
                    now=cls._second_precision(datetime.now()),
                    max_attempts=max_attempts,
                    retry_delays_seconds=retry_delays_seconds,
                )
            return await cls._record_commit_failure(
                db,
                claimed=claimed,
                error=exc,
                now=cls._second_precision(datetime.now()),
                max_attempts=max_attempts,
                retry_delays_seconds=retry_delays_seconds,
            )

        if claimed.execution_status == 'publishing':
            return await cls._mark_published(
                db,
                claimed=claimed,
                soft_timeout_exceeded=soft_timeout_exceeded,
            )
        try:
            await ShotGridVersionSubmissionService.commit_published_submission(
                db,
                submission_id=claimed.submission_id,
                worker_id=claimed.lease_owner,
                attempt_count=claimed.attempt_count,
                published_sha256=publish_result.sha256,
                published_file_size=publish_result.file_size,
            )
        except Exception as exc:
            return await cls._record_commit_failure(
                db,
                claimed=claimed,
                error=exc,
                now=cls._second_precision(datetime.now()),
                max_attempts=max_attempts,
                retry_delays_seconds=retry_delays_seconds,
            )
        return VersionWorkerRunResult(
            outcome='committed',
            submission_id=claimed.submission_id,
            attempt_count=claimed.attempt_count,
            soft_timeout_exceeded=soft_timeout_exceeded,
        )

    @classmethod
    async def renew_lease(
        cls,
        db: AsyncSession,
        *,
        submission_id: int,
        worker_id: str,
        expected_attempt_count: int,
        execution_status: str,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        now: datetime | None = None,
    ) -> bool:
        normalized_worker_id = cls._validate_worker_id(worker_id)
        if submission_id <= 0 or expected_attempt_count <= 0 or lease_seconds <= 0:
            raise ValueError('submission_id、expected_attempt_count 和 lease_seconds 必须大于0')
        renewed_at = cls._second_precision(now or datetime.now())
        try:
            renewed = await ShotGridVersionSubmissionDao.renew_lease(
                db,
                submission_id=submission_id,
                worker_id=normalized_worker_id,
                attempt_count=expected_attempt_count,
                status=execution_status,
                lease_until=renewed_at + timedelta(seconds=lease_seconds),
                now=renewed_at,
            )
            await db.commit()
            return renewed
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def _mark_published(
        cls,
        db: AsyncSession,
        *,
        claimed: _ClaimedSubmission,
        soft_timeout_exceeded: bool,
    ) -> VersionWorkerRunResult:
        try:
            updated = await ShotGridVersionSubmissionDao.mark_published(
                db,
                submission_id=claimed.submission_id,
                worker_id=claimed.lease_owner,
                attempt_count=claimed.attempt_count,
                now=cls._second_precision(datetime.now()),
            )
            if not updated:
                await db.rollback()
                return cls._lease_lost_result(claimed, soft_timeout_exceeded=soft_timeout_exceeded)
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return VersionWorkerRunResult(
            outcome='published',
            submission_id=claimed.submission_id,
            attempt_count=claimed.attempt_count,
            soft_timeout_exceeded=soft_timeout_exceeded,
        )

    @classmethod
    async def _record_publish_failure(
        cls,
        db: AsyncSession,
        *,
        claimed: _ClaimedSubmission,
        error: Exception,
        now: datetime,
        max_attempts: int,
        retry_delays_seconds: tuple[int, ...],
    ) -> VersionWorkerRunResult:
        error_key, safe_message, retryable = cls._safe_error(error)
        terminal = not retryable or claimed.attempt_count >= max_attempts
        try:
            if terminal:
                updated = await ShotGridVersionSubmissionDao.mark_failed(
                    db,
                    submission_id=claimed.submission_id,
                    worker_id=claimed.lease_owner,
                    attempt_count=claimed.attempt_count,
                    from_status='publishing',
                    error_key=error_key,
                    error_message=safe_message,
                    now=now,
                )
                outcome: VersionWorkerOutcome = 'failed'
            else:
                updated = await ShotGridVersionSubmissionDao.mark_retry_pending(
                    db,
                    submission_id=claimed.submission_id,
                    worker_id=claimed.lease_owner,
                    attempt_count=claimed.attempt_count,
                    next_retry_time=now
                    + timedelta(seconds=cls._retry_delay_seconds(claimed.attempt_count, retry_delays_seconds)),
                )
                outcome = 'retry_wait'
            if not updated:
                await db.rollback()
                return cls._lease_lost_result(claimed, error_key=error_key)
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return VersionWorkerRunResult(
            outcome=outcome,
            submission_id=claimed.submission_id,
            attempt_count=claimed.attempt_count,
            error_key=error_key,
        )

    @classmethod
    async def _record_commit_failure(
        cls,
        db: AsyncSession,
        *,
        claimed: _ClaimedSubmission,
        error: Exception,
        now: datetime,
        max_attempts: int,
        retry_delays_seconds: tuple[int, ...],
    ) -> VersionWorkerRunResult:
        error_key, safe_message, retryable = cls._safe_error(error)
        terminal = (
            isinstance(error, (VersionPublishPathAdapterError, ShotGridDomainException)) and not retryable
        ) or claimed.attempt_count >= max_attempts
        try:
            if terminal:
                updated = await ShotGridVersionSubmissionDao.mark_failed(
                    db,
                    submission_id=claimed.submission_id,
                    worker_id=claimed.lease_owner,
                    attempt_count=claimed.attempt_count,
                    from_status='committing',
                    error_key=error_key,
                    error_message=safe_message,
                    now=now,
                )
                outcome: VersionWorkerOutcome = 'failed'
            else:
                updated = await ShotGridVersionSubmissionDao.reset_committing_to_published(
                    db,
                    submission_id=claimed.submission_id,
                    worker_id=claimed.lease_owner,
                    attempt_count=claimed.attempt_count,
                    next_attempt_count=claimed.attempt_count + 1,
                    temporary_relative_path=cls._next_attempt_temporary_path(claimed),
                    next_retry_time=now
                    + timedelta(seconds=cls._retry_delay_seconds(claimed.attempt_count, retry_delays_seconds)),
                )
                outcome = 'retry_wait'
            if not updated:
                await db.rollback()
                return cls._lease_lost_result(claimed, error_key=error_key)
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return VersionWorkerRunResult(
            outcome=outcome,
            submission_id=claimed.submission_id,
            attempt_count=claimed.attempt_count,
            error_key=error_key,
        )

    @classmethod
    async def _execute_with_heartbeat(
        cls,
        db: AsyncSession,
        *,
        adapter: ShotGridVersionPublishPathAdapter,
        context: VersionPublishPathContext,
        claimed: _ClaimedSubmission,
        lease_seconds: int,
        heartbeat_seconds: float,
        operation_timeout_seconds: float,
    ) -> tuple[VersionPublishResult, bool]:
        """延后调度取消，直到不可强杀的文件 I/O 与租约心跳一起收敛。"""

        guardian_task = asyncio.create_task(
            cls._run_publish_io_guardian(
                db,
                adapter=adapter,
                context=context,
                claimed=claimed,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                operation_timeout_seconds=operation_timeout_seconds,
            )
        )
        while not guardian_task.done():
            try:
                await asyncio.shield(guardian_task)
            except asyncio.CancelledError:  # noqa: PERF203 - drain 必须覆盖整个守护周期
                continue
        return guardian_task.result()

    @classmethod
    async def _run_publish_io_guardian(
        cls,
        db: AsyncSession,
        *,
        adapter: ShotGridVersionPublishPathAdapter,
        context: VersionPublishPathContext,
        claimed: _ClaimedSubmission,
        lease_seconds: int,
        heartbeat_seconds: float,
        operation_timeout_seconds: float,
    ) -> tuple[VersionPublishResult, bool]:
        event_loop = asyncio.get_running_loop()
        started_at = event_loop.time()
        soft_deadline = started_at + operation_timeout_seconds
        next_heartbeat = started_at + heartbeat_seconds
        soft_timeout_exceeded = False
        io_task = asyncio.create_task(adapter.publish(context))
        while not io_task.done():
            next_wakeup = next_heartbeat
            if not soft_timeout_exceeded:
                next_wakeup = min(next_wakeup, soft_deadline)
            await asyncio.wait({io_task}, timeout=max(next_wakeup - event_loop.time(), 0))
            now_monotonic = event_loop.time()
            if not soft_timeout_exceeded and now_monotonic >= soft_deadline:
                soft_timeout_exceeded = True
            if not io_task.done() and now_monotonic >= next_heartbeat:
                try:
                    renewed = await cls.renew_lease(
                        db,
                        submission_id=claimed.submission_id,
                        worker_id=claimed.lease_owner,
                        expected_attempt_count=claimed.attempt_count,
                        execution_status=claimed.execution_status,
                        lease_seconds=lease_seconds,
                    )
                except Exception:
                    await io_task
                    raise
                if not renewed:
                    await io_task
                    raise _LeaseLostDuringExecution
                next_heartbeat = event_loop.time() + heartbeat_seconds
        return io_task.result(), soft_timeout_exceeded

    @staticmethod
    def _build_context(
        row: dict[str, object],
        claimed: _ClaimedSubmission,
    ) -> VersionPublishPathContext:
        valid_source = (
            row['submission_status'] == claimed.execution_status
            and row['lease_owner'] == claimed.lease_owner
            and row['attempt_count'] == claimed.attempt_count
            and row['source_storage_type'] == 'local'
            and row['source_access_type'] == 'private'
            and row['source_status'] == 'active'
            and row['source_del_flag'] == '0'
            and str(row['current_source_sha256']).casefold() == str(row['source_sha256']).casefold()
            and row['current_source_file_size'] == row['source_file_size']
        )
        if not valid_source:
            raise VersionPublishPathAdapterError(
                error_key='SG_VERSION_SOURCE_FILE_CHANGED',
                safe_message='平台源文件状态、摘要或大小已发生变化',
                retryable=False,
            )
        return VersionPublishPathContext(
            submission_id=int(row['submission_id']),
            attempt_count=int(row['attempt_count']),
            task_kind=str(row['task_kind']),
            source_storage_key=str(row['source_storage_key']),
            source_sha256=str(row['source_sha256']),
            source_file_size=int(row['source_file_size']),
            business_file_name=str(row['business_file_name']),
            target_relative_path=str(row['target_relative_path']),
            temporary_relative_path=str(row['temporary_relative_path']),
            storage_status=str(row['storage_status']),
            protocol=str(row['protocol']),
            configured_root_path=str(row['configured_root_path']),
            root_path_snapshot=str(row['root_path_snapshot']),
            project_relative_path=str(row['project_relative_path']),
            project_path_snapshot=str(row['project_path_snapshot']),
            root_del_flag=str(row['root_del_flag']),
        )

    @staticmethod
    def _safe_error(error: Exception) -> tuple[str, str, bool]:
        if isinstance(error, VersionPublishPathAdapterError):
            return error.error_key, error.safe_message[:500], error.retryable
        if isinstance(error, ShotGridDomainException):
            return error.error_key, error.message[:500], False
        if isinstance(error, (TimeoutError, OSError)):
            return 'SG_STORAGE_ROOT_UNAVAILABLE', 'NAS 版本文件发布暂时不可用', True
        return 'SG_VERSION_SUBMISSION_FAILED', '版本发布或正式提交执行失败', True

    @staticmethod
    def _retry_delay_seconds(attempt_count: int, retry_delays_seconds: tuple[int, ...]) -> int:
        retry_index = min(max(attempt_count - 1, 0), len(retry_delays_seconds) - 1)
        return retry_delays_seconds[retry_index]

    @staticmethod
    async def _is_leader(predicate: LeaderPredicate) -> bool:
        result = predicate()
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    @classmethod
    def _validate_boundaries(
        cls,
        *,
        lease_seconds: int,
        max_attempts: int,
        retry_delays_seconds: tuple[int, ...],
        operation_timeout_seconds: float,
        heartbeat_seconds: float,
    ) -> None:
        if (
            lease_seconds <= 0
            or max_attempts <= 0
            or not retry_delays_seconds
            or operation_timeout_seconds <= 0
            or heartbeat_seconds <= 0
            or heartbeat_seconds >= lease_seconds
        ):
            raise ValueError('租约、超时、最大次数和退避序列必须为正数')
        if any(delay <= 0 for delay in retry_delays_seconds):
            raise ValueError('retry_delays_seconds 必须全部大于0')

    @classmethod
    def _validate_worker_id(cls, worker_id: str) -> str:
        if not isinstance(worker_id, str):
            raise ValueError('worker_id 不合法')
        normalized = worker_id.strip()
        if (
            not normalized
            or len(normalized) > cls.MAX_WORKER_ID_LENGTH
            or any(ord(char) < cls.CONTROL_CHARACTER_LIMIT for char in normalized)
        ):
            raise ValueError('worker_id 不合法')
        return normalized

    @staticmethod
    def _new_claim_owner(worker_id: str) -> str:
        return f'{worker_id[:60]}:{uuid.uuid4().hex}'

    @staticmethod
    def _next_attempt_temporary_path(claimed: _ClaimedSubmission) -> str:
        current = PureWindowsPath(claimed.temporary_relative_path)
        next_attempt = claimed.attempt_count + 1
        return str(current.parent / f'.sgtmp-{claimed.submission_id}-a{next_attempt}-{uuid.uuid4().hex}.part')

    @staticmethod
    def _second_precision(value: datetime) -> datetime:
        return value.replace(microsecond=0)

    @staticmethod
    def _lease_lost_result(
        claimed: _ClaimedSubmission,
        *,
        error_key: str | None = None,
        soft_timeout_exceeded: bool = False,
    ) -> VersionWorkerRunResult:
        return VersionWorkerRunResult(
            outcome='lease_lost',
            submission_id=claimed.submission_id,
            attempt_count=claimed.attempt_count,
            error_key=error_key,
            soft_timeout_exceeded=soft_timeout_exceeded,
        )

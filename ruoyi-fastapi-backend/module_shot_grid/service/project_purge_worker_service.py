import asyncio
import inspect
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.dao.project_purge_dao import ShotGridProjectPurgeDao
from module_shot_grid.service.project_purge_path_adapter import (
    ProjectPurgePathAdapterError,
    ProjectPurgePathContext,
    ShotGridProjectPurgePathAdapter,
)

ProjectPurgeWorkerOutcome = Literal['idle', 'succeeded', 'retry_wait', 'failed', 'lease_lost']
LeaderPredicate = Callable[[], bool | Awaitable[bool]]


@dataclass(frozen=True)
class ProjectPurgeWorkerRunResult:
    outcome: ProjectPurgeWorkerOutcome
    purge_id: int | None = None
    attempt_count: int = 0
    error_key: str | None = None
    soft_timeout_exceeded: bool = False


@dataclass(frozen=True)
class _ClaimedPurge:
    purge_id: int
    attempt_count: int
    lease_owner: str
    context: ProjectPurgePathContext


class _PurgeLeaseLost(Exception):
    pass


class ShotGridProjectPurgeWorkerService:
    """使用租约、SKIP LOCKED 和 owner+attempt fencing 清理项目物理数据。"""

    MAX_WORKER_ID_LENGTH = 100
    CONTROL_CHARACTER_LIMIT = 32
    MAX_BATCH_SIZE = 100

    @classmethod
    async def run_scheduled_batch(
        cls,
        db: AsyncSession,
        *,
        worker_id: str,
        adapter: ShotGridProjectPurgePathAdapter | None = None,
        max_operations: int = 20,
        leader_predicate: LeaderPredicate | None = None,
        lease_seconds: int = 120,
        max_attempts: int = 5,
        retry_delays_seconds: tuple[int, ...] = (5, 15, 60, 300),
        operation_timeout_seconds: float = 60,
        heartbeat_seconds: float = 30,
    ) -> tuple[ProjectPurgeWorkerRunResult, ...]:
        if max_operations <= 0 or max_operations > cls.MAX_BATCH_SIZE:
            raise ValueError('max_operations 超出允许范围')
        results: list[ProjectPurgeWorkerRunResult] = []
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
            if result.outcome == 'idle':
                break
        return tuple(results)

    @classmethod
    async def run_once(
        cls,
        db: AsyncSession,
        *,
        worker_id: str,
        adapter: ShotGridProjectPurgePathAdapter | None = None,
        now: datetime | None = None,
        lease_seconds: int = 120,
        max_attempts: int = 5,
        retry_delays_seconds: tuple[int, ...] = (5, 15, 60, 300),
        operation_timeout_seconds: float = 60,
        heartbeat_seconds: float = 30,
    ) -> ProjectPurgeWorkerRunResult:
        normalized_worker_id = cls._validate_worker_id(worker_id)
        if (
            lease_seconds <= 0
            or max_attempts <= 0
            or not retry_delays_seconds
            or operation_timeout_seconds <= 0
            or heartbeat_seconds <= 0
            or heartbeat_seconds >= lease_seconds
        ):
            raise ValueError('租约、超时、最大次数和退避序列必须为正数')
        claimed_at = cls._second_precision(now or datetime.now())
        claim_owner = f'{normalized_worker_id[:60]}:{uuid.uuid4().hex}'
        try:
            purge = await ShotGridProjectPurgeDao.claim_next(
                db,
                worker_id=claim_owner,
                now=claimed_at,
                lease_until=claimed_at + timedelta(seconds=lease_seconds),
            )
            if purge is None:
                await db.commit()
                return ProjectPurgeWorkerRunResult(outcome='idle')
            claimed = _ClaimedPurge(
                purge_id=purge.purge_id,
                attempt_count=purge.attempt_count,
                lease_owner=purge.lease_owner,
                context=ProjectPurgePathContext(
                    purge_id=purge.purge_id,
                    project_id=purge.project_id,
                    root_path_snapshot=purge.root_path_snapshot,
                    project_relative_path=purge.project_relative_path,
                    project_path_snapshot=purge.project_path_snapshot,
                    file_manifest=list(purge.file_manifest),
                ),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        if claimed.attempt_count > max_attempts:
            return await cls._record_failure(
                db,
                claimed=claimed,
                error=ProjectPurgePathAdapterError(
                    error_key='SG_PROJECT_PURGE_FAILED',
                    safe_message='项目物理清理已达到最大自动尝试次数',
                    retryable=False,
                ),
                now=cls._second_precision(datetime.now()),
                max_attempts=max_attempts,
                retry_delays_seconds=retry_delays_seconds,
            )

        soft_timeout_exceeded = False
        try:
            soft_timeout_exceeded = await cls._execute_with_heartbeat(
                db,
                adapter=adapter or ShotGridProjectPurgePathAdapter(),
                claimed=claimed,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                operation_timeout_seconds=operation_timeout_seconds,
            )
        except _PurgeLeaseLost:
            return ProjectPurgeWorkerRunResult(
                outcome='lease_lost',
                purge_id=claimed.purge_id,
                attempt_count=claimed.attempt_count,
                soft_timeout_exceeded=soft_timeout_exceeded,
            )
        except Exception as exc:
            return await cls._record_failure(
                db,
                claimed=claimed,
                error=exc,
                now=cls._second_precision(datetime.now()),
                max_attempts=max_attempts,
                retry_delays_seconds=retry_delays_seconds,
            )

        file_ids = [str(item['fileId']) for item in claimed.context.file_manifest]
        completed_at = cls._second_precision(datetime.now())
        try:
            updated = await ShotGridProjectPurgeDao.mark_succeeded(
                db,
                purge_id=claimed.purge_id,
                worker_id=claimed.lease_owner,
                expected_attempt_count=claimed.attempt_count,
                now=completed_at,
                file_ids=file_ids,
            )
            if not updated:
                await db.rollback()
                return ProjectPurgeWorkerRunResult(
                    outcome='lease_lost',
                    purge_id=claimed.purge_id,
                    attempt_count=claimed.attempt_count,
                    soft_timeout_exceeded=soft_timeout_exceeded,
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return ProjectPurgeWorkerRunResult(
            outcome='succeeded',
            purge_id=claimed.purge_id,
            attempt_count=claimed.attempt_count,
            soft_timeout_exceeded=soft_timeout_exceeded,
        )

    @classmethod
    async def _execute_with_heartbeat(
        cls,
        db: AsyncSession,
        *,
        adapter: ShotGridProjectPurgePathAdapter,
        claimed: _ClaimedPurge,
        lease_seconds: int,
        heartbeat_seconds: float,
        operation_timeout_seconds: float,
    ) -> bool:
        guardian_task = asyncio.create_task(
            cls._run_io_guardian(
                db,
                adapter=adapter,
                claimed=claimed,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                operation_timeout_seconds=operation_timeout_seconds,
            )
        )
        while not guardian_task.done():
            try:
                await asyncio.shield(guardian_task)
            except asyncio.CancelledError:  # noqa: PERF203 - 不可强杀的文件 I/O 必须先收敛
                continue
        return guardian_task.result()

    @classmethod
    async def _run_io_guardian(
        cls,
        db: AsyncSession,
        *,
        adapter: ShotGridProjectPurgePathAdapter,
        claimed: _ClaimedPurge,
        lease_seconds: int,
        heartbeat_seconds: float,
        operation_timeout_seconds: float,
    ) -> bool:
        event_loop = asyncio.get_running_loop()
        soft_deadline = event_loop.time() + operation_timeout_seconds
        next_heartbeat = event_loop.time() + heartbeat_seconds
        soft_timeout_exceeded = False
        io_task = asyncio.create_task(adapter.purge(claimed.context))
        while not io_task.done():
            next_wakeup = next_heartbeat if soft_timeout_exceeded else min(next_heartbeat, soft_deadline)
            await asyncio.wait({io_task}, timeout=max(next_wakeup - event_loop.time(), 0))
            now_monotonic = event_loop.time()
            if not soft_timeout_exceeded and now_monotonic >= soft_deadline:
                soft_timeout_exceeded = True
            if not io_task.done() and now_monotonic >= next_heartbeat:
                renewed_at = cls._second_precision(datetime.now())
                try:
                    renewed = await ShotGridProjectPurgeDao.renew_lease(
                        db,
                        purge_id=claimed.purge_id,
                        worker_id=claimed.lease_owner,
                        expected_attempt_count=claimed.attempt_count,
                        now=renewed_at,
                        lease_until=renewed_at + timedelta(seconds=lease_seconds),
                    )
                    await db.commit()
                except Exception:
                    await db.rollback()
                    await io_task
                    raise
                if not renewed:
                    await io_task
                    raise _PurgeLeaseLost
                next_heartbeat = event_loop.time() + heartbeat_seconds
        io_task.result()
        return soft_timeout_exceeded

    @classmethod
    async def _record_failure(
        cls,
        db: AsyncSession,
        *,
        claimed: _ClaimedPurge,
        error: Exception,
        now: datetime,
        max_attempts: int,
        retry_delays_seconds: tuple[int, ...],
    ) -> ProjectPurgeWorkerRunResult:
        error_key, safe_message, retryable = cls._safe_error(error)
        terminal = not retryable or claimed.attempt_count >= max_attempts
        try:
            if terminal:
                updated = await ShotGridProjectPurgeDao.mark_failed(
                    db,
                    purge_id=claimed.purge_id,
                    worker_id=claimed.lease_owner,
                    expected_attempt_count=claimed.attempt_count,
                    now=now,
                    error_key=error_key,
                    error_message=safe_message,
                )
                outcome: ProjectPurgeWorkerOutcome = 'failed'
            else:
                retry_index = min(max(claimed.attempt_count - 1, 0), len(retry_delays_seconds) - 1)
                updated = await ShotGridProjectPurgeDao.mark_retry_wait(
                    db,
                    purge_id=claimed.purge_id,
                    worker_id=claimed.lease_owner,
                    expected_attempt_count=claimed.attempt_count,
                    now=now,
                    next_retry_time=now + timedelta(seconds=retry_delays_seconds[retry_index]),
                    error_key=error_key,
                    error_message=safe_message,
                )
                outcome = 'retry_wait'
            if not updated:
                await db.rollback()
                return ProjectPurgeWorkerRunResult(
                    outcome='lease_lost',
                    purge_id=claimed.purge_id,
                    attempt_count=claimed.attempt_count,
                    error_key=error_key,
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return ProjectPurgeWorkerRunResult(
            outcome=outcome,
            purge_id=claimed.purge_id,
            attempt_count=claimed.attempt_count,
            error_key=error_key,
        )

    @staticmethod
    def _safe_error(error: Exception) -> tuple[str, str, bool]:
        if isinstance(error, ProjectPurgePathAdapterError):
            return error.error_key, error.safe_message[:500], error.retryable
        if isinstance(error, OSError):
            return 'SG_PROJECT_PURGE_STORAGE_UNAVAILABLE', '项目物理数据暂时无法清理', True
        return 'SG_PROJECT_PURGE_FAILED', '项目物理清理执行失败', True

    @staticmethod
    async def _is_leader(predicate: LeaderPredicate) -> bool:
        result = predicate()
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

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
    def _second_precision(value: datetime) -> datetime:
        return value.replace(microsecond=0)

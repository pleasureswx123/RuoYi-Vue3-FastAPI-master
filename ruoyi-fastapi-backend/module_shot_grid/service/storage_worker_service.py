import asyncio
import inspect
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.dao.storage_operation_dao import ShotGridStorageOperationDao
from module_shot_grid.service.storage_path_adapter import (
    ShotGridStoragePathAdapter,
    StorageOperationPathContext,
    StoragePathAdapterError,
)

StorageWorkerOutcome = Literal['idle', 'succeeded', 'retry_wait', 'failed', 'lease_lost']
LeaderPredicate = Callable[[], bool | Awaitable[bool]]


@dataclass(frozen=True)
class StorageWorkerRunResult:
    """一次 Worker 消费的安全摘要。"""

    outcome: StorageWorkerOutcome
    operation_id: int | None = None
    attempt_count: int = 0
    error_key: str | None = None
    soft_timeout_exceeded: bool = False


@dataclass(frozen=True)
class _ClaimedOperation:
    operation_id: int
    attempt_count: int
    lease_owner: str


class _LeaseLostDuringExecution(Exception):
    """心跳续租发现 owner+attempt fencing 已失效。"""


class ShotGridStorageWorkerService:
    """以短数据库事务驱动 NAS 目录 Outbox。"""

    DEFAULT_LEASE_SECONDS = 120
    MAX_ATTEMPTS = 5
    DEFAULT_RETRY_DELAYS_SECONDS = (5, 15, 60, 300)
    DEFAULT_OPERATION_TIMEOUT_SECONDS = 60
    DEFAULT_HEARTBEAT_SECONDS = 30
    MAX_WORKER_ID_LENGTH = 100
    CONTROL_CHARACTER_LIMIT = 32
    MAX_BATCH_SIZE = 100

    @classmethod
    async def run_scheduled_batch(
        cls,
        db: AsyncSession,
        *,
        worker_id: str,
        adapter: ShotGridStoragePathAdapter | None = None,
        max_operations: int = 20,
        leader_predicate: LeaderPredicate | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
        retry_delays_seconds: tuple[int, ...] = DEFAULT_RETRY_DELAYS_SECONDS,
        operation_timeout_seconds: float = DEFAULT_OPERATION_TIMEOUT_SECONDS,
        heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    ) -> tuple[StorageWorkerRunResult, ...]:
        """供 Leader 专属调度薄包装调用；每条操作前重新确认 Leader 身份。"""

        if max_operations <= 0 or max_operations > cls.MAX_BATCH_SIZE:
            raise ValueError('max_operations 超出允许范围')
        results: list[StorageWorkerRunResult] = []
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
        adapter: ShotGridStoragePathAdapter | None = None,
        now: datetime | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
        retry_delays_seconds: tuple[int, ...] = DEFAULT_RETRY_DELAYS_SECONDS,
        operation_timeout_seconds: float = DEFAULT_OPERATION_TIMEOUT_SECONDS,
        heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    ) -> StorageWorkerRunResult:
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
        if any(delay <= 0 for delay in retry_delays_seconds):
            raise ValueError('retry_delays_seconds 必须全部大于 0')
        claimed_at = cls._second_precision(now or datetime.now())
        lease_until = claimed_at + timedelta(seconds=lease_seconds)
        claim_owner = cls._new_claim_owner(normalized_worker_id)

        try:
            operation = await ShotGridStorageOperationDao.claim_next_operation(
                db,
                worker_id=claim_owner,
                now=claimed_at,
                lease_until=lease_until,
            )
            if operation is None:
                await db.commit()
                return StorageWorkerRunResult(outcome='idle')

            # commit 前冻结标量，避免 expire_on_commit 后异步访问 ORM 属性。
            claimed = _ClaimedOperation(
                operation_id=operation.operation_id,
                attempt_count=operation.attempt_count,
                lease_owner=operation.lease_owner,
            )
            context_row = (
                await ShotGridStorageOperationDao.get_execution_context(db, claimed.operation_id)
                if claimed.attempt_count <= max_attempts
                else None
            )
            context = StorageOperationPathContext(**context_row) if context_row is not None else None
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        if claimed.attempt_count > max_attempts:
            return await cls._record_failure(
                db,
                claimed=claimed,
                error=StoragePathAdapterError(
                    error_key='SG_STORAGE_INITIALIZATION_FAILED',
                    safe_message='目录操作已达到最大自动尝试次数',
                    retryable=False,
                ),
                now=cls._second_precision(datetime.now()),
                max_attempts=max_attempts,
                retry_delays_seconds=retry_delays_seconds,
            )

        path_adapter = adapter or ShotGridStoragePathAdapter()
        soft_timeout_exceeded = False
        try:
            if context is None:
                raise StoragePathAdapterError(
                    error_key='SG_STORAGE_INITIALIZATION_FAILED',
                    safe_message='目录操作缺少有效的项目存储绑定',
                    retryable=False,
                )
            soft_timeout_exceeded = await cls._execute_with_heartbeat(
                db,
                adapter=path_adapter,
                context=context,
                claimed=claimed,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                operation_timeout_seconds=operation_timeout_seconds,
            )
        except _LeaseLostDuringExecution:
            return StorageWorkerRunResult(
                outcome='lease_lost',
                operation_id=claimed.operation_id,
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

        completed_at = cls._second_precision(datetime.now())
        try:
            updated = await ShotGridStorageOperationDao.mark_succeeded(
                db,
                operation_id=claimed.operation_id,
                worker_id=claimed.lease_owner,
                expected_attempt_count=claimed.attempt_count,
                now=completed_at,
            )
            if not updated:
                await db.rollback()
                return StorageWorkerRunResult(
                    outcome='lease_lost',
                    operation_id=claimed.operation_id,
                    attempt_count=claimed.attempt_count,
                    soft_timeout_exceeded=soft_timeout_exceeded,
                )
            await db.commit()
            try:
                finalizer = getattr(path_adapter, 'finalize_operation', None)
                if finalizer is not None:
                    await finalizer(context)
            except StoragePathAdapterError:
                # 业务事务已经成功，残留的空事务目录只作为可诊断痕迹保留，不能反向改写成功状态。
                pass
        except Exception:
            await db.rollback()
            raise
        return StorageWorkerRunResult(
            outcome='succeeded',
            operation_id=claimed.operation_id,
            attempt_count=claimed.attempt_count,
            soft_timeout_exceeded=soft_timeout_exceeded,
        )

    @classmethod
    async def renew_lease(
        cls,
        db: AsyncSession,
        *,
        operation_id: int,
        worker_id: str,
        expected_attempt_count: int,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        now: datetime | None = None,
    ) -> bool:
        """长操作心跳调用；仅当前且尚未过期的租约可以续期。"""

        normalized_worker_id = cls._validate_worker_id(worker_id)
        if operation_id <= 0 or expected_attempt_count <= 0 or lease_seconds <= 0:
            raise ValueError('operation_id、expected_attempt_count 和 lease_seconds 必须大于 0')
        renewed_at = cls._second_precision(now or datetime.now())
        try:
            renewed = await ShotGridStorageOperationDao.renew_lease(
                db,
                operation_id=operation_id,
                worker_id=normalized_worker_id,
                expected_attempt_count=expected_attempt_count,
                now=renewed_at,
                lease_until=renewed_at + timedelta(seconds=lease_seconds),
            )
            await db.commit()
            return renewed
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def _record_failure(
        cls,
        db: AsyncSession,
        *,
        claimed: _ClaimedOperation,
        error: Exception,
        now: datetime,
        max_attempts: int,
        retry_delays_seconds: tuple[int, ...],
    ) -> StorageWorkerRunResult:
        error_key, safe_message, retryable = cls._safe_error(error)
        terminal = not retryable or claimed.attempt_count >= max_attempts
        try:
            if terminal:
                updated = await ShotGridStorageOperationDao.mark_failed(
                    db,
                    operation_id=claimed.operation_id,
                    worker_id=claimed.lease_owner,
                    expected_attempt_count=claimed.attempt_count,
                    now=now,
                    error_key=error_key,
                    error_message=safe_message,
                )
                outcome: StorageWorkerOutcome = 'failed'
            else:
                updated = await ShotGridStorageOperationDao.mark_retry_wait(
                    db,
                    operation_id=claimed.operation_id,
                    worker_id=claimed.lease_owner,
                    expected_attempt_count=claimed.attempt_count,
                    now=now,
                    next_retry_time=now
                    + timedelta(seconds=cls._retry_delay_seconds(claimed.attempt_count, retry_delays_seconds)),
                    error_key=error_key,
                    error_message=safe_message,
                )
                outcome = 'retry_wait'
            if not updated:
                await db.rollback()
                return StorageWorkerRunResult(
                    outcome='lease_lost',
                    operation_id=claimed.operation_id,
                    attempt_count=claimed.attempt_count,
                    error_key=error_key,
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return StorageWorkerRunResult(
            outcome=outcome,
            operation_id=claimed.operation_id,
            attempt_count=claimed.attempt_count,
            error_key=error_key,
        )

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
    async def _execute_with_heartbeat(
        cls,
        db: AsyncSession,
        *,
        adapter: ShotGridStoragePathAdapter,
        context: StorageOperationPathContext,
        claimed: _ClaimedOperation,
        lease_seconds: int,
        heartbeat_seconds: float,
        operation_timeout_seconds: float,
    ) -> bool:
        """软超时不取消线程；租约有效时持续续租并等待 I/O 退出，不承诺接管窗口零重叠。"""

        # APScheduler 会在失锁或关闭时取消外层 Job。用独立守护任务覆盖完整的
        # “目录 I/O + 心跳”状态机，避免取消恰好落在续租或异常收尾 await 时，
        # 让不可强杀的 to_thread 脱离租约继续写目录。
        guardian_task = asyncio.create_task(
            cls._run_directory_io_guardian(
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
            except asyncio.CancelledError:  # noqa: PERF203 - 取消收敛必须覆盖整个守护周期
                # 只延后当前 Job 的调度取消；正常关机/失锁已先撤销 Leader 身份，
                # 外层批处理在本操作结束后不会再领取下一条。
                continue
        return guardian_task.result()

    @classmethod
    async def _run_directory_io_guardian(
        cls,
        db: AsyncSession,
        *,
        adapter: ShotGridStoragePathAdapter,
        context: StorageOperationPathContext,
        claimed: _ClaimedOperation,
        lease_seconds: int,
        heartbeat_seconds: float,
        operation_timeout_seconds: float,
    ) -> bool:
        """在调度取消之外完成单条目录操作及其租约心跳。"""

        event_loop = asyncio.get_running_loop()
        started_at = event_loop.time()
        soft_deadline = started_at + operation_timeout_seconds
        next_heartbeat = started_at + heartbeat_seconds
        soft_timeout_exceeded = False
        io_task = asyncio.create_task(adapter.ensure_directories(context))
        while not io_task.done():
            now_monotonic = event_loop.time()
            next_wakeup = next_heartbeat
            if not soft_timeout_exceeded:
                next_wakeup = min(next_wakeup, soft_deadline)
            await asyncio.wait({io_task}, timeout=max(next_wakeup - now_monotonic, 0))
            now_monotonic = event_loop.time()
            if not soft_timeout_exceeded and now_monotonic >= soft_deadline:
                soft_timeout_exceeded = True
            if not io_task.done() and now_monotonic >= next_heartbeat:
                try:
                    renewed = await cls.renew_lease(
                        db,
                        operation_id=claimed.operation_id,
                        worker_id=claimed.lease_owner,
                        expected_attempt_count=claimed.attempt_count,
                        lease_seconds=lease_seconds,
                    )
                except Exception:
                    # to_thread 不能被安全终止；先等待物理 I/O 退出再传播数据库错误。
                    await io_task
                    raise
                if not renewed:
                    # 不取消仍在运行的线程，避免释放租约后继续后台写目录。
                    await io_task
                    raise _LeaseLostDuringExecution
                next_heartbeat = event_loop.time() + heartbeat_seconds
        # io_task 已结束，直接读取结果，避免再次传播此前被接住的调度取消。
        io_task.result()
        return soft_timeout_exceeded

    @staticmethod
    def _safe_error(error: Exception) -> tuple[str, str, bool]:
        if isinstance(error, StoragePathAdapterError):
            return error.error_key, error.safe_message[:500], error.retryable
        if isinstance(error, TimeoutError):
            return 'SG_STORAGE_ROOT_UNAVAILABLE', 'NAS 目录操作执行超时', True
        if isinstance(error, OSError):
            return 'SG_STORAGE_ROOT_UNAVAILABLE', 'NAS 根目录暂时不可访问或不可写', True
        return 'SG_STORAGE_INITIALIZATION_FAILED', '目录操作执行失败', True

    @staticmethod
    def _validate_worker_id(worker_id: str) -> str:
        if not isinstance(worker_id, str):
            raise ValueError('worker_id 不合法')
        normalized = worker_id.strip()
        if (
            not normalized
            or len(normalized) > ShotGridStorageWorkerService.MAX_WORKER_ID_LENGTH
            or any(ord(char) < ShotGridStorageWorkerService.CONTROL_CHARACTER_LIMIT for char in normalized)
        ):
            raise ValueError('worker_id 不合法')
        return normalized

    @staticmethod
    def _new_claim_owner(worker_id: str) -> str:
        owner_prefix = worker_id[:60]
        return f'{owner_prefix}:{uuid.uuid4().hex}'

    @staticmethod
    def _second_precision(value: datetime) -> datetime:
        return value.replace(microsecond=0)

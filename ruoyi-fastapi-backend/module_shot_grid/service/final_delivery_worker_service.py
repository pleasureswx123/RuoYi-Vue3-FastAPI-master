import asyncio
import inspect
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.dao.final_delivery_dao import ShotGridFinalDeliveryDao
from module_shot_grid.service.final_delivery_path_adapter import (
    FinalDeliveryPathContext,
    FinalDeliveryPublishResult,
    ShotGridFinalDeliveryPathAdapter,
)
from module_shot_grid.service.version_publish_path_adapter import VersionPublishPathAdapterError

FinalDeliveryOutcome = Literal['idle', 'published', 'retry_wait', 'failed', 'lease_lost']
LeaderPredicate = Callable[[], bool | Awaitable[bool]]


@dataclass(frozen=True)
class FinalDeliveryWorkerRunResult:
    outcome: FinalDeliveryOutcome
    final_delivery_id: int | None = None
    attempt_count: int = 0
    error_key: str | None = None
    soft_timeout_exceeded: bool = False


@dataclass(frozen=True)
class _ClaimedDelivery:
    final_delivery_id: int
    attempt_count: int
    lease_owner: str


class _LeaseLostDuringExecution(Exception):
    """owner + attempt fencing 已失效。"""


class ShotGridFinalDeliveryWorkerService:
    """以短事务、租约和 fencing 发布最终文件与 FINAL.json。"""

    MAX_BATCH_SIZE = 20
    MAX_WORKER_ID_LENGTH = 100
    DEFAULT_LEASE_SECONDS = 900
    DEFAULT_MAX_ATTEMPTS = 5
    DEFAULT_RETRY_DELAYS_SECONDS = (5, 15, 60, 300)
    DEFAULT_OPERATION_TIMEOUT_SECONDS = 300
    DEFAULT_HEARTBEAT_SECONDS = 30
    CONTROL_CHARACTER_LIMIT = 32

    @classmethod
    async def run_scheduled_batch(
        cls,
        db: AsyncSession,
        *,
        worker_id: str,
        adapter: ShotGridFinalDeliveryPathAdapter | None = None,
        max_operations: int = 5,
        leader_predicate: LeaderPredicate | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_delays_seconds: tuple[int, ...] = DEFAULT_RETRY_DELAYS_SECONDS,
        operation_timeout_seconds: float = DEFAULT_OPERATION_TIMEOUT_SECONDS,
        heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    ) -> tuple[FinalDeliveryWorkerRunResult, ...]:
        if max_operations <= 0 or max_operations > cls.MAX_BATCH_SIZE:
            raise ValueError('max_operations 超出允许范围')
        results: list[FinalDeliveryWorkerRunResult] = []
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
        adapter: ShotGridFinalDeliveryPathAdapter | None = None,
        now: datetime | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_delays_seconds: tuple[int, ...] = DEFAULT_RETRY_DELAYS_SECONDS,
        operation_timeout_seconds: float = DEFAULT_OPERATION_TIMEOUT_SECONDS,
        heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    ) -> FinalDeliveryWorkerRunResult:
        cls._validate_boundaries(
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
            retry_delays_seconds=retry_delays_seconds,
            operation_timeout_seconds=operation_timeout_seconds,
            heartbeat_seconds=heartbeat_seconds,
        )
        claim_owner = cls._new_claim_owner(cls._validate_worker_id(worker_id))
        claimed_at = cls._second_precision(now or datetime.now())
        try:
            delivery = await ShotGridFinalDeliveryDao.claim_next(
                db,
                worker_id=claim_owner,
                now=claimed_at,
                lease_seconds=lease_seconds,
            )
            if delivery is None:
                await db.commit()
                return FinalDeliveryWorkerRunResult(outcome='idle')
            claimed = _ClaimedDelivery(
                final_delivery_id=int(delivery.final_delivery_id),
                attempt_count=int(delivery.attempt_count),
                lease_owner=str(delivery.lease_owner),
            )
            row = await ShotGridFinalDeliveryDao.get_publish_context(db, claimed.final_delivery_id)
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        if claimed.attempt_count > max_attempts:
            return await cls._record_failure(
                db,
                claimed=claimed,
                error=VersionPublishPathAdapterError(
                    error_key='SG_FINAL_DELIVERY_FAILED',
                    safe_message='最终版本发布已达到最大自动尝试次数',
                    retryable=False,
                ),
                now=cls._second_precision(datetime.now()),
                max_attempts=max_attempts,
                retry_delays_seconds=retry_delays_seconds,
            )
        try:
            context = cls._build_context(row, claimed)
            result, soft_timeout_exceeded = await cls._execute_with_heartbeat(
                db,
                adapter=adapter or ShotGridFinalDeliveryPathAdapter(),
                context=context,
                claimed=claimed,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                operation_timeout_seconds=operation_timeout_seconds,
            )
            marked = await ShotGridFinalDeliveryDao.mark_published(
                db,
                final_delivery_id=claimed.final_delivery_id,
                worker_id=claimed.lease_owner,
                attempt_count=claimed.attempt_count,
                publish_mode=result.publish_mode,
                now=cls._second_precision(datetime.now()),
            )
            if not marked:
                await db.rollback()
                return cls._lease_lost_result(claimed, soft_timeout_exceeded=soft_timeout_exceeded)
            await db.commit()
            return FinalDeliveryWorkerRunResult(
                outcome='published',
                final_delivery_id=claimed.final_delivery_id,
                attempt_count=claimed.attempt_count,
                soft_timeout_exceeded=soft_timeout_exceeded,
            )
        except _LeaseLostDuringExecution:
            return cls._lease_lost_result(claimed)
        except Exception as exc:
            return await cls._record_failure(
                db,
                claimed=claimed,
                error=exc,
                now=cls._second_precision(datetime.now()),
                max_attempts=max_attempts,
                retry_delays_seconds=retry_delays_seconds,
            )

    @classmethod
    async def _execute_with_heartbeat(
        cls,
        db: AsyncSession,
        *,
        adapter: ShotGridFinalDeliveryPathAdapter,
        context: FinalDeliveryPathContext,
        claimed: _ClaimedDelivery,
        lease_seconds: int,
        heartbeat_seconds: float,
        operation_timeout_seconds: float,
    ) -> tuple[FinalDeliveryPublishResult, bool]:
        guardian = asyncio.create_task(
            cls._run_io_guardian(
                db,
                adapter=adapter,
                context=context,
                claimed=claimed,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                operation_timeout_seconds=operation_timeout_seconds,
            )
        )
        while not guardian.done():
            try:
                await asyncio.shield(guardian)
            except asyncio.CancelledError:  # noqa: PERF203 - 同步 SMB I/O 必须完成收敛
                continue
        return guardian.result()

    @classmethod
    async def _run_io_guardian(
        cls,
        db: AsyncSession,
        *,
        adapter: ShotGridFinalDeliveryPathAdapter,
        context: FinalDeliveryPathContext,
        claimed: _ClaimedDelivery,
        lease_seconds: int,
        heartbeat_seconds: float,
        operation_timeout_seconds: float,
    ) -> tuple[FinalDeliveryPublishResult, bool]:
        loop = asyncio.get_running_loop()
        soft_deadline = loop.time() + operation_timeout_seconds
        next_heartbeat = loop.time() + heartbeat_seconds
        soft_timeout_exceeded = False
        io_task = asyncio.create_task(adapter.publish(context))
        while not io_task.done():
            wakeup = next_heartbeat if soft_timeout_exceeded else min(next_heartbeat, soft_deadline)
            await asyncio.wait({io_task}, timeout=max(wakeup - loop.time(), 0))
            current = loop.time()
            if not soft_timeout_exceeded and current >= soft_deadline:
                soft_timeout_exceeded = True
            if not io_task.done() and current >= next_heartbeat:
                renewed = await cls._renew_lease(
                    db,
                    claimed=claimed,
                    lease_seconds=lease_seconds,
                )
                if not renewed:
                    await io_task
                    raise _LeaseLostDuringExecution
                next_heartbeat = loop.time() + heartbeat_seconds
        return io_task.result(), soft_timeout_exceeded

    @classmethod
    async def _renew_lease(
        cls,
        db: AsyncSession,
        *,
        claimed: _ClaimedDelivery,
        lease_seconds: int,
    ) -> bool:
        now = cls._second_precision(datetime.now())
        try:
            renewed = await ShotGridFinalDeliveryDao.renew_lease(
                db,
                final_delivery_id=claimed.final_delivery_id,
                worker_id=claimed.lease_owner,
                attempt_count=claimed.attempt_count,
                lease_until=now + timedelta(seconds=lease_seconds),
                now=now,
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
        claimed: _ClaimedDelivery,
        error: Exception,
        now: datetime,
        max_attempts: int,
        retry_delays_seconds: tuple[int, ...],
    ) -> FinalDeliveryWorkerRunResult:
        error_key, safe_message, retryable = cls._safe_error(error)
        terminal = not retryable or claimed.attempt_count >= max_attempts
        try:
            if terminal:
                updated = await ShotGridFinalDeliveryDao.mark_failed(
                    db,
                    final_delivery_id=claimed.final_delivery_id,
                    worker_id=claimed.lease_owner,
                    attempt_count=claimed.attempt_count,
                    error_key=error_key,
                    error_message=safe_message,
                    now=now,
                )
                outcome: FinalDeliveryOutcome = 'failed'
            else:
                retry_index = min(max(claimed.attempt_count - 1, 0), len(retry_delays_seconds) - 1)
                updated = await ShotGridFinalDeliveryDao.mark_retry_pending(
                    db,
                    final_delivery_id=claimed.final_delivery_id,
                    worker_id=claimed.lease_owner,
                    attempt_count=claimed.attempt_count,
                    next_retry_time=now + timedelta(seconds=retry_delays_seconds[retry_index]),
                )
                outcome = 'retry_wait'
            if not updated:
                await db.rollback()
                return cls._lease_lost_result(claimed, error_key=error_key)
            await db.commit()
            return FinalDeliveryWorkerRunResult(
                outcome=outcome,
                final_delivery_id=claimed.final_delivery_id,
                attempt_count=claimed.attempt_count,
                error_key=error_key,
            )
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    def _build_context(row: dict[str, object] | None, claimed: _ClaimedDelivery) -> FinalDeliveryPathContext:
        valid = (
            row is not None
            and row['delivery_status'] == 'publishing'
            and row['attempt_count'] == claimed.attempt_count
            and row['lease_owner'] == claimed.lease_owner
            and row['version_status'] == 'final'
            and row['task_status'] == 'completed'
            and row['selected_candidate_id'] == row['candidate_id']
        )
        if not valid or row is None:
            raise VersionPublishPathAdapterError(
                error_key='SG_FINAL_DELIVERY_STATE_CHANGED',
                safe_message='最终版本、任务或最佳候选状态已变化',
                retryable=False,
            )
        approved_time = row['approved_time']
        return FinalDeliveryPathContext(
            final_delivery_id=int(row['final_delivery_id']),
            attempt_count=int(row['attempt_count']),
            project_id=int(row['project_id']),
            task_id=int(row['task_id']),
            version_id=int(row['version_id']),
            version_no=int(row['version_no']),
            candidate_id=int(row['candidate_id']),
            candidate_no=int(row['candidate_no']),
            approved_by=int(row['approved_by']),
            approved_time_iso=approved_time.isoformat(timespec='seconds'),  # type: ignore[union-attr]
            business_file_name=str(row['business_file_name']),
            source_nas_relative_path=str(row['source_nas_relative_path']),
            final_nas_relative_path=str(row['final_nas_relative_path']),
            manifest_nas_relative_path=str(row['manifest_nas_relative_path']),
            source_sha256=str(row['source_sha256']),
            source_file_size=int(row['source_file_size']),
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
        if isinstance(error, (TimeoutError, OSError)):
            return 'SG_STORAGE_ROOT_UNAVAILABLE', 'NAS 最终版本发布暂时不可用', True
        return 'SG_FINAL_DELIVERY_FAILED', '最终版本发布执行失败', True

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
            or any(delay <= 0 for delay in retry_delays_seconds)
            or operation_timeout_seconds <= 0
            or heartbeat_seconds <= 0
            or heartbeat_seconds >= lease_seconds
        ):
            raise ValueError('租约、超时、最大次数和退避序列必须为正数')

    @staticmethod
    def _validate_worker_id(worker_id: str) -> str:
        if not isinstance(worker_id, str):
            raise ValueError('worker_id 不合法')
        normalized = worker_id.strip()
        if (
            not normalized
            or len(normalized) > ShotGridFinalDeliveryWorkerService.MAX_WORKER_ID_LENGTH
            or any(ord(char) < ShotGridFinalDeliveryWorkerService.CONTROL_CHARACTER_LIMIT for char in normalized)
        ):
            raise ValueError('worker_id 不合法')
        return normalized

    @staticmethod
    def _new_claim_owner(worker_id: str) -> str:
        return f'{worker_id[:60]}:{uuid.uuid4().hex}'

    @staticmethod
    def _second_precision(value: datetime) -> datetime:
        return value.replace(microsecond=0)

    @staticmethod
    def _lease_lost_result(
        claimed: _ClaimedDelivery,
        *,
        error_key: str | None = None,
        soft_timeout_exceeded: bool = False,
    ) -> FinalDeliveryWorkerRunResult:
        return FinalDeliveryWorkerRunResult(
            outcome='lease_lost',
            final_delivery_id=claimed.final_delivery_id,
            attempt_count=claimed.attempt_count,
            error_key=error_key,
            soft_timeout_exceeded=soft_timeout_exceeded,
        )

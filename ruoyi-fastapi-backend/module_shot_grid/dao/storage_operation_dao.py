from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.entity.do.asset_do import ShotGridAssetItem
from module_shot_grid.entity.do.project_do import ShotGridProject, ShotGridShot
from module_shot_grid.entity.do.storage_do import (
    ShotGridProjectStorage,
    ShotGridStorageOperation,
    ShotGridStorageRoot,
)
from module_shot_grid.entity.do.task_do import ShotGridTask


class ShotGridStorageOperationDao:
    """NAS 目录操作 Outbox 的领取、租约与结果回写。"""

    MAX_RENUMBER_SHOTS = 2000
    LAZY_DIRECTORY_RENUMBER_SCHEMA = 2
    RETRYABLE_STATUSES = ('pending', 'retry_wait')
    UNRESOLVED_ERROR_STATUSES = (
        'retry_wait',
        'failed',
        'compensation_pending',
        'compensation_failed',
    )

    @classmethod
    def build_claim_statement(cls, now: datetime) -> Select[tuple[ShotGridStorageOperation]]:
        """构造 PostgreSQL 多 Worker 安全领取语句，供执行和契约测试复用。"""

        due_operation = or_(
            ShotGridStorageOperation.operation_status == 'pending',
            and_(
                ShotGridStorageOperation.operation_status == 'retry_wait',
                or_(
                    ShotGridStorageOperation.next_retry_time.is_(None),
                    ShotGridStorageOperation.next_retry_time <= now,
                ),
            ),
            and_(
                ShotGridStorageOperation.operation_status == 'processing',
                ShotGridStorageOperation.lease_until <= now,
            ),
        )
        # 兼容升级前已经排队的资产目录操作：至少一个制作分项真正开始后才允许物理执行。
        asset_production_started = exists(
            select(1)
            .select_from(ShotGridTask)
            .join(
                ShotGridAssetItem,
                and_(
                    ShotGridAssetItem.asset_item_id == ShotGridTask.asset_item_id,
                    ShotGridAssetItem.project_id == ShotGridTask.project_id,
                ),
            )
            .where(
                ShotGridTask.project_id == ShotGridStorageOperation.project_id,
                ShotGridTask.task_kind == 'asset_image',
                ShotGridTask.task_status.in_(('preparing', 'in_progress', 'pending_review', 'revision', 'completed')),
                ShotGridTask.del_flag == '0',
                ShotGridAssetItem.asset_id == ShotGridStorageOperation.aggregate_id,
                ShotGridAssetItem.del_flag == '0',
            )
        )
        asset_directory_is_eligible = or_(
            ShotGridStorageOperation.aggregate_type != 'asset',
            asset_production_started,
        )
        return (
            select(ShotGridStorageOperation)
            .where(due_operation, asset_directory_is_eligible)
            .order_by(
                ShotGridStorageOperation.next_retry_time.asc().nullsfirst(),
                ShotGridStorageOperation.operation_id.asc(),
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )

    @classmethod
    async def claim_next_operation(
        cls,
        db: AsyncSession,
        *,
        worker_id: str,
        now: datetime,
        lease_until: datetime,
    ) -> ShotGridStorageOperation | None:
        operation = (await db.execute(cls.build_claim_statement(now))).scalar_one_or_none()
        if operation is None:
            return None

        operation.operation_status = 'processing'
        operation.attempt_count = (operation.attempt_count or 0) + 1
        operation.next_retry_time = None
        operation.lease_owner = worker_id
        operation.lease_until = lease_until
        operation.started_time = operation.started_time or now
        operation.completed_time = None
        operation.update_time = now
        await db.flush()
        return operation

    @classmethod
    async def get_execution_context(cls, db: AsyncSession, operation_id: int) -> dict[str, Any] | None:
        """取得执行所需的不可变路径快照；不返回凭据引用。"""

        row = (
            (
                await db.execute(
                    select(
                        ShotGridStorageOperation.operation_id,
                        ShotGridStorageOperation.project_id,
                        ShotGridStorageOperation.operation_type,
                        ShotGridStorageOperation.aggregate_type,
                        ShotGridStorageOperation.aggregate_id,
                        ShotGridStorageOperation.target_relative_path,
                        ShotGridStorageOperation.operation_payload,
                        ShotGridProjectStorage.storage_root_id,
                        ShotGridProjectStorage.root_path_snapshot,
                        ShotGridProjectStorage.project_relative_path,
                        ShotGridProjectStorage.project_path_snapshot,
                        ShotGridProjectStorage.storage_status,
                        ShotGridStorageRoot.protocol,
                        ShotGridStorageRoot.unc_root_path.label('configured_root_path'),
                        ShotGridStorageRoot.root_status,
                        ShotGridStorageRoot.del_flag.label('root_del_flag'),
                    )
                    .join(
                        ShotGridProjectStorage,
                        ShotGridProjectStorage.project_id == ShotGridStorageOperation.project_id,
                    )
                    .join(
                        ShotGridStorageRoot,
                        ShotGridStorageRoot.storage_root_id == ShotGridProjectStorage.storage_root_id,
                    )
                    .where(ShotGridStorageOperation.operation_id == operation_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @classmethod
    async def renew_lease(
        cls,
        db: AsyncSession,
        *,
        operation_id: int,
        worker_id: str,
        expected_attempt_count: int,
        now: datetime,
        lease_until: datetime,
    ) -> bool:
        result = await db.execute(
            update(ShotGridStorageOperation)
            .where(
                ShotGridStorageOperation.operation_id == operation_id,
                ShotGridStorageOperation.operation_status == 'processing',
                ShotGridStorageOperation.lease_owner == worker_id,
                ShotGridStorageOperation.attempt_count == expected_attempt_count,
                ShotGridStorageOperation.lease_until > now,
            )
            .values(lease_until=lease_until, update_time=now)
        )
        return bool(result.rowcount)

    @classmethod
    async def mark_succeeded(
        cls,
        db: AsyncSession,
        *,
        operation_id: int,
        worker_id: str,
        expected_attempt_count: int,
        now: datetime,
    ) -> bool:
        # 与任务开工共用项目锁；必须先于操作锁和任务锁，避免遗漏并发开工或形成反向锁序。
        # 此处仅在 NAS I/O 已结束后的回写短事务执行，等待后仍须重新校验 owner + attempt。
        project_id = (
            await db.execute(
                select(ShotGridProject.project_id)
                .join(ShotGridStorageOperation, ShotGridStorageOperation.project_id == ShotGridProject.project_id)
                .where(ShotGridStorageOperation.operation_id == operation_id)
                .with_for_update(of=ShotGridProject)
            )
        ).scalar_one_or_none()
        if project_id is None:
            return False
        operation = await cls._lock_owned_operation(
            db,
            operation_id=operation_id,
            worker_id=worker_id,
            expected_attempt_count=expected_attempt_count,
        )
        if operation is None:
            return False

        if cls._is_shot_renumber(operation):
            await cls._apply_shot_renumber(db, operation=operation, now=now)
        elif cls._completes_task_start(operation):
            await db.execute(cls._advance_preparing_tasks_statement(operation, now))

        operation.operation_status = 'succeeded'
        operation.next_retry_time = None
        operation.lease_owner = None
        operation.lease_until = None
        operation.completed_time = now
        operation.last_error_key = None
        operation.last_error_message = None
        operation.update_time = now

        storage = await cls._lock_project_storage(db, operation.project_id)
        if storage is not None:
            if cls._is_project_initialization(operation):
                storage.storage_status = 'ready'
                storage.initialized_time = storage.initialized_time or now
                storage.last_error_key = None
                storage.last_error_message = None
            elif cls._is_shot_renumber(operation):
                storage.storage_status = 'ready'
                storage.last_error_key = None
                storage.last_error_message = None
            elif not await cls._has_other_unresolved_errors(db, operation):
                storage.last_error_key = None
                storage.last_error_message = None
            cls._touch_storage(storage, actor_name=cls._operation_actor(operation), now=now)
        await db.flush()
        return True

    @classmethod
    async def mark_retry_wait(
        cls,
        db: AsyncSession,
        *,
        operation_id: int,
        worker_id: str,
        expected_attempt_count: int,
        now: datetime,
        next_retry_time: datetime,
        error_key: str,
        error_message: str,
    ) -> bool:
        operation = await cls._lock_owned_operation(
            db,
            operation_id=operation_id,
            worker_id=worker_id,
            expected_attempt_count=expected_attempt_count,
        )
        if operation is None:
            return False

        operation.operation_status = 'retry_wait'
        operation.next_retry_time = next_retry_time
        operation.lease_owner = None
        operation.lease_until = None
        operation.completed_time = None
        operation.last_error_key = error_key
        operation.last_error_message = error_message
        operation.update_time = now
        await cls._record_storage_error(
            db,
            operation=operation,
            worker_id=worker_id,
            now=now,
            error_key=error_key,
            error_message=error_message,
            terminal=False,
        )
        await db.flush()
        return True

    @classmethod
    async def mark_failed(
        cls,
        db: AsyncSession,
        *,
        operation_id: int,
        worker_id: str,
        expected_attempt_count: int,
        now: datetime,
        error_key: str,
        error_message: str,
    ) -> bool:
        operation = await cls._lock_owned_operation(
            db,
            operation_id=operation_id,
            worker_id=worker_id,
            expected_attempt_count=expected_attempt_count,
        )
        if operation is None:
            return False

        operation.operation_status = 'failed'
        operation.next_retry_time = None
        operation.lease_owner = None
        operation.lease_until = None
        operation.completed_time = now
        operation.last_error_key = error_key
        operation.last_error_message = error_message
        operation.update_time = now
        await cls._record_storage_error(
            db,
            operation=operation,
            worker_id=worker_id,
            now=now,
            error_key=error_key,
            error_message=error_message,
            terminal=True,
        )
        await db.flush()
        return True

    @classmethod
    async def _lock_owned_operation(
        cls,
        db: AsyncSession,
        *,
        operation_id: int,
        worker_id: str,
        expected_attempt_count: int,
    ) -> ShotGridStorageOperation | None:
        return (
            await db.execute(
                select(ShotGridStorageOperation)
                .where(
                    ShotGridStorageOperation.operation_id == operation_id,
                    ShotGridStorageOperation.operation_status == 'processing',
                    ShotGridStorageOperation.lease_owner == worker_id,
                    ShotGridStorageOperation.attempt_count == expected_attempt_count,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @classmethod
    async def _lock_project_storage(
        cls,
        db: AsyncSession,
        project_id: int,
    ) -> ShotGridProjectStorage | None:
        return (
            await db.execute(
                select(ShotGridProjectStorage).where(ShotGridProjectStorage.project_id == project_id).with_for_update()
            )
        ).scalar_one_or_none()

    @classmethod
    async def _has_other_unresolved_errors(
        cls,
        db: AsyncSession,
        operation: ShotGridStorageOperation,
    ) -> bool:
        latest_operation_ids = (
            select(func.max(ShotGridStorageOperation.operation_id).label('operation_id'))
            .where(ShotGridStorageOperation.project_id == operation.project_id)
            .group_by(
                ShotGridStorageOperation.aggregate_type,
                ShotGridStorageOperation.aggregate_id,
            )
            .subquery()
        )
        count = await db.scalar(
            select(func.count(ShotGridStorageOperation.operation_id)).where(
                ShotGridStorageOperation.project_id == operation.project_id,
                ShotGridStorageOperation.operation_id.in_(select(latest_operation_ids.c.operation_id)),
                ShotGridStorageOperation.operation_status.in_(cls.UNRESOLVED_ERROR_STATUSES),
            )
        )
        return bool(count)

    @classmethod
    async def _record_storage_error(
        cls,
        db: AsyncSession,
        *,
        operation: ShotGridStorageOperation,
        worker_id: str,
        now: datetime,
        error_key: str,
        error_message: str,
        terminal: bool,
    ) -> None:
        storage = await cls._lock_project_storage(db, operation.project_id)
        if storage is None:
            return
        if cls._is_project_initialization(operation):
            storage.storage_status = 'failed' if terminal else 'initializing'
        elif cls._is_shot_renumber(operation):
            storage.storage_status = 'migrating'
        storage.last_error_key = error_key
        storage.last_error_message = error_message
        cls._touch_storage(storage, actor_name=cls._operation_actor(operation), now=now)

    @staticmethod
    def _touch_storage(storage: ShotGridProjectStorage, *, actor_name: str, now: datetime) -> None:
        storage.update_by = actor_name[:64]
        storage.update_time = now
        storage.lock_version = (storage.lock_version or 0) + 1

    @staticmethod
    def _operation_actor(operation: ShotGridStorageOperation) -> str:
        """业务审计字段使用发起人；Worker 租约只保留在执行字段中。"""
        return (operation.create_by or '').strip()[:64] or '系统目录服务'

    @staticmethod
    def _is_project_initialization(operation: ShotGridStorageOperation) -> bool:
        return operation.operation_type == 'initialize_project' or (
            operation.operation_type == 'reconcile_directory' and operation.aggregate_type == 'project'
        )

    @staticmethod
    def _is_shot_renumber(operation: ShotGridStorageOperation) -> bool:
        return operation.operation_type == 'renumber_shot_directories' and operation.aggregate_type == 'scene'

    @staticmethod
    def _completes_task_start(operation: ShotGridStorageOperation) -> bool:
        return (
            operation.aggregate_type == 'shot'
            and operation.operation_type in {'ensure_shot_directory', 'reconcile_directory'}
        ) or (
            operation.aggregate_type == 'asset'
            and operation.operation_type in {'ensure_asset_directory', 'reconcile_directory'}
        )

    @classmethod
    def _advance_preparing_tasks_statement(
        cls,
        operation: ShotGridStorageOperation,
        now: datetime,
    ) -> Any:
        conditions = [
            ShotGridTask.project_id == operation.project_id,
            ShotGridTask.task_status == 'preparing',
            ShotGridTask.del_flag == '0',
        ]
        if operation.aggregate_type == 'shot':
            conditions.extend(
                (
                    ShotGridTask.shot_id == operation.aggregate_id,
                    ShotGridTask.task_kind == 'shot_video',
                )
            )
        else:
            asset_item_ids = select(ShotGridAssetItem.asset_item_id).where(
                ShotGridAssetItem.project_id == operation.project_id,
                ShotGridAssetItem.asset_id == operation.aggregate_id,
                ShotGridAssetItem.lifecycle_status == 'active',
                ShotGridAssetItem.del_flag == '0',
            )
            conditions.extend(
                (
                    ShotGridTask.asset_item_id.in_(asset_item_ids),
                    ShotGridTask.task_kind == 'asset_image',
                )
            )
        return (
            update(ShotGridTask)
            .where(*conditions)
            .values(
                task_status='in_progress',
                update_by=cls._operation_actor(operation),
                update_time=now,
                lock_version=ShotGridTask.lock_version + 1,
            )
        )

    @classmethod
    async def _apply_shot_renumber(
        cls,
        db: AsyncSession,
        *,
        operation: ShotGridStorageOperation,
        now: datetime,
    ) -> None:
        """目录迁移成功后，以两阶段临时编号原子切换镜头身份快照。"""

        payload = operation.operation_payload
        items = payload.get('items') if isinstance(payload, dict) else None
        if (
            not isinstance(payload, dict)
            or payload.get('schemaVersion') not in {1, 2}
            or payload.get('sceneId') != operation.aggregate_id
            or not isinstance(items, list)
            or not 1 <= len(items) <= cls.MAX_RENUMBER_SHOTS
        ):
            raise ValueError('镜头重编号目录操作载荷无效')
        shot_ids = [item.get('shotId') for item in items if isinstance(item, dict)]
        if (
            len(shot_ids) != len(items)
            or len(set(shot_ids)) != len(items)
            or any(not isinstance(i, int) for i in shot_ids)
        ):
            raise ValueError('镜头重编号目录操作载荷无效')
        shots = list(
            (
                await db.execute(
                    select(ShotGridShot)
                    .where(
                        ShotGridShot.project_id == operation.project_id,
                        ShotGridShot.scene_id == operation.aggregate_id,
                        ShotGridShot.shot_id.in_(shot_ids),
                        ShotGridShot.lifecycle_status == 'active',
                        ShotGridShot.del_flag == '0',
                    )
                    .order_by(ShotGridShot.shot_id)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        if len(shots) != len(items):
            raise ValueError('镜头重编号目标已发生变化')
        shot_by_id = {shot.shot_id: shot for shot in shots}
        temporary_numbers: set[int] = set()
        target_numbers: set[int] = set()
        for item in items:
            shot = shot_by_id.get(item.get('shotId'))
            source_no = item.get('sourceShotNo')
            target_no = item.get('targetShotNo')
            temporary_no = item.get('temporaryShotNo')
            source_dir = item.get('sourceDirName')
            target_dir = item.get('targetDirName')
            expected_lock = item.get('expectedLockVersion')
            if (
                shot is None
                or not all(isinstance(value, int) for value in (source_no, target_no, temporary_no, expected_lock))
                or source_no <= 0
                or target_no <= 0
                or temporary_no <= 0
                or not (
                    (isinstance(source_dir, str) and isinstance(target_dir, str))
                    or (
                        payload.get('schemaVersion') == cls.LAZY_DIRECTORY_RENUMBER_SCHEMA
                        and source_dir is None
                        and target_dir is None
                    )
                )
                or (source_no == target_no and source_dir == target_dir)
                or temporary_no in temporary_numbers
                or target_no in target_numbers
                or shot.shot_no != source_no
                or shot.storage_dir_name != source_dir
                or shot.lock_version != expected_lock
            ):
                raise ValueError('镜头重编号目标已发生变化')
            temporary_numbers.add(temporary_no)
            target_numbers.add(target_no)

        for item in items:
            result = await db.execute(
                update(ShotGridShot)
                .where(
                    ShotGridShot.shot_id == item['shotId'],
                    ShotGridShot.project_id == operation.project_id,
                    ShotGridShot.scene_id == operation.aggregate_id,
                    ShotGridShot.shot_no == item['sourceShotNo'],
                    ShotGridShot.lock_version == item['expectedLockVersion'],
                    ShotGridShot.lifecycle_status == 'active',
                    ShotGridShot.del_flag == '0',
                )
                .values(shot_no=item['temporaryShotNo'])
            )
            if result.rowcount != 1:
                raise ValueError('镜头重编号目标已发生变化')
        for item in items:
            result = await db.execute(
                update(ShotGridShot)
                .where(
                    ShotGridShot.shot_id == item['shotId'],
                    ShotGridShot.project_id == operation.project_id,
                    ShotGridShot.scene_id == operation.aggregate_id,
                    ShotGridShot.shot_no == item['temporaryShotNo'],
                    ShotGridShot.lock_version == item['expectedLockVersion'],
                    ShotGridShot.lifecycle_status == 'active',
                    ShotGridShot.del_flag == '0',
                )
                .values(
                    shot_no=item['targetShotNo'],
                    storage_dir_name=item['targetDirName'],
                    sort_order=item['targetShotNo'] * 10,
                    update_by=operation.create_by,
                    update_time=now,
                    lock_version=ShotGridShot.lock_version + 1,
                )
            )
            if result.rowcount != 1:
                raise ValueError('镜头重编号目标已发生变化')

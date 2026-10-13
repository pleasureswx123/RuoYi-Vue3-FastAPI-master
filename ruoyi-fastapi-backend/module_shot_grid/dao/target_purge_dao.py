"""独立目标清理队列；不自动接管失租的在途文件删除。"""

from datetime import datetime

from sqlalchemy import Select, and_, delete, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.entity.do.file_do import SysFileReference
from module_shot_grid.entity.do.target_purge_do import ShotGridTargetPurge, ShotGridTargetPurgePath
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.target_purge_paths import paths_overlap


class ShotGridTargetPurgeDao:
    @staticmethod
    async def require_schema(db: AsyncSession) -> None:
        ready = await db.scalar(
            text(
                "SELECT count(*) = 2 FROM pg_trigger WHERE tgname IN ('trg_sg_shot_purge_guard', 'trg_sg_asset_purge_guard') AND NOT tgisinternal AND tgenabled <> 'D'"
            )
        )
        if not ready:
            raise shot_grid_error(409, 'SG_TARGET_PURGE_UPGRADE_REQUIRED', '永久删除需要先完成数据库 20261013_40 升级')

    @staticmethod
    async def query_page(db: AsyncSession, project_id: int, query: object) -> tuple[list, int]:
        statement = select(ShotGridTargetPurge).where(
            ShotGridTargetPurge.project_id == project_id,
            ShotGridTargetPurge.target_kind == query.target_kind,
        )
        if query.purge_id is not None:
            statement = statement.where(ShotGridTargetPurge.purge_id == query.purge_id)
        if query.unfinished_only:
            statement = statement.where(ShotGridTargetPurge.purge_status != 'succeeded')
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = list(
            await db.scalars(
                statement.order_by(ShotGridTargetPurge.purge_id.desc())
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        )
        return rows, int(total or 0)

    @staticmethod
    async def assert_paths_available(db: AsyncSession, project_id: int, paths: list[str]) -> None:
        """调用者持有项目锁，成功清理才会释放占用。"""
        reserved = list(
            await db.scalars(
                select(ShotGridTargetPurgePath.path_key).where(ShotGridTargetPurgePath.project_id == project_id)
            )
        )
        if any(paths_overlap(path, existing) for path in paths for existing in reserved):
            raise shot_grid_error(
                409, 'SG_TARGET_PURGE_PATH_RESERVED', '旧目标文件仍在清理中，清理完成后才能复用此编号或名称'
            )

    @staticmethod
    async def assert_project_clear(db: AsyncSession, project_id: int) -> None:
        if (
            await db.scalar(
                select(ShotGridTargetPurge.purge_id)
                .where(ShotGridTargetPurge.project_id == project_id, ShotGridTargetPurge.purge_status != 'succeeded')
                .limit(1)
            )
            is not None
        ):
            raise shot_grid_error(409, 'SG_TARGET_PURGE_PENDING', '项目还有目标文件待清理，暂不能移动或删除项目目录')

    @classmethod
    def build_claim_statement(cls, now: datetime) -> Select[tuple[ShotGridTargetPurge]]:
        due = or_(
            ShotGridTargetPurge.purge_status == 'pending',
            and_(
                ShotGridTargetPurge.purge_status == 'retry_wait',
                ShotGridTargetPurge.next_retry_time <= now,
            ),
        )
        return (
            select(ShotGridTargetPurge)
            .where(due)
            .order_by(ShotGridTargetPurge.next_retry_time.asc().nullsfirst(), ShotGridTargetPurge.purge_id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )

    @classmethod
    async def claim_next(
        cls,
        db: AsyncSession,
        *,
        worker_id: str,
        now: datetime,
        lease_until: datetime,
    ) -> ShotGridTargetPurge | None:
        purge = (await db.execute(cls.build_claim_statement(now))).scalar_one_or_none()
        if purge is None:
            return None
        purge.purge_status = 'processing'
        purge.attempt_count = (purge.attempt_count or 0) + 1
        purge.next_retry_time = None
        purge.lease_owner = worker_id
        purge.lease_until = lease_until
        purge.completed_time = None
        purge.last_error_key = None
        purge.last_error_message = None
        purge.update_time = now
        await db.flush()
        return purge

    @classmethod
    async def renew_lease(
        cls,
        db: AsyncSession,
        *,
        purge_id: int,
        worker_id: str,
        expected_attempt_count: int,
        now: datetime,
        lease_until: datetime,
    ) -> bool:
        result = await db.execute(
            update(ShotGridTargetPurge)
            .where(
                ShotGridTargetPurge.purge_id == purge_id,
                ShotGridTargetPurge.purge_status == 'processing',
                ShotGridTargetPurge.lease_owner == worker_id,
                ShotGridTargetPurge.attempt_count == expected_attempt_count,
                ShotGridTargetPurge.lease_until > now,
            )
            .values(lease_until=lease_until, update_time=now)
        )
        return bool(result.rowcount)

    @classmethod
    async def mark_succeeded(
        cls,
        db: AsyncSession,
        *,
        purge_id: int,
        worker_id: str,
        expected_attempt_count: int,
        now: datetime,
        file_ids: list[str],
    ) -> bool:
        purge = await cls._lock_owned(db, purge_id, worker_id, expected_attempt_count)
        if purge is None:
            return False
        if file_ids:
            remaining_references = await db.scalar(
                select(SysFileReference.reference_id).where(SysFileReference.file_id.in_(file_ids)).limit(1)
            )
            if remaining_references is not None:
                raise RuntimeError('目标独占文件在清理期间出现新的业务引用')
            await FileInfoDao.purge_file_infos(db, file_ids)
        purge.purge_status = 'succeeded'
        purge.next_retry_time = None
        purge.lease_owner = None
        purge.lease_until = None
        purge.completed_time = now
        purge.last_error_key = None
        purge.last_error_message = None
        purge.update_time = now
        await db.execute(delete(ShotGridTargetPurgePath).where(ShotGridTargetPurgePath.purge_id == purge_id))
        await db.flush()
        return True

    @classmethod
    async def mark_retry_wait(
        cls,
        db: AsyncSession,
        *,
        purge_id: int,
        worker_id: str,
        expected_attempt_count: int,
        now: datetime,
        next_retry_time: datetime,
        error_key: str,
        error_message: str,
    ) -> bool:
        purge = await cls._lock_owned(db, purge_id, worker_id, expected_attempt_count)
        if purge is None:
            return False
        purge.purge_status = 'retry_wait'
        purge.next_retry_time = next_retry_time
        purge.lease_owner = None
        purge.lease_until = None
        purge.completed_time = None
        purge.last_error_key = error_key
        purge.last_error_message = error_message
        purge.update_time = now
        await db.flush()
        return True

    @classmethod
    async def mark_failed(
        cls,
        db: AsyncSession,
        *,
        purge_id: int,
        worker_id: str,
        expected_attempt_count: int,
        now: datetime,
        error_key: str,
        error_message: str,
    ) -> bool:
        purge = await cls._lock_owned(db, purge_id, worker_id, expected_attempt_count)
        if purge is None:
            return False
        purge.purge_status = 'failed'
        purge.next_retry_time = None
        purge.lease_owner = None
        purge.lease_until = None
        purge.completed_time = now
        purge.last_error_key = error_key
        purge.last_error_message = error_message
        purge.update_time = now
        await db.flush()
        return True

    @classmethod
    async def _lock_owned(
        cls,
        db: AsyncSession,
        purge_id: int,
        worker_id: str,
        expected_attempt_count: int,
    ) -> ShotGridTargetPurge | None:
        return await db.scalar(
            select(ShotGridTargetPurge)
            .where(
                ShotGridTargetPurge.purge_id == purge_id,
                ShotGridTargetPurge.purge_status == 'processing',
                ShotGridTargetPurge.lease_owner == worker_id,
                ShotGridTargetPurge.attempt_count == expected_attempt_count,
                ShotGridTargetPurge.lease_until > datetime.now(),
            )
            .with_for_update()
        )

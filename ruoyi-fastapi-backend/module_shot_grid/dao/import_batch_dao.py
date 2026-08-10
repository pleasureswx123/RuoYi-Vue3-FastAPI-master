from datetime import datetime
from typing import Any, Literal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.entity.do.import_do import ShotGridImportBatch


class ShotGridImportBatchDao:
    """Shot Grid 导入批次数据访问；事务由 Service 统一管理。"""

    @classmethod
    async def create_preview_batch(  # noqa: PLR0913
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        import_type: Literal['shot', 'asset'],
        original_file_name: str,
        file_sha256: str,
        template_version: str,
        total_rows: int,
        valid_rows: int,
        warning_rows: int,
        error_rows: int,
        preview_token_hash: str,
        preview_expires_time: datetime,
        previewed_by: int,
    ) -> ShotGridImportBatch:
        batch = ShotGridImportBatch(
            project_id=project_id,
            import_type=import_type,
            original_file_name=original_file_name,
            file_sha256=file_sha256,
            template_version=template_version,
            batch_status='previewed',
            total_rows=total_rows,
            valid_rows=valid_rows,
            warning_rows=warning_rows,
            error_rows=error_rows,
            committed_rows=0,
            preview_token_hash=preview_token_hash,
            preview_expires_time=preview_expires_time,
            previewed_by=previewed_by,
        )
        db.add(batch)
        await db.flush()
        return batch

    @staticmethod
    async def get_for_update(db: AsyncSession, project_id: int, batch_id: int) -> ShotGridImportBatch | None:
        statement = (
            select(ShotGridImportBatch)
            .where(
                ShotGridImportBatch.project_id == project_id,
                ShotGridImportBatch.batch_id == batch_id,
            )
            .with_for_update()
        )
        return (await db.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def lock_idempotency(db: AsyncSession, lock_id: int) -> None:
        """在当前 PostgreSQL 事务内串行化同一幂等键的提交。"""
        await db.execute(select(func.pg_advisory_xact_lock(lock_id)))

    @staticmethod
    async def find_by_idempotency(
        db: AsyncSession,
        project_id: int,
        import_type: Literal['shot', 'asset'],
        committed_by: int,
        idempotency_key: str,
    ) -> ShotGridImportBatch | None:
        statement = select(ShotGridImportBatch).where(
            ShotGridImportBatch.project_id == project_id,
            ShotGridImportBatch.import_type == import_type,
            ShotGridImportBatch.committed_by == committed_by,
            ShotGridImportBatch.idempotency_key == idempotency_key,
        )
        return (await db.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def find_by_token_hash(
        db: AsyncSession,
        project_id: int,
        import_type: Literal['shot', 'asset'],
        preview_token_hash: str,
    ) -> ShotGridImportBatch | None:
        statement = select(ShotGridImportBatch).where(
            ShotGridImportBatch.project_id == project_id,
            ShotGridImportBatch.import_type == import_type,
            ShotGridImportBatch.preview_token_hash == preview_token_hash,
        )
        return (await db.execute(statement)).scalar_one_or_none()

    @staticmethod
    def mark_committing(
        batch: ShotGridImportBatch,
        *,
        committed_by: int,
        idempotency_key: str,
        selection_hash: str,
    ) -> None:
        batch.batch_status = 'committing'
        batch.committed_by = committed_by
        batch.idempotency_key = idempotency_key
        batch.selection_hash = selection_hash
        batch.last_error_key = None
        batch.last_error_message = None
        batch.update_time = datetime.now()

    @staticmethod
    def mark_committed(
        batch: ShotGridImportBatch,
        *,
        committed_rows: int,
        selection_hash: str,
        result_summary: dict[str, Any],
    ) -> None:
        now = datetime.now()
        batch.batch_status = 'committed'
        batch.committed_rows = committed_rows
        batch.selection_hash = selection_hash
        batch.result_summary = result_summary
        batch.committed_time = now
        batch.update_time = now

    @staticmethod
    async def mark_failed(
        db: AsyncSession,
        *,
        project_id: int,
        batch_id: int,
        committed_by: int,
        idempotency_key: str,
        selection_hash: str,
        error_key: str,
        error_message: str,
    ) -> None:
        statement = (
            update(ShotGridImportBatch)
            .where(
                ShotGridImportBatch.project_id == project_id,
                ShotGridImportBatch.batch_id == batch_id,
                ShotGridImportBatch.batch_status == 'previewed',
            )
            .values(
                batch_status='failed',
                committed_by=committed_by,
                idempotency_key=idempotency_key,
                selection_hash=selection_hash,
                result_summary=None,
                committed_time=None,
                last_error_key=error_key[:100],
                last_error_message=error_message[:500],
                update_time=datetime.now(),
            )
        )
        await db.execute(statement)

    @staticmethod
    async def expire_preview(db: AsyncSession, project_id: int, batch_id: int) -> None:
        statement = (
            update(ShotGridImportBatch)
            .where(
                ShotGridImportBatch.project_id == project_id,
                ShotGridImportBatch.batch_id == batch_id,
                ShotGridImportBatch.batch_status == 'previewed',
            )
            .values(batch_status='expired', update_time=datetime.now())
        )
        await db.execute(statement)

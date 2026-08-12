from typing import Any

from sqlalchemy import asc, delete, desc, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.file_do import SysFileInfo
from module_admin.entity.do.user_do import SysUser
from module_shot_grid.entity.do.project_do import ShotGridProject, ShotGridProjectMember, ShotGridShot
from module_shot_grid.entity.do.review_do import (
    ShotGridNote,
    ShotGridNoteReply,
    ShotGridReviewAction,
    ShotGridReviewList,
    ShotGridReviewListVersion,
)
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridMediaDerivation, ShotGridVersion, ShotGridVersionFile
from module_shot_grid.entity.vo.review_vo import (
    ShotGridNoteListQueryModel,
    ShotGridNoteReplyListQueryModel,
    ShotGridReviewActionQueryModel,
    ShotGridReviewListQueryModel,
    ShotGridVersionListQueryModel,
)


class ShotGridReviewDao:
    """版本读取、意见和自动审核单数据访问。"""

    @staticmethod
    def _review_media_projection() -> tuple[Any, Any]:
        thumbnail_file_id = (
            select(ShotGridVersionFile.file_id)
            .where(
                ShotGridVersionFile.version_id == ShotGridVersion.version_id,
                ShotGridVersionFile.file_role == 'thumbnail',
            )
            .order_by(ShotGridVersionFile.sort_order, ShotGridVersionFile.file_id)
            .limit(1)
            .correlate(ShotGridVersion)
            .scalar_subquery()
        )
        derivation_status = (
            select(ShotGridMediaDerivation.derivation_status)
            .where(ShotGridMediaDerivation.version_id == ShotGridVersion.version_id)
            .correlate(ShotGridVersion)
            .scalar_subquery()
        )
        return thumbnail_file_id, derivation_status

    @classmethod
    async def get_task_context(cls, db: AsyncSession, task_id: int) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridTask.task_id,
                        ShotGridTask.project_id,
                        ShotGridTask.task_kind,
                        ShotGridTask.task_status,
                        ShotGridTask.assignee_user_id,
                        ShotGridTask.shot_id,
                        ShotGridTask.asset_item_id,
                        ShotGridTask.lock_version,
                    ).where(ShotGridTask.task_id == task_id, ShotGridTask.del_flag == '0')
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @classmethod
    async def get_mine_review_lists(
        cls, db: AsyncSession, user_id: int, query: ShotGridReviewListQueryModel, has_all_scope: bool
    ) -> tuple[list[dict[str, Any]], int]:
        thumbnail_file_id, derivation_status = cls._review_media_projection()
        relation_count = (
            select(func.count(ShotGridReviewListVersion.version_id))
            .where(ShotGridReviewListVersion.review_list_id == ShotGridReviewList.review_list_id)
            .correlate(ShotGridReviewList)
            .scalar_subquery()
        )
        statement = (
            select(
                ShotGridReviewList.review_list_id,
                ShotGridReviewList.project_id,
                ShotGridProject.project_code,
                ShotGridProject.project_name,
                ShotGridReviewList.review_list_name,
                ShotGridReviewList.description,
                ShotGridReviewList.review_date,
                ShotGridReviewList.review_mode,
                ShotGridReviewList.review_status,
                ShotGridReviewList.auto_version_id,
                ShotGridVersion.task_id,
                ShotGridVersion.version_no,
                ShotGridVersion.version_status,
                relation_count.label('version_count'),
                ShotGridReviewList.lock_version,
                thumbnail_file_id.label('thumbnail_file_id'),
                derivation_status.label('media_derivation_status'),
                ShotGridReviewList.create_time,
            )
            .join(ShotGridProject, ShotGridProject.project_id == ShotGridReviewList.project_id)
            .outerjoin(ShotGridVersion, ShotGridVersion.version_id == ShotGridReviewList.auto_version_id)
            .where(
                ShotGridReviewList.del_flag == '0',
                ShotGridReviewList.review_status == 'active',
                ShotGridProject.del_flag == '0',
                ShotGridProject.project_status != 'archived',
            )
        )
        if not has_all_scope:
            statement = statement.join(
                ShotGridProjectMember,
                (ShotGridProjectMember.project_id == ShotGridReviewList.project_id)
                & (ShotGridProjectMember.user_id == user_id)
                & (ShotGridProjectMember.project_role == 'director')
                & (ShotGridProjectMember.member_status == 'active'),
            )
        if query.review_mode:
            statement = statement.where(ShotGridReviewList.review_mode == query.review_mode)
        if query.keyword:
            statement = statement.where(ShotGridReviewList.review_list_name.ilike(f'%{query.keyword.strip()}%'))
        statement = statement.order_by(ShotGridReviewList.create_time.desc(), ShotGridReviewList.review_list_id.desc())
        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        rows = (
            await db.execute(statement.offset((query.page_num - 1) * query.page_size).limit(query.page_size))
        ).mappings()
        return [dict(row) for row in rows], total

    @classmethod
    async def get_recent_mine_versions(
        cls, db: AsyncSession, user_id: int, query: ShotGridVersionListQueryModel
    ) -> tuple[list[dict[str, Any]], int]:
        statement = (
            select(
                ShotGridVersion.version_id,
                ShotGridVersion.project_id,
                ShotGridVersion.task_id,
                ShotGridVersion.version_no,
                ShotGridVersion.version_status,
                ShotGridVersion.changelog,
                ShotGridVersion.submitted_by,
                SysUser.nick_name.label('submitter_name'),
                ShotGridVersion.submitted_time,
                ShotGridVersion.generated_at_ms,
                ShotGridVersion.lock_version,
            )
            .join(ShotGridProject, ShotGridProject.project_id == ShotGridVersion.project_id)
            .join(
                ShotGridProjectMember,
                (ShotGridProjectMember.project_id == ShotGridVersion.project_id)
                & (ShotGridProjectMember.user_id == user_id)
                & (ShotGridProjectMember.member_status == 'active'),
            )
            .outerjoin(SysUser, SysUser.user_id == ShotGridVersion.submitted_by)
            .where(
                ShotGridVersion.submitted_by == user_id,
                ShotGridProject.del_flag == '0',
                ShotGridProject.project_status != 'archived',
            )
        )
        if query.version_status:
            statement = statement.where(ShotGridVersion.version_status == query.version_status)
        statement = statement.order_by(ShotGridVersion.submitted_time.desc(), ShotGridVersion.version_id.desc())
        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        rows = (
            await db.execute(statement.offset((query.page_num - 1) * query.page_size).limit(query.page_size))
        ).mappings()
        return [dict(row) for row in rows], total

    @classmethod
    async def get_version_context(cls, db: AsyncSession, version_id: int) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridVersion.version_id,
                        ShotGridVersion.project_id,
                        ShotGridVersion.task_id,
                        ShotGridVersion.version_no,
                        ShotGridVersion.version_status,
                        ShotGridVersion.lock_version,
                        ShotGridTask.task_kind,
                        ShotGridTask.task_status,
                        ShotGridTask.assignee_user_id,
                        ShotGridTask.shot_id,
                        ShotGridTask.asset_item_id,
                        ShotGridShot.duration_ms.label('shot_duration_ms'),
                    )
                    .join(ShotGridTask, ShotGridTask.task_id == ShotGridVersion.task_id)
                    .outerjoin(ShotGridShot, ShotGridShot.shot_id == ShotGridTask.shot_id)
                    .where(ShotGridVersion.version_id == version_id, ShotGridTask.del_flag == '0')
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @classmethod
    async def get_note_context(cls, db: AsyncSession, note_id: int) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridNote.note_id,
                        ShotGridNote.project_id,
                        ShotGridNote.version_id,
                        ShotGridNote.reviewer_user_id,
                        ShotGridNote.note_status,
                        ShotGridVersion.task_id,
                        ShotGridVersion.version_status,
                        ShotGridTask.task_kind,
                        ShotGridTask.task_status,
                        ShotGridTask.assignee_user_id,
                        ShotGridTask.shot_id,
                        ShotGridTask.asset_item_id,
                    )
                    .join(ShotGridVersion, ShotGridVersion.version_id == ShotGridNote.version_id)
                    .join(ShotGridTask, ShotGridTask.task_id == ShotGridVersion.task_id)
                    .where(ShotGridNote.note_id == note_id, ShotGridTask.del_flag == '0')
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @classmethod
    async def get_review_list_context(cls, db: AsyncSession, review_list_id: int) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridReviewList.review_list_id,
                        ShotGridReviewList.project_id,
                        ShotGridReviewList.review_mode,
                        ShotGridReviewList.review_status,
                        ShotGridReviewList.auto_version_id,
                    ).where(
                        ShotGridReviewList.review_list_id == review_list_id,
                        ShotGridReviewList.del_flag == '0',
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @classmethod
    async def get_task_versions(
        cls,
        db: AsyncSession,
        project_id: int,
        task_id: int,
        query: ShotGridVersionListQueryModel,
    ) -> tuple[list[dict[str, Any]], int]:
        statement = (
            select(
                ShotGridVersion.version_id,
                ShotGridVersion.project_id,
                ShotGridVersion.task_id,
                ShotGridVersion.version_no,
                ShotGridVersion.version_status,
                ShotGridVersion.changelog,
                ShotGridVersion.submitted_by,
                SysUser.nick_name.label('submitter_name'),
                ShotGridVersion.submitted_time,
                ShotGridVersion.generated_at_ms,
                ShotGridVersion.lock_version,
            )
            .outerjoin(SysUser, SysUser.user_id == ShotGridVersion.submitted_by)
            .where(ShotGridVersion.project_id == project_id, ShotGridVersion.task_id == task_id)
        )
        if query.version_status:
            statement = statement.where(ShotGridVersion.version_status == query.version_status)
        order_column = (
            ShotGridVersion.version_no if query.order_by_column == 'versionNo' else ShotGridVersion.submitted_time
        )
        statement = statement.order_by(
            asc(order_column) if query.is_asc == 'ascending' else desc(order_column),
            ShotGridVersion.version_id.desc(),
        )
        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        rows = (
            await db.execute(statement.offset((query.page_num - 1) * query.page_size).limit(query.page_size))
        ).mappings()
        return [dict(row) for row in rows], total

    @classmethod
    async def get_version_row(cls, db: AsyncSession, project_id: int, version_id: int) -> dict[str, Any] | None:
        media_derivation_status = (
            select(ShotGridMediaDerivation.derivation_status)
            .where(ShotGridMediaDerivation.version_id == ShotGridVersion.version_id)
            .correlate(ShotGridVersion)
            .scalar_subquery()
        )
        row = (
            (
                await db.execute(
                    select(
                        ShotGridVersion.version_id,
                        ShotGridVersion.project_id,
                        ShotGridVersion.task_id,
                        ShotGridVersion.version_no,
                        ShotGridVersion.version_status,
                        ShotGridVersion.changelog,
                        ShotGridVersion.ai_params,
                        ShotGridVersion.submitted_by,
                        SysUser.nick_name.label('submitter_name'),
                        ShotGridVersion.submitted_time,
                        ShotGridVersion.generated_at_ms,
                        ShotGridVersion.lock_version,
                        media_derivation_status.label('media_derivation_status'),
                    )
                    .outerjoin(SysUser, SysUser.user_id == ShotGridVersion.submitted_by)
                    .where(ShotGridVersion.project_id == project_id, ShotGridVersion.version_id == version_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @classmethod
    async def get_version_files(cls, db: AsyncSession, version_id: int) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(
                    ShotGridVersionFile.file_id,
                    SysFileInfo.original_name,
                    ShotGridVersionFile.business_file_name,
                    ShotGridVersionFile.file_role.label('role'),
                    ShotGridVersionFile.is_primary,
                    ShotGridVersionFile.sort_order,
                    SysFileInfo.content_type,
                    SysFileInfo.file_size,
                )
                .join(SysFileInfo, SysFileInfo.file_id == ShotGridVersionFile.file_id)
                .where(
                    ShotGridVersionFile.version_id == version_id,
                    SysFileInfo.status == 'active',
                    SysFileInfo.del_flag == '0',
                )
                .order_by(ShotGridVersionFile.sort_order, ShotGridVersionFile.file_id, ShotGridVersionFile.file_role)
            )
        ).mappings()
        return [dict(row) for row in rows]

    @classmethod
    async def get_auto_review_summary(cls, db: AsyncSession, version_id: int) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridReviewList.review_list_id,
                        ShotGridReviewList.review_list_name,
                        ShotGridReviewList.review_status,
                        ShotGridReviewList.lock_version,
                    ).where(
                        ShotGridReviewList.auto_version_id == version_id,
                        ShotGridReviewList.review_mode == 'auto_single',
                        ShotGridReviewList.del_flag == '0',
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @classmethod
    async def get_auto_review_lists(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridReviewListQueryModel,
    ) -> tuple[list[dict[str, Any]], int]:
        thumbnail_file_id, derivation_status = cls._review_media_projection()
        statement = (
            select(
                ShotGridReviewList.review_list_id,
                ShotGridReviewList.project_id,
                ShotGridReviewList.review_list_name,
                ShotGridReviewList.description,
                ShotGridReviewList.review_date,
                ShotGridReviewList.review_mode,
                ShotGridReviewList.review_status,
                ShotGridReviewList.auto_version_id,
                ShotGridVersion.task_id,
                ShotGridVersion.version_no,
                ShotGridVersion.version_status,
                thumbnail_file_id.label('thumbnail_file_id'),
                derivation_status.label('media_derivation_status'),
                ShotGridReviewList.lock_version,
                ShotGridReviewList.create_time,
            )
            .join(ShotGridVersion, ShotGridVersion.version_id == ShotGridReviewList.auto_version_id)
            .where(
                ShotGridReviewList.project_id == project_id,
                ShotGridReviewList.review_mode == 'auto_single',
                ShotGridReviewList.del_flag == '0',
            )
        )
        if query.review_status:
            statement = statement.where(ShotGridReviewList.review_status == query.review_status)
        if query.task_id:
            statement = statement.where(ShotGridVersion.task_id == query.task_id)
        if query.version_id:
            statement = statement.where(ShotGridVersion.version_id == query.version_id)
        if query.keyword:
            statement = statement.where(ShotGridReviewList.review_list_name.ilike(f'%{query.keyword.strip()}%'))
        order_column = (
            ShotGridReviewList.create_time if query.order_by_column == 'createTime' else ShotGridReviewList.review_date
        )
        statement = statement.order_by(
            asc(order_column) if query.is_asc == 'ascending' else desc(order_column),
            ShotGridReviewList.review_list_id.desc(),
        )
        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        rows = (
            await db.execute(statement.offset((query.page_num - 1) * query.page_size).limit(query.page_size))
        ).mappings()
        return [dict(row) for row in rows], total

    @classmethod
    async def get_review_lists(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridReviewListQueryModel,
    ) -> tuple[list[dict[str, Any]], int]:
        thumbnail_file_id, derivation_status = cls._review_media_projection()
        relation_count = (
            select(func.count(ShotGridReviewListVersion.version_id))
            .where(ShotGridReviewListVersion.review_list_id == ShotGridReviewList.review_list_id)
            .correlate(ShotGridReviewList)
            .scalar_subquery()
        )
        statement = (
            select(
                ShotGridReviewList.review_list_id,
                ShotGridReviewList.project_id,
                ShotGridReviewList.review_list_name,
                ShotGridReviewList.description,
                ShotGridReviewList.review_date,
                ShotGridReviewList.review_mode,
                ShotGridReviewList.review_status,
                ShotGridReviewList.auto_version_id,
                ShotGridVersion.task_id,
                ShotGridVersion.version_no,
                ShotGridVersion.version_status,
                relation_count.label('version_count'),
                thumbnail_file_id.label('thumbnail_file_id'),
                derivation_status.label('media_derivation_status'),
                ShotGridReviewList.lock_version,
                ShotGridReviewList.create_time,
            )
            .outerjoin(ShotGridVersion, ShotGridVersion.version_id == ShotGridReviewList.auto_version_id)
            .where(ShotGridReviewList.project_id == project_id, ShotGridReviewList.del_flag == '0')
        )
        if query.review_mode:
            statement = statement.where(ShotGridReviewList.review_mode == query.review_mode)
        if query.review_status:
            statement = statement.where(ShotGridReviewList.review_status == query.review_status)
        if query.task_id:
            statement = statement.where(ShotGridVersion.task_id == query.task_id)
        if query.version_id:
            statement = statement.where(ShotGridVersion.version_id == query.version_id)
        if query.keyword:
            statement = statement.where(ShotGridReviewList.review_list_name.ilike(f'%{query.keyword.strip()}%'))
        order_column = (
            ShotGridReviewList.create_time if query.order_by_column == 'createTime' else ShotGridReviewList.review_date
        )
        statement = statement.order_by(
            asc(order_column) if query.is_asc == 'ascending' else desc(order_column),
            ShotGridReviewList.review_list_id.desc(),
        )
        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        rows = (
            await db.execute(statement.offset((query.page_num - 1) * query.page_size).limit(query.page_size))
        ).mappings()
        return [dict(row) for row in rows], total

    @classmethod
    async def get_review_list_row(
        cls,
        db: AsyncSession,
        project_id: int,
        review_list_id: int,
    ) -> dict[str, Any] | None:
        thumbnail_file_id, derivation_status = cls._review_media_projection()
        relation_count = (
            select(func.count(ShotGridReviewListVersion.version_id))
            .where(ShotGridReviewListVersion.review_list_id == ShotGridReviewList.review_list_id)
            .correlate(ShotGridReviewList)
            .scalar_subquery()
        )
        row = (
            (
                await db.execute(
                    select(
                        ShotGridReviewList.review_list_id,
                        ShotGridReviewList.project_id,
                        ShotGridReviewList.review_list_name,
                        ShotGridReviewList.description,
                        ShotGridReviewList.review_date,
                        ShotGridReviewList.review_mode,
                        ShotGridReviewList.review_status,
                        ShotGridReviewList.auto_version_id,
                        ShotGridVersion.task_id,
                        ShotGridVersion.version_no,
                        ShotGridVersion.version_status,
                        relation_count.label('version_count'),
                        thumbnail_file_id.label('thumbnail_file_id'),
                        derivation_status.label('media_derivation_status'),
                        ShotGridReviewList.lock_version,
                        ShotGridReviewList.create_time,
                    )
                    .outerjoin(ShotGridVersion, ShotGridVersion.version_id == ShotGridReviewList.auto_version_id)
                    .where(
                        ShotGridReviewList.review_list_id == review_list_id,
                        ShotGridReviewList.project_id == project_id,
                        ShotGridReviewList.del_flag == '0',
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @classmethod
    async def get_manual_review_versions(
        cls, db: AsyncSession, project_id: int, review_list_id: int
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(
                    ShotGridVersion.version_id,
                    ShotGridVersion.project_id,
                    ShotGridVersion.task_id,
                    ShotGridVersion.version_no,
                    ShotGridVersion.version_status,
                    ShotGridVersion.changelog,
                    ShotGridVersion.submitted_by,
                    SysUser.nick_name.label('submitter_name'),
                    ShotGridVersion.submitted_time,
                    ShotGridVersion.generated_at_ms,
                    ShotGridVersion.lock_version,
                )
                .join(ShotGridReviewListVersion, ShotGridReviewListVersion.version_id == ShotGridVersion.version_id)
                .outerjoin(SysUser, SysUser.user_id == ShotGridVersion.submitted_by)
                .where(
                    ShotGridReviewListVersion.review_list_id == review_list_id,
                    ShotGridVersion.project_id == project_id,
                )
                .order_by(ShotGridReviewListVersion.sort_order, ShotGridVersion.version_id)
            )
        ).mappings()
        return [dict(row) for row in rows]

    @classmethod
    async def get_versions_for_manual_review(
        cls, db: AsyncSession, project_id: int, version_ids: list[int]
    ) -> list[ShotGridVersion]:
        return list(
            (
                await db.execute(
                    select(ShotGridVersion)
                    .where(
                        ShotGridVersion.project_id == project_id,
                        ShotGridVersion.version_id.in_(version_ids),
                        ShotGridVersion.version_status == 'pending_review',
                    )
                    .with_for_update()
                )
            ).scalars()
        )

    @classmethod
    async def get_review_list_for_update(
        cls, db: AsyncSession, project_id: int, review_list_id: int
    ) -> ShotGridReviewList | None:
        return (
            await db.execute(
                select(ShotGridReviewList)
                .where(
                    ShotGridReviewList.project_id == project_id,
                    ShotGridReviewList.review_list_id == review_list_id,
                    ShotGridReviewList.del_flag == '0',
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @classmethod
    async def add_manual_review_list(cls, db: AsyncSession, review_list: ShotGridReviewList) -> ShotGridReviewList:
        db.add(review_list)
        await db.flush()
        return review_list

    @classmethod
    async def add_manual_review_versions(cls, db: AsyncSession, relations: list[ShotGridReviewListVersion]) -> None:
        db.add_all(relations)
        await db.flush()

    @classmethod
    async def remove_manual_review_version(cls, db: AsyncSession, review_list_id: int, version_id: int) -> int:
        result = await db.execute(
            delete(ShotGridReviewListVersion).where(
                ShotGridReviewListVersion.review_list_id == review_list_id,
                ShotGridReviewListVersion.version_id == version_id,
            )
        )
        return int(result.rowcount or 0)

    @classmethod
    async def reorder_manual_review_versions(
        cls, db: AsyncSession, review_list_id: int, orders: list[tuple[int, int]]
    ) -> None:
        # 契约要求最终顺序为 0..n-1；先移到 n..2n-1，避免交换时唯一索引瞬时冲突。
        temporary_offset = len(orders)
        for index, (version_id, _) in enumerate(orders):
            await db.execute(
                update(ShotGridReviewListVersion)
                .where(
                    ShotGridReviewListVersion.review_list_id == review_list_id,
                    ShotGridReviewListVersion.version_id == version_id,
                )
                .values(sort_order=temporary_offset + index)
            )
        await db.flush()
        for version_id, sort_order in orders:
            await db.execute(
                update(ShotGridReviewListVersion)
                .where(
                    ShotGridReviewListVersion.review_list_id == review_list_id,
                    ShotGridReviewListVersion.version_id == version_id,
                )
                .values(sort_order=sort_order)
            )
        await db.flush()

    @classmethod
    async def get_auto_review_list_detail(
        cls,
        db: AsyncSession,
        project_id: int,
        review_list_id: int,
    ) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridReviewList.review_list_id,
                        ShotGridReviewList.project_id,
                        ShotGridReviewList.review_list_name,
                        ShotGridReviewList.description,
                        ShotGridReviewList.review_date,
                        ShotGridReviewList.review_mode,
                        ShotGridReviewList.review_status,
                        ShotGridReviewList.auto_version_id,
                        ShotGridVersion.task_id,
                        ShotGridVersion.version_no,
                        ShotGridVersion.version_status,
                        ShotGridReviewList.lock_version,
                        ShotGridReviewList.create_time,
                    )
                    .join(ShotGridVersion, ShotGridVersion.version_id == ShotGridReviewList.auto_version_id)
                    .where(
                        ShotGridReviewList.review_list_id == review_list_id,
                        ShotGridReviewList.project_id == project_id,
                        ShotGridReviewList.review_mode == 'auto_single',
                        ShotGridReviewList.del_flag == '0',
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @classmethod
    async def get_notes(
        cls,
        db: AsyncSession,
        project_id: int,
        version_id: int,
        query: ShotGridNoteListQueryModel,
    ) -> tuple[list[dict[str, Any]], int]:
        reply_counts = (
            select(ShotGridNoteReply.note_id, func.count(ShotGridNoteReply.reply_id).label('reply_count'))
            .group_by(ShotGridNoteReply.note_id)
            .subquery()
        )
        statement = (
            select(
                ShotGridNote.note_id,
                ShotGridNote.project_id,
                ShotGridNote.version_id,
                ShotGridNote.reviewer_user_id,
                SysUser.nick_name.label('reviewer_name'),
                ShotGridNote.content,
                ShotGridNote.media_time_ms,
                ShotGridNote.annotations,
                ShotGridNote.is_mandatory,
                ShotGridNote.note_status,
                func.coalesce(reply_counts.c.reply_count, 0).label('reply_count'),
                ShotGridNote.create_time,
                ShotGridNote.update_time,
            )
            .outerjoin(SysUser, SysUser.user_id == ShotGridNote.reviewer_user_id)
            .outerjoin(reply_counts, reply_counts.c.note_id == ShotGridNote.note_id)
            .where(ShotGridNote.project_id == project_id, ShotGridNote.version_id == version_id)
        )
        if query.note_status:
            statement = statement.where(ShotGridNote.note_status == query.note_status)
        if query.is_mandatory is not None:
            statement = statement.where(ShotGridNote.is_mandatory == ('1' if query.is_mandatory else '0'))
        if query.keyword:
            statement = statement.where(ShotGridNote.content.ilike(f'%{query.keyword.strip()}%'))
        statement = statement.order_by(
            ShotGridNote.create_time.asc() if query.is_asc == 'ascending' else ShotGridNote.create_time.desc(),
            ShotGridNote.note_id.asc() if query.is_asc == 'ascending' else ShotGridNote.note_id.desc(),
        )
        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        rows = (
            await db.execute(statement.offset((query.page_num - 1) * query.page_size).limit(query.page_size))
        ).mappings()
        return [dict(row) for row in rows], total

    @classmethod
    async def get_note_row(cls, db: AsyncSession, project_id: int, note_id: int) -> dict[str, Any] | None:
        reply_count = (
            select(func.count(ShotGridNoteReply.reply_id))
            .where(ShotGridNoteReply.note_id == ShotGridNote.note_id)
            .correlate(ShotGridNote)
            .scalar_subquery()
        )
        row = (
            (
                await db.execute(
                    select(
                        ShotGridNote.note_id,
                        ShotGridNote.project_id,
                        ShotGridNote.version_id,
                        ShotGridNote.reviewer_user_id,
                        SysUser.nick_name.label('reviewer_name'),
                        ShotGridNote.content,
                        ShotGridNote.media_time_ms,
                        ShotGridNote.annotations,
                        ShotGridNote.is_mandatory,
                        ShotGridNote.note_status,
                        reply_count.label('reply_count'),
                        ShotGridNote.create_time,
                        ShotGridNote.update_time,
                    )
                    .outerjoin(SysUser, SysUser.user_id == ShotGridNote.reviewer_user_id)
                    .where(ShotGridNote.project_id == project_id, ShotGridNote.note_id == note_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @classmethod
    async def get_note_replies(
        cls,
        db: AsyncSession,
        project_id: int,
        note_id: int,
        query: ShotGridNoteReplyListQueryModel,
    ) -> tuple[list[dict[str, Any]], int]:
        statement = (
            select(
                ShotGridNoteReply.reply_id,
                ShotGridNoteReply.project_id,
                ShotGridNoteReply.note_id,
                ShotGridNoteReply.reply_user_id,
                SysUser.nick_name.label('reply_user_name'),
                ShotGridNoteReply.content,
                ShotGridNoteReply.create_time,
            )
            .outerjoin(SysUser, SysUser.user_id == ShotGridNoteReply.reply_user_id)
            .where(ShotGridNoteReply.project_id == project_id, ShotGridNoteReply.note_id == note_id)
            .order_by(
                ShotGridNoteReply.create_time.asc()
                if query.is_asc == 'ascending'
                else ShotGridNoteReply.create_time.desc(),
                ShotGridNoteReply.reply_id.asc() if query.is_asc == 'ascending' else ShotGridNoteReply.reply_id.desc(),
            )
        )
        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        rows = (
            await db.execute(statement.offset((query.page_num - 1) * query.page_size).limit(query.page_size))
        ).mappings()
        return [dict(row) for row in rows], total

    @classmethod
    async def get_review_actions(
        cls,
        db: AsyncSession,
        project_id: int,
        version_id: int,
        query: ShotGridReviewActionQueryModel,
    ) -> tuple[list[dict[str, Any]], int]:
        statement = (
            select(
                ShotGridReviewAction.action_id,
                ShotGridReviewAction.project_id,
                ShotGridReviewAction.version_id,
                ShotGridReviewAction.reviewer_user_id,
                SysUser.nick_name.label('reviewer_name'),
                ShotGridReviewAction.action_type,
                ShotGridReviewAction.from_status,
                ShotGridReviewAction.to_status,
                ShotGridReviewAction.reason,
                ShotGridReviewAction.create_time,
            )
            .outerjoin(SysUser, SysUser.user_id == ShotGridReviewAction.reviewer_user_id)
            .where(
                ShotGridReviewAction.project_id == project_id,
                ShotGridReviewAction.version_id == version_id,
            )
        )
        if query.action_type:
            statement = statement.where(ShotGridReviewAction.action_type == query.action_type)
        statement = statement.order_by(
            ShotGridReviewAction.create_time.asc()
            if query.is_asc == 'ascending'
            else ShotGridReviewAction.create_time.desc(),
            ShotGridReviewAction.action_id.asc()
            if query.is_asc == 'ascending'
            else ShotGridReviewAction.action_id.desc(),
        )
        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        rows = (
            await db.execute(statement.offset((query.page_num - 1) * query.page_size).limit(query.page_size))
        ).mappings()
        return [dict(row) for row in rows], total

    @classmethod
    async def get_task_for_update(
        cls,
        db: AsyncSession,
        project_id: int,
        task_id: int,
    ) -> ShotGridTask | None:
        return (
            await db.execute(
                select(ShotGridTask)
                .where(
                    ShotGridTask.task_id == task_id,
                    ShotGridTask.project_id == project_id,
                    ShotGridTask.del_flag == '0',
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @classmethod
    async def get_version_for_update(
        cls,
        db: AsyncSession,
        project_id: int,
        task_id: int,
        version_id: int,
    ) -> ShotGridVersion | None:
        return (
            await db.execute(
                select(ShotGridVersion)
                .where(
                    ShotGridVersion.version_id == version_id,
                    ShotGridVersion.project_id == project_id,
                    ShotGridVersion.task_id == task_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @classmethod
    async def get_auto_review_list_for_update(
        cls,
        db: AsyncSession,
        project_id: int,
        version_id: int,
    ) -> ShotGridReviewList | None:
        return (
            await db.execute(
                select(ShotGridReviewList)
                .where(
                    ShotGridReviewList.project_id == project_id,
                    ShotGridReviewList.auto_version_id == version_id,
                    ShotGridReviewList.review_mode == 'auto_single',
                    ShotGridReviewList.del_flag == '0',
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @classmethod
    async def get_note_for_update(
        cls,
        db: AsyncSession,
        project_id: int,
        version_id: int,
        note_id: int,
    ) -> ShotGridNote | None:
        return (
            await db.execute(
                select(ShotGridNote)
                .where(
                    ShotGridNote.note_id == note_id,
                    ShotGridNote.project_id == project_id,
                    ShotGridNote.version_id == version_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @classmethod
    async def get_latest_version_no(cls, db: AsyncSession, task_id: int) -> int | None:
        value = (
            await db.execute(select(func.max(ShotGridVersion.version_no)).where(ShotGridVersion.task_id == task_id))
        ).scalar_one()
        return int(value) if value is not None else None

    @classmethod
    async def has_open_mandatory_note(cls, db: AsyncSession, version_id: int) -> bool:
        return bool(
            (
                await db.execute(
                    select(
                        exists().where(
                            ShotGridNote.version_id == version_id,
                            ShotGridNote.note_status == 'open',
                            ShotGridNote.is_mandatory == '1',
                        )
                    )
                )
            ).scalar_one()
        )

    @classmethod
    async def has_other_final_version(cls, db: AsyncSession, task_id: int, version_id: int) -> bool:
        return bool(
            (
                await db.execute(
                    select(
                        exists().where(
                            ShotGridVersion.task_id == task_id,
                            ShotGridVersion.version_id != version_id,
                            ShotGridVersion.version_status == 'final',
                        )
                    )
                )
            ).scalar_one()
        )

    @classmethod
    async def get_auto_review_relation_version_ids(
        cls,
        db: AsyncSession,
        review_list_id: int,
    ) -> list[int]:
        values = (
            await db.execute(
                select(ShotGridReviewListVersion.version_id)
                .where(ShotGridReviewListVersion.review_list_id == review_list_id)
                .order_by(ShotGridReviewListVersion.sort_order, ShotGridReviewListVersion.version_id)
            )
        ).scalars()
        return [int(value) for value in values]

    @classmethod
    async def find_review_action_by_idempotency(
        cls,
        db: AsyncSession,
        version_id: int,
        reviewer_user_id: int,
        idempotency_key: str,
    ) -> ShotGridReviewAction | None:
        return (
            await db.execute(
                select(ShotGridReviewAction).where(
                    ShotGridReviewAction.version_id == version_id,
                    ShotGridReviewAction.reviewer_user_id == reviewer_user_id,
                    ShotGridReviewAction.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()

    @classmethod
    async def add_note(cls, db: AsyncSession, note: ShotGridNote) -> ShotGridNote:
        db.add(note)
        await db.flush()
        return note

    @classmethod
    async def add_reply(cls, db: AsyncSession, reply: ShotGridNoteReply) -> ShotGridNoteReply:
        db.add(reply)
        await db.flush()
        return reply

    @classmethod
    async def add_review_action(cls, db: AsyncSession, action: ShotGridReviewAction) -> ShotGridReviewAction:
        db.add(action)
        await db.flush()
        return action

    @classmethod
    async def add_auto_review_list(
        cls,
        db: AsyncSession,
        review_list: ShotGridReviewList,
        relation: ShotGridReviewListVersion,
    ) -> ShotGridReviewList:
        """供正式版本事务复用；只 flush，不提交。"""
        db.add(review_list)
        await db.flush()
        relation.review_list_id = review_list.review_list_id
        db.add(relation)
        await db.flush()
        return review_list

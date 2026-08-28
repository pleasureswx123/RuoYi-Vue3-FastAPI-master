from typing import Any

from sqlalchemy import and_, asc, case, desc, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.user_do import SysUser
from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridAssetItem, ShotGridShotAsset
from module_shot_grid.entity.do.project_do import ShotGridProjectMember
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageOperation
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import (
    ShotGridVersion,
    ShotGridVersionCandidate,
    ShotGridVersionFile,
    ShotGridVersionSubmission,
)
from module_shot_grid.entity.vo.asset_crud_vo import ASSET_ITEM_STATUSES, ShotGridAssetListQueryModel

ACTIVE_TASK_STATUSES = ('not_started', 'preparing', 'in_progress', 'pending_review', 'revision')
STATUS_RANK_REVISION = 6
STATUS_RANK_REVIEWING = 5
STATUS_RANK_IN_PROGRESS = 4
STATUS_RANK_PREPARING = 3
STATUS_RANK_UNASSIGNED = 2


class ShotGridAssetCrudDao:
    """资产及制作分项普通管理数据访问层。"""

    @classmethod
    def _item_state_subquery(cls) -> Any:
        final_versions = (
            select(ShotGridVersion.task_id, func.count(ShotGridVersion.version_id).label('final_count'))
            .where(ShotGridVersion.version_status == 'final')
            .group_by(ShotGridVersion.task_id)
            .subquery('asset_final_versions')
        )
        item_state = case(
            (ShotGridTask.task_id.is_(None), 'unassigned'),
            (ShotGridTask.task_status == 'revision', 'revision'),
            (ShotGridTask.task_status == 'pending_review', 'reviewing'),
            (ShotGridTask.task_status == 'in_progress', 'in_progress'),
            (ShotGridTask.task_status == 'preparing', 'preparing'),
            (
                (ShotGridTask.task_status == 'completed') & (func.coalesce(final_versions.c.final_count, 0) > 0),
                'completed',
            ),
            (ShotGridTask.task_status == 'completed', 'reviewing'),
            else_='not_started',
        ).label('item_status')
        return (
            select(
                ShotGridAssetItem.asset_id,
                ShotGridAssetItem.asset_item_id,
                ShotGridTask.assignee_user_id,
                item_state,
                and_(
                    ShotGridTask.task_status == 'not_started',
                    func.length(func.trim(ShotGridAssetItem.production_item)) > 0,
                    cls._assignee_valid_expression(),
                ).label('startable'),
            )
            .outerjoin(
                ShotGridTask,
                (ShotGridTask.asset_item_id == ShotGridAssetItem.asset_item_id) & (ShotGridTask.del_flag == '0'),
            )
            .outerjoin(final_versions, final_versions.c.task_id == ShotGridTask.task_id)
            .outerjoin(SysUser, SysUser.user_id == ShotGridTask.assignee_user_id)
            .outerjoin(
                ShotGridProjectMember,
                (ShotGridProjectMember.project_id == ShotGridTask.project_id)
                & (ShotGridProjectMember.user_id == ShotGridTask.assignee_user_id),
            )
            .where(
                ShotGridAssetItem.lifecycle_status == 'active',
                ShotGridAssetItem.del_flag == '0',
            )
            .subquery('asset_item_states')
        )

    @classmethod
    def _asset_rollup_subquery(cls) -> Any:
        item_state = cls._item_state_subquery()
        rollup = (
            select(
                item_state.c.asset_id,
                func.count(item_state.c.asset_item_id).label('item_count'),
                *[
                    func.count().filter(item_state.c.item_status == status).label(f'{status}_count')
                    for status in ASSET_ITEM_STATUSES
                ],
                func.count().filter(item_state.c.startable).label('startable_item_count'),
                func.max(
                    case(
                        (item_state.c.item_status == 'revision', STATUS_RANK_REVISION),
                        (item_state.c.item_status == 'reviewing', STATUS_RANK_REVIEWING),
                        (item_state.c.item_status == 'in_progress', STATUS_RANK_IN_PROGRESS),
                        (item_state.c.item_status == 'preparing', STATUS_RANK_PREPARING),
                        (item_state.c.item_status == 'unassigned', 2),
                        (item_state.c.item_status == 'not_started', 1),
                        else_=0,
                    )
                ).label('priority_rank'),
            )
            .group_by(item_state.c.asset_id)
            .subquery('asset_item_rollup')
        )
        asset_status = case(
            (rollup.c.item_count == rollup.c.completed_count, 'completed'),
            (rollup.c.priority_rank == STATUS_RANK_REVISION, 'revision'),
            (rollup.c.priority_rank == STATUS_RANK_REVIEWING, 'reviewing'),
            (rollup.c.priority_rank == STATUS_RANK_IN_PROGRESS, 'in_progress'),
            (rollup.c.priority_rank == STATUS_RANK_PREPARING, 'preparing'),
            (rollup.c.priority_rank == STATUS_RANK_UNASSIGNED, 'unassigned'),
            else_='not_started',
        ).label('asset_status')
        return select(
            rollup.c.asset_id,
            rollup.c.item_count,
            *[rollup.c[f'{status}_count'] for status in ASSET_ITEM_STATUSES],
            rollup.c.startable_item_count,
            asset_status,
        ).subquery('asset_status_rollup')

    @classmethod
    async def get_asset_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridAssetListQueryModel,
    ) -> tuple[list[dict[str, Any]], int]:
        rollup = cls._asset_rollup_subquery()
        usage = (
            select(
                ShotGridShotAsset.asset_id,
                func.count(ShotGridShotAsset.shot_id).label('usage_shot_count'),
            )
            .where(ShotGridShotAsset.project_id == project_id)
            .group_by(ShotGridShotAsset.asset_id)
            .subquery('asset_shot_usage')
        )
        effective_status = func.coalesce(rollup.c.asset_status, 'unassigned')
        statement = (
            select(
                ShotGridAsset.asset_id,
                ShotGridAsset.project_id,
                ShotGridAsset.asset_type,
                ShotGridAsset.asset_name,
                ShotGridAsset.description,
                ShotGridAsset.sort_order,
                ShotGridAsset.lifecycle_status,
                effective_status.label('asset_status'),
                func.coalesce(rollup.c.item_count, 0).label('item_count'),
                *[
                    func.coalesce(rollup.c[f'{status}_count'], 0).label(f'{status}_count')
                    for status in ASSET_ITEM_STATUSES
                ],
                func.coalesce(rollup.c.startable_item_count, 0).label('startable_item_count'),
                func.coalesce(usage.c.usage_shot_count, 0).label('usage_shot_count'),
                ShotGridAsset.lock_version,
                ShotGridAsset.update_time,
            )
            .outerjoin(rollup, rollup.c.asset_id == ShotGridAsset.asset_id)
            .outerjoin(usage, usage.c.asset_id == ShotGridAsset.asset_id)
            .where(
                ShotGridAsset.project_id == project_id,
                ShotGridAsset.lifecycle_status == 'active',
                ShotGridAsset.del_flag == '0',
            )
        )
        keyword = query.keyword.strip() if query.keyword else None
        if keyword:
            statement = statement.where(
                or_(
                    ShotGridAsset.asset_name.ilike(f'%{keyword}%'),
                    ShotGridAsset.description.ilike(f'%{keyword}%'),
                )
            )
        if query.asset_type:
            statement = statement.where(ShotGridAsset.asset_type == query.asset_type)
        if query.asset_status:
            statement = statement.where(effective_status == query.asset_status)
        if query.assignee_user_id:
            assigned = exists(
                select(1)
                .select_from(ShotGridAssetItem)
                .join(
                    ShotGridTask,
                    (ShotGridTask.asset_item_id == ShotGridAssetItem.asset_item_id) & (ShotGridTask.del_flag == '0'),
                )
                .where(
                    ShotGridAssetItem.asset_id == ShotGridAsset.asset_id,
                    ShotGridAssetItem.lifecycle_status == 'active',
                    ShotGridAssetItem.del_flag == '0',
                    ShotGridTask.assignee_user_id == query.assignee_user_id,
                )
            )
            statement = statement.where(assigned)

        order_columns = {
            'assetName': ShotGridAsset.asset_name,
            'assetType': ShotGridAsset.asset_type,
            'sortOrder': ShotGridAsset.sort_order,
            'updateTime': ShotGridAsset.update_time,
        }
        order_column = order_columns[query.order_by_column]
        statement = statement.order_by(
            asc(order_column) if query.is_asc == 'ascending' else desc(order_column),
            ShotGridAsset.asset_id,
        )
        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        rows = (
            await db.execute(statement.offset((query.page_num - 1) * query.page_size).limit(query.page_size))
        ).mappings()
        return [dict(row) for row in rows], total

    @classmethod
    async def get_asset(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_id: int,
        *,
        for_update: bool = False,
    ) -> ShotGridAsset | None:
        statement = select(ShotGridAsset).where(
            ShotGridAsset.project_id == project_id,
            ShotGridAsset.asset_id == asset_id,
            ShotGridAsset.del_flag == '0',
        )
        if for_update:
            statement = statement.with_for_update()
        return (await db.execute(statement)).scalar_one_or_none()

    @classmethod
    async def get_asset_item(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_item_id: int,
        *,
        for_update: bool = False,
    ) -> ShotGridAssetItem | None:
        statement = select(ShotGridAssetItem).where(
            ShotGridAssetItem.project_id == project_id,
            ShotGridAssetItem.asset_item_id == asset_item_id,
            ShotGridAssetItem.del_flag == '0',
        )
        if for_update:
            statement = statement.with_for_update()
        return (await db.execute(statement)).scalar_one_or_none()

    @classmethod
    async def get_asset_items(cls, db: AsyncSession, project_id: int, asset_id: int) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(
                    ShotGridAssetItem.asset_item_id,
                    ShotGridAssetItem.project_id,
                    ShotGridAssetItem.asset_id,
                    ShotGridAssetItem.production_item,
                    ShotGridAssetItem.description,
                    ShotGridAssetItem.sort_order,
                    ShotGridAssetItem.remark,
                    ShotGridAssetItem.lifecycle_status,
                    ShotGridAssetItem.lock_version,
                    ShotGridAssetItem.create_time,
                    ShotGridAssetItem.update_time,
                    ShotGridTask.task_id,
                    ShotGridTask.assignee_user_id,
                    cls._assignee_valid_expression().label('assignee_valid'),
                    SysUser.nick_name.label('assignee_name'),
                    func.upper(SysUser.nick_name).label('producer_code'),
                    ShotGridTask.task_status,
                    ShotGridTask.priority,
                    ShotGridTask.due_date,
                    ShotGridTask.requirements,
                    ShotGridTask.lock_version.label('task_lock_version'),
                    exists(
                        select(1).where(
                            ShotGridVersionSubmission.task_id == ShotGridTask.task_id,
                            ShotGridVersionSubmission.submission_status != 'committed',
                        )
                    ).label('has_uncommitted_submission'),
                )
                .outerjoin(
                    ShotGridTask,
                    (ShotGridTask.asset_item_id == ShotGridAssetItem.asset_item_id) & (ShotGridTask.del_flag == '0'),
                )
                .outerjoin(SysUser, SysUser.user_id == ShotGridTask.assignee_user_id)
                .outerjoin(
                    ShotGridProjectMember,
                    (ShotGridProjectMember.project_id == ShotGridTask.project_id)
                    & (ShotGridProjectMember.user_id == ShotGridTask.assignee_user_id),
                )
                .where(
                    ShotGridAssetItem.project_id == project_id,
                    ShotGridAssetItem.asset_id == asset_id,
                    ShotGridAssetItem.del_flag == '0',
                )
                .order_by(
                    case((ShotGridAssetItem.lifecycle_status == 'active', 0), else_=1),
                    ShotGridAssetItem.sort_order,
                    ShotGridAssetItem.asset_item_id,
                )
            )
        ).mappings()
        return [dict(row) for row in rows]

    @classmethod
    async def get_versions_for_tasks(cls, db: AsyncSession, task_ids: list[int]) -> list[dict[str, Any]]:
        if not task_ids:
            return []
        display_candidate_id = (
            select(ShotGridVersionCandidate.candidate_id)
            .where(ShotGridVersionCandidate.version_id == ShotGridVersion.version_id)
            .order_by(
                case(
                    (ShotGridVersionCandidate.candidate_id == ShotGridVersion.selected_candidate_id, 0),
                    else_=1,
                ),
                ShotGridVersionCandidate.sort_order,
                ShotGridVersionCandidate.candidate_no,
                ShotGridVersionCandidate.candidate_id,
            )
            .limit(1)
            .correlate(ShotGridVersion)
            .scalar_subquery()
        )
        thumbnail_file_id = (
            select(ShotGridVersionFile.file_id)
            .where(
                ShotGridVersionFile.version_id == ShotGridVersion.version_id,
                ShotGridVersionFile.candidate_id == display_candidate_id,
                ShotGridVersionFile.file_role == 'thumbnail',
            )
            .order_by(ShotGridVersionFile.sort_order, ShotGridVersionFile.file_id)
            .limit(1)
            .scalar_subquery()
        )
        thumbnail_business_file_name = (
            select(ShotGridVersionFile.business_file_name)
            .where(
                ShotGridVersionFile.version_id == ShotGridVersion.version_id,
                ShotGridVersionFile.candidate_id == display_candidate_id,
                ShotGridVersionFile.file_role == 'thumbnail',
            )
            .order_by(ShotGridVersionFile.sort_order, ShotGridVersionFile.file_id)
            .limit(1)
            .scalar_subquery()
        )
        rows = (
            await db.execute(
                select(
                    ShotGridVersion.task_id,
                    ShotGridVersion.version_id,
                    ShotGridVersion.version_no,
                    ShotGridVersion.version_status,
                    ShotGridVersion.submitted_time,
                    thumbnail_file_id.label('thumbnail_file_id'),
                    thumbnail_business_file_name.label('thumbnail_business_file_name'),
                )
                .where(ShotGridVersion.task_id.in_(task_ids))
                .order_by(ShotGridVersion.task_id, ShotGridVersion.version_no.desc())
            )
        ).mappings()
        return [dict(row) for row in rows]

    @classmethod
    async def get_active_asset_task_refs(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_ids: list[int],
    ) -> list[dict[str, int]]:
        """批量返回资产活动制作分项与其唯一任务，用于代表缩略图聚合。"""

        if not asset_ids:
            return []
        rows = (
            await db.execute(
                select(
                    ShotGridAssetItem.asset_id,
                    ShotGridAssetItem.asset_item_id,
                    ShotGridAssetItem.sort_order,
                    ShotGridTask.task_id,
                )
                .join(
                    ShotGridTask,
                    (ShotGridTask.asset_item_id == ShotGridAssetItem.asset_item_id) & (ShotGridTask.del_flag == '0'),
                )
                .where(
                    ShotGridAssetItem.project_id == project_id,
                    ShotGridAssetItem.asset_id.in_(asset_ids),
                    ShotGridAssetItem.lifecycle_status == 'active',
                    ShotGridAssetItem.del_flag == '0',
                )
                .order_by(
                    ShotGridAssetItem.asset_id,
                    ShotGridAssetItem.sort_order,
                    ShotGridAssetItem.asset_item_id,
                )
            )
        ).mappings()
        return [dict(row) for row in rows]

    @classmethod
    async def get_latest_directory_operations(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_ids: list[int],
    ) -> dict[int, str]:
        if not asset_ids:
            return {}
        rows = (
            await db.execute(
                select(
                    ShotGridStorageOperation.aggregate_id,
                    ShotGridStorageOperation.operation_status,
                )
                .where(
                    ShotGridStorageOperation.project_id == project_id,
                    ShotGridStorageOperation.aggregate_type == 'asset',
                    ShotGridStorageOperation.aggregate_id.in_(asset_ids),
                )
                .order_by(
                    ShotGridStorageOperation.aggregate_id,
                    ShotGridStorageOperation.operation_id.desc(),
                )
            )
        ).all()
        latest: dict[int, str] = {}
        for aggregate_id, operation_status in rows:
            latest.setdefault(int(aggregate_id), str(operation_status))
        return latest

    @classmethod
    async def get_assignee_ids(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_ids: list[int],
    ) -> dict[int, list[int]]:
        if not asset_ids:
            return {}
        rows = (
            await db.execute(
                select(ShotGridAssetItem.asset_id, ShotGridTask.assignee_user_id)
                .join(
                    ShotGridTask,
                    (ShotGridTask.asset_item_id == ShotGridAssetItem.asset_item_id) & (ShotGridTask.del_flag == '0'),
                )
                .where(
                    ShotGridAssetItem.project_id == project_id,
                    ShotGridAssetItem.asset_id.in_(asset_ids),
                    ShotGridAssetItem.lifecycle_status == 'active',
                    ShotGridAssetItem.del_flag == '0',
                )
                .distinct()
                .order_by(ShotGridAssetItem.asset_id, ShotGridTask.assignee_user_id)
            )
        ).all()
        result: dict[int, list[int]] = {}
        for asset_id, user_id in rows:
            result.setdefault(int(asset_id), []).append(int(user_id))
        return result

    @classmethod
    async def get_assets_with_active_tasks(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_ids: list[int],
    ) -> set[int]:
        """批量返回仍有活动任务的资产，语义与归档事务门禁一致。"""

        if not asset_ids:
            return set()
        rows = (
            await db.execute(
                select(ShotGridAssetItem.asset_id)
                .join(ShotGridTask, ShotGridTask.asset_item_id == ShotGridAssetItem.asset_item_id)
                .where(
                    ShotGridTask.project_id == project_id,
                    ShotGridAssetItem.asset_id.in_(asset_ids),
                    ShotGridTask.task_status.in_(ACTIVE_TASK_STATUSES),
                    ShotGridTask.del_flag == '0',
                )
                .distinct()
            )
        ).scalars()
        return {int(asset_id) for asset_id in rows}

    @classmethod
    async def get_assets_with_delete_blockers(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_ids: list[int],
    ) -> set[int]:
        """返回存在已开始任务或版本的活动制作分项资产。"""

        if not asset_ids:
            return set()
        rows = (
            await db.execute(
                select(ShotGridAssetItem.asset_id)
                .join(ShotGridTask, ShotGridTask.asset_item_id == ShotGridAssetItem.asset_item_id)
                .outerjoin(ShotGridVersion, ShotGridVersion.task_id == ShotGridTask.task_id)
                .where(
                    ShotGridAssetItem.project_id == project_id,
                    ShotGridAssetItem.asset_id.in_(asset_ids),
                    ShotGridAssetItem.lifecycle_status == 'active',
                    ShotGridAssetItem.del_flag == '0',
                    ShotGridTask.del_flag == '0',
                    or_(
                        ShotGridTask.task_status != 'not_started',
                        ShotGridVersion.version_id.is_not(None),
                    ),
                )
                .distinct()
            )
        ).scalars()
        return {int(asset_id) for asset_id in rows}

    @classmethod
    async def get_assets_with_assignment_blockers(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_ids: list[int],
    ) -> set[int]:
        """返回包含未命名分项、已完成任务或未完成版本提交的资产。"""

        if not asset_ids:
            return set()
        has_uncommitted_submission = exists(
            select(1).where(
                ShotGridVersionSubmission.task_id == ShotGridTask.task_id,
                ShotGridVersionSubmission.submission_status != 'committed',
            )
        )
        rows = (
            await db.execute(
                select(ShotGridAssetItem.asset_id)
                .outerjoin(
                    ShotGridTask,
                    (ShotGridTask.asset_item_id == ShotGridAssetItem.asset_item_id) & (ShotGridTask.del_flag == '0'),
                )
                .where(
                    ShotGridAssetItem.project_id == project_id,
                    ShotGridAssetItem.asset_id.in_(asset_ids),
                    ShotGridAssetItem.lifecycle_status == 'active',
                    ShotGridAssetItem.del_flag == '0',
                    or_(
                        ShotGridAssetItem.production_item.is_(None),
                        func.btrim(ShotGridAssetItem.production_item) == '',
                        ShotGridTask.task_status == 'completed',
                        has_uncommitted_submission,
                    ),
                )
                .distinct()
            )
        ).scalars()
        return {int(asset_id) for asset_id in rows}

    @classmethod
    async def get_usage_shot_count(cls, db: AsyncSession, project_id: int, asset_id: int) -> int:
        return int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(ShotGridShotAsset)
                    .where(
                        ShotGridShotAsset.project_id == project_id,
                        ShotGridShotAsset.asset_id == asset_id,
                    )
                )
            ).scalar_one()
        )

    @classmethod
    async def asset_name_or_path_exists(
        cls,
        db: AsyncSession,
        project_id: int,
        *,
        asset_type: str,
        asset_name_key: str,
        storage_path_key: str,
        exclude_asset_id: int | None = None,
    ) -> bool:
        statement = (
            select(func.count())
            .select_from(ShotGridAsset)
            .where(
                ShotGridAsset.project_id == project_id,
                ShotGridAsset.del_flag == '0',
                or_(
                    (
                        (ShotGridAsset.lifecycle_status == 'active')
                        & (ShotGridAsset.asset_type == asset_type)
                        & (ShotGridAsset.asset_name_key == asset_name_key)
                    ),
                    ShotGridAsset.storage_path_key == storage_path_key,
                ),
            )
        )
        if exclude_asset_id is not None:
            statement = statement.where(ShotGridAsset.asset_id != exclude_asset_id)
        return bool((await db.execute(statement)).scalar_one())

    @classmethod
    async def item_name_exists(
        cls,
        db: AsyncSession,
        asset_id: int,
        production_item_key: str,
        *,
        exclude_item_id: int | None = None,
    ) -> bool:
        statement = (
            select(func.count())
            .select_from(ShotGridAssetItem)
            .where(
                ShotGridAssetItem.asset_id == asset_id,
                ShotGridAssetItem.production_item_key == production_item_key,
                ShotGridAssetItem.lifecycle_status == 'active',
                ShotGridAssetItem.del_flag == '0',
            )
        )
        if exclude_item_id is not None:
            statement = statement.where(ShotGridAssetItem.asset_item_id != exclude_item_id)
        return bool((await db.execute(statement)).scalar_one())

    @classmethod
    async def get_task_for_item(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_item_id: int,
        *,
        for_update: bool = False,
    ) -> ShotGridTask | None:
        statement = select(ShotGridTask).where(
            ShotGridTask.project_id == project_id,
            ShotGridTask.asset_item_id == asset_item_id,
            ShotGridTask.del_flag == '0',
        )
        if for_update:
            statement = statement.with_for_update()
        return (await db.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def get_active_items_for_update(
        db: AsyncSession,
        project_id: int,
        asset_id: int,
    ) -> list[ShotGridAssetItem]:
        return list(
            (
                await db.execute(
                    select(ShotGridAssetItem)
                    .where(
                        ShotGridAssetItem.project_id == project_id,
                        ShotGridAssetItem.asset_id == asset_id,
                        ShotGridAssetItem.lifecycle_status == 'active',
                        ShotGridAssetItem.del_flag == '0',
                    )
                    .order_by(ShotGridAssetItem.asset_item_id)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )

    @staticmethod
    async def delete_not_started_task(
        db: AsyncSession,
        *,
        task_id: int,
        actor_name: str,
        now: Any,
    ) -> bool:
        result = await db.execute(
            update(ShotGridTask)
            .where(
                ShotGridTask.task_id == task_id,
                ShotGridTask.task_status == 'not_started',
                ShotGridTask.del_flag == '0',
            )
            .values(
                del_flag='2',
                update_by=actor_name,
                update_time=now,
                lock_version=ShotGridTask.lock_version + 1,
            )
        )
        return bool(result.rowcount)

    @classmethod
    async def has_versions_for_item(cls, db: AsyncSession, project_id: int, asset_item_id: int) -> bool:
        return bool(
            (
                await db.execute(
                    select(func.count())
                    .select_from(ShotGridVersion)
                    .join(ShotGridTask, ShotGridTask.task_id == ShotGridVersion.task_id)
                    .where(
                        ShotGridVersion.project_id == project_id,
                        ShotGridTask.asset_item_id == asset_item_id,
                    )
                )
            ).scalar_one()
        )

    @classmethod
    async def has_active_tasks_for_asset(cls, db: AsyncSession, project_id: int, asset_id: int) -> bool:
        return bool(
            (
                await db.execute(
                    select(func.count())
                    .select_from(ShotGridTask)
                    .join(ShotGridAssetItem, ShotGridAssetItem.asset_item_id == ShotGridTask.asset_item_id)
                    .where(
                        ShotGridTask.project_id == project_id,
                        ShotGridAssetItem.asset_id == asset_id,
                        ShotGridTask.task_status.in_(ACTIVE_TASK_STATUSES),
                        ShotGridTask.del_flag == '0',
                    )
                )
            ).scalar_one()
        )

    @classmethod
    async def has_active_items(cls, db: AsyncSession, asset_id: int) -> bool:
        return bool(
            (
                await db.execute(
                    select(func.count())
                    .select_from(ShotGridAssetItem)
                    .where(
                        ShotGridAssetItem.asset_id == asset_id,
                        ShotGridAssetItem.lifecycle_status == 'active',
                        ShotGridAssetItem.del_flag == '0',
                    )
                )
            ).scalar_one()
        )

    @classmethod
    async def get_project_storage_status(cls, db: AsyncSession, project_id: int) -> str | None:
        return (
            await db.execute(
                select(ShotGridProjectStorage.storage_status).where(ShotGridProjectStorage.project_id == project_id)
            )
        ).scalar_one_or_none()

    @classmethod
    async def add_asset(cls, db: AsyncSession, asset: ShotGridAsset) -> ShotGridAsset:
        db.add(asset)
        await db.flush()
        return asset

    @classmethod
    async def add_item(cls, db: AsyncSession, item: ShotGridAssetItem) -> ShotGridAssetItem:
        db.add(item)
        await db.flush()
        return item

    @staticmethod
    def _assignee_valid_expression() -> Any:
        return and_(
            ShotGridProjectMember.member_status == 'active',
            ShotGridProjectMember.project_role == 'creator',
            SysUser.status == '0',
            SysUser.del_flag == '0',
        )

from datetime import datetime
from typing import Any

from sqlalchemy import String, and_, asc, case, cast, desc, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql import Select

from module_admin.entity.do.user_do import SysUser
from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridAssetItem
from module_shot_grid.entity.do.project_do import (
    ShotGridEpisode,
    ShotGridProject,
    ShotGridProjectMember,
    ShotGridScene,
    ShotGridShot,
)
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageOperation
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion, ShotGridVersionSubmission
from module_shot_grid.entity.vo.task_vo import (
    ShotGridMineTaskListQueryModel,
    ShotGridTaskFilterModel,
    ShotGridTaskListQueryModel,
)


class ShotGridTaskDao:
    """独立任务管理数据访问层；不提交业务事务。"""

    @classmethod
    def build_task_statement(
        cls,
        query: ShotGridTaskFilterModel,
        *,
        project_id: int | None = None,
        mine_user_id: int | None = None,
    ) -> Select:
        """构造项目内或跨项目本人任务查询，并保持稳定排序。"""

        assignee = aliased(SysUser, name='task_assignee')
        assignee_member = aliased(ShotGridProjectMember, name='task_assignee_member')
        ranked_versions = select(
            ShotGridVersion.task_id,
            ShotGridVersion.version_id,
            ShotGridVersion.version_no,
            ShotGridVersion.version_status,
            ShotGridVersion.submitted_time,
            func.row_number()
            .over(
                partition_by=ShotGridVersion.task_id,
                order_by=(ShotGridVersion.version_no.desc(), ShotGridVersion.version_id.desc()),
            )
            .label('row_no'),
        ).subquery('task_ranked_versions')
        latest_version = (
            select(
                ranked_versions.c.task_id,
                ranked_versions.c.version_id,
                ranked_versions.c.version_no,
                ranked_versions.c.version_status,
                ranked_versions.c.submitted_time,
            )
            .where(ranked_versions.c.row_no == 1)
            .subquery('task_latest_version')
        )
        final_version = (
            select(
                ShotGridVersion.task_id,
                ShotGridVersion.version_id,
                ShotGridVersion.version_no,
                ShotGridVersion.version_status,
                ShotGridVersion.submitted_time,
            )
            .where(ShotGridVersion.version_status == 'final')
            .subquery('task_final_version')
        )
        version_count = (
            select(
                ShotGridVersion.task_id,
                func.count(ShotGridVersion.version_id).label('version_count'),
            )
            .group_by(ShotGridVersion.task_id)
            .subquery('task_version_count')
        )
        has_uncommitted_submission = exists(
            select(1).where(
                ShotGridVersionSubmission.task_id == ShotGridTask.task_id,
                ShotGridVersionSubmission.submission_status != 'committed',
            )
        )

        statement = (
            select(
                ShotGridTask.task_id,
                ShotGridTask.project_id,
                ShotGridTask.shot_id,
                ShotGridTask.asset_item_id,
                ShotGridTask.task_name,
                ShotGridTask.task_kind,
                ShotGridTask.assignee_user_id,
                ShotGridTask.task_status,
                ShotGridTask.priority,
                ShotGridTask.due_date,
                ShotGridTask.expected_start_time,
                ShotGridTask.expected_end_time,
                ShotGridTask.requirements,
                ShotGridTask.remark,
                ShotGridTask.lock_version,
                ShotGridTask.create_by,
                ShotGridTask.create_time,
                ShotGridTask.update_by,
                ShotGridTask.update_time,
                ShotGridProject.project_code,
                ShotGridProject.project_name,
                ShotGridProject.project_status,
                assignee.user_name.label('assignee_user_name'),
                assignee.nick_name.label('assignee_nick_name'),
                func.upper(assignee.nick_name).label('assignee_producer_code'),
                assignee_member.member_status.label('assignee_member_status'),
                and_(
                    assignee_member.member_status == 'active',
                    assignee_member.project_role == 'creator',
                    assignee.status == '0',
                    assignee.del_flag == '0',
                ).label('assignee_valid'),
                ShotGridShot.episode_id,
                ShotGridEpisode.episode_no,
                ShotGridShot.scene_id,
                ShotGridScene.scene_no,
                ShotGridScene.scene_name,
                ShotGridShot.shot_no,
                ShotGridShot.storage_dir_name.label('shot_storage_dir_name'),
                ShotGridShot.duration_ms.label('shot_duration_ms'),
                ShotGridShot.description.label('shot_description'),
                ShotGridShot.shot_size.label('shot_size'),
                ShotGridShot.camera_position.label('shot_camera_position'),
                ShotGridShot.camera_movement.label('shot_camera_movement'),
                ShotGridShot.focal_length.label('shot_focal_length'),
                ShotGridShot.dialogue.label('shot_dialogue'),
                ShotGridShot.sound_effect.label('shot_sound_effect'),
                ShotGridShot.color_reference.label('shot_color_reference'),
                ShotGridShot.remark.label('shot_remark'),
                ShotGridShot.lifecycle_status.label('shot_lifecycle_status'),
                ShotGridAssetItem.asset_id,
                ShotGridAssetItem.production_item,
                ShotGridAssetItem.description.label('asset_item_description'),
                ShotGridAssetItem.lifecycle_status.label('asset_item_lifecycle_status'),
                ShotGridAsset.asset_type,
                ShotGridAsset.asset_name,
                ShotGridAsset.description.label('asset_description'),
                ShotGridAsset.lifecycle_status.label('asset_lifecycle_status'),
                func.coalesce(version_count.c.version_count, 0).label('version_count'),
                latest_version.c.version_id.label('latest_version_id'),
                latest_version.c.version_no.label('latest_version_no'),
                latest_version.c.version_status.label('latest_version_status'),
                latest_version.c.submitted_time.label('latest_submitted_time'),
                final_version.c.version_id.label('final_version_id'),
                final_version.c.version_no.label('final_version_no'),
                final_version.c.version_status.label('final_version_status'),
                final_version.c.submitted_time.label('final_submitted_time'),
                has_uncommitted_submission.label('has_uncommitted_submission'),
            )
            .join(ShotGridProject, ShotGridProject.project_id == ShotGridTask.project_id)
            .outerjoin(assignee, assignee.user_id == ShotGridTask.assignee_user_id)
            .outerjoin(
                assignee_member,
                and_(
                    assignee_member.project_id == ShotGridTask.project_id,
                    assignee_member.user_id == ShotGridTask.assignee_user_id,
                ),
            )
            .outerjoin(
                ShotGridShot,
                and_(
                    ShotGridShot.shot_id == ShotGridTask.shot_id,
                    ShotGridShot.project_id == ShotGridTask.project_id,
                ),
            )
            .outerjoin(
                ShotGridEpisode,
                and_(
                    ShotGridEpisode.episode_id == ShotGridShot.episode_id,
                    ShotGridEpisode.project_id == ShotGridTask.project_id,
                ),
            )
            .outerjoin(
                ShotGridScene,
                and_(
                    ShotGridScene.scene_id == ShotGridShot.scene_id,
                    ShotGridScene.project_id == ShotGridTask.project_id,
                    ShotGridScene.episode_id == ShotGridShot.episode_id,
                ),
            )
            .outerjoin(
                ShotGridAssetItem,
                and_(
                    ShotGridAssetItem.asset_item_id == ShotGridTask.asset_item_id,
                    ShotGridAssetItem.project_id == ShotGridTask.project_id,
                ),
            )
            .outerjoin(
                ShotGridAsset,
                and_(
                    ShotGridAsset.asset_id == ShotGridAssetItem.asset_id,
                    ShotGridAsset.project_id == ShotGridTask.project_id,
                ),
            )
            .outerjoin(version_count, version_count.c.task_id == ShotGridTask.task_id)
            .outerjoin(latest_version, latest_version.c.task_id == ShotGridTask.task_id)
            .outerjoin(final_version, final_version.c.task_id == ShotGridTask.task_id)
            .where(
                ShotGridTask.del_flag == '0',
                ShotGridProject.del_flag == '0',
            )
        )
        if project_id is not None:
            statement = statement.where(ShotGridTask.project_id == project_id)
        if mine_user_id is not None:
            statement = statement.where(
                ShotGridTask.assignee_user_id == mine_user_id,
                assignee_member.user_id == mine_user_id,
                assignee_member.member_status == 'active',
            )

        keyword = query.keyword.strip() if query.keyword else None
        if keyword:
            statement = statement.where(
                or_(
                    ShotGridTask.task_name.ilike(f'%{keyword}%'),
                    ShotGridTask.requirements.ilike(f'%{keyword}%'),
                    ShotGridProject.project_name.ilike(f'%{keyword}%'),
                    ShotGridProject.project_code.ilike(f'%{keyword}%'),
                    cast(ShotGridShot.shot_no, String).ilike(f'%{keyword}%'),
                    ShotGridShot.description.ilike(f'%{keyword}%'),
                    ShotGridAsset.asset_name.ilike(f'%{keyword}%'),
                    ShotGridAssetItem.production_item.ilike(f'%{keyword}%'),
                )
            )
        if query.task_kind is not None:
            statement = statement.where(ShotGridTask.task_kind == query.task_kind)
        if query.task_status is not None:
            statement = statement.where(ShotGridTask.task_status == query.task_status)
        if query.priority is not None:
            statement = statement.where(ShotGridTask.priority == query.priority)
        if query.due_date_from is not None:
            statement = statement.where(ShotGridTask.due_date >= query.due_date_from)
        if query.due_date_to is not None:
            statement = statement.where(ShotGridTask.due_date <= query.due_date_to)

        assignee_user_id = getattr(query, 'assignee_user_id', None)
        scope = getattr(query, 'scope', 'project')
        if mine_user_id is None and scope == 'mine':
            raise ValueError('scope=mine 必须由服务端提供当前用户范围')
        if mine_user_id is None and assignee_user_id is not None:
            statement = statement.where(ShotGridTask.assignee_user_id == assignee_user_id)

        priority_order = case(
            (ShotGridTask.priority == 'urgent', 0),
            (ShotGridTask.priority == 'high', 1),
            (ShotGridTask.priority == 'normal', 2),
            else_=3,
        )
        order_columns = {
            'taskId': ShotGridTask.task_id,
            'dueDate': ShotGridTask.due_date,
            'priority': priority_order,
            'createTime': ShotGridTask.create_time,
            'updateTime': ShotGridTask.update_time,
        }
        direction = asc if query.is_asc == 'ascending' else desc
        primary_order = direction(order_columns[query.order_by_column])
        if query.order_by_column == 'dueDate':
            primary_order = primary_order.nulls_last()
        return statement.order_by(primary_order, ShotGridTask.task_id.desc())

    @classmethod
    async def _page(
        cls,
        db: AsyncSession,
        statement: Select,
        query: ShotGridTaskFilterModel,
    ) -> tuple[list[dict[str, Any]], int]:
        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        rows = (
            await db.execute(statement.offset((query.page_num - 1) * query.page_size).limit(query.page_size))
        ).mappings()
        return [dict(row) for row in rows], total

    @classmethod
    async def get_project_task_page(
        cls,
        db: AsyncSession,
        project_id: int,
        actor_user_id: int,
        query: ShotGridTaskListQueryModel,
    ) -> tuple[list[dict[str, Any]], int]:
        mine_user_id = actor_user_id if query.scope == 'mine' else None
        statement = cls.build_task_statement(query, project_id=project_id, mine_user_id=mine_user_id)
        return await cls._page(db, statement, query)

    @classmethod
    async def get_mine_task_page(
        cls,
        db: AsyncSession,
        actor_user_id: int,
        query: ShotGridTaskFilterModel,
    ) -> tuple[list[dict[str, Any]], int]:
        statement = cls.build_task_statement(query, mine_user_id=actor_user_id)
        return await cls._page(db, statement, query)

    @classmethod
    async def get_task_detail(cls, db: AsyncSession, task_id: int) -> dict[str, Any] | None:
        statement = cls.build_task_statement(
            ShotGridMineTaskListQueryModel(pageNum=1, pageSize=1),
        ).where(ShotGridTask.task_id == task_id)
        row = (await db.execute(statement.limit(1))).mappings().one_or_none()
        return dict(row) if row is not None else None

    @staticmethod
    async def get_task_project_id(db: AsyncSession, task_id: int) -> int | None:
        return await db.scalar(
            select(ShotGridTask.project_id).where(
                ShotGridTask.task_id == task_id,
                ShotGridTask.del_flag == '0',
            )
        )

    @staticmethod
    async def lock_project_storage(
        db: AsyncSession,
        project_id: int,
    ) -> tuple[ShotGridProject | None, ShotGridProjectStorage | None]:
        row = (
            await db.execute(
                select(ShotGridProject, ShotGridProjectStorage)
                .outerjoin(ShotGridProjectStorage, ShotGridProjectStorage.project_id == ShotGridProject.project_id)
                .where(ShotGridProject.project_id == project_id, ShotGridProject.del_flag == '0')
                .with_for_update(of=ShotGridProject)
            )
        ).one_or_none()
        return (None, None) if row is None else (row[0], row[1])

    @staticmethod
    async def get_task_for_update(
        db: AsyncSession,
        project_id: int,
        task_id: int,
    ) -> ShotGridTask | None:
        return (
            await db.execute(
                select(ShotGridTask)
                .where(
                    ShotGridTask.project_id == project_id,
                    ShotGridTask.task_id == task_id,
                    ShotGridTask.del_flag == '0',
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @staticmethod
    async def get_task_for_shot_update(
        db: AsyncSession,
        project_id: int,
        shot_id: int,
    ) -> ShotGridTask | None:
        return (
            await db.execute(
                select(ShotGridTask)
                .where(
                    ShotGridTask.project_id == project_id,
                    ShotGridTask.shot_id == shot_id,
                    ShotGridTask.task_kind == 'shot_video',
                    ShotGridTask.del_flag == '0',
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @staticmethod
    async def get_task_for_asset_item_update(
        db: AsyncSession,
        project_id: int,
        asset_item_id: int,
    ) -> ShotGridTask | None:
        return (
            await db.execute(
                select(ShotGridTask)
                .where(
                    ShotGridTask.project_id == project_id,
                    ShotGridTask.asset_item_id == asset_item_id,
                    ShotGridTask.task_kind == 'asset_image',
                    ShotGridTask.del_flag == '0',
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @staticmethod
    async def lock_shot_target(
        db: AsyncSession,
        project_id: int,
        shot_id: int,
    ) -> tuple[ShotGridShot, ShotGridEpisode, ShotGridScene] | None:
        row = (
            await db.execute(
                select(ShotGridShot, ShotGridEpisode, ShotGridScene)
                .join(
                    ShotGridEpisode,
                    and_(
                        ShotGridEpisode.episode_id == ShotGridShot.episode_id,
                        ShotGridEpisode.project_id == ShotGridShot.project_id,
                    ),
                )
                .join(
                    ShotGridScene,
                    and_(
                        ShotGridScene.scene_id == ShotGridShot.scene_id,
                        ShotGridScene.episode_id == ShotGridShot.episode_id,
                        ShotGridScene.project_id == ShotGridShot.project_id,
                    ),
                )
                .where(
                    ShotGridShot.project_id == project_id,
                    ShotGridShot.shot_id == shot_id,
                    ShotGridShot.lifecycle_status == 'active',
                    ShotGridShot.del_flag == '0',
                    ShotGridEpisode.lifecycle_status == 'active',
                    ShotGridEpisode.del_flag == '0',
                    ShotGridScene.lifecycle_status == 'active',
                    ShotGridScene.del_flag == '0',
                )
                .with_for_update(of=ShotGridShot)
            )
        ).one_or_none()
        return None if row is None else (row[0], row[1], row[2])

    @staticmethod
    async def get_latest_shot_directory_operation_status(
        db: AsyncSession,
        project_id: int,
        shot_id: int,
    ) -> str | None:
        return await db.scalar(
            select(ShotGridStorageOperation.operation_status)
            .where(
                ShotGridStorageOperation.project_id == project_id,
                ShotGridStorageOperation.aggregate_type == 'shot',
                ShotGridStorageOperation.aggregate_id == shot_id,
            )
            .order_by(ShotGridStorageOperation.operation_id.desc())
            .limit(1)
        )

    @staticmethod
    async def get_latest_asset_directory_operation_status(
        db: AsyncSession,
        project_id: int,
        asset_id: int,
    ) -> str | None:
        return await db.scalar(
            select(ShotGridStorageOperation.operation_status)
            .where(
                ShotGridStorageOperation.project_id == project_id,
                ShotGridStorageOperation.aggregate_type == 'asset',
                ShotGridStorageOperation.aggregate_id == asset_id,
            )
            .order_by(ShotGridStorageOperation.operation_id.desc())
            .limit(1)
        )

    @staticmethod
    async def get_latest_succeeded_shot_directory_operation_actor(
        db: AsyncSession,
        project_id: int,
        shot_id: int,
    ) -> str | None:
        """回溯成功目录操作的业务发起人，用于治理历史 Worker 审计脏值。"""
        return await db.scalar(
            select(ShotGridStorageOperation.create_by)
            .where(
                ShotGridStorageOperation.project_id == project_id,
                ShotGridStorageOperation.operation_type == 'ensure_shot_directory',
                ShotGridStorageOperation.aggregate_type == 'shot',
                ShotGridStorageOperation.aggregate_id == shot_id,
                ShotGridStorageOperation.operation_status == 'succeeded',
            )
            .order_by(ShotGridStorageOperation.operation_id.desc())
            .limit(1)
        )

    @staticmethod
    async def get_asset_item_project_context(
        db: AsyncSession,
        project_id: int,
        asset_item_id: int,
    ) -> tuple[int, int] | None:
        row = (
            await db.execute(
                select(ShotGridAssetItem.asset_id, ShotGridAssetItem.asset_item_id).where(
                    ShotGridAssetItem.project_id == project_id,
                    ShotGridAssetItem.asset_item_id == asset_item_id,
                    ShotGridAssetItem.del_flag == '0',
                )
            )
        ).one_or_none()
        return None if row is None else (int(row[0]), int(row[1]))

    @staticmethod
    async def lock_asset(db: AsyncSession, project_id: int, asset_id: int) -> ShotGridAsset | None:
        return (
            await db.execute(
                select(ShotGridAsset)
                .where(
                    ShotGridAsset.project_id == project_id,
                    ShotGridAsset.asset_id == asset_id,
                    ShotGridAsset.lifecycle_status == 'active',
                    ShotGridAsset.del_flag == '0',
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @staticmethod
    async def lock_asset_item(
        db: AsyncSession,
        project_id: int,
        asset_item_id: int,
    ) -> ShotGridAssetItem | None:
        return (
            await db.execute(
                select(ShotGridAssetItem)
                .where(
                    ShotGridAssetItem.project_id == project_id,
                    ShotGridAssetItem.asset_item_id == asset_item_id,
                    ShotGridAssetItem.lifecycle_status == 'active',
                    ShotGridAssetItem.del_flag == '0',
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @staticmethod
    async def get_assignable_member(
        db: AsyncSession,
        project_id: int,
        user_id: int,
    ) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridProjectMember.user_id,
                        func.upper(SysUser.nick_name).label('producer_code'),
                        SysUser.nick_name,
                    )
                    .join(SysUser, SysUser.user_id == ShotGridProjectMember.user_id)
                    .where(
                        ShotGridProjectMember.project_id == project_id,
                        ShotGridProjectMember.user_id == user_id,
                        ShotGridProjectMember.member_status == 'active',
                        ShotGridProjectMember.project_role == 'creator',
                        SysUser.status == '0',
                        SysUser.del_flag == '0',
                    )
                    .with_for_update(of=ShotGridProjectMember)
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @staticmethod
    async def get_uncommitted_submission_for_update(db: AsyncSession, task_id: int) -> int | None:
        return await db.scalar(
            select(ShotGridVersionSubmission.submission_id)
            .where(
                ShotGridVersionSubmission.task_id == task_id,
                ShotGridVersionSubmission.submission_status != 'committed',
            )
            .order_by(ShotGridVersionSubmission.submission_id)
            .limit(1)
            .with_for_update()
        )

    @staticmethod
    async def add_task(db: AsyncSession, task: ShotGridTask) -> ShotGridTask:
        db.add(task)
        await db.flush()
        return task

    @staticmethod
    async def flush(db: AsyncSession) -> None:
        await db.flush()

    @staticmethod
    def now() -> datetime:
        return datetime.now().replace(microsecond=0)

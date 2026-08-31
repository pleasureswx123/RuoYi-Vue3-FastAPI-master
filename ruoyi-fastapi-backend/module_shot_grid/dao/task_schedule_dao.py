from datetime import datetime
from typing import Any

from sqlalchemy import String, and_, case, cast, exists, func, or_, select
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
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.task_schedule_change_do import ShotGridTaskScheduleChange
from module_shot_grid.entity.vo.task_schedule_vo import ShotGridScheduleQueryModel


class ShotGridTaskScheduleDao:
    """任务排期窗口、冲突、历史和写入锁的数据访问层；不提交事务。"""

    @staticmethod
    def _target_is_active() -> Any:
        return or_(
            and_(
                ShotGridTask.task_kind == 'shot_video',
                ShotGridShot.lifecycle_status == 'active',
                ShotGridShot.del_flag == '0',
                ShotGridEpisode.lifecycle_status == 'active',
                ShotGridEpisode.del_flag == '0',
                ShotGridScene.lifecycle_status == 'active',
                ShotGridScene.del_flag == '0',
            ),
            and_(
                ShotGridTask.task_kind == 'asset_image',
                ShotGridAssetItem.lifecycle_status == 'active',
                ShotGridAssetItem.del_flag == '0',
                ShotGridAsset.lifecycle_status == 'active',
                ShotGridAsset.del_flag == '0',
            ),
        )

    @staticmethod
    def _group_expressions(query: ShotGridScheduleQueryModel, assignee: Any) -> tuple[Any, Any, Any]:
        if query.group_by == 'assignee':
            return (
                func.concat('assignee:', ShotGridTask.assignee_user_id),
                func.coalesce(assignee.user_name, '未知人员'),
                func.lower(func.coalesce(assignee.user_name, '')),
            )
        if query.group_by == 'task_kind':
            return (
                func.concat('task_kind:', ShotGridTask.task_kind),
                case((ShotGridTask.task_kind == 'shot_video', '镜头任务'), else_='资产任务'),
                case((ShotGridTask.task_kind == 'shot_video', 0), else_=1),
            )
        if query.group_by == 'status':
            status_sort = case(
                (ShotGridTask.task_status == 'revision', 0),
                (ShotGridTask.task_status == 'pending_review', 1),
                (ShotGridTask.task_status == 'in_progress', 2),
                (ShotGridTask.task_status == 'preparing', 3),
                (ShotGridTask.task_status == 'not_started', 4),
                else_=5,
            )
            return (
                func.concat('status:', ShotGridTask.task_status),
                ShotGridTask.task_status,
                status_sort,
            )
        if query.group_by == 'episode':
            return (
                func.concat('episode:', func.coalesce(cast(ShotGridEpisode.episode_id, String), 'none')),
                func.coalesce(ShotGridEpisode.episode_name, cast(ShotGridEpisode.episode_no, String), '未分集'),
                func.coalesce(ShotGridEpisode.sort_order, 2_147_483_647),
            )
        if query.group_by == 'scene':
            return (
                func.concat('scene:', func.coalesce(cast(ShotGridScene.scene_id, String), 'none')),
                func.coalesce(ShotGridScene.scene_name, cast(ShotGridScene.scene_no, String), '未分场'),
                func.coalesce(ShotGridScene.sort_order, 2_147_483_647),
            )
        return (
            func.concat('asset_type:', func.coalesce(ShotGridAsset.asset_type, 'none')),
            func.coalesce(ShotGridAsset.asset_type, '非资产任务'),
            case(
                (ShotGridAsset.asset_type == 'Character', 0),
                (ShotGridAsset.asset_type == 'Environment', 1),
                (ShotGridAsset.asset_type == 'Prop', 2),
                else_=3,
            ),
        )

    @classmethod
    def _base_task_statement(cls, query: ShotGridScheduleQueryModel) -> Select:
        assignee = aliased(SysUser, name='schedule_assignee')
        assignee_member = aliased(ShotGridProjectMember, name='schedule_assignee_member')
        group_key, group_name, group_sort = cls._group_expressions(query, assignee)
        target_sort = case(
            (ShotGridTask.task_kind == 'shot_video', ShotGridShot.sort_order),
            else_=ShotGridAssetItem.sort_order,
        )
        target_id = case(
            (ShotGridTask.task_kind == 'shot_video', ShotGridTask.shot_id),
            else_=ShotGridTask.asset_item_id,
        )
        parent_id = case(
            (ShotGridTask.task_kind == 'shot_video', ShotGridShot.scene_id),
            else_=ShotGridAssetItem.asset_id,
        )

        return (
            select(
                ShotGridTask.task_id,
                ShotGridTask.project_id,
                ShotGridTask.task_name,
                ShotGridTask.task_kind,
                ShotGridTask.task_status,
                ShotGridTask.priority,
                ShotGridTask.assignee_user_id,
                ShotGridTask.expected_start_time,
                ShotGridTask.expected_end_time,
                ShotGridTask.baseline_start_time,
                ShotGridTask.baseline_end_time,
                ShotGridTask.lock_version,
                assignee.user_name.label('assignee_user_name'),
                assignee.nick_name.label('assignee_nick_name'),
                target_id.label('target_id'),
                parent_id.label('target_parent_id'),
                target_sort.label('target_sort_order'),
                ShotGridShot.shot_id,
                ShotGridShot.shot_no,
                ShotGridEpisode.episode_id,
                ShotGridEpisode.episode_no,
                ShotGridEpisode.sort_order.label('episode_sort_order'),
                ShotGridScene.scene_id,
                ShotGridScene.scene_no,
                ShotGridScene.scene_name,
                ShotGridScene.sort_order.label('scene_sort_order'),
                ShotGridAsset.asset_id,
                ShotGridAsset.asset_name,
                ShotGridAsset.asset_type,
                ShotGridAsset.sort_order.label('asset_sort_order'),
                ShotGridAssetItem.asset_item_id,
                ShotGridAssetItem.production_item,
                ShotGridAssetItem.sort_order.label('asset_item_sort_order'),
                group_key.label('group_key'),
                group_name.label('group_name'),
                group_sort.label('group_sort_order'),
            )
            .join(ShotGridProject, ShotGridProject.project_id == ShotGridTask.project_id)
            .join(
                assignee_member,
                and_(
                    assignee_member.project_id == ShotGridTask.project_id,
                    assignee_member.user_id == ShotGridTask.assignee_user_id,
                ),
            )
            .join(assignee, assignee.user_id == ShotGridTask.assignee_user_id)
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
            .where(
                ShotGridTask.del_flag == '0',
                ShotGridProject.del_flag == '0',
                assignee_member.member_status == 'active',
                assignee_member.project_role == 'creator',
                assignee.status == '0',
                assignee.del_flag == '0',
                cls._target_is_active(),
            )
        )

    @classmethod
    def _apply_filters(
        cls,
        statement: Select,
        query: ShotGridScheduleQueryModel,
        *,
        include_display_filters: bool,
    ) -> Select:
        if query.target_kind == 'shot':
            statement = statement.where(ShotGridTask.task_kind == 'shot_video')
        elif query.target_kind == 'asset_item':
            statement = statement.where(ShotGridTask.task_kind == 'asset_image')
        if query.assignee_user_id is not None:
            statement = statement.where(ShotGridTask.assignee_user_id == query.assignee_user_id)
        if query.task_kind is not None:
            statement = statement.where(ShotGridTask.task_kind == query.task_kind)
        if query.task_status is not None:
            statement = statement.where(ShotGridTask.task_status == query.task_status)
        if query.priority is not None:
            statement = statement.where(ShotGridTask.priority == query.priority)
        if query.episode_id is not None:
            statement = statement.where(ShotGridShot.episode_id == query.episode_id)
        if query.scene_id is not None:
            statement = statement.where(ShotGridShot.scene_id == query.scene_id)
        if query.asset_type is not None:
            statement = statement.where(ShotGridAsset.asset_type == query.asset_type)
        if query.keyword:
            keyword = f'%{query.keyword}%'
            statement = statement.where(
                or_(
                    ShotGridTask.task_name.ilike(keyword),
                    cast(ShotGridShot.shot_no, String).ilike(keyword),
                    ShotGridShot.description.ilike(keyword),
                    ShotGridAsset.asset_name.ilike(keyword),
                    ShotGridAssetItem.production_item.ilike(keyword),
                )
            )
        if include_display_filters and query.only_delayed:
            statement = statement.where(
                ShotGridTask.baseline_end_time.is_not(None),
                ShotGridTask.expected_end_time > ShotGridTask.baseline_end_time,
            )
        if include_display_filters and query.only_conflicts:
            statement = statement.where(
                exists(
                    cls.build_overlap_statement(
                        project_id=ShotGridTask.project_id,
                        task_id=ShotGridTask.task_id,
                        assignee_user_id=ShotGridTask.assignee_user_id,
                        start_time=ShotGridTask.expected_start_time,
                        end_time=ShotGridTask.expected_end_time,
                    ).order_by(None)
                )
            )
        return statement

    @classmethod
    def build_schedule_statement(cls, project_id: int, query: ShotGridScheduleQueryModel) -> Select:
        """当前或基线与窗口相交的稳定分页查询。"""

        current_intersects = and_(
            ShotGridTask.expected_start_time.is_not(None),
            ShotGridTask.expected_end_time.is_not(None),
            ShotGridTask.expected_start_time < query.window_end,
            ShotGridTask.expected_end_time > query.window_start,
        )
        baseline_intersects = and_(
            ShotGridTask.baseline_start_time.is_not(None),
            ShotGridTask.baseline_end_time.is_not(None),
            ShotGridTask.baseline_start_time < query.window_end,
            ShotGridTask.baseline_end_time > query.window_start,
        )
        statement = cls._base_task_statement(query).where(
            ShotGridTask.project_id == project_id,
            or_(current_intersects, baseline_intersects),
        )
        statement = cls._apply_filters(statement, query, include_display_filters=True)
        return statement.order_by(
            statement.selected_columns.group_sort_order,
            ShotGridTask.expected_start_time.asc().nulls_last(),
            statement.selected_columns.target_sort_order.asc().nulls_last(),
            ShotGridTask.task_id,
        )

    @classmethod
    def build_unscheduled_statement(cls, project_id: int, query: ShotGridScheduleQueryModel) -> Select:
        """只查询已有真实任务、负责人有效且目标活动的未排期任务。"""

        statement = cls._base_task_statement(query).where(
            ShotGridTask.project_id == project_id,
            ShotGridTask.task_status != 'completed',
            ShotGridTask.expected_start_time.is_(None),
            ShotGridTask.expected_end_time.is_(None),
        )
        statement = cls._apply_filters(statement, query, include_display_filters=False)
        return statement.order_by(
            statement.selected_columns.group_sort_order,
            statement.selected_columns.target_sort_order.asc().nulls_last(),
            ShotGridTask.task_id,
        )

    @classmethod
    def build_overlap_statement(
        cls,
        *,
        project_id: Any,
        task_id: Any,
        assignee_user_id: Any,
        start_time: Any,
        end_time: Any,
    ) -> Select:
        """冲突查询不接收 UI 筛选，按自然时间半开区间计算。"""

        other = aliased(ShotGridTask, name='schedule_overlap_task')
        member = aliased(ShotGridProjectMember, name='schedule_overlap_member')
        user = aliased(SysUser, name='schedule_overlap_user')
        shot = aliased(ShotGridShot, name='schedule_overlap_shot')
        episode = aliased(ShotGridEpisode, name='schedule_overlap_episode')
        scene = aliased(ShotGridScene, name='schedule_overlap_scene')
        asset_item = aliased(ShotGridAssetItem, name='schedule_overlap_asset_item')
        asset = aliased(ShotGridAsset, name='schedule_overlap_asset')
        target_active = or_(
            and_(
                other.task_kind == 'shot_video',
                shot.lifecycle_status == 'active',
                shot.del_flag == '0',
                episode.lifecycle_status == 'active',
                episode.del_flag == '0',
                scene.lifecycle_status == 'active',
                scene.del_flag == '0',
            ),
            and_(
                other.task_kind == 'asset_image',
                asset_item.lifecycle_status == 'active',
                asset_item.del_flag == '0',
                asset.lifecycle_status == 'active',
                asset.del_flag == '0',
            ),
        )
        return (
            select(other.task_id)
            .join(
                member,
                and_(member.project_id == other.project_id, member.user_id == other.assignee_user_id),
            )
            .join(user, user.user_id == other.assignee_user_id)
            .outerjoin(shot, and_(shot.shot_id == other.shot_id, shot.project_id == other.project_id))
            .outerjoin(
                episode,
                and_(episode.episode_id == shot.episode_id, episode.project_id == other.project_id),
            )
            .outerjoin(
                scene,
                and_(
                    scene.scene_id == shot.scene_id,
                    scene.episode_id == shot.episode_id,
                    scene.project_id == other.project_id,
                ),
            )
            .outerjoin(
                asset_item,
                and_(asset_item.asset_item_id == other.asset_item_id, asset_item.project_id == other.project_id),
            )
            .outerjoin(
                asset,
                and_(asset.asset_id == asset_item.asset_id, asset.project_id == other.project_id),
            )
            .where(
                other.project_id == project_id,
                other.assignee_user_id == assignee_user_id,
                other.task_id != task_id,
                other.task_status != 'completed',
                other.del_flag == '0',
                other.expected_start_time.is_not(None),
                other.expected_end_time.is_not(None),
                other.expected_start_time < end_time,
                other.expected_end_time > start_time,
                member.member_status == 'active',
                member.project_role == 'creator',
                user.status == '0',
                user.del_flag == '0',
                target_active,
            )
            .order_by(other.task_id)
        )

    @staticmethod
    def build_history_statement(task_id: int) -> Select:
        operator = aliased(SysUser, name='schedule_change_operator')
        return (
            select(
                ShotGridTaskScheduleChange.schedule_change_id,
                ShotGridTaskScheduleChange.task_id,
                ShotGridTaskScheduleChange.operator_user_id,
                operator.user_name.label('operator_user_name'),
                operator.nick_name.label('operator_nick_name'),
                ShotGridTaskScheduleChange.from_start_time,
                ShotGridTaskScheduleChange.from_end_time,
                ShotGridTaskScheduleChange.to_start_time,
                ShotGridTaskScheduleChange.to_end_time,
                ShotGridTaskScheduleChange.change_type,
                ShotGridTaskScheduleChange.operation_source,
                ShotGridTaskScheduleChange.change_reason,
                ShotGridTaskScheduleChange.overlap_acknowledged,
                ShotGridTaskScheduleChange.overlap_task_ids,
                ShotGridTaskScheduleChange.task_lock_version_before,
                ShotGridTaskScheduleChange.task_lock_version_after,
                ShotGridTaskScheduleChange.create_time,
            )
            .join(operator, operator.user_id == ShotGridTaskScheduleChange.operator_user_id)
            .where(ShotGridTaskScheduleChange.task_id == task_id)
            .order_by(
                ShotGridTaskScheduleChange.create_time.desc(),
                ShotGridTaskScheduleChange.schedule_change_id.desc(),
            )
        )

    @staticmethod
    def build_idempotency_statement(task_id: int, operator_user_id: int, idempotency_key: str) -> Select:
        return select(ShotGridTaskScheduleChange).where(
            ShotGridTaskScheduleChange.task_id == task_id,
            ShotGridTaskScheduleChange.operator_user_id == operator_user_id,
            ShotGridTaskScheduleChange.idempotency_key == idempotency_key,
        )

    @staticmethod
    def build_project_lock_statement(project_id: int) -> Select:
        return (
            select(ShotGridProject)
            .where(ShotGridProject.project_id == project_id, ShotGridProject.del_flag == '0')
            .with_for_update()
        )

    @staticmethod
    def build_task_lock_statement(project_id: int, task_id: int) -> Select:
        return (
            select(ShotGridTask)
            .where(
                ShotGridTask.project_id == project_id,
                ShotGridTask.task_id == task_id,
                ShotGridTask.del_flag == '0',
            )
            .with_for_update()
        )

    @staticmethod
    async def _page(
        db: AsyncSession,
        statement: Select,
        *,
        page_num: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        result = await db.execute(statement.offset((page_num - 1) * page_size).limit(page_size))
        return [dict(row) for row in result.mappings().all()], total

    @classmethod
    async def get_schedule_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridScheduleQueryModel,
    ) -> tuple[list[dict[str, Any]], int, int]:
        rows, total = await cls._page(
            db,
            cls.build_schedule_statement(project_id, query),
            page_num=query.page_num,
            page_size=query.page_size,
        )
        unscheduled_count = int(
            (
                await db.execute(
                    select(func.count()).select_from(cls.build_unscheduled_statement(project_id, query).subquery())
                )
            ).scalar_one()
        )
        return rows, total, unscheduled_count

    @classmethod
    async def get_unscheduled_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridScheduleQueryModel,
    ) -> tuple[list[dict[str, Any]], int]:
        return await cls._page(
            db,
            cls.build_unscheduled_statement(project_id, query),
            page_num=query.page_num,
            page_size=query.page_size,
        )

    @classmethod
    async def get_schedule_changes(
        cls,
        db: AsyncSession,
        task_id: int,
        *,
        page_num: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        return await cls._page(
            db,
            cls.build_history_statement(task_id),
            page_num=page_num,
            page_size=page_size,
        )

    @classmethod
    async def find_overlap_task_ids(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        task_id: int,
        assignee_user_id: int,
        start_time: datetime,
        end_time: datetime,
    ) -> list[int]:
        values = await db.scalars(
            cls.build_overlap_statement(
                project_id=project_id,
                task_id=task_id,
                assignee_user_id=assignee_user_id,
                start_time=start_time,
                end_time=end_time,
            )
        )
        return [int(value) for value in values]

    @classmethod
    async def get_idempotency_result(
        cls,
        db: AsyncSession,
        task_id: int,
        operator_user_id: int,
        idempotency_key: str,
    ) -> ShotGridTaskScheduleChange | None:
        return await db.scalar(cls.build_idempotency_statement(task_id, operator_user_id, idempotency_key))

    @classmethod
    async def lock_project(cls, db: AsyncSession, project_id: int) -> ShotGridProject | None:
        return await db.scalar(cls.build_project_lock_statement(project_id))

    @classmethod
    async def lock_task(cls, db: AsyncSession, project_id: int, task_id: int) -> ShotGridTask | None:
        return await db.scalar(cls.build_task_lock_statement(project_id, task_id))

    @classmethod
    async def lock_actor_member(
        cls,
        db: AsyncSession,
        project_id: int,
        user_id: int,
    ) -> ShotGridProjectMember | None:
        return await db.scalar(
            select(ShotGridProjectMember)
            .where(
                ShotGridProjectMember.project_id == project_id,
                ShotGridProjectMember.user_id == user_id,
                ShotGridProjectMember.member_status == 'active',
            )
            .with_for_update()
        )

    @classmethod
    async def add_schedule_change(
        cls,
        db: AsyncSession,
        change: ShotGridTaskScheduleChange,
    ) -> ShotGridTaskScheduleChange:
        db.add(change)
        await db.flush()
        return change

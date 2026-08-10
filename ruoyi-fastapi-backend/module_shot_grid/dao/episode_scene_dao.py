from typing import Any

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.entity.do.project_do import ShotGridEpisode, ShotGridProject, ShotGridScene, ShotGridShot
from module_shot_grid.entity.do.storage_do import (
    ShotGridProjectStorage,
    ShotGridStorageOperation,
)
from module_shot_grid.entity.vo.episode_scene_vo import ShotGridEpisodeQueryModel, ShotGridSceneQueryModel


class ShotGridEpisodeSceneDao:
    """集与场次普通管理数据访问层。"""

    @classmethod
    async def lock_project_storage(
        cls,
        db: AsyncSession,
        project_id: int,
    ) -> tuple[ShotGridProject | None, ShotGridProjectStorage | None]:
        """锁定项目行，使普通写入与 Excel 正式导入按项目串行。"""

        statement = (
            select(ShotGridProject, ShotGridProjectStorage)
            .outerjoin(ShotGridProjectStorage, ShotGridProjectStorage.project_id == ShotGridProject.project_id)
            .where(
                ShotGridProject.project_id == project_id,
                ShotGridProject.del_flag == '0',
            )
            .with_for_update(of=ShotGridProject)
        )
        row = (await db.execute(statement)).one_or_none()
        if row is None:
            return None, None
        return row[0], row[1]

    @classmethod
    async def get_episode_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridEpisodeQueryModel,
    ) -> tuple[list[dict[str, Any]], int]:
        scene_counts = (
            select(
                ShotGridScene.episode_id.label('episode_id'),
                func.count(ShotGridScene.scene_id).label('scene_count'),
                func.count(ShotGridScene.scene_id)
                .filter(ShotGridScene.lifecycle_status == 'active')
                .label('active_scene_count'),
            )
            .where(ShotGridScene.del_flag == '0')
            .group_by(ShotGridScene.episode_id)
            .subquery('episode_scene_counts')
        )
        shot_counts = (
            select(
                ShotGridShot.episode_id.label('episode_id'),
                func.count(ShotGridShot.shot_id).label('shot_count'),
                func.count(ShotGridShot.shot_id)
                .filter(ShotGridShot.lifecycle_status == 'active')
                .label('active_shot_count'),
            )
            .where(ShotGridShot.del_flag == '0')
            .group_by(ShotGridShot.episode_id)
            .subquery('episode_shot_counts')
        )
        operation_status = cls._latest_episode_operation_status(project_id)
        statement = (
            select(
                *cls._episode_columns(),
                operation_status,
                func.coalesce(scene_counts.c.scene_count, 0).label('scene_count'),
                func.coalesce(scene_counts.c.active_scene_count, 0).label('active_scene_count'),
                func.coalesce(shot_counts.c.shot_count, 0).label('shot_count'),
                func.coalesce(shot_counts.c.active_shot_count, 0).label('active_shot_count'),
            )
            .outerjoin(scene_counts, scene_counts.c.episode_id == ShotGridEpisode.episode_id)
            .outerjoin(shot_counts, shot_counts.c.episode_id == ShotGridEpisode.episode_id)
            .where(
                ShotGridEpisode.project_id == project_id,
                ShotGridEpisode.del_flag == '0',
                ShotGridEpisode.lifecycle_status == query.lifecycle_status if query.lifecycle_status else True,
            )
        )
        keyword = query.keyword.strip() if query.keyword else None
        if keyword:
            statement = statement.where(
                or_(
                    ShotGridEpisode.episode_name.ilike(f'%{keyword}%'),
                    ShotGridEpisode.description.ilike(f'%{keyword}%'),
                )
            )
        order_columns = {
            'episodeNo': ShotGridEpisode.episode_no,
            'episodeName': ShotGridEpisode.episode_name,
            'sortOrder': ShotGridEpisode.sort_order,
            'createTime': ShotGridEpisode.create_time,
        }
        order_column = order_columns[query.order_by_column]
        statement = statement.order_by(
            asc(order_column) if query.is_asc == 'ascending' else desc(order_column),
            ShotGridEpisode.episode_id,
        )
        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        rows = (
            (await db.execute(statement.offset((query.page_num - 1) * query.page_size).limit(query.page_size)))
            .mappings()
            .all()
        )
        return [dict(row) for row in rows], total

    @classmethod
    async def get_episode_detail(
        cls,
        db: AsyncSession,
        project_id: int,
        episode_id: int,
    ) -> dict[str, Any] | None:
        scene_count = (
            select(func.count(ShotGridScene.scene_id))
            .where(
                ShotGridScene.project_id == project_id,
                ShotGridScene.episode_id == episode_id,
                ShotGridScene.del_flag == '0',
            )
            .scalar_subquery()
        )
        active_scene_count = (
            select(func.count(ShotGridScene.scene_id))
            .where(
                ShotGridScene.project_id == project_id,
                ShotGridScene.episode_id == episode_id,
                ShotGridScene.lifecycle_status == 'active',
                ShotGridScene.del_flag == '0',
            )
            .scalar_subquery()
        )
        shot_count = (
            select(func.count(ShotGridShot.shot_id))
            .where(
                ShotGridShot.project_id == project_id,
                ShotGridShot.episode_id == episode_id,
                ShotGridShot.del_flag == '0',
            )
            .scalar_subquery()
        )
        active_shot_count = (
            select(func.count(ShotGridShot.shot_id))
            .where(
                ShotGridShot.project_id == project_id,
                ShotGridShot.episode_id == episode_id,
                ShotGridShot.lifecycle_status == 'active',
                ShotGridShot.del_flag == '0',
            )
            .scalar_subquery()
        )
        statement = select(
            *cls._episode_columns(),
            cls._latest_episode_operation_status(project_id),
            scene_count.label('scene_count'),
            active_scene_count.label('active_scene_count'),
            shot_count.label('shot_count'),
            active_shot_count.label('active_shot_count'),
        ).where(
            ShotGridEpisode.project_id == project_id,
            ShotGridEpisode.episode_id == episode_id,
            ShotGridEpisode.del_flag == '0',
        )
        row = (await db.execute(statement)).mappings().one_or_none()
        return dict(row) if row is not None else None

    @staticmethod
    async def get_episode_for_update(
        db: AsyncSession,
        project_id: int,
        episode_id: int,
    ) -> ShotGridEpisode | None:
        statement = (
            select(ShotGridEpisode)
            .where(
                ShotGridEpisode.project_id == project_id,
                ShotGridEpisode.episode_id == episode_id,
                ShotGridEpisode.del_flag == '0',
            )
            .with_for_update()
        )
        return (await db.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def episode_no_exists(
        db: AsyncSession,
        project_id: int,
        episode_no: int,
    ) -> bool:
        statement = select(ShotGridEpisode.episode_id).where(
            ShotGridEpisode.project_id == project_id,
            ShotGridEpisode.episode_no == episode_no,
            ShotGridEpisode.del_flag == '0',
        )
        return (await db.execute(statement)).scalar_one_or_none() is not None

    @staticmethod
    async def add_episode(db: AsyncSession, episode: ShotGridEpisode) -> ShotGridEpisode:
        db.add(episode)
        await db.flush()
        return episode

    @staticmethod
    async def has_active_scenes(db: AsyncSession, project_id: int, episode_id: int) -> bool:
        statement = select(ShotGridScene.scene_id).where(
            ShotGridScene.project_id == project_id,
            ShotGridScene.episode_id == episode_id,
            ShotGridScene.lifecycle_status == 'active',
            ShotGridScene.del_flag == '0',
        )
        return (await db.execute(statement.limit(1))).scalar_one_or_none() is not None

    @classmethod
    async def get_scene_page(
        cls,
        db: AsyncSession,
        project_id: int,
        episode_id: int,
        query: ShotGridSceneQueryModel,
    ) -> tuple[list[dict[str, Any]], int]:
        shot_counts = (
            select(
                ShotGridShot.scene_id.label('scene_id'),
                func.count(ShotGridShot.shot_id).label('shot_count'),
                func.count(ShotGridShot.shot_id)
                .filter(ShotGridShot.lifecycle_status == 'active')
                .label('active_shot_count'),
            )
            .where(ShotGridShot.del_flag == '0')
            .group_by(ShotGridShot.scene_id)
            .subquery('scene_shot_counts')
        )
        statement = (
            select(
                *cls._scene_columns(),
                func.coalesce(shot_counts.c.shot_count, 0).label('shot_count'),
                func.coalesce(shot_counts.c.active_shot_count, 0).label('active_shot_count'),
            )
            .outerjoin(shot_counts, shot_counts.c.scene_id == ShotGridScene.scene_id)
            .where(
                ShotGridScene.project_id == project_id,
                ShotGridScene.episode_id == episode_id,
                ShotGridScene.del_flag == '0',
                ShotGridScene.lifecycle_status == query.lifecycle_status if query.lifecycle_status else True,
            )
        )
        keyword = query.keyword.strip() if query.keyword else None
        if keyword:
            statement = statement.where(
                or_(
                    ShotGridScene.scene_name.ilike(f'%{keyword}%'),
                    ShotGridScene.description.ilike(f'%{keyword}%'),
                )
            )
        order_columns = {
            'sceneNo': ShotGridScene.scene_no,
            'sceneName': ShotGridScene.scene_name,
            'sortOrder': ShotGridScene.sort_order,
            'createTime': ShotGridScene.create_time,
        }
        order_column = order_columns[query.order_by_column]
        statement = statement.order_by(
            asc(order_column) if query.is_asc == 'ascending' else desc(order_column),
            ShotGridScene.scene_id,
        )
        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        rows = (
            (await db.execute(statement.offset((query.page_num - 1) * query.page_size).limit(query.page_size)))
            .mappings()
            .all()
        )
        return [dict(row) for row in rows], total

    @classmethod
    async def get_scene_detail(
        cls,
        db: AsyncSession,
        project_id: int,
        scene_id: int,
    ) -> dict[str, Any] | None:
        shot_count = (
            select(func.count(ShotGridShot.shot_id))
            .where(
                ShotGridShot.project_id == project_id,
                ShotGridShot.scene_id == scene_id,
                ShotGridShot.del_flag == '0',
            )
            .scalar_subquery()
        )
        active_shot_count = (
            select(func.count(ShotGridShot.shot_id))
            .where(
                ShotGridShot.project_id == project_id,
                ShotGridShot.scene_id == scene_id,
                ShotGridShot.lifecycle_status == 'active',
                ShotGridShot.del_flag == '0',
            )
            .scalar_subquery()
        )
        statement = select(
            *cls._scene_columns(),
            shot_count.label('shot_count'),
            active_shot_count.label('active_shot_count'),
        ).where(
            ShotGridScene.project_id == project_id,
            ShotGridScene.scene_id == scene_id,
            ShotGridScene.del_flag == '0',
        )
        row = (await db.execute(statement)).mappings().one_or_none()
        return dict(row) if row is not None else None

    @staticmethod
    async def get_scene_for_update(
        db: AsyncSession,
        project_id: int,
        scene_id: int,
    ) -> ShotGridScene | None:
        statement = (
            select(ShotGridScene)
            .where(
                ShotGridScene.project_id == project_id,
                ShotGridScene.scene_id == scene_id,
                ShotGridScene.del_flag == '0',
            )
            .with_for_update()
        )
        return (await db.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def scene_no_exists(
        db: AsyncSession,
        project_id: int,
        episode_id: int,
        scene_no: int,
    ) -> bool:
        statement = select(ShotGridScene.scene_id).where(
            ShotGridScene.project_id == project_id,
            ShotGridScene.episode_id == episode_id,
            ShotGridScene.scene_no == scene_no,
            ShotGridScene.del_flag == '0',
        )
        return (await db.execute(statement)).scalar_one_or_none() is not None

    @staticmethod
    async def add_scene(db: AsyncSession, scene: ShotGridScene) -> ShotGridScene:
        db.add(scene)
        await db.flush()
        return scene

    @staticmethod
    async def has_active_shots(db: AsyncSession, project_id: int, scene_id: int) -> bool:
        statement = select(ShotGridShot.shot_id).where(
            ShotGridShot.project_id == project_id,
            ShotGridShot.scene_id == scene_id,
            ShotGridShot.lifecycle_status == 'active',
            ShotGridShot.del_flag == '0',
        )
        return (await db.execute(statement.limit(1))).scalar_one_or_none() is not None

    @staticmethod
    async def add_storage_operation(db: AsyncSession, operation: ShotGridStorageOperation) -> None:
        db.add(operation)
        await db.flush()

    @staticmethod
    def _episode_columns() -> list[Any]:
        return [
            ShotGridEpisode.episode_id,
            ShotGridEpisode.project_id,
            ShotGridEpisode.episode_no,
            ShotGridEpisode.storage_dir_name,
            ShotGridEpisode.episode_name,
            ShotGridEpisode.description,
            ShotGridEpisode.sort_order,
            ShotGridEpisode.lifecycle_status,
            ShotGridEpisode.create_by,
            ShotGridEpisode.create_time,
            ShotGridEpisode.update_by,
            ShotGridEpisode.update_time,
            ShotGridEpisode.remark,
            ShotGridEpisode.lock_version,
        ]

    @staticmethod
    def _scene_columns() -> list[Any]:
        return [
            ShotGridScene.scene_id,
            ShotGridScene.project_id,
            ShotGridScene.episode_id,
            ShotGridScene.scene_no,
            ShotGridScene.scene_name,
            ShotGridScene.description,
            ShotGridScene.sort_order,
            ShotGridScene.lifecycle_status,
            ShotGridScene.create_by,
            ShotGridScene.create_time,
            ShotGridScene.update_by,
            ShotGridScene.update_time,
            ShotGridScene.remark,
            ShotGridScene.lock_version,
        ]

    @staticmethod
    def _latest_episode_operation_status(project_id: int) -> Any:
        return (
            select(ShotGridStorageOperation.operation_status)
            .where(
                ShotGridStorageOperation.project_id == project_id,
                ShotGridStorageOperation.aggregate_type == 'episode',
                ShotGridStorageOperation.aggregate_id == ShotGridEpisode.episode_id,
            )
            .order_by(ShotGridStorageOperation.operation_id.desc())
            .limit(1)
            .correlate(ShotGridEpisode)
            .scalar_subquery()
            .label('operation_status')
        )

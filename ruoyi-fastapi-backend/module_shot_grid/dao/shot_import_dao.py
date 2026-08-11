from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.user_do import SysUser
from module_shot_grid.entity.do.asset_do import ShotGridAsset
from module_shot_grid.entity.do.project_do import (
    ShotGridEpisode,
    ShotGridProject,
    ShotGridProjectMember,
    ShotGridScene,
    ShotGridShot,
)
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage


class ShotGridShotImportDao:
    """镜头导入所需的批量查询和加锁读取。"""

    @staticmethod
    async def get_project_storage(
        db: AsyncSession,
        project_id: int,
        *,
        for_update: bool = False,
    ) -> tuple[ShotGridProject | None, ShotGridProjectStorage | None]:
        statement = (
            select(ShotGridProject, ShotGridProjectStorage)
            .outerjoin(ShotGridProjectStorage, ShotGridProjectStorage.project_id == ShotGridProject.project_id)
            .where(
                ShotGridProject.project_id == project_id,
                ShotGridProject.del_flag == '0',
            )
        )
        if for_update:
            statement = statement.with_for_update(of=ShotGridProject)
        row = (await db.execute(statement)).one_or_none()
        if row is None:
            return None, None
        return row[0], row[1]

    @staticmethod
    async def list_assignable_members(
        db: AsyncSession,
        project_id: int,
        names: set[str],
    ) -> list[tuple[int, str, str, str | None]]:
        if not names:
            return []
        statement = (
            select(
                SysUser.user_id,
                SysUser.user_name,
                SysUser.nick_name,
                ShotGridProjectMember.producer_code,
            )
            .join(
                ShotGridProjectMember,
                ShotGridProjectMember.user_id == SysUser.user_id,
            )
            .where(
                ShotGridProjectMember.project_id == project_id,
                ShotGridProjectMember.member_status == 'active',
                SysUser.status == '0',
                SysUser.del_flag == '0',
                (SysUser.user_name.in_(names) | SysUser.nick_name.in_(names)),
            )
        )
        return [tuple(row) for row in (await db.execute(statement)).all()]

    @staticmethod
    async def list_environment_assets(
        db: AsyncSession,
        project_id: int,
        normalized_names: set[str],
    ) -> list[ShotGridAsset]:
        if not normalized_names:
            return []
        statement = select(ShotGridAsset).where(
            ShotGridAsset.project_id == project_id,
            ShotGridAsset.asset_type == 'Environment',
            ShotGridAsset.asset_name_key.in_(normalized_names),
            ShotGridAsset.lifecycle_status == 'active',
            ShotGridAsset.del_flag == '0',
        )
        return list((await db.execute(statement)).scalars().all())

    @staticmethod
    async def list_episodes(
        db: AsyncSession,
        project_id: int,
        episode_numbers: set[int],
    ) -> list[ShotGridEpisode]:
        if not episode_numbers:
            return []
        statement = select(ShotGridEpisode).where(
            ShotGridEpisode.project_id == project_id,
            ShotGridEpisode.episode_no.in_(episode_numbers),
            ShotGridEpisode.del_flag == '0',
        )
        return list((await db.execute(statement)).scalars().all())

    @staticmethod
    async def list_scenes(
        db: AsyncSession,
        episode_ids: Iterable[int],
        scene_numbers: set[int],
    ) -> list[ShotGridScene]:
        episode_id_list = list(episode_ids)
        if not episode_id_list or not scene_numbers:
            return []
        statement = select(ShotGridScene).where(
            ShotGridScene.episode_id.in_(episode_id_list),
            ShotGridScene.scene_no.in_(scene_numbers),
            ShotGridScene.del_flag == '0',
        )
        return list((await db.execute(statement)).scalars().all())

    @staticmethod
    async def list_shots(
        db: AsyncSession,
        episode_ids: Iterable[int],
        shot_numbers: set[int],
    ) -> list[ShotGridShot]:
        episode_id_list = list(episode_ids)
        if not episode_id_list or not shot_numbers:
            return []
        statement = select(ShotGridShot).where(
            ShotGridShot.episode_id.in_(episode_id_list),
            ShotGridShot.shot_no.in_(shot_numbers),
            ShotGridShot.del_flag == '0',
        )
        return list((await db.execute(statement)).scalars().all())

    @staticmethod
    async def flush(db: AsyncSession) -> None:
        await db.flush()

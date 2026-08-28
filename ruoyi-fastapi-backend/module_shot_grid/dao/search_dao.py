from typing import Any

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from module_admin.entity.do.file_do import SysFileInfo
from module_shot_grid.entity.do.asset_do import ShotGridAsset
from module_shot_grid.entity.do.project_do import (
    ShotGridEpisode,
    ShotGridProject,
    ShotGridProjectMember,
    ShotGridScene,
    ShotGridShot,
)
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion, ShotGridVersionFile


class ShotGridSearchDao:
    """跨领域只读搜索；所有查询均在 SQL 层收敛项目可见范围。"""

    @staticmethod
    def _apply_project_scope(statement: Select, user_id: int, has_all_scope: bool) -> Select:
        if has_all_scope:
            return statement
        return statement.join(
            ShotGridProjectMember,
            (ShotGridProjectMember.project_id == ShotGridProject.project_id)
            & (ShotGridProjectMember.user_id == user_id)
            & (ShotGridProjectMember.member_status == 'active'),
        )

    @classmethod
    async def search_shots(
        cls,
        db: AsyncSession,
        *,
        keyword: str,
        limit: int,
        user_id: int,
        has_all_scope: bool,
    ) -> list[dict[str, Any]]:
        pattern = f'%{keyword}%'
        shot_code = func.concat(
            'EP',
            func.lpad(cast(ShotGridEpisode.episode_no, String), 3, '0'),
            '-',
            func.lpad(cast(ShotGridScene.scene_no, String), 3, '0'),
            '-',
            func.lpad(
                cast(ShotGridShot.shot_no, String),
                func.greatest(4, func.length(cast(ShotGridShot.shot_no, String))),
                '0',
            ),
        )
        statement = (
            select(
                ShotGridShot.shot_id,
                ShotGridShot.project_id,
                ShotGridProject.project_code,
                ShotGridProject.project_name,
                ShotGridEpisode.episode_no,
                ShotGridScene.scene_no,
                ShotGridScene.scene_name,
                ShotGridShot.shot_no,
                ShotGridShot.description,
                ShotGridShot.lifecycle_status,
            )
            .join(ShotGridProject, ShotGridProject.project_id == ShotGridShot.project_id)
            .join(ShotGridEpisode, ShotGridEpisode.episode_id == ShotGridShot.episode_id)
            .join(ShotGridScene, ShotGridScene.scene_id == ShotGridShot.scene_id)
            .where(
                ShotGridProject.del_flag == '0',
                ShotGridEpisode.del_flag == '0',
                ShotGridScene.del_flag == '0',
                ShotGridShot.del_flag == '0',
                or_(
                    ShotGridProject.project_code.ilike(pattern),
                    ShotGridProject.project_name.ilike(pattern),
                    ShotGridScene.scene_name.ilike(pattern),
                    ShotGridShot.storage_dir_name.ilike(pattern),
                    ShotGridShot.description.ilike(pattern),
                    ShotGridShot.dialogue.ilike(pattern),
                    shot_code.ilike(pattern),
                    cast(ShotGridEpisode.episode_no, String).ilike(pattern),
                    cast(ShotGridScene.scene_no, String).ilike(pattern),
                    cast(ShotGridShot.shot_no, String).ilike(pattern),
                ),
            )
            .order_by(
                ShotGridProject.project_code.asc(),
                ShotGridEpisode.episode_no.asc(),
                ShotGridShot.sort_order.asc(),
                ShotGridShot.shot_id.asc(),
            )
            .limit(limit + 1)
        )
        statement = cls._apply_project_scope(statement, user_id, has_all_scope)
        rows = (await db.execute(statement)).mappings().all()
        return [dict(row) for row in rows]

    @classmethod
    async def search_assets(
        cls,
        db: AsyncSession,
        *,
        keyword: str,
        limit: int,
        user_id: int,
        has_all_scope: bool,
    ) -> list[dict[str, Any]]:
        pattern = f'%{keyword}%'
        statement = (
            select(
                ShotGridAsset.asset_id,
                ShotGridAsset.project_id,
                ShotGridProject.project_code,
                ShotGridProject.project_name,
                ShotGridAsset.asset_name,
                ShotGridAsset.asset_type,
                ShotGridAsset.description,
                ShotGridAsset.lifecycle_status,
            )
            .join(ShotGridProject, ShotGridProject.project_id == ShotGridAsset.project_id)
            .where(
                ShotGridProject.del_flag == '0',
                ShotGridAsset.del_flag == '0',
                or_(
                    ShotGridProject.project_code.ilike(pattern),
                    ShotGridProject.project_name.ilike(pattern),
                    ShotGridAsset.asset_name.ilike(pattern),
                    ShotGridAsset.asset_name_key.ilike(pattern),
                    ShotGridAsset.asset_type.ilike(pattern),
                    ShotGridAsset.description.ilike(pattern),
                ),
            )
            .order_by(
                ShotGridProject.project_code.asc(),
                ShotGridAsset.sort_order.asc(),
                ShotGridAsset.asset_id.asc(),
            )
            .limit(limit + 1)
        )
        statement = cls._apply_project_scope(statement, user_id, has_all_scope)
        rows = (await db.execute(statement)).mappings().all()
        return [dict(row) for row in rows]

    @classmethod
    async def search_files(
        cls,
        db: AsyncSession,
        *,
        keyword: str,
        limit: int,
        user_id: int,
        has_all_scope: bool,
    ) -> list[dict[str, Any]]:
        pattern = f'%{keyword}%'
        statement = (
            select(
                ShotGridVersionFile.file_id,
                ShotGridVersion.version_id,
                ShotGridVersion.project_id,
                ShotGridProject.project_code,
                ShotGridProject.project_name,
                ShotGridTask.task_name,
                ShotGridTask.task_kind,
                ShotGridVersion.version_no,
                ShotGridVersion.version_status,
                ShotGridVersionFile.business_file_name,
            )
            .join(ShotGridVersion, ShotGridVersion.version_id == ShotGridVersionFile.version_id)
            .join(ShotGridTask, ShotGridTask.task_id == ShotGridVersion.task_id)
            .join(ShotGridProject, ShotGridProject.project_id == ShotGridVersion.project_id)
            .join(SysFileInfo, SysFileInfo.file_id == ShotGridVersionFile.file_id)
            .where(
                ShotGridProject.del_flag == '0',
                ShotGridTask.del_flag == '0',
                SysFileInfo.status == 'active',
                SysFileInfo.del_flag == '0',
                or_(
                    ShotGridProject.project_code.ilike(pattern),
                    ShotGridProject.project_name.ilike(pattern),
                    ShotGridTask.task_name.ilike(pattern),
                    ShotGridVersionFile.business_file_name.ilike(pattern),
                    SysFileInfo.original_name.ilike(pattern),
                ),
            )
            .order_by(ShotGridVersion.submitted_time.desc(), ShotGridVersionFile.sort_order.asc())
            .limit(limit + 1)
        )
        statement = cls._apply_project_scope(statement, user_id, has_all_scope)
        rows = (await db.execute(statement)).mappings().all()
        return [dict(row) for row in rows]

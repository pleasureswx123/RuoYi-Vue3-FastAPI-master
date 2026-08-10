from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.entity.do.project_do import ShotGridProjectMember


class ShotGridProjectMemberDao:
    """Shot Grid 项目成员数据访问层。"""

    @classmethod
    async def get_member(
        cls,
        db: AsyncSession,
        project_id: int,
        user_id: int,
    ) -> ShotGridProjectMember | None:
        """按项目和用户查询成员关系。"""
        return (
            await db.execute(
                select(ShotGridProjectMember).where(
                    ShotGridProjectMember.project_id == project_id,
                    ShotGridProjectMember.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

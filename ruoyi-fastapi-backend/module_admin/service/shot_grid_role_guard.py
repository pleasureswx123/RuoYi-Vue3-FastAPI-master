from __future__ import annotations

from typing import TYPE_CHECKING

from config.env import DataBaseConfig

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from module_shot_grid.service.platform_role_service import ShotGridPlatformRoleService


def _shot_grid_role_binding_enabled() -> bool:
    """Shot Grid 平台角色联动当前只在 PostgreSQL 契约下启用。"""

    return DataBaseConfig.db_type == 'postgresql'


def _platform_role_service() -> type[ShotGridPlatformRoleService]:
    # 延迟导入避免非 PostgreSQL 平台仅加载 module_admin 时注册部分 Shot Grid 元数据。
    from module_shot_grid.service.platform_role_service import ShotGridPlatformRoleService  # noqa: PLC0415

    return ShotGridPlatformRoleService


async def validate_role_mutation(
    db: AsyncSession,
    role_id: int,
    *,
    previous_role_key: str | None = None,
    deleting: bool = False,
) -> None:
    if not _shot_grid_role_binding_enabled():
        return
    await _platform_role_service().validate_platform_role_mutation(
        db,
        role_id,
        previous_role_key=previous_role_key,
        deleting=deleting,
    )


async def validate_menu_mutation(db: AsyncSession, menu_id: int) -> None:
    if not _shot_grid_role_binding_enabled():
        return
    await _platform_role_service().validate_menu_mutation(db, menu_id)


async def ensure_user_role_replacement_safe(
    db: AsyncSession,
    user_id: int,
    retained_role_ids: set[int],
) -> set[int]:
    if not _shot_grid_role_binding_enabled():
        return set()
    return await _platform_role_service().ensure_user_role_replacement_safe(
        db,
        user_id,
        retained_role_ids,
    )


async def ensure_user_role_deletion_safe(
    db: AsyncSession,
    user_ids: set[int],
    role_id: int,
) -> None:
    if not _shot_grid_role_binding_enabled():
        return
    await _platform_role_service().ensure_user_role_deletion_safe(db, user_ids, role_id)


async def ensure_user_deletion_safe(db: AsyncSession, user_ids: set[int]) -> None:
    if not _shot_grid_role_binding_enabled():
        return
    await _platform_role_service().ensure_user_deletion_safe(db, user_ids)


async def lock_user_role_mutation(db: AsyncSession, user_ids: set[int]) -> None:
    if not _shot_grid_role_binding_enabled():
        return
    await _platform_role_service().lock_target_users(db, user_ids)

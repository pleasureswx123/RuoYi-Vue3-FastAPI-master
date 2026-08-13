"""增加平台管理端 NAS 根目录管理菜单。

Revision ID: 20260812_08
Revises: 20260812_07
Create Date: 2026-08-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = '20260812_08'
down_revision: str | Sequence[str] | None = '20260812_07'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_MARKER = 'shotgrid_migration_20260812_08'
MENU_ROUTE_NAME = 'ShotGridNasRoot'
PERMISSIONS = (
    ('新增 NAS 根目录', 1, 'shotgrid:storageRoot:add'),
    ('修改或启停 NAS 根目录', 2, 'shotgrid:storageRoot:edit'),
    ('探测 NAS 根目录', 3, 'shotgrid:storageRoot:probe'),
)


def _execute(statement: str) -> None:
    op.execute(statement)


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return

    _execute(
        f"""
        INSERT INTO sys_menu (
            menu_name, parent_id, order_num, path, component, query, route_name,
            is_frame, is_cache, menu_type, visible, status, perms, icon,
            create_by, create_time, update_by, update_time, remark
        )
        SELECT
            'NAS 根目录', parent.menu_id, 12, 'nas', 'system/nas/index', '', '{MENU_ROUTE_NAME}',
            1, 0, 'C', '0', '0', 'shotgrid:storageRoot:query', 'folder-opened',
            '{SEED_MARKER}', current_timestamp, '', NULL, 'Shot Grid NAS 根目录白名单管理'
        FROM (
            SELECT menu_id
            FROM sys_menu
            WHERE parent_id = 0 AND path = 'system' AND menu_type = 'M'
            ORDER BY menu_id
            LIMIT 1
        ) parent
        WHERE NOT EXISTS (
            SELECT 1 FROM sys_menu WHERE route_name = '{MENU_ROUTE_NAME}' AND menu_type = 'C'
        )
        """
    )

    for menu_name, order_num, permission in PERMISSIONS:
        _execute(
            f"""
            INSERT INTO sys_menu (
                menu_name, parent_id, order_num, path, component, query, route_name,
                is_frame, is_cache, menu_type, visible, status, perms, icon,
                create_by, create_time, update_by, update_time, remark
            )
            SELECT
                '{menu_name}', parent.menu_id, {order_num}, '#', '', '', '',
                1, 0, 'F', '0', '0', '{permission}', '#',
                '{SEED_MARKER}', current_timestamp, '', NULL, 'Shot Grid NAS 根目录管理权限'
            FROM (
                SELECT menu_id
                FROM sys_menu
                WHERE route_name = '{MENU_ROUTE_NAME}' AND menu_type = 'C'
                ORDER BY menu_id
                LIMIT 1
            ) parent
            WHERE NOT EXISTS (
                SELECT 1 FROM sys_menu
                WHERE parent_id = parent.menu_id AND perms = '{permission}' AND menu_type = 'F'
            )
            """
        )


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    _execute(
        f"""
        DELETE FROM sys_role_menu
        WHERE menu_id IN (SELECT menu_id FROM sys_menu WHERE create_by = '{SEED_MARKER}')
        """
    )
    _execute(f"DELETE FROM sys_menu WHERE create_by = '{SEED_MARKER}' AND menu_type = 'F'")
    _execute(
        f"""
        DELETE FROM sys_menu menu
        WHERE menu.create_by = '{SEED_MARKER}'
          AND menu.route_name = '{MENU_ROUTE_NAME}'
          AND NOT EXISTS (SELECT 1 FROM sys_menu child WHERE child.parent_id = menu.menu_id)
        """
    )

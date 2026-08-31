"""增加 NAS 根目录平台配置删除权限。"""

from collections.abc import Sequence

from alembic import op

revision: str = '20260831_26'
down_revision: str | Sequence[str] | None = '20260831_25'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_MARKER = 'shotgrid_migration_20260831_26'
MENU_ROUTE_NAME = 'ShotGridNasRoot'
PERMISSION = 'shotgrid:storageRoot:remove'


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def upgrade() -> None:
    if not _is_postgresql():
        return

    op.execute(
        f"""
INSERT INTO sys_menu (
    menu_name, parent_id, order_num, path, component, query, route_name,
    is_frame, is_cache, menu_type, visible, status, perms, icon,
    create_by, create_time, update_by, update_time, remark
)
SELECT
    '删除 NAS 根目录', parent.menu_id, 4, '#', '', '', '',
    1, 0, 'F', '0', '0', '{PERMISSION}', '#',
    '{SEED_MARKER}', current_timestamp, '', NULL, '仅删除平台配置，不删除 NAS 目录或文件'
FROM (
    SELECT menu_id
    FROM sys_menu
    WHERE route_name = '{MENU_ROUTE_NAME}' AND menu_type = 'C'
    ORDER BY menu_id
    LIMIT 1
) parent
WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms = '{PERMISSION}' AND menu_type = 'F')
"""
    )


def downgrade() -> None:
    if not _is_postgresql():
        return

    op.execute(
        f"DELETE FROM sys_role_menu WHERE menu_id IN (SELECT menu_id FROM sys_menu WHERE perms = '{PERMISSION}')"
    )
    op.execute(f"DELETE FROM sys_menu WHERE perms = '{PERMISSION}' AND create_by = '{SEED_MARKER}'")

"""增加镜头和资产独立强制删除权限，不自动授予角色。"""

from alembic import op

revision = '20261013_39'
down_revision = '20261012_38'
branch_labels = None
depends_on = None

UPGRADE_SQL = """
INSERT INTO sys_menu (menu_name, parent_id, order_num, path, component, query, route_name,
 is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, remark)
SELECT seed.name, parent.menu_id, 99, '#', '', '', '', 1, 0, 'F', '0', '0', seed.perm, '#',
 'shotgrid_migration_20261013_39', current_timestamp, '强制逻辑删除，保留历史和NAS文件'
FROM (VALUES ('强制删除镜头','shotgrid:shot:forceDelete','shotgrid:shot:list'),
             ('强制删除资产','shotgrid:asset:forceDelete','shotgrid:asset:list')) seed(name,perm,parent_perm)
JOIN LATERAL (SELECT menu_id FROM sys_menu WHERE perms=seed.parent_perm AND menu_type='C' ORDER BY menu_id LIMIT 1) parent ON true
WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms=seed.perm);
"""


def upgrade() -> None:
    if op.get_context().dialect.name == 'postgresql':
        op.execute(UPGRADE_SQL)


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    scope = "SELECT menu_id FROM sys_menu WHERE create_by='shotgrid_migration_20261013_39' AND perms IN ('shotgrid:shot:forceDelete','shotgrid:asset:forceDelete')"
    op.execute(f'DELETE FROM sys_role_menu WHERE menu_id IN ({scope})')
    op.execute(f'DELETE FROM sys_menu WHERE menu_id IN ({scope})')

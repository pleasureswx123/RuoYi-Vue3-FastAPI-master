"""每日多平台制作记录（PostgreSQL）。"""

from alembic import op
from sqlalchemy import text

revision = '20261111_43'
down_revision = '20261102_42'
branch_labels = None
depends_on = None
TABLE_SQL = "CREATE TABLE sg_daily_record (\n record_id VARCHAR(36) PRIMARY KEY, project_id BIGINT NOT NULL, task_id BIGINT NOT NULL,\n user_id BIGINT NOT NULL REFERENCES sys_user(user_id), record_date DATE NOT NULL,\n platform VARCHAR(80) NOT NULL, account VARCHAR(80) NOT NULL DEFAULT '', model VARCHAR(80) NOT NULL DEFAULT '',\n media_type VARCHAR(10) NOT NULL CHECK (media_type IN ('image','video')),\n generated_count INTEGER NOT NULL CHECK (generated_count BETWEEN 0 AND 1000000),\n actual_points NUMERIC(16,4) CHECK (actual_points >= 0), unit_points NUMERIC(16,4) CHECK (unit_points >= 0),\n history JSONB NOT NULL DEFAULT '[]', create_by VARCHAR(64) NOT NULL DEFAULT '', create_time TIMESTAMP(0) NOT NULL DEFAULT CURRENT_TIMESTAMP,\n update_by VARCHAR(64) NOT NULL DEFAULT '', update_time TIMESTAMP(0) NOT NULL DEFAULT CURRENT_TIMESTAMP,\n remark VARCHAR(500), lock_version INTEGER NOT NULL DEFAULT 0 CHECK(lock_version >= 0), del_flag CHAR(1) NOT NULL DEFAULT '0',\n CONSTRAINT fk_sg_daily_task FOREIGN KEY(task_id,project_id) REFERENCES sg_task(task_id,project_id) ON DELETE CASCADE,\n CHECK(btrim(platform) <> ''), CHECK(actual_points IS NOT NULL OR unit_points IS NOT NULL), CHECK(del_flag IN ('0','2'))\n);\nCREATE INDEX ix_sg_daily_scope_date ON sg_daily_record(project_id,record_date,user_id);\nCREATE UNIQUE INDEX uq_sg_daily_dimensions ON sg_daily_record(project_id,task_id,user_id,record_date,platform,account,model,media_type) WHERE del_flag='0';\nWITH seed(title,route,perm,sort) AS (VALUES ('每日记录','daily-records','shotgrid:daily:write',2),('产出统计','production-statistics','shotgrid:daily:stats',7))\nINSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,query,route_name,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)\nSELECT seed.title,p.menu_id,seed.sort,'/'||seed.route,NULL,'',seed.route,1,0,'C','0','0',seed.perm,'chart','daily_43',CURRENT_TIMESTAMP,'每日记录与统计'\nFROM seed CROSS JOIN LATERAL (SELECT menu_id FROM sys_menu WHERE route_name='ShotGrid' AND menu_type='M' ORDER BY menu_id LIMIT 1) p\nWHERE NOT EXISTS(SELECT 1 FROM sys_menu m WHERE m.route_name=seed.route);\nINSERT INTO sys_role_menu(role_id,menu_id)\nSELECT DISTINCT rm.role_id,new.menu_id FROM sys_role_menu rm JOIN sys_menu old ON old.menu_id=rm.menu_id\nJOIN sys_menu new ON (new.perms='shotgrid:daily:write' AND old.perms='shotgrid:task:list') OR (new.perms='shotgrid:daily:stats' AND old.perms='shotgrid:task:schedule')\nON CONFLICT DO NOTHING;\n"


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    for statement in TABLE_SQL.split(';'):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    if op.get_bind().execute(text('SELECT EXISTS(SELECT 1 FROM sg_daily_record)')).scalar():
        raise RuntimeError('已有每日记录，拒绝降级丢失数据；请先备份并评审')
    op.execute("DELETE FROM sys_role_menu WHERE menu_id IN (SELECT menu_id FROM sys_menu WHERE create_by='daily_43')")
    op.execute("DELETE FROM sys_menu WHERE create_by='daily_43'")
    op.execute('DROP TABLE sg_daily_record')

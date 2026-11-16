"""增加反馈讨论；不改变正式审核流程。"""

from alembic import op
from sqlalchemy import text

revision = '20261030_41'
down_revision = '20261013_40'
branch_labels = None
depends_on = None

TABLE_SQL = """
CREATE TABLE sg_issue_comment (
 comment_id BIGSERIAL PRIMARY KEY,
 project_id BIGINT NOT NULL,
 note_id BIGINT NOT NULL,
 author_id BIGINT NOT NULL REFERENCES sys_user(user_id) ON DELETE RESTRICT,
 author_name VARCHAR(64) NOT NULL,
 content VARCHAR(2000) NOT NULL,
 request_id VARCHAR(100) NOT NULL,
 create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
 CONSTRAINT fk_sg_issue_comment_note_project FOREIGN KEY(note_id,project_id)
   REFERENCES sg_note(note_id,project_id) ON DELETE RESTRICT,
 CONSTRAINT uk_sg_issue_comment_request UNIQUE(note_id,author_id,request_id),
 CONSTRAINT ck_sg_issue_comment_content CHECK(btrim(content) <> '' AND btrim(request_id) <> '')
);
CREATE INDEX idx_sg_issue_comment_note_id ON sg_issue_comment(note_id,comment_id);
COMMENT ON TABLE sg_issue_comment IS 'Shot Grid审核反馈讨论记录';
"""
MENU_SQL = """
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,query,route_name,
 is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '评论审核反馈',parent_id,98,'#','','','',1,0,'F','0','0','shotgrid:note:comment','#',
 'shotgrid_migration_20261030_41',current_timestamp,'追加讨论，不修改审核状态'
FROM sys_menu WHERE perms='shotgrid:note:list'
AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='shotgrid:note:comment')
ORDER BY menu_id LIMIT 1;
INSERT INTO sys_role_menu(role_id,menu_id)
SELECT r.role_id,m.menu_id FROM sys_role r CROSS JOIN sys_menu m
WHERE r.role_key IN ('shotgrid_admin','shotgrid_creator') AND r.status='0' AND r.del_flag='0'
AND m.perms='shotgrid:note:comment'
AND EXISTS(SELECT 1 FROM sys_role_menu rm JOIN sys_menu n ON n.menu_id=rm.menu_id
           WHERE rm.role_id=r.role_id AND n.perms='shotgrid:note:list' AND n.status='0')
AND NOT EXISTS(SELECT 1 FROM sys_role_menu rm WHERE rm.role_id=r.role_id AND rm.menu_id=m.menu_id);
"""


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    for statement in (TABLE_SQL + MENU_SQL).split(';'):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    if op.get_bind().execute(text('SELECT EXISTS(SELECT 1 FROM sg_issue_comment)')).scalar():
        raise RuntimeError('已有反馈评论，拒绝降级以免丢失讨论记录；请先备份并另行评审迁移方案')
    scope = "SELECT menu_id FROM sys_menu WHERE create_by='shotgrid_migration_20261030_41' AND perms='shotgrid:note:comment'"
    op.execute(f'DELETE FROM sys_role_menu WHERE menu_id IN ({scope})')
    op.execute(f'DELETE FROM sys_menu WHERE menu_id IN ({scope})')
    op.execute('DROP TABLE sg_issue_comment')

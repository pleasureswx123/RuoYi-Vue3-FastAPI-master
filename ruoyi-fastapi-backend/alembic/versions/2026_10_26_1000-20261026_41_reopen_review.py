"""重新审核周期、不可变审核历史与最终交付撤销。"""

from alembic import op

revision = '20261026_41'
down_revision = '20261013_40'
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
-- 重新审核：版本不复制，审核周期和交付事件只追加。
ALTER TABLE sg_version ADD COLUMN review_cycle integer NOT NULL DEFAULT 1 CHECK (review_cycle > 0);
ALTER TABLE sg_review_action ADD COLUMN review_cycle integer NOT NULL DEFAULT 1;
ALTER TABLE sg_note ADD COLUMN review_cycle integer NOT NULL DEFAULT 1;
ALTER TABLE sg_review_issue_draft ADD COLUMN review_cycle integer NOT NULL DEFAULT 1;
CREATE TABLE sg_review_cycle (
 version_id bigint NOT NULL REFERENCES sg_version(version_id) ON DELETE RESTRICT,
 cycle_no integer NOT NULL CHECK (cycle_no > 0),
 opened_by bigint REFERENCES sys_user(user_id) ON DELETE RESTRICT,
 reason varchar(1000), opened_time timestamp(0) NOT NULL, closed_time timestamp(0),
 outcome varchar(20) CHECK (outcome IS NULL OR outcome IN ('approve','reject')),
 PRIMARY KEY(version_id,cycle_no)
);
INSERT INTO sg_review_cycle(version_id,cycle_no,opened_time,closed_time,outcome)
SELECT v.version_id,1,v.submitted_time,a.create_time,a.action_type FROM sg_version v
LEFT JOIN LATERAL (SELECT create_time,action_type FROM sg_review_action WHERE version_id=v.version_id
 AND action_type IN ('approve','reject') ORDER BY action_id DESC LIMIT 1) a ON true;
ALTER TABLE sg_review_action DROP CONSTRAINT ck_sg_review_action_type;
ALTER TABLE sg_review_action ADD CONSTRAINT ck_sg_review_action_type CHECK (action_type IN ('approve','reject','defer','reopen'));
ALTER TABLE sg_review_action DROP CONSTRAINT ck_sg_review_action_transition;
ALTER TABLE sg_review_action ADD CONSTRAINT ck_sg_review_action_transition CHECK (
 (action_type='approve' AND from_status='pending_review' AND to_status='final') OR
 (action_type='reject' AND from_status='pending_review' AND to_status='rejected') OR
 (action_type='defer' AND from_status='pending_review' AND to_status='pending_review') OR
 (action_type='reopen' AND from_status='final' AND to_status='pending_review'));
ALTER TABLE sg_final_delivery ADD COLUMN review_cycle integer NOT NULL DEFAULT 1;
ALTER TABLE sg_final_delivery ADD COLUMN operation varchar(20) NOT NULL DEFAULT 'publish'
 CONSTRAINT ck_sg_final_delivery_operation CHECK (operation IN ('publish','revoke'));
ALTER TABLE sg_final_delivery ADD COLUMN validity_status varchar(20) NOT NULL DEFAULT 'current'
 CONSTRAINT ck_sg_final_delivery_validity CHECK (validity_status IN ('current','revoked'));
DROP INDEX uk_sg_final_delivery_version;
CREATE UNIQUE INDEX uk_sg_final_delivery_cycle_operation ON sg_final_delivery(version_id,review_cycle,operation);
ALTER TABLE sg_final_delivery DROP CONSTRAINT ck_sg_final_delivery_status;
ALTER TABLE sg_final_delivery ADD CONSTRAINT ck_sg_final_delivery_status
 CHECK (delivery_status IN ('pending','publishing','published','failed','cancelled'));
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,query,route_name,is_frame,is_cache,
 menu_type,visible,status,perms,icon,create_by,create_time,remark)
SELECT '重新审核',parent_id,99,'#','','','',1,0,'F','0','0','shotgrid:version:reopen','#',
 'shotgrid_migration_20261026_41',current_timestamp,'独立授权；不自动扩大制作人权限'
FROM sys_menu WHERE perms='shotgrid:version:review'
 AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='shotgrid:version:reopen') LIMIT 1;
"""


def upgrade() -> None:
    if op.get_context().dialect.name == 'postgresql':
        for statement in UPGRADE_SQL.split(';'):
            if statement.strip():
                op.execute(statement)


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    # 已产生新语义的数据必须从备份恢复，禁止静默抹去审核或交付历史。
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM sg_version WHERE review_cycle > 1)
        OR EXISTS(SELECT 1 FROM sg_final_delivery WHERE operation='revoke'
          OR final_nas_relative_path ~ 'T[0-9]+-V[0-9]+-R[0-9]+')
      THEN RAISE EXCEPTION '已存在重新审核或新交付数据，禁止无损降级以外的操作'; END IF;
    END $$;""")
    downgrade_sql = """
    DELETE FROM sys_role_menu WHERE menu_id IN (SELECT menu_id FROM sys_menu WHERE create_by='shotgrid_migration_20261026_41');
    DELETE FROM sys_menu WHERE create_by='shotgrid_migration_20261026_41';
    ALTER TABLE sg_review_action DROP CONSTRAINT ck_sg_review_action_type;
    ALTER TABLE sg_review_action ADD CONSTRAINT ck_sg_review_action_type CHECK(action_type IN ('approve','reject','defer'));
    ALTER TABLE sg_review_action DROP CONSTRAINT ck_sg_review_action_transition;
    ALTER TABLE sg_review_action ADD CONSTRAINT ck_sg_review_action_transition CHECK(
      (action_type='approve' AND from_status='pending_review' AND to_status='final') OR
      (action_type='reject' AND from_status='pending_review' AND to_status='rejected') OR
      (action_type='defer' AND from_status='pending_review' AND to_status='pending_review'));
    DROP TABLE sg_review_cycle;
    ALTER TABLE sg_version DROP COLUMN review_cycle;
    ALTER TABLE sg_note DROP COLUMN review_cycle;
    ALTER TABLE sg_review_issue_draft DROP COLUMN review_cycle;
    ALTER TABLE sg_review_action DROP COLUMN review_cycle;
    DROP INDEX uk_sg_final_delivery_cycle_operation;
    CREATE UNIQUE INDEX uk_sg_final_delivery_version ON sg_final_delivery(version_id);
    ALTER TABLE sg_final_delivery DROP COLUMN review_cycle, DROP COLUMN operation, DROP COLUMN validity_status;
    ALTER TABLE sg_final_delivery DROP CONSTRAINT ck_sg_final_delivery_status;
    ALTER TABLE sg_final_delivery ADD CONSTRAINT ck_sg_final_delivery_status CHECK(delivery_status IN ('pending','publishing','published','failed'));
    """
    for statement in downgrade_sql.split(';'):
        if statement.strip():
            op.execute(statement)

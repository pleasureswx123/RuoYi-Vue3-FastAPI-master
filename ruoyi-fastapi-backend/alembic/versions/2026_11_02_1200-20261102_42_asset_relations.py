"""增加同项目资产间资料关联。"""

from alembic import op
from sqlalchemy import text

revision = '20261102_42'
down_revision = '20261030_41'
branch_labels = None
depends_on = None

TABLE_SQL = """
CREATE TABLE sg_asset_relation (
 project_id BIGINT NOT NULL,
 asset_id BIGINT NOT NULL,
 related_asset_id BIGINT NOT NULL,
 create_by VARCHAR(64) NOT NULL DEFAULT '',
 create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY (asset_id, related_asset_id),
 CONSTRAINT fk_sg_asset_relation_source FOREIGN KEY (asset_id, project_id) REFERENCES sg_asset(asset_id, project_id) ON DELETE CASCADE,
 CONSTRAINT fk_sg_asset_relation_target FOREIGN KEY (related_asset_id, project_id) REFERENCES sg_asset(asset_id, project_id) ON DELETE CASCADE,
 CONSTRAINT ck_sg_asset_relation_not_self CHECK (asset_id <> related_asset_id)
);
CREATE INDEX idx_sg_asset_relation_target ON sg_asset_relation(project_id, related_asset_id);
COMMENT ON TABLE sg_asset_relation IS '资产之间的资料关联，不阻止开工';
"""


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    for statement in TABLE_SQL.split(';'):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    if op.get_bind().execute(text('SELECT EXISTS(SELECT 1 FROM sg_asset_relation)')).scalar():
        raise RuntimeError('已有资产关联，拒绝降级丢失资料关系；请先备份并评审恢复方案')
    op.execute('DROP TABLE sg_asset_relation')

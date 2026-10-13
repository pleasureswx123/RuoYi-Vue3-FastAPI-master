"""新增目标永久清理队列及路径占用。"""

import re

from alembic import op
from sqlalchemy import inspect, text

revision = '20261013_40'
down_revision = '20261013_39'
branch_labels = None
depends_on = None
UPGRADE_SQL = """
CREATE TABLE sg_target_purge (
	purge_id BIGSERIAL NOT NULL,
	project_id BIGINT NOT NULL,
	target_kind VARCHAR(10) NOT NULL,
	target_id BIGINT NOT NULL,
	target_label VARCHAR(240) NOT NULL,
	root_path_snapshot VARCHAR(1000) NOT NULL,
	project_relative_path VARCHAR(1200) NOT NULL,
	project_path_snapshot VARCHAR(2000) NOT NULL,
	nas_manifest JSONB NOT NULL,
	file_manifest JSONB NOT NULL,
	purge_status VARCHAR(20) DEFAULT 'pending' NOT NULL,
	attempt_count INTEGER DEFAULT '0' NOT NULL,
	next_retry_time TIMESTAMP(0) WITHOUT TIME ZONE,
	lease_owner VARCHAR(100),
	lease_until TIMESTAMP(0) WITHOUT TIME ZONE,
	requested_by_user_id BIGINT NOT NULL,
	requested_by VARCHAR(64) NOT NULL,
	reason VARCHAR(500) NOT NULL,
	last_error_key VARCHAR(100),
	last_error_message VARCHAR(500),
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	update_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	completed_time TIMESTAMP(0) WITHOUT TIME ZONE,
	PRIMARY KEY (purge_id),
	CONSTRAINT uk_sg_target_purge_target UNIQUE (project_id, target_kind, target_id),
	CONSTRAINT ck_sg_target_purge_kind CHECK (target_kind in ('shot','asset')),
	CONSTRAINT ck_sg_target_purge_status CHECK (purge_status in ('pending','processing','retry_wait','succeeded','failed')),
	CONSTRAINT ck_sg_target_purge_attempt CHECK (attempt_count >= 0),
	CONSTRAINT ck_sg_target_purge_required CHECK (btrim(reason) <> '' AND btrim(target_label) <> '' AND btrim(requested_by) <> ''),
	CONSTRAINT ck_sg_target_purge_manifest CHECK (jsonb_typeof(nas_manifest) = 'array' AND jsonb_typeof(file_manifest) = 'array'),
	CONSTRAINT ck_sg_target_purge_lease CHECK ((purge_status = 'processing') = (lease_owner IS NOT NULL AND lease_until IS NOT NULL))
)

;

CREATE TABLE sg_target_purge_path (
	purge_id BIGINT NOT NULL,
	path_key VARCHAR(1200) NOT NULL,
	project_id BIGINT NOT NULL,
	PRIMARY KEY (purge_id, path_key),
	CONSTRAINT uk_sg_target_purge_path UNIQUE (project_id, path_key),
	CONSTRAINT ck_sg_target_purge_path_required CHECK (btrim(path_key) <> ''),
	FOREIGN KEY(purge_id) REFERENCES sg_target_purge (purge_id) ON DELETE RESTRICT
)

;
CREATE INDEX idx_sg_target_purge_queue ON sg_target_purge (purge_status, next_retry_time, purge_id);"""


GUARD_SQL = [
    """CREATE OR REPLACE FUNCTION sg_guard_target_purge_identity() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE candidate text; extra_candidate text; episode_dir text; scene_number integer;
BEGIN
    PERFORM 1 FROM sg_project WHERE project_id = NEW.project_id FOR UPDATE;
    IF TG_TABLE_NAME = 'sg_shot' THEN
        SELECT e.storage_dir_name, s.scene_no INTO episode_dir, scene_number
        FROM sg_scene s JOIN sg_episode e ON e.episode_id = s.episode_id
        WHERE s.scene_id = NEW.scene_id;
        candidate := 'VIDEO/' || episode_dir || '/' || COALESCE(NEW.storage_dir_name,
            lpad(scene_number::text, greatest(3,length(scene_number::text)), '0') || '_' ||
            lpad(NEW.shot_no::text, greatest(4,length(NEW.shot_no::text)), '0'));
        extra_candidate := 'VIDEO/' || episode_dir || '/' ||
            lpad(scene_number::text, greatest(3,length(scene_number::text)), '0') || '_' ||
            lpad(NEW.shot_no::text, greatest(4,length(NEW.shot_no::text)), '0');
    ELSE
        candidate := 'ASSET/' || NEW.asset_type || '/' || NEW.storage_dir_name;
        extra_candidate := 'ASSET/' || NEW.asset_type || '/' || NEW.asset_name_key;
    END IF;
    candidate := lower(normalize(replace(candidate, chr(92), '/'), NFC));
    extra_candidate := lower(normalize(replace(extra_candidate, chr(92), '/'), NFC));
    IF EXISTS (SELECT 1 FROM sg_target_purge_path p WHERE p.project_id = NEW.project_id AND
        (p.path_key = candidate OR p.path_key = extra_candidate OR
         starts_with(candidate, p.path_key || '/') OR starts_with(p.path_key, candidate || '/'))) THEN
        RAISE EXCEPTION '旧目标文件仍在清理中，完成后才能复用编号或名称'
            USING ERRCODE = '23514', CONSTRAINT = 'ck_sg_target_purge_reserved';
    END IF;
    RETURN NEW;
END $$""",
    """CREATE TRIGGER trg_sg_shot_purge_guard BEFORE INSERT OR UPDATE OF project_id, episode_id, scene_id, shot_no, storage_dir_name ON sg_shot FOR EACH ROW EXECUTE FUNCTION sg_guard_target_purge_identity()""",
    """CREATE TRIGGER trg_sg_asset_purge_guard BEFORE INSERT OR UPDATE OF project_id, asset_type, asset_name_key, storage_dir_name ON sg_asset FOR EACH ROW EXECUTE FUNCTION sg_guard_target_purge_identity()""",
]


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    inspector = inspect(op.get_bind())
    # 兼容启动阶段由 ORM 先建出的同构表，结构不一致时拒绝采用。
    for table_name in ('sg_target_purge', 'sg_target_purge_path'):
        if not inspector.has_table(table_name):
            continue
        definition = re.split(r'\n\)\s*;', UPGRADE_SQL.split(f'CREATE TABLE {table_name} (', 1)[1], maxsplit=1)[0]
        expected = {}
        for line in definition.splitlines():
            match = re.match(r'\s*(\w+) (BIGSERIAL|BIGINT|VARCHAR\(\d+\)|JSONB|INTEGER|TIMESTAMP)', line)
            if match:
                expected[match[1]] = (match[2].replace('BIGSERIAL', 'BIGINT'), 'NOT NULL' not in line)
        actual = {
            column['name']: (str(column['type']), column['nullable']) for column in inspector.get_columns(table_name)
        }
        if actual != expected:
            raise RuntimeError(f'{table_name} 已存在但与永久清理迁移结构不一致')
        required = set(re.findall(r'CONSTRAINT (\w+)', definition))
        present = {item['name'] for item in inspector.get_check_constraints(table_name)}
        present.update(item['name'] for item in inspector.get_unique_constraints(table_name))
        present.update(item['name'] for item in inspector.get_foreign_keys(table_name))
        if not required.issubset(present):
            raise RuntimeError(f'{table_name} 缺少永久清理约束')
    for statement in UPGRADE_SQL.split(';'):
        if statement.strip():
            op.execute(
                statement.replace('CREATE TABLE ', 'CREATE TABLE IF NOT EXISTS ').replace(
                    'CREATE INDEX ', 'CREATE INDEX IF NOT EXISTS '
                )
            )
    op.execute('DROP TRIGGER IF EXISTS trg_sg_shot_purge_guard ON sg_shot')
    op.execute('DROP TRIGGER IF EXISTS trg_sg_asset_purge_guard ON sg_asset')
    for statement in GUARD_SQL:
        op.execute(text(statement))


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    if op.get_bind().scalar(text("SELECT count(*) FROM sg_target_purge WHERE purge_status != 'succeeded'")):
        raise RuntimeError('存在未完成目标清理，拒绝降级')
    op.execute('DROP TRIGGER IF EXISTS trg_sg_shot_purge_guard ON sg_shot')
    op.execute('DROP TRIGGER IF EXISTS trg_sg_asset_purge_guard ON sg_asset')
    op.execute('DROP FUNCTION IF EXISTS sg_guard_target_purge_identity()')
    op.drop_table('sg_target_purge_path')
    op.drop_table('sg_target_purge')

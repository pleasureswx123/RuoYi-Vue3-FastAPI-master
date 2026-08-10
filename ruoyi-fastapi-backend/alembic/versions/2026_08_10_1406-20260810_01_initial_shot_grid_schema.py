"""创建 Shot Grid 首批 PostgreSQL 业务表、菜单、权限和字典种子。

Revision ID: 20260810_01
Revises:
Create Date: 2026-08-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '20260810_01'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_MARKER = 'shotgrid_migration_20260810_01'

SHOT_GRID_TABLES = (
    'sg_project',
    'sg_storage_root',
    'sg_asset',
    'sg_episode',
    'sg_import_batch',
    'sg_project_member',
    'sg_project_storage',
    'sg_storage_operation',
    'sg_asset_item',
    'sg_scene',
    'sg_shot',
    'sg_shot_asset',
    'sg_shot_asset_requirement',
    'sg_task',
    'sg_version_submission',
    'sg_version',
    'sg_note',
    'sg_review_action',
    'sg_review_list',
    'sg_version_file',
    'sg_note_reply',
    'sg_review_list_version',
)

SHOT_GRID_DDL = (
    r"""
CREATE TABLE sg_project (
	project_id BIGSERIAL NOT NULL,
	project_code VARCHAR(12) NOT NULL,
	project_name VARCHAR(200) NOT NULL,
	project_type VARCHAR(50) DEFAULT 'ai_short_film' NOT NULL,
	project_description TEXT,
	aspect_ratio VARCHAR(20) DEFAULT '16:9' NOT NULL,
	planned_duration_ms BIGINT,
	delivery_date DATE,
	project_status VARCHAR(20) DEFAULT 'preparing' NOT NULL,
	current_phase VARCHAR(50) DEFAULT 'planning' NOT NULL,
	create_by VARCHAR(64) DEFAULT '' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	update_by VARCHAR(64) DEFAULT '' NOT NULL,
	update_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	remark VARCHAR(500),
	lock_version INTEGER DEFAULT '0' NOT NULL,
	del_flag CHAR(1) DEFAULT '0' NOT NULL,
	PRIMARY KEY (project_id),
	CONSTRAINT ck_sg_project_code_format CHECK (project_code ~ '^[A-Z0-9]{2,12}$'),
	CONSTRAINT ck_sg_project_type CHECK (project_type in ('ai_short_film')),
	CONSTRAINT ck_sg_project_aspect_ratio CHECK (aspect_ratio in ('16:9', '21:9', '2.39:1', '9:16', '1:1')),
	CONSTRAINT ck_sg_project_status CHECK (project_status in ('preparing', 'active', 'completed', 'archived')),
	CONSTRAINT ck_sg_project_phase CHECK (current_phase in ('planning', 'asset_production', 'shot_production', 'review', 'delivery', 'completed')),
	CONSTRAINT ck_sg_project_duration CHECK (planned_duration_ms is null or planned_duration_ms >= 0),
	CONSTRAINT ck_sg_project_lock_version CHECK (lock_version >= 0),
	CONSTRAINT ck_sg_project_del_flag CHECK (del_flag in ('0', '2'))
)
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_project_code_active ON sg_project (lower(project_code)) WHERE project_status <> 'archived' AND del_flag = '0'
""".strip(),
    r"""
COMMENT ON TABLE sg_project IS 'Shot Grid项目主表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.project_code IS '项目代号及产出文件前缀'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.project_name IS '项目名称'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.project_type IS '项目类型代码'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.project_description IS '项目描述'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.aspect_ratio IS '画幅'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.planned_duration_ms IS '计划总时长（毫秒）'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.delivery_date IS '交付日期'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.project_status IS '项目状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.current_phase IS '当前阶段'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.create_by IS '创建者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.create_time IS '创建时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.update_by IS '更新者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.update_time IS '更新时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.remark IS '备注'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.lock_version IS '乐观锁版本'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project.del_flag IS '删除标志（0正常 2删除）'
""".strip(),
    r"""
CREATE TABLE sg_storage_root (
	storage_root_id BIGSERIAL NOT NULL,
	root_code VARCHAR(50) NOT NULL,
	root_name VARCHAR(120) NOT NULL,
	protocol VARCHAR(20) DEFAULT 'smb_unc' NOT NULL,
	unc_root_path VARCHAR(1000) NOT NULL,
	root_path_key VARCHAR(1000) NOT NULL,
	credential_ref VARCHAR(200),
	root_status VARCHAR(20) DEFAULT 'enabled' NOT NULL,
	last_probe_status VARCHAR(20) DEFAULT 'unknown' NOT NULL,
	last_probe_time TIMESTAMP(0) WITHOUT TIME ZONE,
	last_error_key VARCHAR(100),
	last_error_message VARCHAR(500),
	create_by VARCHAR(64) DEFAULT '' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	update_by VARCHAR(64) DEFAULT '' NOT NULL,
	update_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	remark VARCHAR(500),
	lock_version INTEGER DEFAULT '0' NOT NULL,
	del_flag CHAR(1) DEFAULT '0' NOT NULL,
	PRIMARY KEY (storage_root_id),
	CONSTRAINT ck_sg_storage_root_code CHECK (btrim(root_code) <> ''),
	CONSTRAINT ck_sg_storage_root_name CHECK (btrim(root_name) <> ''),
	CONSTRAINT ck_sg_storage_root_protocol CHECK (protocol in ('smb_unc')),
	CONSTRAINT ck_sg_storage_root_unc_path CHECK (left(unc_root_path, 2) = '\\' and position('..' in unc_root_path) = 0 and position('*' in unc_root_path) = 0 and position('?' in unc_root_path) = 0 and position('://' in unc_root_path) = 0),
	CONSTRAINT ck_sg_storage_root_path_key CHECK (btrim(root_path_key) <> ''),
	CONSTRAINT ck_sg_storage_root_status CHECK (root_status in ('enabled', 'disabled')),
	CONSTRAINT ck_sg_storage_root_probe_status CHECK (last_probe_status in ('unknown', 'healthy', 'unreachable', 'unwritable')),
	CONSTRAINT ck_sg_storage_root_lock_version CHECK (lock_version >= 0),
	CONSTRAINT ck_sg_storage_root_del_flag CHECK (del_flag in ('0', '2'))
)
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_storage_root_code_active ON sg_storage_root (lower(root_code)) WHERE del_flag = '0'
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_storage_root_path_active ON sg_storage_root (root_path_key) WHERE del_flag = '0'
""".strip(),
    r"""
COMMENT ON TABLE sg_storage_root IS 'Shot Grid NAS根目录白名单表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.storage_root_id IS '存储根ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.root_code IS '存储根稳定代码'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.root_name IS '存储根显示名称'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.protocol IS '存储协议'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.unc_root_path IS '规范化UNC根路径'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.root_path_key IS '大小写不敏感规范化路径键'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.credential_ref IS '外部凭据配置引用'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.root_status IS '存储根状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.last_probe_status IS '最近探测状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.last_probe_time IS '最近探测时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.last_error_key IS '最近安全错误键'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.last_error_message IS '已净化错误摘要'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.create_by IS '创建者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.create_time IS '创建时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.update_by IS '更新者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.update_time IS '更新时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.remark IS '备注'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.lock_version IS '乐观锁版本'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_root.del_flag IS '删除标志（0正常 2删除）'
""".strip(),
    r"""
CREATE TABLE sg_asset (
	asset_id BIGSERIAL NOT NULL,
	project_id BIGINT NOT NULL,
	asset_name VARCHAR(200) NOT NULL,
	asset_name_key VARCHAR(200) NOT NULL,
	asset_type VARCHAR(20) NOT NULL,
	storage_dir_name VARCHAR(240) NOT NULL,
	storage_path_key VARCHAR(500) NOT NULL,
	description TEXT,
	sort_order INTEGER DEFAULT '0' NOT NULL,
	lifecycle_status VARCHAR(20) DEFAULT 'active' NOT NULL,
	create_by VARCHAR(64) DEFAULT '' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	update_by VARCHAR(64) DEFAULT '' NOT NULL,
	update_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	remark VARCHAR(500),
	lock_version INTEGER DEFAULT '0' NOT NULL,
	del_flag CHAR(1) DEFAULT '0' NOT NULL,
	PRIMARY KEY (asset_id),
	CONSTRAINT uk_sg_asset_id_project UNIQUE (asset_id, project_id),
	CONSTRAINT uk_sg_asset_id_project_type UNIQUE (asset_id, project_id, asset_type),
	CONSTRAINT ck_sg_asset_name CHECK (btrim(asset_name) <> ''),
	CONSTRAINT ck_sg_asset_name_key CHECK (btrim(asset_name_key) <> ''),
	CONSTRAINT ck_sg_asset_type CHECK (asset_type in ('Character', 'Environment', 'Prop')),
	CONSTRAINT ck_sg_asset_storage_dir CHECK (btrim(storage_dir_name) <> ''),
	CONSTRAINT ck_sg_asset_storage_key CHECK (btrim(storage_path_key) <> ''),
	CONSTRAINT ck_sg_asset_sort_order CHECK (sort_order >= 0),
	CONSTRAINT ck_sg_asset_lifecycle CHECK (lifecycle_status in ('active', 'archived')),
	CONSTRAINT ck_sg_asset_lock_version CHECK (lock_version >= 0),
	CONSTRAINT ck_sg_asset_del_flag CHECK (del_flag in ('0', '2')),
	FOREIGN KEY(project_id) REFERENCES sg_project (project_id) ON DELETE RESTRICT
)
""".strip(),
    r"""
CREATE INDEX idx_sg_asset_project_type_lifecycle_sort ON sg_asset (project_id, asset_type, lifecycle_status, sort_order)
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_asset_name_active ON sg_asset (project_id, asset_type, asset_name_key) WHERE lifecycle_status = 'active' AND del_flag = '0'
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_asset_storage_path ON sg_asset (project_id, storage_path_key) WHERE del_flag = '0'
""".strip(),
    r"""
COMMENT ON TABLE sg_asset IS 'Shot Grid资产主表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.asset_id IS '资产ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.asset_name IS '资产名称'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.asset_name_key IS '资产名称规范化匹配键'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.asset_type IS '资产类型'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.storage_dir_name IS 'NAS资产子目录名快照'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.storage_path_key IS '项目内规范化存储路径键'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.description IS '资产说明'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.sort_order IS '项目内排序'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.lifecycle_status IS '生命周期状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.create_by IS '创建者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.create_time IS '创建时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.update_by IS '更新者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.update_time IS '更新时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.remark IS '备注'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.lock_version IS '乐观锁版本'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset.del_flag IS '删除标志（0正常 2删除）'
""".strip(),
    r"""
CREATE TABLE sg_episode (
	episode_id BIGSERIAL NOT NULL,
	project_id BIGINT NOT NULL,
	episode_no INTEGER NOT NULL,
	storage_dir_name VARCHAR(32) NOT NULL,
	episode_name VARCHAR(200),
	description TEXT,
	sort_order INTEGER DEFAULT '0' NOT NULL,
	lifecycle_status VARCHAR(20) DEFAULT 'active' NOT NULL,
	create_by VARCHAR(64) DEFAULT '' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	update_by VARCHAR(64) DEFAULT '' NOT NULL,
	update_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	remark VARCHAR(500),
	lock_version INTEGER DEFAULT '0' NOT NULL,
	del_flag CHAR(1) DEFAULT '0' NOT NULL,
	PRIMARY KEY (episode_id),
	CONSTRAINT uk_sg_episode_id_project UNIQUE (episode_id, project_id),
	CONSTRAINT ck_sg_episode_no CHECK (episode_no > 0),
	CONSTRAINT ck_sg_episode_sort_order CHECK (sort_order >= 0),
	CONSTRAINT ck_sg_episode_lifecycle CHECK (lifecycle_status in ('active', 'archived')),
	CONSTRAINT ck_sg_episode_lock_version CHECK (lock_version >= 0),
	CONSTRAINT ck_sg_episode_del_flag CHECK (del_flag in ('0', '2')),
	FOREIGN KEY(project_id) REFERENCES sg_project (project_id) ON DELETE RESTRICT
)
""".strip(),
    r"""
CREATE INDEX idx_sg_episode_project_lifecycle_sort ON sg_episode (project_id, lifecycle_status, sort_order)
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_episode_no_active ON sg_episode (project_id, episode_no) WHERE del_flag = '0'
""".strip(),
    r"""
COMMENT ON TABLE sg_episode IS 'Shot Grid集主表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_episode.episode_id IS '集ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_episode.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_episode.episode_no IS '集号'
""".strip(),
    r"""
COMMENT ON COLUMN sg_episode.storage_dir_name IS 'NAS集目录快照'
""".strip(),
    r"""
COMMENT ON COLUMN sg_episode.episode_name IS '集名称'
""".strip(),
    r"""
COMMENT ON COLUMN sg_episode.description IS '集说明'
""".strip(),
    r"""
COMMENT ON COLUMN sg_episode.sort_order IS '项目内排序'
""".strip(),
    r"""
COMMENT ON COLUMN sg_episode.lifecycle_status IS '生命周期状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_episode.create_by IS '创建者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_episode.create_time IS '创建时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_episode.update_by IS '更新者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_episode.update_time IS '更新时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_episode.remark IS '备注'
""".strip(),
    r"""
COMMENT ON COLUMN sg_episode.lock_version IS '乐观锁版本'
""".strip(),
    r"""
COMMENT ON COLUMN sg_episode.del_flag IS '删除标志（0正常 2删除）'
""".strip(),
    r"""
CREATE TABLE sg_import_batch (
	batch_id BIGSERIAL NOT NULL,
	project_id BIGINT NOT NULL,
	import_type VARCHAR(20) NOT NULL,
	original_file_name VARCHAR(255) NOT NULL,
	file_sha256 CHAR(64) NOT NULL,
	template_version VARCHAR(30) NOT NULL,
	batch_status VARCHAR(20) DEFAULT 'previewed' NOT NULL,
	total_rows INTEGER DEFAULT '0' NOT NULL,
	valid_rows INTEGER DEFAULT '0' NOT NULL,
	warning_rows INTEGER DEFAULT '0' NOT NULL,
	error_rows INTEGER DEFAULT '0' NOT NULL,
	committed_rows INTEGER DEFAULT '0' NOT NULL,
	preview_token_hash CHAR(64),
	preview_expires_time TIMESTAMP(0) WITHOUT TIME ZONE,
	idempotency_key VARCHAR(100),
	last_error_key VARCHAR(100),
	last_error_message VARCHAR(500),
	previewed_by BIGINT NOT NULL,
	committed_by BIGINT,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	update_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	committed_time TIMESTAMP(0) WITHOUT TIME ZONE,
	PRIMARY KEY (batch_id),
	CONSTRAINT uk_sg_import_batch_id_project UNIQUE (batch_id, project_id),
	CONSTRAINT ck_sg_import_batch_type CHECK (import_type in ('shot', 'asset')),
	CONSTRAINT ck_sg_import_batch_file_name CHECK (btrim(original_file_name) <> ''),
	CONSTRAINT ck_sg_import_batch_template_version CHECK (btrim(template_version) <> ''),
	CONSTRAINT ck_sg_import_batch_status CHECK (batch_status in ('previewed', 'committing', 'committed', 'failed', 'expired')),
	CONSTRAINT ck_sg_import_batch_counts_nonnegative CHECK (total_rows >= 0 and valid_rows >= 0 and warning_rows >= 0 and error_rows >= 0 and committed_rows >= 0),
	CONSTRAINT ck_sg_import_batch_counts_bounds CHECK (valid_rows <= total_rows and warning_rows <= total_rows and error_rows <= total_rows and committed_rows <= valid_rows),
	CONSTRAINT ck_sg_import_batch_commit_identity CHECK ((batch_status in ('committing', 'committed', 'failed') and committed_by is not null and idempotency_key is not null and btrim(idempotency_key) <> '') or (batch_status in ('previewed', 'expired') and committed_by is null and idempotency_key is null)),
	CONSTRAINT ck_sg_import_batch_committed_time CHECK ((batch_status = 'committed' and committed_time is not null) or (batch_status <> 'committed' and committed_time is null)),
	FOREIGN KEY(project_id) REFERENCES sg_project (project_id) ON DELETE RESTRICT,
	FOREIGN KEY(previewed_by) REFERENCES sys_user (user_id) ON DELETE RESTRICT,
	FOREIGN KEY(committed_by) REFERENCES sys_user (user_id) ON DELETE RESTRICT
)
""".strip(),
    r"""
CREATE INDEX idx_sg_import_batch_project_type_status_time ON sg_import_batch (project_id, import_type, batch_status, create_time)
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_import_batch_idempotency ON sg_import_batch (project_id, import_type, committed_by, idempotency_key) WHERE idempotency_key IS NOT NULL
""".strip(),
    r"""
COMMENT ON TABLE sg_import_batch IS 'Shot Grid Excel导入批次表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.batch_id IS '导入批次ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.import_type IS '导入类型'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.original_file_name IS '原始Excel文件名'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.file_sha256 IS '原文件SHA-256摘要'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.template_version IS '模板版本'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.batch_status IS '批次状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.total_rows IS '数据总行数'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.valid_rows IS '可导入行数'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.warning_rows IS '有警告行数'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.error_rows IS '有错误行数'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.committed_rows IS '已提交行数'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.preview_token_hash IS '预览Token哈希'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.preview_expires_time IS '预览数据到期时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.idempotency_key IS '正式提交幂等键'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.last_error_key IS '最近失败错误键'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.last_error_message IS '已净化失败摘要'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.previewed_by IS '预检查用户ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.committed_by IS '正式提交用户ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.create_time IS '创建时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.update_time IS '更新时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_import_batch.committed_time IS '正式提交完成时间'
""".strip(),
    r"""
CREATE TABLE sg_project_member (
	project_id BIGINT NOT NULL,
	user_id BIGINT NOT NULL,
	project_role VARCHAR(20) NOT NULL,
	producer_code VARCHAR(12),
	joined_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	create_by VARCHAR(64) DEFAULT '' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (project_id, user_id),
	CONSTRAINT ck_sg_project_member_role CHECK (project_role in ('director', 'creator')),
	CONSTRAINT ck_sg_project_member_producer_code CHECK (producer_code is null or producer_code ~ '^[A-Z0-9]{2,12}$'),
	FOREIGN KEY(project_id) REFERENCES sg_project (project_id) ON DELETE RESTRICT,
	FOREIGN KEY(user_id) REFERENCES sys_user (user_id) ON DELETE RESTRICT
)
""".strip(),
    r"""
CREATE INDEX idx_sg_project_member_user_project ON sg_project_member (user_id, project_id)
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_project_member_producer_code ON sg_project_member (project_id, lower(producer_code)) WHERE producer_code IS NOT NULL
""".strip(),
    r"""
COMMENT ON TABLE sg_project_member IS 'Shot Grid项目成员表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_member.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_member.user_id IS '用户ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_member.project_role IS '项目角色'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_member.producer_code IS '制作人文件名缩写'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_member.joined_time IS '加入时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_member.create_by IS '创建者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_member.create_time IS '创建时间'
""".strip(),
    r"""
CREATE TABLE sg_project_storage (
	project_id BIGINT NOT NULL,
	storage_root_id BIGINT NOT NULL,
	root_path_snapshot VARCHAR(1000) NOT NULL,
	project_type_dir_snapshot VARCHAR(120) NOT NULL,
	project_dir_name_snapshot VARCHAR(240) NOT NULL,
	project_relative_path VARCHAR(1200) NOT NULL,
	project_path_snapshot VARCHAR(2000) NOT NULL,
	project_path_key VARCHAR(2000) NOT NULL,
	storage_status VARCHAR(20) DEFAULT 'initializing' NOT NULL,
	initialized_time TIMESTAMP(0) WITHOUT TIME ZONE,
	last_error_key VARCHAR(100),
	last_error_message VARCHAR(500),
	lock_version INTEGER DEFAULT '0' NOT NULL,
	create_by VARCHAR(64) DEFAULT '' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	update_by VARCHAR(64) DEFAULT '' NOT NULL,
	update_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (project_id),
	CONSTRAINT uk_sg_project_storage_path UNIQUE (storage_root_id, project_path_key),
	CONSTRAINT ck_sg_project_storage_root_path CHECK (btrim(root_path_snapshot) <> ''),
	CONSTRAINT ck_sg_project_storage_type_dir CHECK (btrim(project_type_dir_snapshot) <> ''),
	CONSTRAINT ck_sg_project_storage_project_dir CHECK (btrim(project_dir_name_snapshot) <> ''),
	CONSTRAINT ck_sg_project_storage_relative_path CHECK (btrim(project_relative_path) <> ''),
	CONSTRAINT ck_sg_project_storage_snapshot CHECK (btrim(project_path_snapshot) <> ''),
	CONSTRAINT ck_sg_project_storage_path_key CHECK (btrim(project_path_key) <> ''),
	CONSTRAINT ck_sg_project_storage_status CHECK (storage_status in ('initializing', 'ready', 'failed', 'migrating')),
	CONSTRAINT ck_sg_project_storage_lock_version CHECK (lock_version >= 0),
	FOREIGN KEY(project_id) REFERENCES sg_project (project_id) ON DELETE RESTRICT,
	FOREIGN KEY(storage_root_id) REFERENCES sg_storage_root (storage_root_id) ON DELETE RESTRICT
)
""".strip(),
    r"""
COMMENT ON TABLE sg_project_storage IS 'Shot Grid项目NAS存储绑定表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.storage_root_id IS '存储根ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.root_path_snapshot IS 'UNC根路径快照'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.project_type_dir_snapshot IS '项目类型目录快照'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.project_dir_name_snapshot IS '项目目录名快照'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.project_relative_path IS '相对根目录项目路径'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.project_path_snapshot IS '完整UNC项目路径快照'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.project_path_key IS '大小写不敏感规范化项目路径键'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.storage_status IS '项目存储状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.initialized_time IS '初始目录就绪时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.last_error_key IS '最近错误键'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.last_error_message IS '已净化错误摘要'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.lock_version IS '乐观锁版本'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.create_by IS '创建者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.create_time IS '创建时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.update_by IS '更新者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_project_storage.update_time IS '更新时间'
""".strip(),
    r"""
CREATE TABLE sg_storage_operation (
	operation_id BIGSERIAL NOT NULL,
	project_id BIGINT NOT NULL,
	operation_type VARCHAR(30) NOT NULL,
	aggregate_type VARCHAR(20) NOT NULL,
	aggregate_id BIGINT NOT NULL,
	target_relative_path VARCHAR(1200) NOT NULL,
	operation_status VARCHAR(30) DEFAULT 'pending' NOT NULL,
	idempotency_key VARCHAR(100) NOT NULL,
	attempt_count INTEGER DEFAULT '0' NOT NULL,
	next_retry_time TIMESTAMP(0) WITHOUT TIME ZONE,
	lease_owner VARCHAR(100),
	lease_until TIMESTAMP(0) WITHOUT TIME ZONE,
	started_time TIMESTAMP(0) WITHOUT TIME ZONE,
	completed_time TIMESTAMP(0) WITHOUT TIME ZONE,
	last_error_key VARCHAR(100),
	last_error_message VARCHAR(500),
	create_by VARCHAR(64) DEFAULT '' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	update_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (operation_id),
	CONSTRAINT uk_sg_storage_operation_idempotency UNIQUE (idempotency_key),
	CONSTRAINT ck_sg_storage_operation_type CHECK (operation_type in ('initialize_project', 'ensure_episode_directory', 'ensure_shot_directory', 'ensure_asset_directory', 'reconcile_directory')),
	CONSTRAINT ck_sg_storage_operation_aggregate_type CHECK (aggregate_type in ('project', 'episode', 'shot', 'asset')),
	CONSTRAINT ck_sg_storage_operation_target_type CHECK (operation_type = 'reconcile_directory' or (operation_type = 'initialize_project' and aggregate_type = 'project') or (operation_type = 'ensure_episode_directory' and aggregate_type = 'episode') or (operation_type = 'ensure_shot_directory' and aggregate_type = 'shot') or (operation_type = 'ensure_asset_directory' and aggregate_type = 'asset')),
	CONSTRAINT ck_sg_storage_operation_aggregate_id CHECK (aggregate_id > 0),
	CONSTRAINT ck_sg_storage_operation_target_path CHECK (btrim(target_relative_path) <> ''),
	CONSTRAINT ck_sg_storage_operation_status CHECK (operation_status in ('pending', 'processing', 'succeeded', 'retry_wait', 'failed', 'compensation_pending', 'compensated', 'compensation_failed')),
	CONSTRAINT ck_sg_storage_operation_idempotency CHECK (btrim(idempotency_key) <> ''),
	CONSTRAINT ck_sg_storage_operation_attempt_count CHECK (attempt_count >= 0),
	CONSTRAINT ck_sg_storage_operation_lease CHECK ((lease_owner is null and lease_until is null) or (lease_owner is not null and btrim(lease_owner) <> '' and lease_until is not null)),
	FOREIGN KEY(project_id) REFERENCES sg_project (project_id) ON DELETE RESTRICT
)
""".strip(),
    r"""
CREATE INDEX idx_sg_storage_operation_status_retry_lease ON sg_storage_operation (operation_status, next_retry_time, lease_until)
""".strip(),
    r"""
COMMENT ON TABLE sg_storage_operation IS 'Shot Grid NAS目录操作Outbox表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.operation_id IS '目录操作ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.operation_type IS '操作类型'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.aggregate_type IS '目标聚合类型'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.aggregate_id IS '目标业务对象ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.target_relative_path IS '项目根目录内目标相对路径'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.operation_status IS '执行状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.idempotency_key IS '服务端稳定幂等键'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.attempt_count IS '已执行次数'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.next_retry_time IS '下次允许重试时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.lease_owner IS 'Worker租约持有者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.lease_until IS 'Worker租约到期时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.started_time IS '开始时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.completed_time IS '成功或最终失败时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.last_error_key IS '最近错误键'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.last_error_message IS '已净化错误摘要'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.create_by IS '创建者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.create_time IS '创建时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_storage_operation.update_time IS '更新时间'
""".strip(),
    r"""
CREATE TABLE sg_asset_item (
	asset_item_id BIGSERIAL NOT NULL,
	project_id BIGINT NOT NULL,
	asset_id BIGINT NOT NULL,
	production_item VARCHAR(240),
	production_item_key VARCHAR(240),
	description TEXT,
	sort_order INTEGER DEFAULT '0' NOT NULL,
	source_import_batch_id BIGINT,
	source_row_no INTEGER,
	import_row_key CHAR(64),
	lifecycle_status VARCHAR(20) DEFAULT 'active' NOT NULL,
	create_by VARCHAR(64) DEFAULT '' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	update_by VARCHAR(64) DEFAULT '' NOT NULL,
	update_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	remark VARCHAR(500),
	lock_version INTEGER DEFAULT '0' NOT NULL,
	del_flag CHAR(1) DEFAULT '0' NOT NULL,
	PRIMARY KEY (asset_item_id),
	CONSTRAINT fk_sg_asset_item_asset_project FOREIGN KEY(asset_id, project_id) REFERENCES sg_asset (asset_id, project_id) ON DELETE RESTRICT,
	CONSTRAINT fk_sg_asset_item_import_project FOREIGN KEY(source_import_batch_id, project_id) REFERENCES sg_import_batch (batch_id, project_id) ON DELETE RESTRICT,
	CONSTRAINT uk_sg_asset_item_id_project UNIQUE (asset_item_id, project_id),
	CONSTRAINT ck_sg_asset_item_name_key CHECK (((production_item is null and production_item_key is null) or (production_item is not null and btrim(production_item) <> '' and production_item_key is not null and btrim(production_item_key) <> ''))),
	CONSTRAINT ck_sg_asset_item_sort_order CHECK (sort_order >= 0),
	CONSTRAINT ck_sg_asset_item_source_row CHECK (source_row_no is null or source_row_no > 0),
	CONSTRAINT ck_sg_asset_item_lifecycle CHECK (lifecycle_status in ('active', 'archived')),
	CONSTRAINT ck_sg_asset_item_lock_version CHECK (lock_version >= 0),
	CONSTRAINT ck_sg_asset_item_del_flag CHECK (del_flag in ('0', '2'))
)
""".strip(),
    r"""
CREATE INDEX idx_sg_asset_item_project_asset_lifecycle_sort ON sg_asset_item (project_id, asset_id, lifecycle_status, sort_order)
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_asset_item_import_row ON sg_asset_item (project_id, import_row_key) WHERE import_row_key IS NOT NULL AND del_flag = '0'
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_asset_item_name_active ON sg_asset_item (asset_id, production_item_key) WHERE production_item_key IS NOT NULL AND lifecycle_status = 'active' AND del_flag = '0'
""".strip(),
    r"""
COMMENT ON TABLE sg_asset_item IS 'Shot Grid资产制作分项表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.asset_item_id IS '制作分项ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.asset_id IS '资产ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.production_item IS '制作分项名称'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.production_item_key IS '制作分项规范化匹配键'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.description IS '制作分项描述'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.sort_order IS '资产内稳定顺序'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.source_import_batch_id IS '来源资产导入批次ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.source_row_no IS '来源Sheet明细行号'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.import_row_key IS '导入行幂等键'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.lifecycle_status IS '生命周期状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.create_by IS '创建者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.create_time IS '创建时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.update_by IS '更新者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.update_time IS '更新时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.remark IS '备注'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.lock_version IS '乐观锁版本'
""".strip(),
    r"""
COMMENT ON COLUMN sg_asset_item.del_flag IS '删除标志（0正常 2删除）'
""".strip(),
    r"""
CREATE TABLE sg_scene (
	scene_id BIGSERIAL NOT NULL,
	project_id BIGINT NOT NULL,
	episode_id BIGINT NOT NULL,
	scene_no INTEGER NOT NULL,
	scene_name VARCHAR(200),
	description TEXT,
	sort_order INTEGER DEFAULT '0' NOT NULL,
	lifecycle_status VARCHAR(20) DEFAULT 'active' NOT NULL,
	create_by VARCHAR(64) DEFAULT '' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	update_by VARCHAR(64) DEFAULT '' NOT NULL,
	update_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	remark VARCHAR(500),
	lock_version INTEGER DEFAULT '0' NOT NULL,
	del_flag CHAR(1) DEFAULT '0' NOT NULL,
	PRIMARY KEY (scene_id),
	CONSTRAINT fk_sg_scene_episode_project FOREIGN KEY(episode_id, project_id) REFERENCES sg_episode (episode_id, project_id) ON DELETE RESTRICT,
	CONSTRAINT uk_sg_scene_id_project_episode UNIQUE (scene_id, project_id, episode_id),
	CONSTRAINT ck_sg_scene_no CHECK (scene_no >= 0),
	CONSTRAINT ck_sg_scene_prologue_name CHECK ((scene_no = 0 and scene_name is not null and scene_name = '序') or (scene_no > 0 and (scene_name is null or scene_name <> '序'))),
	CONSTRAINT ck_sg_scene_sort_order CHECK (sort_order >= 0),
	CONSTRAINT ck_sg_scene_lifecycle CHECK (lifecycle_status in ('active', 'archived')),
	CONSTRAINT ck_sg_scene_lock_version CHECK (lock_version >= 0),
	CONSTRAINT ck_sg_scene_del_flag CHECK (del_flag in ('0', '2'))
)
""".strip(),
    r"""
CREATE INDEX idx_sg_scene_episode_lifecycle_sort ON sg_scene (episode_id, lifecycle_status, sort_order)
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_scene_no_active ON sg_scene (episode_id, scene_no) WHERE del_flag = '0'
""".strip(),
    r"""
COMMENT ON TABLE sg_scene IS 'Shot Grid场次主表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_scene.scene_id IS '场次ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_scene.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_scene.episode_id IS '集ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_scene.scene_no IS '集内场次号'
""".strip(),
    r"""
COMMENT ON COLUMN sg_scene.scene_name IS '场次名称'
""".strip(),
    r"""
COMMENT ON COLUMN sg_scene.description IS '场次描述'
""".strip(),
    r"""
COMMENT ON COLUMN sg_scene.sort_order IS '集内排序'
""".strip(),
    r"""
COMMENT ON COLUMN sg_scene.lifecycle_status IS '生命周期状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_scene.create_by IS '创建者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_scene.create_time IS '创建时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_scene.update_by IS '更新者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_scene.update_time IS '更新时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_scene.remark IS '备注'
""".strip(),
    r"""
COMMENT ON COLUMN sg_scene.lock_version IS '乐观锁版本'
""".strip(),
    r"""
COMMENT ON COLUMN sg_scene.del_flag IS '删除标志（0正常 2删除）'
""".strip(),
    r"""
CREATE TABLE sg_shot (
	shot_id BIGSERIAL NOT NULL,
	project_id BIGINT NOT NULL,
	episode_id BIGINT NOT NULL,
	scene_id BIGINT NOT NULL,
	shot_no INTEGER NOT NULL,
	storage_dir_name VARCHAR(32) NOT NULL,
	duration_ms BIGINT DEFAULT '0' NOT NULL,
	shot_size VARCHAR(40),
	camera_position VARCHAR(100),
	camera_movement VARCHAR(100),
	focal_length VARCHAR(50),
	description TEXT NOT NULL,
	dialogue TEXT,
	sound_effect TEXT,
	color_reference TEXT,
	sort_order INTEGER DEFAULT '0' NOT NULL,
	lifecycle_status VARCHAR(20) DEFAULT 'active' NOT NULL,
	create_by VARCHAR(64) DEFAULT '' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	update_by VARCHAR(64) DEFAULT '' NOT NULL,
	update_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	remark VARCHAR(500),
	lock_version INTEGER DEFAULT '0' NOT NULL,
	del_flag CHAR(1) DEFAULT '0' NOT NULL,
	PRIMARY KEY (shot_id),
	CONSTRAINT fk_sg_shot_scene_project_episode FOREIGN KEY(scene_id, project_id, episode_id) REFERENCES sg_scene (scene_id, project_id, episode_id) ON DELETE RESTRICT,
	CONSTRAINT uk_sg_shot_id_project UNIQUE (shot_id, project_id),
	CONSTRAINT ck_sg_shot_no CHECK (shot_no > 0),
	CONSTRAINT ck_sg_shot_duration CHECK (duration_ms >= 0),
	CONSTRAINT ck_sg_shot_sort_order CHECK (sort_order >= 0),
	CONSTRAINT ck_sg_shot_lifecycle CHECK (lifecycle_status in ('active', 'archived')),
	CONSTRAINT ck_sg_shot_lock_version CHECK (lock_version >= 0),
	CONSTRAINT ck_sg_shot_del_flag CHECK (del_flag in ('0', '2'))
)
""".strip(),
    r"""
CREATE INDEX idx_sg_shot_project_episode_scene_lifecycle_sort ON sg_shot (project_id, episode_id, scene_id, lifecycle_status, sort_order)
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_shot_no_active ON sg_shot (episode_id, shot_no) WHERE del_flag = '0'
""".strip(),
    r"""
COMMENT ON TABLE sg_shot IS 'Shot Grid镜头主表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.shot_id IS '镜头ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.episode_id IS '集ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.scene_id IS '场次ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.shot_no IS '集内镜头号'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.storage_dir_name IS 'NAS镜头目录快照'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.duration_ms IS '镜头时长（毫秒）'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.shot_size IS '景别'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.camera_position IS '机位'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.camera_movement IS '镜头运动'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.focal_length IS '焦段原始文本'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.description IS '镜头描述'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.dialogue IS '台词或对白'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.sound_effect IS '音效说明'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.color_reference IS '色调参考说明'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.sort_order IS '集内成片顺序'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.lifecycle_status IS '生命周期状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.create_by IS '创建者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.create_time IS '创建时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.update_by IS '更新者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.update_time IS '更新时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.remark IS '备注'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.lock_version IS '乐观锁版本'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot.del_flag IS '删除标志（0正常 2删除）'
""".strip(),
    r"""
CREATE TABLE sg_shot_asset (
	project_id BIGINT NOT NULL,
	shot_id BIGINT NOT NULL,
	asset_id BIGINT NOT NULL,
	usage_note VARCHAR(500),
	create_by VARCHAR(64) DEFAULT '' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (shot_id, asset_id),
	CONSTRAINT fk_sg_shot_asset_shot_project FOREIGN KEY(shot_id, project_id) REFERENCES sg_shot (shot_id, project_id) ON DELETE RESTRICT,
	CONSTRAINT fk_sg_shot_asset_asset_project FOREIGN KEY(asset_id, project_id) REFERENCES sg_asset (asset_id, project_id) ON DELETE RESTRICT
)
""".strip(),
    r"""
CREATE INDEX idx_sg_shot_asset_project_asset ON sg_shot_asset (project_id, asset_id)
""".strip(),
    r"""
COMMENT ON TABLE sg_shot_asset IS 'Shot Grid镜头与资产关系表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset.shot_id IS '镜头ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset.asset_id IS '资产ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset.usage_note IS '使用说明'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset.create_by IS '创建者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset.create_time IS '创建时间'
""".strip(),
    r"""
CREATE TABLE sg_shot_asset_requirement (
	requirement_id BIGSERIAL NOT NULL,
	project_id BIGINT NOT NULL,
	shot_id BIGINT NOT NULL,
	asset_type VARCHAR(20) NOT NULL,
	raw_name VARCHAR(200) NOT NULL,
	normalized_name VARCHAR(200) NOT NULL,
	resolution_status VARCHAR(20) DEFAULT 'pending' NOT NULL,
	asset_id BIGINT,
	source_import_batch_id BIGINT NOT NULL,
	resolved_by BIGINT,
	resolved_time TIMESTAMP(0) WITHOUT TIME ZONE,
	resolution_reason VARCHAR(500),
	create_by VARCHAR(64) DEFAULT '' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	update_by VARCHAR(64),
	update_time TIMESTAMP(0) WITHOUT TIME ZONE,
	PRIMARY KEY (requirement_id),
	CONSTRAINT fk_sg_requirement_shot_project FOREIGN KEY(shot_id, project_id) REFERENCES sg_shot (shot_id, project_id) ON DELETE RESTRICT,
	CONSTRAINT fk_sg_requirement_asset_project_type FOREIGN KEY(asset_id, project_id, asset_type) REFERENCES sg_asset (asset_id, project_id, asset_type) ON DELETE RESTRICT,
	CONSTRAINT fk_sg_requirement_import_project FOREIGN KEY(source_import_batch_id, project_id) REFERENCES sg_import_batch (batch_id, project_id) ON DELETE RESTRICT,
	CONSTRAINT ck_sg_requirement_asset_type CHECK (asset_type in ('Character', 'Environment', 'Prop')),
	CONSTRAINT ck_sg_requirement_raw_name CHECK (btrim(raw_name) <> ''),
	CONSTRAINT ck_sg_requirement_normalized_name CHECK (btrim(normalized_name) <> ''),
	CONSTRAINT ck_sg_requirement_status CHECK (resolution_status in ('pending', 'matched', 'conflict', 'ignored')),
	CONSTRAINT ck_sg_requirement_matched_asset CHECK ((resolution_status = 'matched' and asset_id is not null) or (resolution_status <> 'matched' and asset_id is null)),
	FOREIGN KEY(resolved_by) REFERENCES sys_user (user_id) ON DELETE RESTRICT
)
""".strip(),
    r"""
CREATE INDEX idx_sg_requirement_project_status_type_name ON sg_shot_asset_requirement (project_id, resolution_status, asset_type, normalized_name)
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_shot_asset_requirement_key ON sg_shot_asset_requirement (shot_id, asset_type, normalized_name)
""".strip(),
    r"""
COMMENT ON TABLE sg_shot_asset_requirement IS 'Shot Grid镜头资产待匹配需求表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset_requirement.requirement_id IS '需求ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset_requirement.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset_requirement.shot_id IS '来源镜头ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset_requirement.asset_type IS '资产类型'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset_requirement.raw_name IS 'Excel原始资产名称'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset_requirement.normalized_name IS '规范化匹配名称'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset_requirement.resolution_status IS '解析状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset_requirement.asset_id IS '匹配资产ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset_requirement.source_import_batch_id IS '来源镜头导入批次ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset_requirement.resolved_by IS '人工解决用户ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset_requirement.resolved_time IS '解决时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset_requirement.resolution_reason IS '解决或忽略原因'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset_requirement.create_by IS '创建者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset_requirement.create_time IS '创建时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset_requirement.update_by IS '更新者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_shot_asset_requirement.update_time IS '更新时间'
""".strip(),
    r"""
CREATE TABLE sg_task (
	task_id BIGSERIAL NOT NULL,
	project_id BIGINT NOT NULL,
	shot_id BIGINT,
	asset_item_id BIGINT,
	task_name VARCHAR(240) NOT NULL,
	task_kind VARCHAR(20) NOT NULL,
	assignee_user_id BIGINT NOT NULL,
	task_status VARCHAR(20) DEFAULT 'not_started' NOT NULL,
	priority VARCHAR(10) DEFAULT 'normal' NOT NULL,
	due_date DATE,
	requirements TEXT,
	create_by VARCHAR(64) DEFAULT '' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	update_by VARCHAR(64) DEFAULT '' NOT NULL,
	update_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	remark VARCHAR(500),
	lock_version INTEGER DEFAULT '0' NOT NULL,
	del_flag CHAR(1) DEFAULT '0' NOT NULL,
	PRIMARY KEY (task_id),
	CONSTRAINT fk_sg_task_assignee_member FOREIGN KEY(project_id, assignee_user_id) REFERENCES sg_project_member (project_id, user_id) ON DELETE RESTRICT,
	CONSTRAINT fk_sg_task_shot_project FOREIGN KEY(shot_id, project_id) REFERENCES sg_shot (shot_id, project_id) ON DELETE RESTRICT,
	CONSTRAINT fk_sg_task_asset_item_project FOREIGN KEY(asset_item_id, project_id) REFERENCES sg_asset_item (asset_item_id, project_id) ON DELETE RESTRICT,
	CONSTRAINT uk_sg_task_id_project UNIQUE (task_id, project_id),
	CONSTRAINT ck_sg_task_name CHECK (btrim(task_name) <> ''),
	CONSTRAINT ck_sg_task_owner_kind CHECK (((shot_id is not null and asset_item_id is null and task_kind = 'shot_video') or (shot_id is null and asset_item_id is not null and task_kind = 'asset_image'))),
	CONSTRAINT ck_sg_task_status CHECK (task_status in ('not_started', 'in_progress', 'pending_review', 'revision', 'completed')),
	CONSTRAINT ck_sg_task_priority CHECK (priority in ('low', 'normal', 'high', 'urgent')),
	CONSTRAINT ck_sg_task_lock_version CHECK (lock_version >= 0),
	CONSTRAINT ck_sg_task_del_flag CHECK (del_flag in ('0', '2'))
)
""".strip(),
    r"""
CREATE INDEX idx_sg_task_project_assignee_status_due ON sg_task (project_id, assignee_user_id, task_status, due_date)
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_task_asset_item ON sg_task (asset_item_id) WHERE asset_item_id IS NOT NULL AND del_flag = '0'
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_task_shot ON sg_task (shot_id) WHERE shot_id IS NOT NULL AND del_flag = '0'
""".strip(),
    r"""
COMMENT ON TABLE sg_task IS 'Shot Grid制作任务表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.task_id IS '任务ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.shot_id IS '镜头ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.asset_item_id IS '资产制作分项ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.task_name IS '任务名称'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.task_kind IS '任务类型'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.assignee_user_id IS '负责人用户ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.task_status IS '任务状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.priority IS '任务优先级'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.due_date IS '截止日期'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.requirements IS '制作要求'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.create_by IS '创建者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.create_time IS '创建时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.update_by IS '更新者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.update_time IS '更新时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.remark IS '备注'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.lock_version IS '乐观锁版本'
""".strip(),
    r"""
COMMENT ON COLUMN sg_task.del_flag IS '删除标志（0正常 2删除）'
""".strip(),
    r"""
CREATE TABLE sg_version_submission (
	submission_id BIGSERIAL NOT NULL,
	project_id BIGINT NOT NULL,
	task_id BIGINT NOT NULL,
	source_file_id VARCHAR(36) NOT NULL,
	reserved_version_no INTEGER NOT NULL,
	generated_at_ms BIGINT NOT NULL,
	business_file_name VARCHAR(255) NOT NULL,
	target_relative_path VARCHAR(1200) NOT NULL,
	temporary_relative_path VARCHAR(1200) NOT NULL,
	source_sha256 CHAR(64) NOT NULL,
	source_file_size BIGINT NOT NULL,
	changelog TEXT NOT NULL,
	ai_params JSONB,
	submission_status VARCHAR(20) DEFAULT 'pending' NOT NULL,
	submitted_by BIGINT NOT NULL,
	idempotency_key VARCHAR(100) NOT NULL,
	attempt_count INTEGER DEFAULT '0' NOT NULL,
	lease_owner VARCHAR(100),
	lease_until TIMESTAMP(0) WITHOUT TIME ZONE,
	last_error_key VARCHAR(100),
	last_error_message VARCHAR(500),
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	update_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (submission_id),
	CONSTRAINT fk_sg_submission_task_project FOREIGN KEY(task_id, project_id) REFERENCES sg_task (task_id, project_id) ON DELETE RESTRICT,
	CONSTRAINT uk_sg_submission_id_project_task UNIQUE (submission_id, project_id, task_id),
	CONSTRAINT uk_sg_submission_task_version UNIQUE (task_id, reserved_version_no),
	CONSTRAINT uk_sg_submission_task_user_idempotency UNIQUE (task_id, submitted_by, idempotency_key),
	CONSTRAINT ck_sg_submission_version_no CHECK (reserved_version_no > 0),
	CONSTRAINT ck_sg_submission_generated_at CHECK (generated_at_ms > 0),
	CONSTRAINT ck_sg_submission_business_name CHECK (btrim(business_file_name) <> ''),
	CONSTRAINT ck_sg_submission_target_path CHECK (btrim(target_relative_path) <> ''),
	CONSTRAINT ck_sg_submission_temp_path CHECK (btrim(temporary_relative_path) <> ''),
	CONSTRAINT ck_sg_submission_distinct_paths CHECK (temporary_relative_path <> target_relative_path),
	CONSTRAINT ck_sg_submission_file_size CHECK (source_file_size >= 0),
	CONSTRAINT ck_sg_submission_changelog CHECK (btrim(changelog) <> ''),
	CONSTRAINT ck_sg_submission_status CHECK (submission_status in ('pending', 'publishing', 'published', 'committing', 'committed', 'failed')),
	CONSTRAINT ck_sg_submission_idempotency CHECK (btrim(idempotency_key) <> ''),
	CONSTRAINT ck_sg_submission_attempt_count CHECK (attempt_count >= 0),
	CONSTRAINT ck_sg_submission_lease CHECK ((lease_owner is null and lease_until is null) or (lease_owner is not null and btrim(lease_owner) <> '' and lease_until is not null)),
	FOREIGN KEY(source_file_id) REFERENCES sys_file_info (file_id) ON DELETE RESTRICT,
	FOREIGN KEY(submitted_by) REFERENCES sys_user (user_id) ON DELETE RESTRICT
)
""".strip(),
    r"""
CREATE INDEX idx_sg_submission_status_lease_update ON sg_version_submission (submission_status, lease_until, update_time)
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_version_submission_active ON sg_version_submission (task_id) WHERE submission_status IN ('pending', 'publishing', 'published', 'committing')
""".strip(),
    r"""
COMMENT ON TABLE sg_version_submission IS 'Shot Grid版本暂存与NAS发布编排表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.submission_id IS '版本提交ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.task_id IS '任务ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.source_file_id IS '平台源文件ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.reserved_version_no IS '保留版本号'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.generated_at_ms IS '业务文件名服务端时间戳'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.business_file_name IS '不可变业务文件名'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.target_relative_path IS 'NAS目标相对路径'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.temporary_relative_path IS 'NAS临时文件相对路径'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.source_sha256 IS '源文件SHA-256摘要'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.source_file_size IS '源文件大小'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.changelog IS '本轮修改说明'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.ai_params IS 'AI生成参数快照'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.submission_status IS '提交编排状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.submitted_by IS '提交用户ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.idempotency_key IS '客户端幂等键'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.attempt_count IS 'NAS发布尝试次数'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.lease_owner IS 'Worker租约持有者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.lease_until IS 'Worker租约到期时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.last_error_key IS '最近错误键'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.last_error_message IS '已净化错误摘要'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.create_time IS '创建时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_submission.update_time IS '更新时间'
""".strip(),
    r"""
CREATE TABLE sg_version (
	version_id BIGSERIAL NOT NULL,
	project_id BIGINT NOT NULL,
	task_id BIGINT NOT NULL,
	submission_id BIGINT NOT NULL,
	version_no INTEGER NOT NULL,
	version_status VARCHAR(20) DEFAULT 'pending_review' NOT NULL,
	changelog TEXT NOT NULL,
	ai_params JSONB,
	submitted_by BIGINT NOT NULL,
	submitted_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	generated_at_ms BIGINT NOT NULL,
	lock_version INTEGER DEFAULT '0' NOT NULL,
	PRIMARY KEY (version_id),
	CONSTRAINT fk_sg_version_submission_project_task FOREIGN KEY(submission_id, project_id, task_id) REFERENCES sg_version_submission (submission_id, project_id, task_id) ON DELETE RESTRICT,
	CONSTRAINT uk_sg_version_id_project UNIQUE (version_id, project_id),
	CONSTRAINT uk_sg_version_task_no UNIQUE (task_id, version_no),
	CONSTRAINT uk_sg_version_submission UNIQUE (submission_id),
	CONSTRAINT ck_sg_version_no CHECK (version_no > 0),
	CONSTRAINT ck_sg_version_status CHECK (version_status in ('pending_review', 'rejected', 'final')),
	CONSTRAINT ck_sg_version_changelog CHECK (btrim(changelog) <> ''),
	CONSTRAINT ck_sg_version_generated_at CHECK (generated_at_ms > 0),
	CONSTRAINT ck_sg_version_lock_version CHECK (lock_version >= 0),
	FOREIGN KEY(submitted_by) REFERENCES sys_user (user_id) ON DELETE RESTRICT
)
""".strip(),
    r"""
CREATE INDEX idx_sg_version_task_version_no ON sg_version (task_id, version_no)
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_version_task_final ON sg_version (task_id) WHERE version_status = 'final'
""".strip(),
    r"""
COMMENT ON TABLE sg_version IS 'Shot Grid不可覆盖版本主表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version.version_id IS '版本ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version.task_id IS '任务ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version.submission_id IS '来源版本提交ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version.version_no IS '任务内版本序号'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version.version_status IS '版本状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version.changelog IS '修改说明'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version.ai_params IS 'AI生成参数快照'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version.submitted_by IS '提交用户ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version.submitted_time IS '提交时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version.generated_at_ms IS '业务文件名服务端时间戳'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version.lock_version IS '审核乐观锁版本'
""".strip(),
    r"""
CREATE TABLE sg_note (
	note_id BIGSERIAL NOT NULL,
	project_id BIGINT NOT NULL,
	version_id BIGINT NOT NULL,
	reviewer_user_id BIGINT NOT NULL,
	content TEXT NOT NULL,
	media_time_ms BIGINT,
	annotations JSONB,
	is_mandatory CHAR(1) DEFAULT '0' NOT NULL,
	note_status VARCHAR(20) DEFAULT 'open' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	update_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (note_id),
	CONSTRAINT fk_sg_note_version_project FOREIGN KEY(version_id, project_id) REFERENCES sg_version (version_id, project_id) ON DELETE RESTRICT,
	CONSTRAINT uk_sg_note_id_project UNIQUE (note_id, project_id),
	CONSTRAINT ck_sg_note_content CHECK (btrim(content) <> ''),
	CONSTRAINT ck_sg_note_media_time CHECK (media_time_ms is null or media_time_ms >= 0),
	CONSTRAINT ck_sg_note_mandatory CHECK (is_mandatory in ('0', '1')),
	CONSTRAINT ck_sg_note_status CHECK (note_status in ('open', 'resolved')),
	FOREIGN KEY(reviewer_user_id) REFERENCES sys_user (user_id) ON DELETE RESTRICT
)
""".strip(),
    r"""
CREATE INDEX idx_sg_note_version_status_time ON sg_note (version_id, note_status, create_time)
""".strip(),
    r"""
COMMENT ON TABLE sg_note IS 'Shot Grid版本级审核意见表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note.note_id IS '审核意见ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note.version_id IS '版本ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note.reviewer_user_id IS '审核用户ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note.content IS '审核意见正文'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note.media_time_ms IS '视频时间点（毫秒）'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note.annotations IS '结构化批注数组'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note.is_mandatory IS '是否必须修改'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note.note_status IS '处理状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note.create_time IS '创建时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note.update_time IS '更新时间'
""".strip(),
    r"""
CREATE TABLE sg_review_action (
	action_id BIGSERIAL NOT NULL,
	project_id BIGINT NOT NULL,
	version_id BIGINT NOT NULL,
	reviewer_user_id BIGINT NOT NULL,
	action_type VARCHAR(20) NOT NULL,
	from_status VARCHAR(20) NOT NULL,
	to_status VARCHAR(20) NOT NULL,
	reason VARCHAR(1000),
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (action_id),
	CONSTRAINT fk_sg_review_action_version_project FOREIGN KEY(version_id, project_id) REFERENCES sg_version (version_id, project_id) ON DELETE RESTRICT,
	CONSTRAINT ck_sg_review_action_type CHECK (action_type in ('approve', 'reject', 'defer')),
	CONSTRAINT ck_sg_review_action_from_status CHECK (from_status in ('pending_review', 'rejected', 'final')),
	CONSTRAINT ck_sg_review_action_to_status CHECK (to_status in ('pending_review', 'rejected', 'final')),
	CONSTRAINT ck_sg_review_action_transition CHECK ((action_type = 'approve' and from_status = 'pending_review' and to_status = 'final') or (action_type = 'reject' and from_status = 'pending_review' and to_status = 'rejected') or (action_type = 'defer' and from_status = 'pending_review' and to_status = 'pending_review')),
	FOREIGN KEY(reviewer_user_id) REFERENCES sys_user (user_id) ON DELETE RESTRICT
)
""".strip(),
    r"""
CREATE INDEX idx_sg_review_action_version_time ON sg_review_action (version_id, create_time)
""".strip(),
    r"""
COMMENT ON TABLE sg_review_action IS 'Shot Grid审核动作不可变历史表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_action.action_id IS '审核动作ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_action.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_action.version_id IS '审核版本ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_action.reviewer_user_id IS '操作用户ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_action.action_type IS '审核动作'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_action.from_status IS '操作前版本状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_action.to_status IS '操作后版本状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_action.reason IS '原因或说明'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_action.create_time IS '操作时间'
""".strip(),
    r"""
CREATE TABLE sg_review_list (
	review_list_id BIGSERIAL NOT NULL,
	project_id BIGINT NOT NULL,
	auto_version_id BIGINT,
	review_list_name VARCHAR(240) NOT NULL,
	description TEXT,
	review_date DATE,
	review_mode VARCHAR(20) NOT NULL,
	review_status VARCHAR(20) NOT NULL,
	create_by VARCHAR(64) DEFAULT '' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	update_by VARCHAR(64) DEFAULT '' NOT NULL,
	update_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	remark VARCHAR(500),
	lock_version INTEGER DEFAULT '0' NOT NULL,
	del_flag CHAR(1) DEFAULT '0' NOT NULL,
	PRIMARY KEY (review_list_id),
	CONSTRAINT fk_sg_review_list_auto_version_project FOREIGN KEY(auto_version_id, project_id) REFERENCES sg_version (version_id, project_id) ON DELETE RESTRICT,
	CONSTRAINT ck_sg_review_list_name CHECK (btrim(review_list_name) <> ''),
	CONSTRAINT ck_sg_review_list_mode CHECK (review_mode in ('auto_single', 'manual_batch')),
	CONSTRAINT ck_sg_review_list_status CHECK (review_status in ('draft', 'active', 'completed', 'archived')),
	CONSTRAINT ck_sg_review_list_mode_version CHECK ((review_mode = 'auto_single' and auto_version_id is not null) or (review_mode = 'manual_batch' and auto_version_id is null)),
	CONSTRAINT ck_sg_review_list_auto_status CHECK (review_mode <> 'auto_single' or review_status <> 'draft'),
	CONSTRAINT ck_sg_review_list_lock_version CHECK (lock_version >= 0),
	CONSTRAINT ck_sg_review_list_del_flag CHECK (del_flag in ('0', '2')),
	FOREIGN KEY(project_id) REFERENCES sg_project (project_id) ON DELETE RESTRICT
)
""".strip(),
    r"""
CREATE INDEX idx_sg_review_list_project_status_time ON sg_review_list (project_id, review_status, create_time)
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_review_list_auto_version ON sg_review_list (auto_version_id) WHERE auto_version_id IS NOT NULL
""".strip(),
    r"""
COMMENT ON TABLE sg_review_list IS 'Shot Grid审核单主表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list.review_list_id IS '审核单ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list.auto_version_id IS '自动单版本审核单对应版本ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list.review_list_name IS '审核单名称'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list.description IS '审核单说明'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list.review_date IS '审核日期'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list.review_mode IS '审核单模式'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list.review_status IS '审核单状态'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list.create_by IS '创建者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list.create_time IS '创建时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list.update_by IS '更新者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list.update_time IS '更新时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list.remark IS '备注'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list.lock_version IS '乐观锁版本'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list.del_flag IS '删除标志（0正常 2删除）'
""".strip(),
    r"""
CREATE TABLE sg_version_file (
	version_id BIGINT NOT NULL,
	file_id VARCHAR(36) NOT NULL,
	file_role VARCHAR(30) NOT NULL,
	business_file_name VARCHAR(255) NOT NULL,
	nas_relative_path VARCHAR(1200),
	nas_sha256 CHAR(64),
	nas_file_size BIGINT,
	published_time TIMESTAMP(0) WITHOUT TIME ZONE,
	is_primary CHAR(1) DEFAULT '0' NOT NULL,
	sort_order INTEGER DEFAULT '0' NOT NULL,
	create_by VARCHAR(64) DEFAULT '' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (version_id, file_id, file_role),
	CONSTRAINT ck_sg_version_file_role CHECK (file_role in ('review_media', 'thumbnail', 'proxy_media', 'source_original', 'source_repaired', 'first_frame', 'last_frame', 'reference')),
	CONSTRAINT ck_sg_version_file_business_name CHECK (btrim(business_file_name) <> ''),
	CONSTRAINT ck_sg_version_file_size CHECK (nas_file_size is null or nas_file_size >= 0),
	CONSTRAINT ck_sg_version_file_primary CHECK (is_primary in ('0', '1')),
	CONSTRAINT ck_sg_version_file_primary_role CHECK (is_primary = '0' or file_role = 'review_media'),
	CONSTRAINT ck_sg_version_file_sort_order CHECK (sort_order >= 0),
	CONSTRAINT ck_sg_version_file_review_nas CHECK (not (file_role = 'review_media' and is_primary = '1') or (nas_relative_path is not null and nas_sha256 is not null and nas_file_size is not null and published_time is not null)),
	FOREIGN KEY(version_id) REFERENCES sg_version (version_id) ON DELETE RESTRICT,
	FOREIGN KEY(file_id) REFERENCES sys_file_info (file_id) ON DELETE RESTRICT
)
""".strip(),
    r"""
CREATE INDEX idx_sg_version_file_file ON sg_version_file (file_id)
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_version_file_business_name ON sg_version_file (business_file_name) WHERE file_role = 'review_media' AND is_primary = '1'
""".strip(),
    r"""
CREATE UNIQUE INDEX uk_sg_version_file_primary_review ON sg_version_file (version_id) WHERE file_role = 'review_media' AND is_primary = '1'
""".strip(),
    r"""
COMMENT ON TABLE sg_version_file IS 'Shot Grid版本文件用途关系表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_file.version_id IS '版本ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_file.file_id IS '平台文件ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_file.file_role IS '文件用途'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_file.business_file_name IS '业务展示和下载文件名'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_file.nas_relative_path IS 'NAS相对项目根目录路径'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_file.nas_sha256 IS 'NAS文件SHA-256摘要'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_file.nas_file_size IS 'NAS文件大小'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_file.published_time IS 'NAS发布时间'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_file.is_primary IS '是否主文件'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_file.sort_order IS '展示顺序'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_file.create_by IS '创建者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_version_file.create_time IS '创建时间'
""".strip(),
    r"""
CREATE TABLE sg_note_reply (
	reply_id BIGSERIAL NOT NULL,
	project_id BIGINT NOT NULL,
	note_id BIGINT NOT NULL,
	reply_user_id BIGINT NOT NULL,
	content TEXT NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (reply_id),
	CONSTRAINT fk_sg_note_reply_note_project FOREIGN KEY(note_id, project_id) REFERENCES sg_note (note_id, project_id) ON DELETE RESTRICT,
	CONSTRAINT ck_sg_note_reply_content CHECK (btrim(content) <> ''),
	FOREIGN KEY(reply_user_id) REFERENCES sys_user (user_id) ON DELETE RESTRICT
)
""".strip(),
    r"""
CREATE INDEX idx_sg_note_reply_note_time ON sg_note_reply (note_id, create_time, reply_id)
""".strip(),
    r"""
COMMENT ON TABLE sg_note_reply IS 'Shot Grid审核意见不可变回复历史表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note_reply.reply_id IS '回复ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note_reply.project_id IS '项目ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note_reply.note_id IS '审核意见ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note_reply.reply_user_id IS '回复用户ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note_reply.content IS '回复内容'
""".strip(),
    r"""
COMMENT ON COLUMN sg_note_reply.create_time IS '回复时间'
""".strip(),
    r"""
CREATE TABLE sg_review_list_version (
	review_list_id BIGINT NOT NULL,
	version_id BIGINT NOT NULL,
	sort_order INTEGER NOT NULL,
	create_by VARCHAR(64) DEFAULT '' NOT NULL,
	create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (review_list_id, version_id),
	CONSTRAINT uk_sg_review_list_version_sort UNIQUE (review_list_id, sort_order),
	CONSTRAINT ck_sg_review_list_version_sort_order CHECK (sort_order >= 0),
	FOREIGN KEY(review_list_id) REFERENCES sg_review_list (review_list_id) ON DELETE RESTRICT,
	FOREIGN KEY(version_id) REFERENCES sg_version (version_id) ON DELETE RESTRICT
)
""".strip(),
    r"""
CREATE INDEX idx_sg_review_list_version_version ON sg_review_list_version (version_id)
""".strip(),
    r"""
COMMENT ON TABLE sg_review_list_version IS 'Shot Grid审核单与版本有序关系表'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list_version.review_list_id IS '审核单ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list_version.version_id IS '版本ID'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list_version.sort_order IS '审核顺序'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list_version.create_by IS '创建者'
""".strip(),
    r"""
COMMENT ON COLUMN sg_review_list_version.create_time IS '创建时间'
""".strip(),
)

DICT_TYPE_SEEDS = (
    ('Shot Grid项目类型', 'sg_project_type', 'Shot Grid项目类型'),
    ('Shot Grid画幅', 'sg_aspect_ratio', 'Shot Grid项目画幅'),
    ('Shot Grid资产类型', 'sg_asset_type', 'Shot Grid资产类型'),
    ('Shot Grid项目阶段', 'sg_project_phase', 'Shot Grid项目当前阶段'),
    ('Shot Grid任务优先级', 'sg_task_priority', 'Shot Grid制作任务优先级'),
)

DICT_DATA_SEEDS = (
    (1, 'AI影视短片', 'ai_short_film', 'sg_project_type', 'Y', 'Shot Grid项目类型'),
    (1, '16:9', '16:9', 'sg_aspect_ratio', 'Y', 'Shot Grid项目画幅'),
    (2, '21:9', '21:9', 'sg_aspect_ratio', 'N', 'Shot Grid项目画幅'),
    (3, '2.39:1', '2.39:1', 'sg_aspect_ratio', 'N', 'Shot Grid项目画幅'),
    (4, '9:16', '9:16', 'sg_aspect_ratio', 'N', 'Shot Grid项目画幅'),
    (5, '1:1', '1:1', 'sg_aspect_ratio', 'N', 'Shot Grid项目画幅'),
    (1, '角色', 'Character', 'sg_asset_type', 'N', 'Shot Grid资产类型'),
    (2, '场景', 'Environment', 'sg_asset_type', 'N', 'Shot Grid资产类型'),
    (3, '道具', 'Prop', 'sg_asset_type', 'N', 'Shot Grid资产类型'),
    (1, '策划', 'planning', 'sg_project_phase', 'Y', 'Shot Grid项目阶段'),
    (2, '资产制作', 'asset_production', 'sg_project_phase', 'N', 'Shot Grid项目阶段'),
    (3, '镜头制作', 'shot_production', 'sg_project_phase', 'N', 'Shot Grid项目阶段'),
    (4, '审核', 'review', 'sg_project_phase', 'N', 'Shot Grid项目阶段'),
    (5, '交付', 'delivery', 'sg_project_phase', 'N', 'Shot Grid项目阶段'),
    (6, '已完成', 'completed', 'sg_project_phase', 'N', 'Shot Grid项目阶段'),
    (1, '低', 'low', 'sg_task_priority', 'N', 'Shot Grid任务优先级'),
    (2, '普通', 'normal', 'sg_task_priority', 'Y', 'Shot Grid任务优先级'),
    (3, '高', 'high', 'sg_task_priority', 'N', 'Shot Grid任务优先级'),
    (4, '紧急', 'urgent', 'sg_task_priority', 'N', 'Shot Grid任务优先级'),
)

ROOT_MENU_SEED = (
    'Shot Grid',
    'shot-grid',
    'ShotGrid',
    'video-camera',
    'shotgrid:navigation:list',
)

CHILD_MENU_SEEDS = (
    ('工作台', 1, '/workbench', 'workbench', 'dashboard', 'shotgrid:project:overview'),
    ('项目', 2, '/projects', 'projects', 'project', 'shotgrid:project:list'),
    ('镜头管理', 3, '/shots', 'shots', 'video-camera', 'shotgrid:shot:list'),
    ('资产库管理', 4, '/assets', 'assets', 'picture', 'shotgrid:asset:list'),
    ('版本审核', 5, '/reviews', 'reviews', 'eye-open', 'shotgrid:reviewList:list'),
    ('文件与NAS', 6, '/files', 'files', 'folder-opened', 'shotgrid:storage:path'),
)

PERMISSION_BUTTON_SEEDS = (
    ('files', 1, '查看可选 NAS 根目录', 'shotgrid:storageRoot:list'),
    ('files', 2, '查看 NAS 根目录详情与健康状态', 'shotgrid:storageRoot:query'),
    ('files', 3, '新增 NAS 根目录配置', 'shotgrid:storageRoot:add'),
    ('files', 4, '修改或停用 NAS 根目录配置', 'shotgrid:storageRoot:edit'),
    ('files', 5, '执行 NAS 可达性和写权限探测', 'shotgrid:storageRoot:probe'),
    ('projects', 1, '查看项目详情', 'shotgrid:project:query'),
    ('projects', 2, '创建项目', 'shotgrid:project:add'),
    ('projects', 3, '修改项目', 'shotgrid:project:edit'),
    ('projects', 4, '归档项目', 'shotgrid:project:archive'),
    ('projects', 5, '将筹备中项目转为进行中', 'shotgrid:project:start'),
    ('projects', 6, '完成项目并执行完整性校验', 'shotgrid:project:complete'),
    ('files', 6, '重试项目或业务目录初始化', 'shotgrid:storage:retry'),
    ('projects', 7, '查看项目成员', 'shotgrid:member:list'),
    ('projects', 8, '添加成员', 'shotgrid:member:add'),
    ('projects', 9, '修改项目角色', 'shotgrid:member:edit'),
    ('projects', 10, '移除成员', 'shotgrid:member:remove'),
    ('shots', 1, '查看集列表', 'shotgrid:episode:list'),
    ('shots', 2, '创建集', 'shotgrid:episode:add'),
    ('shots', 3, '修改集', 'shotgrid:episode:edit'),
    ('shots', 4, '归档集', 'shotgrid:episode:archive'),
    ('shots', 5, '查看场次', 'shotgrid:scene:list'),
    ('shots', 6, '查看场次详情', 'shotgrid:scene:query'),
    ('shots', 7, '创建场次', 'shotgrid:scene:add'),
    ('shots', 8, '修改场次', 'shotgrid:scene:edit'),
    ('shots', 9, '归档场次', 'shotgrid:scene:archive'),
    ('shots', 10, '查看镜头详情', 'shotgrid:shot:query'),
    ('shots', 11, '创建镜头', 'shotgrid:shot:add'),
    ('shots', 12, '修改镜头', 'shotgrid:shot:edit'),
    ('shots', 13, '归档镜头', 'shotgrid:shot:archive'),
    ('shots', 14, '导入镜头表', 'shotgrid:shot:import'),
    ('assets', 1, '查看资产详情', 'shotgrid:asset:query'),
    ('assets', 2, '创建资产', 'shotgrid:asset:add'),
    ('assets', 3, '修改资产', 'shotgrid:asset:edit'),
    ('assets', 4, '归档资产', 'shotgrid:asset:archive'),
    ('assets', 5, '导入资产表', 'shotgrid:asset:import'),
    ('assets', 6, '查看镜头资产待匹配需求', 'shotgrid:assetRequirement:list'),
    ('assets', 7, '人工选择唯一正式资产并完成匹配', 'shotgrid:assetRequirement:resolve'),
    ('assets', 8, '有原因地忽略待匹配需求', 'shotgrid:assetRequirement:ignore'),
    ('assets', 9, '重新执行项目范围唯一匹配', 'shotgrid:assetRequirement:rematch'),
    ('projects', 11, '查看所属项目导入批次', 'shotgrid:import:list'),
    ('projects', 12, '查看导入结果摘要', 'shotgrid:import:query'),
    ('workbench', 1, '查看任务列表', 'shotgrid:task:list'),
    ('workbench', 2, '查看任务详情', 'shotgrid:task:query'),
    ('workbench', 3, '修改任务要求、优先级和截止日期', 'shotgrid:task:edit'),
    ('workbench', 4, '分配或改派制作任务', 'shotgrid:task:assign'),
    ('workbench', 5, '开始本人任务', 'shotgrid:task:start'),
    ('reviews', 1, '查看版本列表', 'shotgrid:version:list'),
    ('reviews', 2, '查看版本详情', 'shotgrid:version:query'),
    ('reviews', 3, '上传并提交任务版本', 'shotgrid:version:add'),
    ('reviews', 4, '重试本人失败的版本提交', 'shotgrid:version:retry'),
    ('reviews', 5, '审核版本', 'shotgrid:version:review'),
    ('reviews', 6, '查看版本审核意见', 'shotgrid:note:list'),
    ('reviews', 7, '添加审核意见', 'shotgrid:note:add'),
    ('reviews', 8, '回复有权访问任务的意见', 'shotgrid:note:reply'),
    ('reviews', 9, '解决审核意见', 'shotgrid:note:resolve'),
    ('reviews', 10, '查看审核单详情', 'shotgrid:reviewList:query'),
    ('reviews', 11, '创建人工批量审核单', 'shotgrid:reviewList:add'),
    ('reviews', 12, '修改草稿审核单和顺序', 'shotgrid:reviewList:edit'),
    ('reviews', 13, '激活人工审核单', 'shotgrid:reviewList:activate'),
    ('reviews', 14, '完成人工审核单', 'shotgrid:reviewList:complete'),
    ('reviews', 15, '归档审核单', 'shotgrid:reviewList:archive'),
    ('files', 7, '通过 Shot Grid 授权接口预览或下载版本文件', 'shotgrid:file:download'),
    ('projects', 13, '平台管理员跨项目管理', 'shotgrid:project:all'),
)


def _sql_literal(value: str) -> str:
    """生成仅供本迁移固定种子使用的 SQL 字符串字面量。"""
    return "'" + value.replace("'", "''") + "'"


def _execute(statement: str) -> None:
    """执行一条可同时支持在线和离线模式的 PostgreSQL 语句。"""
    op.execute(sa.text(statement))


def _is_postgresql() -> bool:
    """Shot Grid 首版仅在 PostgreSQL 方言下创建业务结构。"""
    return op.get_context().dialect.name == 'postgresql'


def _insert_dictionary_seeds() -> None:
    for dict_name, dict_type, remark in DICT_TYPE_SEEDS:
        _execute(
            f"""
            INSERT INTO sys_dict_type (
                dict_name, dict_type, status, create_by, create_time, update_by, update_time, remark
            )
            SELECT
                {_sql_literal(dict_name)}, {_sql_literal(dict_type)}, '0',
                {_sql_literal(SEED_MARKER)}, current_timestamp, '', NULL, {_sql_literal(remark)}
            WHERE NOT EXISTS (
                SELECT 1 FROM sys_dict_type WHERE dict_type = {_sql_literal(dict_type)}
            )
            """
        )

    for dict_sort, dict_label, dict_value, dict_type, is_default, remark in DICT_DATA_SEEDS:
        _execute(
            f"""
            INSERT INTO sys_dict_data (
                dict_sort, dict_label, dict_value, dict_type, css_class, list_class,
                is_default, status, create_by, create_time, update_by, update_time, remark
            )
            SELECT
                {dict_sort}, {_sql_literal(dict_label)}, {_sql_literal(dict_value)},
                {_sql_literal(dict_type)}, '', '', {_sql_literal(is_default)}, '0',
                {_sql_literal(SEED_MARKER)}, current_timestamp, '', NULL, {_sql_literal(remark)}
            WHERE NOT EXISTS (
                SELECT 1
                FROM sys_dict_data
                WHERE dict_type = {_sql_literal(dict_type)}
                  AND dict_value = {_sql_literal(dict_value)}
            )
            """
        )


def _insert_menu_seeds() -> None:
    menu_name, path, route_name, icon, perms = ROOT_MENU_SEED
    _execute(
        f"""
        INSERT INTO sys_menu (
            menu_name, parent_id, order_num, path, component, query, route_name,
            is_frame, is_cache, menu_type, visible, status, perms, icon,
            create_by, create_time, update_by, update_time, remark
        )
        SELECT
            {_sql_literal(menu_name)}, 0, 4, {_sql_literal(path)}, NULL, '',
            {_sql_literal(route_name)}, 1, 0, 'M', '0', '0', {_sql_literal(perms)},
            {_sql_literal(icon)}, {_sql_literal(SEED_MARKER)}, current_timestamp,
            '', NULL, {_sql_literal(SEED_MARKER)}
        WHERE NOT EXISTS (
            SELECT 1
            FROM sys_menu
            WHERE route_name = {_sql_literal(route_name)}
              AND menu_type = 'M'
        )
        """
    )

    for child_name, order_num, child_path, child_route, child_icon, child_perms in CHILD_MENU_SEEDS:
        _execute(
            f"""
            WITH root_menu AS (
                SELECT menu_id
                FROM sys_menu
                WHERE route_name = 'ShotGrid'
                  AND menu_type = 'M'
                ORDER BY (create_by = {_sql_literal(SEED_MARKER)}) DESC, menu_id
                LIMIT 1
            )
            INSERT INTO sys_menu (
                menu_name, parent_id, order_num, path, component, query, route_name,
                is_frame, is_cache, menu_type, visible, status, perms, icon,
                create_by, create_time, update_by, update_time, remark
            )
            SELECT
                {_sql_literal(child_name)}, root_menu.menu_id, {order_num},
                {_sql_literal(child_path)}, NULL, '', {_sql_literal(child_route)},
                1, 0, 'C', '0', '0', {_sql_literal(child_perms)}, {_sql_literal(child_icon)},
                {_sql_literal(SEED_MARKER)}, current_timestamp, '', NULL,
                {_sql_literal(SEED_MARKER)}
            FROM root_menu
            WHERE NOT EXISTS (
                SELECT 1
                FROM sys_menu existing
                WHERE existing.parent_id = root_menu.menu_id
                  AND existing.route_name = {_sql_literal(child_route)}
                  AND existing.menu_type = 'C'
            )
            """
        )

    for parent_route, order_num, button_name, button_perms in PERMISSION_BUTTON_SEEDS:
        _execute(
            f"""
            WITH root_menu AS (
                SELECT menu_id
                FROM sys_menu
                WHERE route_name = 'ShotGrid'
                  AND menu_type = 'M'
                ORDER BY (create_by = {_sql_literal(SEED_MARKER)}) DESC, menu_id
                LIMIT 1
            ),
            parent_menu AS (
                SELECT child.menu_id
                FROM sys_menu child
                JOIN root_menu ON root_menu.menu_id = child.parent_id
                WHERE child.route_name = {_sql_literal(parent_route)}
                  AND child.menu_type = 'C'
                ORDER BY (child.create_by = {_sql_literal(SEED_MARKER)}) DESC, child.menu_id
                LIMIT 1
            )
            INSERT INTO sys_menu (
                menu_name, parent_id, order_num, path, component, query, route_name,
                is_frame, is_cache, menu_type, visible, status, perms, icon,
                create_by, create_time, update_by, update_time, remark
            )
            SELECT
                {_sql_literal(button_name)}, parent_menu.menu_id, {order_num}, '#', '', '', '',
                1, 0, 'F', '0', '0', {_sql_literal(button_perms)}, '#',
                {_sql_literal(SEED_MARKER)}, current_timestamp, '', NULL,
                {_sql_literal(SEED_MARKER)}
            FROM parent_menu
            WHERE NOT EXISTS (
                SELECT 1 FROM sys_menu WHERE perms = {_sql_literal(button_perms)}
            )
            """
        )


def _delete_seed_data() -> None:
    marker = _sql_literal(SEED_MARKER)

    _execute(
        f"""
        DELETE FROM sys_role_menu
        WHERE menu_id IN (
            SELECT menu_id FROM sys_menu WHERE create_by = {marker}
        )
        """
    )
    _execute(f"DELETE FROM sys_menu WHERE create_by = {marker} AND menu_type = 'F'")
    _execute(
        f"""
        DELETE FROM sys_menu seed_menu
        WHERE seed_menu.create_by = {marker}
          AND seed_menu.menu_type = 'C'
          AND NOT EXISTS (
              SELECT 1 FROM sys_menu child WHERE child.parent_id = seed_menu.menu_id
          )
        """
    )
    _execute(
        f"""
        DELETE FROM sys_menu seed_menu
        WHERE seed_menu.create_by = {marker}
          AND seed_menu.menu_type = 'M'
          AND NOT EXISTS (
              SELECT 1 FROM sys_menu child WHERE child.parent_id = seed_menu.menu_id
          )
        """
    )

    _execute(f'DELETE FROM sys_dict_data WHERE create_by = {marker}')
    _execute(
        f"""
        DELETE FROM sys_dict_type seed_type
        WHERE seed_type.create_by = {marker}
          AND NOT EXISTS (
              SELECT 1
              FROM sys_dict_data data
              WHERE data.dict_type = seed_type.dict_type
          )
        """
    )


def upgrade() -> None:
    """创建 Shot Grid 首批结构与平台种子。"""
    # 仓库保留 MySQL 平台兼容链；Shot Grid 使用 JSONB、部分索引等 PostgreSQL 能力，非 PG 明确跳过。
    if not _is_postgresql():
        return

    for statement in SHOT_GRID_DDL:
        _execute(statement)

    _insert_dictionary_seeds()
    _insert_menu_seeds()


def downgrade() -> None:
    """撤销本迁移种子并按依赖逆序删除 Shot Grid 表。"""
    if not _is_postgresql():
        return

    _delete_seed_data()

    for table_name in reversed(SHOT_GRID_TABLES):
        op.drop_table(table_name)

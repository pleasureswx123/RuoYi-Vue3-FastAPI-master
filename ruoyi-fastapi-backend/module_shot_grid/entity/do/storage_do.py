from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)

from config.database import Base
from module_shot_grid.entity.do.base_do import SHOT_GRID_DATETIME, ShotGridMutableAuditMixin


class ShotGridStorageRoot(ShotGridMutableAuditMixin, Base):
    """
    Shot Grid NAS/UNC 根目录白名单表。
    """

    __tablename__ = 'sg_storage_root'

    storage_root_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='存储根ID')
    root_code = Column(String(50), nullable=False, comment='存储根稳定代码')
    root_name = Column(String(120), nullable=False, comment='存储根显示名称')
    protocol = Column(String(20), nullable=False, server_default='smb_unc', comment='存储协议')
    unc_root_path = Column(String(1000), nullable=False, comment='规范化UNC根路径')
    root_path_key = Column(String(1000), nullable=False, comment='大小写不敏感规范化路径键')
    credential_ref = Column(String(200), nullable=True, comment='外部凭据配置引用')
    root_status = Column(String(20), nullable=False, server_default='enabled', comment='存储根状态')
    last_probe_status = Column(String(20), nullable=False, server_default='unknown', comment='最近探测状态')
    last_probe_time = Column(SHOT_GRID_DATETIME, nullable=True, comment='最近探测时间')
    last_error_key = Column(String(100), nullable=True, comment='最近安全错误键')
    last_error_message = Column(String(500), nullable=True, comment='已净化错误摘要')

    __table_args__ = (
        CheckConstraint("btrim(root_code) <> ''", name='ck_sg_storage_root_code'),
        CheckConstraint("btrim(root_name) <> ''", name='ck_sg_storage_root_name'),
        CheckConstraint("protocol in ('smb_unc')", name='ck_sg_storage_root_protocol'),
        CheckConstraint(
            "left(unc_root_path, 2) = '\\\\' and position('..' in unc_root_path) = 0 "
            "and position('*' in unc_root_path) = 0 and position('?' in unc_root_path) = 0 "
            "and position('://' in unc_root_path) = 0",
            name='ck_sg_storage_root_unc_path',
        ),
        CheckConstraint("btrim(root_path_key) <> ''", name='ck_sg_storage_root_path_key'),
        CheckConstraint("root_status in ('enabled', 'disabled')", name='ck_sg_storage_root_status'),
        CheckConstraint(
            "last_probe_status in ('unknown', 'healthy', 'unreachable', 'unwritable')",
            name='ck_sg_storage_root_probe_status',
        ),
        CheckConstraint('lock_version >= 0', name='ck_sg_storage_root_lock_version'),
        CheckConstraint("del_flag in ('0', '2')", name='ck_sg_storage_root_del_flag'),
        Index(
            'uk_sg_storage_root_code_active',
            func.lower(root_code),
            unique=True,
            postgresql_where=text("del_flag = '0'"),
        ),
        Index(
            'uk_sg_storage_root_path_active',
            'root_path_key',
            unique=True,
            postgresql_where=text("del_flag = '0'"),
        ),
        {'comment': 'Shot Grid NAS根目录白名单表'},
    )


class ShotGridProjectStorage(Base):
    """
    Shot Grid 项目与 NAS 的一对一存储绑定表。
    """

    __tablename__ = 'sg_project_storage'

    project_id = Column(
        BigInteger,
        ForeignKey('sg_project.project_id', ondelete='RESTRICT'),
        primary_key=True,
        nullable=False,
        comment='项目ID',
    )
    storage_root_id = Column(
        BigInteger,
        ForeignKey('sg_storage_root.storage_root_id', ondelete='RESTRICT'),
        nullable=False,
        comment='存储根ID',
    )
    root_path_snapshot = Column(String(1000), nullable=False, comment='UNC根路径快照')
    project_type_dir_snapshot = Column(String(120), nullable=False, comment='项目类型目录快照')
    project_dir_name_snapshot = Column(String(240), nullable=False, comment='项目目录名快照')
    project_relative_path = Column(String(1200), nullable=False, comment='相对根目录项目路径')
    project_path_snapshot = Column(String(2000), nullable=False, comment='完整UNC项目路径快照')
    project_path_key = Column(String(2000), nullable=False, comment='大小写不敏感规范化项目路径键')
    storage_status = Column(String(20), nullable=False, server_default='initializing', comment='项目存储状态')
    initialized_time = Column(SHOT_GRID_DATETIME, nullable=True, comment='初始目录就绪时间')
    last_error_key = Column(String(100), nullable=True, comment='最近错误键')
    last_error_message = Column(String(500), nullable=True, comment='已净化错误摘要')
    lock_version = Column(Integer, nullable=False, server_default='0', comment='乐观锁版本')
    create_by = Column(String(64), nullable=False, server_default=text("''"), comment='创建者')
    create_time = Column(SHOT_GRID_DATETIME, nullable=False, default=datetime.now, comment='创建时间')
    update_by = Column(String(64), nullable=False, server_default=text("''"), comment='更新者')
    update_time = Column(
        SHOT_GRID_DATETIME,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        comment='更新时间',
    )

    __table_args__ = (
        UniqueConstraint('storage_root_id', 'project_path_key', name='uk_sg_project_storage_path'),
        CheckConstraint("btrim(root_path_snapshot) <> ''", name='ck_sg_project_storage_root_path'),
        CheckConstraint("btrim(project_type_dir_snapshot) <> ''", name='ck_sg_project_storage_type_dir'),
        CheckConstraint("btrim(project_dir_name_snapshot) <> ''", name='ck_sg_project_storage_project_dir'),
        CheckConstraint("btrim(project_relative_path) <> ''", name='ck_sg_project_storage_relative_path'),
        CheckConstraint("btrim(project_path_snapshot) <> ''", name='ck_sg_project_storage_snapshot'),
        CheckConstraint("btrim(project_path_key) <> ''", name='ck_sg_project_storage_path_key'),
        CheckConstraint(
            "storage_status in ('initializing', 'ready', 'failed', 'migrating')",
            name='ck_sg_project_storage_status',
        ),
        CheckConstraint('lock_version >= 0', name='ck_sg_project_storage_lock_version'),
        {'comment': 'Shot Grid项目NAS存储绑定表'},
    )


class ShotGridStorageOperation(Base):
    """
    Shot Grid NAS 目录操作 Outbox 与执行记录表。
    """

    __tablename__ = 'sg_storage_operation'

    operation_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='目录操作ID')
    project_id = Column(
        BigInteger,
        ForeignKey('sg_project.project_id', ondelete='RESTRICT'),
        nullable=False,
        comment='项目ID',
    )
    operation_type = Column(String(30), nullable=False, comment='操作类型')
    aggregate_type = Column(String(20), nullable=False, comment='目标聚合类型')
    aggregate_id = Column(BigInteger, nullable=False, comment='目标业务对象ID')
    target_relative_path = Column(String(1200), nullable=False, comment='项目根目录内目标相对路径')
    operation_status = Column(String(30), nullable=False, server_default='pending', comment='执行状态')
    idempotency_key = Column(String(100), nullable=False, comment='服务端稳定幂等键')
    attempt_count = Column(Integer, nullable=False, server_default='0', comment='已执行次数')
    next_retry_time = Column(SHOT_GRID_DATETIME, nullable=True, comment='下次允许重试时间')
    # 数据库沿用首版字段名，Python 契约使用更明确的 locked_by/locked_until。
    locked_by = Column('lease_owner', String(100), nullable=True, comment='Worker租约持有者')
    locked_until = Column('lease_until', SHOT_GRID_DATETIME, nullable=True, comment='Worker租约到期时间')
    started_time = Column(SHOT_GRID_DATETIME, nullable=True, comment='开始时间')
    completed_time = Column(SHOT_GRID_DATETIME, nullable=True, comment='成功或最终失败时间')
    last_error_key = Column(String(100), nullable=True, comment='最近错误键')
    last_error_message = Column(String(500), nullable=True, comment='已净化错误摘要')
    create_by = Column(String(64), nullable=False, server_default=text("''"), comment='创建者')
    create_time = Column(SHOT_GRID_DATETIME, nullable=False, default=datetime.now, comment='创建时间')
    update_time = Column(
        SHOT_GRID_DATETIME,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        comment='更新时间',
    )

    __table_args__ = (
        UniqueConstraint('idempotency_key', name='uk_sg_storage_operation_idempotency'),
        CheckConstraint(
            "operation_type in ('initialize_project', 'ensure_episode_directory', "
            "'ensure_shot_directory', 'ensure_asset_directory', 'reconcile_directory')",
            name='ck_sg_storage_operation_type',
        ),
        CheckConstraint(
            "aggregate_type in ('project', 'episode', 'shot', 'asset')",
            name='ck_sg_storage_operation_aggregate_type',
        ),
        CheckConstraint(
            "operation_type = 'reconcile_directory' or "
            "(operation_type = 'initialize_project' and aggregate_type = 'project') or "
            "(operation_type = 'ensure_episode_directory' and aggregate_type = 'episode') or "
            "(operation_type = 'ensure_shot_directory' and aggregate_type = 'shot') or "
            "(operation_type = 'ensure_asset_directory' and aggregate_type = 'asset')",
            name='ck_sg_storage_operation_target_type',
        ),
        CheckConstraint('aggregate_id > 0', name='ck_sg_storage_operation_aggregate_id'),
        CheckConstraint("btrim(target_relative_path) <> ''", name='ck_sg_storage_operation_target_path'),
        CheckConstraint(
            "operation_status in ('pending', 'processing', 'succeeded', 'retry_wait', 'failed', "
            "'compensation_pending', 'compensated', 'compensation_failed')",
            name='ck_sg_storage_operation_status',
        ),
        CheckConstraint("btrim(idempotency_key) <> ''", name='ck_sg_storage_operation_idempotency'),
        CheckConstraint('attempt_count >= 0', name='ck_sg_storage_operation_attempt_count'),
        CheckConstraint(
            '(lease_owner is null and lease_until is null) or '
            "(lease_owner is not null and btrim(lease_owner) <> '' and lease_until is not null)",
            name='ck_sg_storage_operation_lease',
        ),
        Index(
            'idx_sg_storage_operation_status_retry_lease',
            'operation_status',
            'next_retry_time',
            'lease_until',
        ),
        {'comment': 'Shot Grid NAS目录操作Outbox表'},
    )

from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
)

from config.database import Base
from module_shot_grid.entity.do.base_do import SHOT_GRID_DATETIME


class ShotGridFinalDelivery(Base):
    """审核通过后，最佳候选到 NAS FINAL 目录的异步交付记录。"""

    __tablename__ = 'sg_final_delivery'

    final_delivery_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='最终交付ID')
    project_id = Column(BigInteger, nullable=False, comment='项目ID')
    task_id = Column(BigInteger, nullable=False, comment='任务ID')
    version_id = Column(BigInteger, nullable=False, comment='最终版本ID')
    candidate_id = Column(BigInteger, nullable=False, comment='最终候选ID')
    source_file_id = Column(
        String(36),
        ForeignKey('sys_file_info.file_id', ondelete='RESTRICT'),
        nullable=False,
        comment='最佳候选平台文件ID',
    )
    business_file_name = Column(String(255), nullable=False, comment='不可变业务文件名')
    source_nas_relative_path = Column(String(1200), nullable=False, comment='候选源文件NAS相对路径')
    final_nas_relative_path = Column(String(1200), nullable=False, comment='FINAL目录最终文件NAS相对路径')
    manifest_nas_relative_path = Column(String(1200), nullable=False, comment='FINAL.json清单NAS相对路径')
    source_sha256 = Column(CHAR(64), nullable=False, comment='候选源文件SHA-256摘要')
    source_file_size = Column(BigInteger, nullable=False, comment='候选源文件字节数')
    delivery_status = Column(String(20), nullable=False, server_default='pending', comment='最终交付状态')
    attempt_count = Column(Integer, nullable=False, server_default='0', comment='发布尝试次数')
    lease_owner = Column(String(100), nullable=True, comment='Worker租约持有者')
    lease_until = Column(SHOT_GRID_DATETIME, nullable=True, comment='Worker租约到期时间')
    last_error_key = Column(String(100), nullable=True, comment='最近错误键')
    last_error_message = Column(String(500), nullable=True, comment='已净化错误摘要')
    publish_mode = Column(String(20), nullable=True, comment='hardlink、copied或reused')
    approved_by = Column(
        BigInteger,
        ForeignKey('sys_user.user_id', ondelete='RESTRICT'),
        nullable=False,
        comment='审核通过用户ID',
    )
    approved_time = Column(SHOT_GRID_DATETIME, nullable=False, comment='审核通过时间')
    published_time = Column(SHOT_GRID_DATETIME, nullable=True, comment='最终交付完成时间')
    create_time = Column(SHOT_GRID_DATETIME, nullable=False, default=datetime.now, comment='创建时间')
    update_time = Column(
        SHOT_GRID_DATETIME,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        comment='更新时间',
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ['task_id', 'project_id'],
            ['sg_task.task_id', 'sg_task.project_id'],
            name='fk_sg_final_delivery_task_project',
            ondelete='RESTRICT',
        ),
        ForeignKeyConstraint(
            ['version_id', 'project_id'],
            ['sg_version.version_id', 'sg_version.project_id'],
            name='fk_sg_final_delivery_version_project',
            ondelete='RESTRICT',
        ),
        ForeignKeyConstraint(
            ['candidate_id', 'version_id'],
            ['sg_version_candidate.candidate_id', 'sg_version_candidate.version_id'],
            name='fk_sg_final_delivery_candidate_version',
            ondelete='RESTRICT',
        ),
        CheckConstraint("btrim(business_file_name) <> ''", name='ck_sg_final_delivery_business_name'),
        CheckConstraint("btrim(source_nas_relative_path) <> ''", name='ck_sg_final_delivery_source_path'),
        CheckConstraint("btrim(final_nas_relative_path) <> ''", name='ck_sg_final_delivery_final_path'),
        CheckConstraint("btrim(manifest_nas_relative_path) <> ''", name='ck_sg_final_delivery_manifest_path'),
        CheckConstraint(
            'source_nas_relative_path <> final_nas_relative_path '
            'and final_nas_relative_path <> manifest_nas_relative_path',
            name='ck_sg_final_delivery_distinct_paths',
        ),
        CheckConstraint("source_sha256 ~ '^[0-9a-f]{64}$'", name='ck_sg_final_delivery_sha256'),
        CheckConstraint('source_file_size > 0', name='ck_sg_final_delivery_file_size'),
        CheckConstraint(
            "delivery_status in ('pending', 'publishing', 'published', 'failed')",
            name='ck_sg_final_delivery_status',
        ),
        CheckConstraint('attempt_count >= 0', name='ck_sg_final_delivery_attempt_count'),
        CheckConstraint(
            "(delivery_status = 'publishing' and lease_owner is not null and btrim(lease_owner) <> '' "
            "and lease_until is not null) or (delivery_status <> 'publishing' and lease_owner is null "
            'and lease_until is null)',
            name='ck_sg_final_delivery_lease',
        ),
        CheckConstraint(
            "(delivery_status = 'failed' and last_error_key is not null and btrim(last_error_key) <> '' "
            "and last_error_message is not null and btrim(last_error_message) <> '') or "
            "(delivery_status <> 'failed' and last_error_key is null and last_error_message is null)",
            name='ck_sg_final_delivery_error',
        ),
        CheckConstraint(
            "(delivery_status = 'published' and published_time is not null and publish_mode in "
            "('hardlink', 'copied', 'reused')) or "
            "(delivery_status <> 'published' and published_time is null and publish_mode is null)",
            name='ck_sg_final_delivery_result',
        ),
        Index('uk_sg_final_delivery_version', 'version_id', unique=True),
        Index('idx_sg_final_delivery_status_lease_update', 'delivery_status', 'lease_until', 'update_time'),
        Index('idx_sg_final_delivery_project_task', 'project_id', 'task_id'),
        {'comment': 'Shot Grid最终版本NAS交付Outbox与执行记录'},
    )

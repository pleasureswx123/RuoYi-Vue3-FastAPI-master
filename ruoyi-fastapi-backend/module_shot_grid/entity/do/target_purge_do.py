"""镜头及资产永久清理队列，独立于已删除的业务图。"""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, Integer, String, UniqueConstraint

from config.database import Base
from module_shot_grid.entity.do.base_do import SHOT_GRID_DATETIME, SHOT_GRID_JSON


class ShotGridTargetPurge(Base):
    __tablename__ = 'sg_target_purge'

    purge_id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, nullable=False)
    target_kind = Column(String(10), nullable=False)
    target_id = Column(BigInteger, nullable=False)
    target_label = Column(String(240), nullable=False)
    root_path_snapshot = Column(String(1000), nullable=False)
    project_relative_path = Column(String(1200), nullable=False)
    project_path_snapshot = Column(String(2000), nullable=False)
    nas_manifest = Column(SHOT_GRID_JSON, nullable=False)
    file_manifest = Column(SHOT_GRID_JSON, nullable=False)
    purge_status = Column(String(20), nullable=False, server_default='pending')
    attempt_count = Column(Integer, nullable=False, server_default='0')
    next_retry_time = Column(SHOT_GRID_DATETIME)
    lease_owner = Column(String(100))
    lease_until = Column(SHOT_GRID_DATETIME)
    requested_by_user_id = Column(BigInteger, nullable=False)
    requested_by = Column(String(64), nullable=False)
    reason = Column(String(500), nullable=False)
    last_error_key = Column(String(100))
    last_error_message = Column(String(500))
    create_time = Column(SHOT_GRID_DATETIME, nullable=False, default=datetime.now)
    update_time = Column(SHOT_GRID_DATETIME, nullable=False, default=datetime.now)
    completed_time = Column(SHOT_GRID_DATETIME)

    __table_args__ = (
        UniqueConstraint('project_id', 'target_kind', 'target_id', name='uk_sg_target_purge_target'),
        CheckConstraint("target_kind in ('shot','asset')", name='ck_sg_target_purge_kind'),
        CheckConstraint(
            "purge_status in ('pending','processing','retry_wait','succeeded','failed')",
            name='ck_sg_target_purge_status',
        ),
        CheckConstraint('attempt_count >= 0', name='ck_sg_target_purge_attempt'),
        CheckConstraint(
            "btrim(reason) <> '' AND btrim(target_label) <> '' AND btrim(requested_by) <> ''",
            name='ck_sg_target_purge_required',
        ),
        CheckConstraint(
            "jsonb_typeof(nas_manifest) = 'array' AND jsonb_typeof(file_manifest) = 'array'",
            name='ck_sg_target_purge_manifest',
        ),
        CheckConstraint(
            "(purge_status = 'processing') = (lease_owner IS NOT NULL AND lease_until IS NOT NULL)",
            name='ck_sg_target_purge_lease',
        ),
        Index('idx_sg_target_purge_queue', 'purge_status', 'next_retry_time', 'purge_id'),
    )


class ShotGridTargetPurgePath(Base):
    """清理成功前保留目录占用，防止旧清理任务删除新目标。"""

    __tablename__ = 'sg_target_purge_path'
    purge_id = Column(BigInteger, ForeignKey('sg_target_purge.purge_id', ondelete='RESTRICT'), primary_key=True)
    path_key = Column(String(1200), primary_key=True)
    project_id = Column(BigInteger, nullable=False)
    __table_args__ = (
        UniqueConstraint('project_id', 'path_key', name='uk_sg_target_purge_path'),
        CheckConstraint("btrim(path_key) <> ''", name='ck_sg_target_purge_path_required'),
    )

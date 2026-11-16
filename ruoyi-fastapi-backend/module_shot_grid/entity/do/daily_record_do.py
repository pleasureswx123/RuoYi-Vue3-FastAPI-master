"""每日制作平台用量，不作为任务状态或审核事实。"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    text,
)

from config.database import Base
from module_shot_grid.entity.do.base_do import SHOT_GRID_JSON, ShotGridMutableAuditMixin


class ShotGridDailyRecord(ShotGridMutableAuditMixin, Base):
    __tablename__ = 'sg_daily_record'
    record_id = Column(String(36), primary_key=True)
    project_id = Column(BigInteger, nullable=False)
    task_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, ForeignKey('sys_user.user_id'), nullable=False)
    record_date = Column(Date, nullable=False)
    platform = Column(String(80), nullable=False)
    account = Column(String(80), nullable=False, server_default='')
    model = Column(String(80), nullable=False, server_default='')
    media_type = Column(String(10), nullable=False)
    generated_count = Column(Integer, nullable=False)
    actual_points = Column(Numeric(16, 4), nullable=True)
    unit_points = Column(Numeric(16, 4), nullable=True)
    history = Column(SHOT_GRID_JSON, nullable=False, server_default=text("'[]'"))
    __table_args__ = (
        CheckConstraint("media_type IN ('image','video')"),
        CheckConstraint('generated_count BETWEEN 0 AND 1000000'),
        CheckConstraint('actual_points >= 0'),
        CheckConstraint('unit_points >= 0'),
        CheckConstraint('actual_points IS NOT NULL OR unit_points IS NOT NULL'),
        CheckConstraint("btrim(platform) <> ''"),
        CheckConstraint("del_flag IN ('0','2')"),
        CheckConstraint('lock_version >= 0'),
        ForeignKeyConstraint(['task_id', 'project_id'], ['sg_task.task_id', 'sg_task.project_id'], ondelete='CASCADE'),
        Index('ix_sg_daily_scope_date', 'project_id', 'record_date', 'user_id'),
        Index(
            'uq_sg_daily_dimensions',
            'project_id',
            'task_id',
            'user_id',
            'record_date',
            'platform',
            'account',
            'model',
            'media_type',
            unique=True,
            postgresql_where=text("del_flag='0'"),
        ),
    )

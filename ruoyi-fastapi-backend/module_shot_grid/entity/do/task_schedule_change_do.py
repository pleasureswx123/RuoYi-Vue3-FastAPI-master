from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)

from config.database import Base
from module_shot_grid.entity.do.base_do import (
    SHOT_GRID_DATETIME,
    SHOT_GRID_JSON,
    ShotGridCreateAuditMixin,
)


class ShotGridTaskScheduleChange(ShotGridCreateAuditMixin, Base):
    """Shot Grid 任务排期的只追加结构化历史。"""

    __tablename__ = 'sg_task_schedule_change'

    schedule_change_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='排期变更ID')
    project_id = Column(BigInteger, nullable=False, comment='项目ID')
    task_id = Column(BigInteger, nullable=False, comment='任务ID')
    operator_user_id = Column(BigInteger, nullable=False, comment='操作用户ID')
    from_start_time = Column(SHOT_GRID_DATETIME, nullable=True, comment='变更前开始时间')
    from_end_time = Column(SHOT_GRID_DATETIME, nullable=True, comment='变更前结束时间')
    to_start_time = Column(SHOT_GRID_DATETIME, nullable=False, comment='变更后开始时间')
    to_end_time = Column(SHOT_GRID_DATETIME, nullable=False, comment='变更后结束时间')
    change_type = Column(String(20), nullable=False, comment='后端规范化的变更类型')
    operation_source = Column(String(20), nullable=False, comment='操作来源')
    change_reason = Column(String(500), nullable=False, comment='改期原因')
    overlap_acknowledged = Column(Boolean, nullable=False, server_default='false', comment='是否确认人员排期重叠')
    overlap_task_ids = Column(SHOT_GRID_JSON, nullable=False, comment='当次确认的重叠任务ID有序快照')
    task_lock_version_before = Column(Integer, nullable=False, comment='修改前任务乐观锁版本')
    task_lock_version_after = Column(Integer, nullable=False, comment='修改后任务乐观锁版本')
    idempotency_key = Column(String(128), nullable=False, comment='客户端排期命令幂等键')
    request_hash = Column(String(64), nullable=False, comment='规范化排期命令SHA-256')
    result_snapshot = Column(SHOT_GRID_JSON, nullable=False, comment='首次成功响应安全快照')

    __table_args__ = (
        ForeignKeyConstraint(
            ['task_id', 'project_id'],
            ['sg_task.task_id', 'sg_task.project_id'],
            name='fk_sg_task_schedule_change_task_project',
            ondelete='RESTRICT',
        ),
        ForeignKeyConstraint(
            ['operator_user_id'],
            ['sys_user.user_id'],
            name='fk_sg_task_schedule_change_operator',
            ondelete='RESTRICT',
        ),
        UniqueConstraint(
            'task_id',
            'operator_user_id',
            'idempotency_key',
            name='uk_sg_task_schedule_idempotency',
        ),
        CheckConstraint(
            '(from_start_time IS NULL AND from_end_time IS NULL) OR '
            '(from_start_time IS NOT NULL AND from_end_time IS NOT NULL AND from_end_time > from_start_time)',
            name='ck_sg_task_schedule_from_range',
        ),
        CheckConstraint('to_end_time > to_start_time', name='ck_sg_task_schedule_to_range'),
        CheckConstraint(
            "change_type in ('initial', 'move', 'resize_start', 'resize_end', 'dialog')",
            name='ck_sg_task_schedule_change_type',
        ),
        CheckConstraint(
            "operation_source in ('start', 'swimlane', 'gantt', 'dialog')",
            name='ck_sg_task_schedule_operation_source',
        ),
        CheckConstraint("btrim(change_reason) <> ''", name='ck_sg_task_schedule_reason'),
        CheckConstraint(
            'task_lock_version_before >= 0 and task_lock_version_after > task_lock_version_before',
            name='ck_sg_task_schedule_lock_versions',
        ),
        CheckConstraint("btrim(idempotency_key) <> ''", name='ck_sg_task_schedule_idempotency'),
        CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name='ck_sg_task_schedule_request_hash',
        ),
        Index(
            'idx_sg_task_schedule_task_time',
            'project_id',
            'task_id',
            text('create_time DESC'),
            schedule_change_id.desc(),
        ),
        Index(
            'idx_sg_task_schedule_project_time',
            'project_id',
            text('create_time DESC'),
            schedule_change_id.desc(),
        ),
        {'comment': 'Shot Grid任务排期不可变结构化历史表'},
    )

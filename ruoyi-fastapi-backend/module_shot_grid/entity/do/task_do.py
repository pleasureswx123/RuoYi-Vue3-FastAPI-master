from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)

from config.database import Base
from module_shot_grid.entity.do.base_do import ShotGridMutableAuditMixin


class ShotGridTask(ShotGridMutableAuditMixin, Base):
    """
    Shot Grid 制作任务表。
    """

    __tablename__ = 'sg_task'

    task_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='任务ID')
    project_id = Column(BigInteger, nullable=False, comment='项目ID')
    shot_id = Column(BigInteger, nullable=True, comment='镜头ID')
    asset_item_id = Column(BigInteger, nullable=True, comment='资产制作分项ID')
    task_name = Column(String(240), nullable=False, comment='任务名称')
    task_kind = Column(String(20), nullable=False, comment='任务类型')
    assignee_user_id = Column(BigInteger, nullable=False, comment='负责人用户ID')
    task_status = Column(String(20), nullable=False, server_default='not_started', comment='任务状态')
    priority = Column(String(10), nullable=False, server_default='normal', comment='任务优先级')
    due_date = Column(Date, nullable=True, comment='截止日期')
    requirements = Column(Text, nullable=True, comment='制作要求')

    __table_args__ = (
        ForeignKeyConstraint(
            ['project_id', 'assignee_user_id'],
            ['sg_project_member.project_id', 'sg_project_member.user_id'],
            name='fk_sg_task_assignee_member',
            ondelete='RESTRICT',
        ),
        ForeignKeyConstraint(
            ['shot_id', 'project_id'],
            ['sg_shot.shot_id', 'sg_shot.project_id'],
            name='fk_sg_task_shot_project',
            ondelete='RESTRICT',
        ),
        ForeignKeyConstraint(
            ['asset_item_id', 'project_id'],
            ['sg_asset_item.asset_item_id', 'sg_asset_item.project_id'],
            name='fk_sg_task_asset_item_project',
            ondelete='RESTRICT',
        ),
        UniqueConstraint('task_id', 'project_id', name='uk_sg_task_id_project'),
        CheckConstraint("btrim(task_name) <> ''", name='ck_sg_task_name'),
        CheckConstraint(
            "((shot_id is not null and asset_item_id is null and task_kind = 'shot_video') or "
            "(shot_id is null and asset_item_id is not null and task_kind = 'asset_image'))",
            name='ck_sg_task_owner_kind',
        ),
        CheckConstraint(
            "task_status in ('not_started', 'in_progress', 'pending_review', 'revision', 'completed')",
            name='ck_sg_task_status',
        ),
        CheckConstraint(
            "priority in ('low', 'normal', 'high', 'urgent')",
            name='ck_sg_task_priority',
        ),
        CheckConstraint('lock_version >= 0', name='ck_sg_task_lock_version'),
        CheckConstraint("del_flag in ('0', '2')", name='ck_sg_task_del_flag'),
        Index(
            'uk_sg_task_shot',
            'shot_id',
            unique=True,
            postgresql_where=text("shot_id IS NOT NULL AND del_flag = '0'"),
        ),
        Index(
            'uk_sg_task_asset_item',
            'asset_item_id',
            unique=True,
            postgresql_where=text("asset_item_id IS NOT NULL AND del_flag = '0'"),
        ),
        Index(
            'idx_sg_task_project_assignee_status_due',
            'project_id',
            'assignee_user_id',
            'task_status',
            'due_date',
        ),
        Index(
            'idx_sg_task_assignee_status_due',
            'assignee_user_id',
            'task_status',
            'due_date',
            'task_id',
            postgresql_where=text("del_flag = '0'"),
        ),
        {'comment': 'Shot Grid制作任务表'},
    )

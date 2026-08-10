from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)

from config.database import Base
from module_shot_grid.entity.do.base_do import SHOT_GRID_JSON, ShotGridCreateAuditMixin, ShotGridMutableAuditMixin


class ShotGridNote(Base):
    """
    Shot Grid 版本级审核意见表。
    """

    __tablename__ = 'sg_note'

    note_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='审核意见ID')
    project_id = Column(BigInteger, nullable=False, comment='项目ID')
    version_id = Column(BigInteger, nullable=False, comment='版本ID')
    reviewer_user_id = Column(
        BigInteger,
        ForeignKey('sys_user.user_id', ondelete='RESTRICT'),
        nullable=False,
        comment='审核用户ID',
    )
    content = Column(Text, nullable=False, comment='审核意见正文')
    media_time_ms = Column(BigInteger, nullable=True, comment='视频时间点（毫秒）')
    annotations = Column(SHOT_GRID_JSON, nullable=True, comment='结构化批注数组')
    is_mandatory = Column(CHAR(1), nullable=False, server_default='0', comment='是否必须修改')
    note_status = Column(String(20), nullable=False, server_default='open', comment='处理状态')
    create_time = Column(DateTime, nullable=False, default=datetime.now, comment='创建时间')
    update_time = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        comment='更新时间',
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ['version_id', 'project_id'],
            ['sg_version.version_id', 'sg_version.project_id'],
            name='fk_sg_note_version_project',
            ondelete='RESTRICT',
        ),
        UniqueConstraint('note_id', 'project_id', name='uk_sg_note_id_project'),
        CheckConstraint("btrim(content) <> ''", name='ck_sg_note_content'),
        CheckConstraint('media_time_ms is null or media_time_ms >= 0', name='ck_sg_note_media_time'),
        CheckConstraint("is_mandatory in ('0', '1')", name='ck_sg_note_mandatory'),
        CheckConstraint("note_status in ('open', 'resolved')", name='ck_sg_note_status'),
        Index('idx_sg_note_version_status_time', 'version_id', 'note_status', 'create_time'),
        {'comment': 'Shot Grid版本级审核意见表'},
    )


class ShotGridNoteReply(Base):
    """
    Shot Grid 审核意见不可变回复历史表。
    """

    __tablename__ = 'sg_note_reply'

    reply_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='回复ID')
    project_id = Column(BigInteger, nullable=False, comment='项目ID')
    note_id = Column(BigInteger, nullable=False, comment='审核意见ID')
    reply_user_id = Column(
        BigInteger,
        ForeignKey('sys_user.user_id', ondelete='RESTRICT'),
        nullable=False,
        comment='回复用户ID',
    )
    content = Column(Text, nullable=False, comment='回复内容')
    create_time = Column(DateTime, nullable=False, default=datetime.now, comment='回复时间')

    __table_args__ = (
        ForeignKeyConstraint(
            ['note_id', 'project_id'],
            ['sg_note.note_id', 'sg_note.project_id'],
            name='fk_sg_note_reply_note_project',
            ondelete='RESTRICT',
        ),
        CheckConstraint("btrim(content) <> ''", name='ck_sg_note_reply_content'),
        Index('idx_sg_note_reply_note_time', 'note_id', 'create_time', 'reply_id'),
        {'comment': 'Shot Grid审核意见不可变回复历史表'},
    )


class ShotGridReviewAction(Base):
    """
    Shot Grid 审核动作不可变历史表。
    """

    __tablename__ = 'sg_review_action'

    action_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='审核动作ID')
    project_id = Column(BigInteger, nullable=False, comment='项目ID')
    version_id = Column(BigInteger, nullable=False, comment='审核版本ID')
    reviewer_user_id = Column(
        BigInteger,
        ForeignKey('sys_user.user_id', ondelete='RESTRICT'),
        nullable=False,
        comment='操作用户ID',
    )
    action_type = Column(String(20), nullable=False, comment='审核动作')
    from_status = Column(String(20), nullable=False, comment='操作前版本状态')
    to_status = Column(String(20), nullable=False, comment='操作后版本状态')
    reason = Column(String(1000), nullable=True, comment='原因或说明')
    create_time = Column(DateTime, nullable=False, default=datetime.now, comment='操作时间')

    __table_args__ = (
        ForeignKeyConstraint(
            ['version_id', 'project_id'],
            ['sg_version.version_id', 'sg_version.project_id'],
            name='fk_sg_review_action_version_project',
            ondelete='RESTRICT',
        ),
        CheckConstraint("action_type in ('approve', 'reject', 'defer')", name='ck_sg_review_action_type'),
        CheckConstraint(
            "from_status in ('pending_review', 'rejected', 'final')",
            name='ck_sg_review_action_from_status',
        ),
        CheckConstraint(
            "to_status in ('pending_review', 'rejected', 'final')",
            name='ck_sg_review_action_to_status',
        ),
        CheckConstraint(
            "(action_type = 'approve' and from_status = 'pending_review' and to_status = 'final') or "
            "(action_type = 'reject' and from_status = 'pending_review' and to_status = 'rejected') or "
            "(action_type = 'defer' and from_status = 'pending_review' and to_status = 'pending_review')",
            name='ck_sg_review_action_transition',
        ),
        Index('idx_sg_review_action_version_time', 'version_id', 'create_time'),
        {'comment': 'Shot Grid审核动作不可变历史表'},
    )


class ShotGridReviewList(ShotGridMutableAuditMixin, Base):
    """
    Shot Grid 审核单主表。
    """

    __tablename__ = 'sg_review_list'

    review_list_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='审核单ID')
    project_id = Column(
        BigInteger,
        ForeignKey('sg_project.project_id', ondelete='RESTRICT'),
        nullable=False,
        comment='项目ID',
    )
    auto_version_id = Column(BigInteger, nullable=True, comment='自动单版本审核单对应版本ID')
    review_list_name = Column(String(240), nullable=False, comment='审核单名称')
    description = Column(Text, nullable=True, comment='审核单说明')
    review_date = Column(Date, nullable=True, comment='审核日期')
    review_mode = Column(String(20), nullable=False, comment='审核单模式')
    review_status = Column(String(20), nullable=False, comment='审核单状态')

    __table_args__ = (
        ForeignKeyConstraint(
            ['auto_version_id', 'project_id'],
            ['sg_version.version_id', 'sg_version.project_id'],
            name='fk_sg_review_list_auto_version_project',
            ondelete='RESTRICT',
        ),
        CheckConstraint("btrim(review_list_name) <> ''", name='ck_sg_review_list_name'),
        CheckConstraint("review_mode in ('auto_single', 'manual_batch')", name='ck_sg_review_list_mode'),
        CheckConstraint(
            "review_status in ('draft', 'active', 'completed', 'archived')",
            name='ck_sg_review_list_status',
        ),
        CheckConstraint(
            "(review_mode = 'auto_single' and auto_version_id is not null) or "
            "(review_mode = 'manual_batch' and auto_version_id is null)",
            name='ck_sg_review_list_mode_version',
        ),
        CheckConstraint(
            "review_mode <> 'auto_single' or review_status <> 'draft'",
            name='ck_sg_review_list_auto_status',
        ),
        CheckConstraint('lock_version >= 0', name='ck_sg_review_list_lock_version'),
        CheckConstraint("del_flag in ('0', '2')", name='ck_sg_review_list_del_flag'),
        Index(
            'uk_sg_review_list_auto_version',
            'auto_version_id',
            unique=True,
            postgresql_where=text('auto_version_id IS NOT NULL'),
        ),
        Index('idx_sg_review_list_project_status_time', 'project_id', 'review_status', 'create_time'),
        {'comment': 'Shot Grid审核单主表'},
    )


class ShotGridReviewListVersion(ShotGridCreateAuditMixin, Base):
    """
    Shot Grid 审核单与版本的有序关系表。
    """

    __tablename__ = 'sg_review_list_version'

    review_list_id = Column(
        BigInteger,
        ForeignKey('sg_review_list.review_list_id', ondelete='RESTRICT'),
        primary_key=True,
        nullable=False,
        comment='审核单ID',
    )
    version_id = Column(
        BigInteger,
        ForeignKey('sg_version.version_id', ondelete='RESTRICT'),
        primary_key=True,
        nullable=False,
        comment='版本ID',
    )
    sort_order = Column(Integer, nullable=False, comment='审核顺序')

    __table_args__ = (
        UniqueConstraint('review_list_id', 'sort_order', name='uk_sg_review_list_version_sort'),
        CheckConstraint('sort_order >= 0', name='ck_sg_review_list_version_sort_order'),
        Index('idx_sg_review_list_version_version', 'version_id'),
        {'comment': 'Shot Grid审核单与版本有序关系表'},
    )

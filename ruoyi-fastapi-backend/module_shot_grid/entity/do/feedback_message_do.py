from datetime import datetime

from sqlalchemy import BigInteger, Column, ForeignKey, Index, String, UniqueConstraint

from config.database import Base
from module_shot_grid.entity.do.base_do import SHOT_GRID_DATETIME, SHOT_GRID_JSON


class ShotGridFeedbackMessage(Base):
    """正式发送时冻结的个人反馈，同一事件只投递一次。"""

    __tablename__ = 'sg_feedback_message'
    message_id = Column(BigInteger, primary_key=True, autoincrement=True)
    recipient_id = Column(BigInteger, ForeignKey('sys_user.user_id'), nullable=False)
    version_id = Column(BigInteger, ForeignKey('sg_version.version_id', ondelete='CASCADE'), nullable=False)
    event_key = Column(String(80), nullable=False)
    sender_name = Column(String(64), nullable=False)
    issues = Column(SHOT_GRID_JSON, nullable=False)
    created_at = Column(SHOT_GRID_DATETIME, nullable=False, default=datetime.now)
    read_at = Column(SHOT_GRID_DATETIME)
    __table_args__ = (
        UniqueConstraint('recipient_id', 'event_key', name='uk_sg_feedback_message_event'),
        Index('ix_sg_feedback_message_recipient', 'recipient_id', 'message_id'),
    )

from datetime import datetime

from sqlalchemy import CHAR, JSON, Column, DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB

# 默认使用通用 JSON，PostgreSQL 主路径使用 JSONB，避免公共模型绑定单一方言。
SHOT_GRID_JSON = JSON().with_variant(JSONB(), 'postgresql')


class ShotGridMutableAuditMixin:
    """
    Shot Grid 可变业务表通用审计字段。
    """

    create_by = Column(String(64), nullable=False, server_default=text("''"), comment='创建者')
    create_time = Column(DateTime, nullable=False, default=datetime.now, comment='创建时间')
    update_by = Column(String(64), nullable=False, server_default=text("''"), comment='更新者')
    update_time = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        comment='更新时间',
    )
    remark = Column(String(500), nullable=True, comment='备注')
    lock_version = Column(Integer, nullable=False, server_default='0', comment='乐观锁版本')
    del_flag = Column(CHAR(1), nullable=False, server_default='0', comment='删除标志（0正常 2删除）')


class ShotGridCreateAuditMixin:
    """
    Shot Grid 不可变关系或历史表的创建审计字段。
    """

    create_by = Column(String(64), nullable=False, server_default=text("''"), comment='创建者')
    create_time = Column(DateTime, nullable=False, default=datetime.now, comment='创建时间')

from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)

from config.database import Base


class ShotGridImportBatch(Base):
    """
    Shot Grid 镜头或资产 Excel 导入批次表。
    """

    __tablename__ = 'sg_import_batch'

    batch_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='导入批次ID')
    project_id = Column(
        BigInteger,
        ForeignKey('sg_project.project_id', ondelete='RESTRICT'),
        nullable=False,
        comment='项目ID',
    )
    import_type = Column(String(20), nullable=False, comment='导入类型')
    original_file_name = Column(String(255), nullable=False, comment='原始Excel文件名')
    file_sha256 = Column(CHAR(64), nullable=False, comment='原文件SHA-256摘要')
    template_version = Column(String(30), nullable=False, comment='模板版本')
    batch_status = Column(String(20), nullable=False, server_default='previewed', comment='批次状态')
    total_rows = Column(Integer, nullable=False, server_default='0', comment='数据总行数')
    valid_rows = Column(Integer, nullable=False, server_default='0', comment='可导入行数')
    warning_rows = Column(Integer, nullable=False, server_default='0', comment='有警告行数')
    error_rows = Column(Integer, nullable=False, server_default='0', comment='有错误行数')
    committed_rows = Column(Integer, nullable=False, server_default='0', comment='已提交行数')
    preview_token_hash = Column(CHAR(64), nullable=True, comment='预览Token哈希')
    preview_expires_time = Column(DateTime, nullable=True, comment='预览数据到期时间')
    idempotency_key = Column(String(100), nullable=True, comment='正式提交幂等键')
    last_error_key = Column(String(100), nullable=True, comment='最近失败错误键')
    last_error_message = Column(String(500), nullable=True, comment='已净化失败摘要')
    previewed_by = Column(
        BigInteger,
        ForeignKey('sys_user.user_id', ondelete='RESTRICT'),
        nullable=False,
        comment='预检查用户ID',
    )
    committed_by = Column(
        BigInteger,
        ForeignKey('sys_user.user_id', ondelete='RESTRICT'),
        nullable=True,
        comment='正式提交用户ID',
    )
    create_time = Column(DateTime, nullable=False, default=datetime.now, comment='创建时间')
    update_time = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        comment='更新时间',
    )
    committed_time = Column(DateTime, nullable=True, comment='正式提交完成时间')

    __table_args__ = (
        UniqueConstraint('batch_id', 'project_id', name='uk_sg_import_batch_id_project'),
        CheckConstraint("import_type in ('shot', 'asset')", name='ck_sg_import_batch_type'),
        CheckConstraint("btrim(original_file_name) <> ''", name='ck_sg_import_batch_file_name'),
        CheckConstraint("btrim(template_version) <> ''", name='ck_sg_import_batch_template_version'),
        CheckConstraint(
            "batch_status in ('previewed', 'committing', 'committed', 'failed', 'expired')",
            name='ck_sg_import_batch_status',
        ),
        CheckConstraint(
            'total_rows >= 0 and valid_rows >= 0 and warning_rows >= 0 and error_rows >= 0 and committed_rows >= 0',
            name='ck_sg_import_batch_counts_nonnegative',
        ),
        CheckConstraint(
            'valid_rows <= total_rows and warning_rows <= total_rows and '
            'error_rows <= total_rows and committed_rows <= valid_rows',
            name='ck_sg_import_batch_counts_bounds',
        ),
        CheckConstraint(
            "(batch_status in ('committing', 'committed', 'failed') and committed_by is not null "
            "and idempotency_key is not null and btrim(idempotency_key) <> '') or "
            "(batch_status in ('previewed', 'expired') and committed_by is null and idempotency_key is null)",
            name='ck_sg_import_batch_commit_identity',
        ),
        CheckConstraint(
            "(batch_status = 'committed' and committed_time is not null) or "
            "(batch_status <> 'committed' and committed_time is null)",
            name='ck_sg_import_batch_committed_time',
        ),
        Index(
            'uk_sg_import_batch_idempotency',
            'project_id',
            'import_type',
            'committed_by',
            'idempotency_key',
            unique=True,
            postgresql_where=text('idempotency_key IS NOT NULL'),
        ),
        Index(
            'idx_sg_import_batch_project_type_status_time',
            'project_id',
            'import_type',
            'batch_status',
            'create_time',
        ),
        {'comment': 'Shot Grid Excel导入批次表'},
    )

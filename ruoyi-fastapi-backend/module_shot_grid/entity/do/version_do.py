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
    Text,
    UniqueConstraint,
    text,
)

from config.database import Base
from module_shot_grid.entity.do.base_do import SHOT_GRID_DATETIME, SHOT_GRID_JSON, ShotGridCreateAuditMixin


class ShotGridVersionSubmission(Base):
    """
    Shot Grid 版本暂存与 NAS 发布编排表。
    """

    __tablename__ = 'sg_version_submission'

    submission_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='版本提交ID')
    project_id = Column(BigInteger, nullable=False, comment='项目ID')
    task_id = Column(BigInteger, nullable=False, comment='任务ID')
    source_file_id = Column(
        String(36),
        ForeignKey('sys_file_info.file_id', ondelete='RESTRICT'),
        nullable=False,
        comment='平台源文件ID',
    )
    reserved_version_no = Column(Integer, nullable=False, comment='保留版本号')
    generated_at_ms = Column(BigInteger, nullable=False, comment='业务文件名服务端时间戳')
    business_file_name = Column(String(255), nullable=False, comment='不可变业务文件名')
    target_relative_path = Column(String(1200), nullable=False, comment='NAS目标相对路径')
    temporary_relative_path = Column(String(1200), nullable=False, comment='NAS临时文件相对路径')
    source_sha256 = Column(CHAR(64), nullable=False, comment='源文件SHA-256摘要')
    source_file_size = Column(BigInteger, nullable=False, comment='源文件大小')
    changelog = Column(Text, nullable=False, comment='本轮修改说明')
    ai_params = Column(SHOT_GRID_JSON, nullable=True, comment='AI生成参数快照')
    open_issue_snapshot_hash = Column(CHAR(64), nullable=False, comment='提交时未关闭问题集合SHA-256')
    submission_status = Column(String(20), nullable=False, server_default='pending', comment='提交编排状态')
    submitted_by = Column(
        BigInteger,
        ForeignKey('sys_user.user_id', ondelete='RESTRICT'),
        nullable=False,
        comment='提交用户ID',
    )
    idempotency_key = Column(String(100), nullable=False, comment='客户端幂等键')
    attempt_count = Column(Integer, nullable=False, server_default='0', comment='NAS发布尝试次数')
    lease_owner = Column(String(100), nullable=True, comment='Worker租约持有者')
    lease_until = Column(SHOT_GRID_DATETIME, nullable=True, comment='Worker租约到期时间')
    last_error_key = Column(String(100), nullable=True, comment='最近错误键')
    last_error_message = Column(String(500), nullable=True, comment='已净化错误摘要')
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
            name='fk_sg_submission_task_project',
            ondelete='RESTRICT',
        ),
        UniqueConstraint('submission_id', 'project_id', 'task_id', name='uk_sg_submission_id_project_task'),
        UniqueConstraint('task_id', 'reserved_version_no', name='uk_sg_submission_task_version'),
        UniqueConstraint(
            'task_id',
            'submitted_by',
            'idempotency_key',
            name='uk_sg_submission_task_user_idempotency',
        ),
        CheckConstraint('reserved_version_no > 0', name='ck_sg_submission_version_no'),
        CheckConstraint('generated_at_ms > 0', name='ck_sg_submission_generated_at'),
        CheckConstraint("btrim(business_file_name) <> ''", name='ck_sg_submission_business_name'),
        CheckConstraint("btrim(target_relative_path) <> ''", name='ck_sg_submission_target_path'),
        CheckConstraint("btrim(temporary_relative_path) <> ''", name='ck_sg_submission_temp_path'),
        CheckConstraint('temporary_relative_path <> target_relative_path', name='ck_sg_submission_distinct_paths'),
        CheckConstraint('source_file_size >= 0', name='ck_sg_submission_file_size'),
        CheckConstraint("btrim(changelog) <> ''", name='ck_sg_submission_changelog'),
        CheckConstraint(
            "open_issue_snapshot_hash ~ '^[0-9a-f]{64}$'",
            name='ck_sg_submission_issue_snapshot_hash',
        ),
        CheckConstraint(
            "submission_status in ('pending', 'publishing', 'published', 'committing', 'committed', 'failed')",
            name='ck_sg_submission_status',
        ),
        CheckConstraint("btrim(idempotency_key) <> ''", name='ck_sg_submission_idempotency'),
        CheckConstraint('attempt_count >= 0', name='ck_sg_submission_attempt_count'),
        CheckConstraint(
            '(lease_owner is null and lease_until is null) or '
            "(lease_owner is not null and btrim(lease_owner) <> '' and lease_until is not null)",
            name='ck_sg_submission_lease',
        ),
        CheckConstraint(
            "(submission_status in ('publishing', 'committing') "
            "and lease_owner is not null and btrim(lease_owner) <> '' and lease_until is not null) or "
            "(submission_status in ('pending', 'published', 'committed', 'failed') "
            'and lease_owner is null and lease_until is null)',
            name='ck_sg_submission_execution_state',
        ),
        CheckConstraint(
            "(submission_status = 'failed' and last_error_key is not null "
            "and btrim(last_error_key) <> '' and last_error_message is not null "
            "and btrim(last_error_message) <> '') or "
            "(submission_status <> 'failed' and last_error_key is null and last_error_message is null)",
            name='ck_sg_submission_error_state',
        ),
        Index('uk_sg_version_submission_source_file', 'source_file_id', unique=True),
        Index(
            'uk_sg_version_submission_active',
            'task_id',
            unique=True,
            postgresql_where=text(
                "submission_status IN ('pending', 'publishing', 'published', 'committing', 'failed')"
            ),
        ),
        Index('idx_sg_submission_status_lease_update', 'submission_status', 'lease_until', 'update_time'),
        {'comment': 'Shot Grid版本暂存与NAS发布编排表'},
    )


class ShotGridVersionSubmissionFile(Base):
    """一次版本提交中的候选源文件及其 NAS 发布状态。"""

    __tablename__ = 'sg_version_submission_file'

    submission_file_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='提交文件ID')
    submission_id = Column(
        BigInteger,
        ForeignKey('sg_version_submission.submission_id', ondelete='RESTRICT'),
        nullable=False,
        comment='版本提交ID',
    )
    client_file_key = Column(String(100), nullable=False, comment='客户端批次内文件稳定键')
    candidate_no = Column(Integer, nullable=False, comment='本轮候选小编号')
    source_file_id = Column(
        String(36),
        ForeignKey('sys_file_info.file_id', ondelete='RESTRICT'),
        nullable=False,
        comment='平台源文件ID',
    )
    business_file_name = Column(String(255), nullable=False, comment='不可变业务文件名')
    target_relative_path = Column(String(1200), nullable=False, comment='NAS目标相对路径')
    temporary_relative_path = Column(String(1200), nullable=False, comment='NAS临时文件相对路径')
    source_sha256 = Column(CHAR(64), nullable=False, comment='源文件SHA-256摘要')
    source_file_size = Column(BigInteger, nullable=False, comment='源文件大小')
    candidate_note = Column(String(500), nullable=True, comment='制作人候选说明')
    sort_order = Column(Integer, nullable=False, comment='候选展示顺序')
    publish_status = Column(String(20), nullable=False, server_default='pending', comment='候选文件发布状态')
    published_time = Column(SHOT_GRID_DATETIME, nullable=True, comment='NAS发布时间')
    last_error_key = Column(String(100), nullable=True, comment='最近错误键')
    last_error_message = Column(String(500), nullable=True, comment='已净化错误摘要')
    create_time = Column(SHOT_GRID_DATETIME, nullable=False, default=datetime.now, comment='创建时间')
    update_time = Column(
        SHOT_GRID_DATETIME,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        comment='更新时间',
    )

    __table_args__ = (
        UniqueConstraint('submission_id', 'candidate_no', name='uk_sg_submission_file_candidate'),
        UniqueConstraint('submission_id', 'client_file_key', name='uk_sg_submission_file_client_key'),
        UniqueConstraint('submission_file_id', 'submission_id', name='uk_sg_submission_file_id_submission'),
        CheckConstraint("btrim(client_file_key) <> ''", name='ck_sg_submission_file_client_key'),
        CheckConstraint('candidate_no > 0', name='ck_sg_submission_file_candidate_no'),
        CheckConstraint("btrim(business_file_name) <> ''", name='ck_sg_submission_file_business_name'),
        CheckConstraint("btrim(target_relative_path) <> ''", name='ck_sg_submission_file_target_path'),
        CheckConstraint("btrim(temporary_relative_path) <> ''", name='ck_sg_submission_file_temp_path'),
        CheckConstraint(
            'temporary_relative_path <> target_relative_path',
            name='ck_sg_submission_file_distinct_paths',
        ),
        CheckConstraint('source_file_size > 0', name='ck_sg_submission_file_size'),
        CheckConstraint('sort_order >= 0', name='ck_sg_submission_file_sort_order'),
        CheckConstraint(
            "publish_status in ('pending', 'publishing', 'published', 'failed')",
            name='ck_sg_submission_file_publish_status',
        ),
        CheckConstraint(
            "(publish_status = 'published' and published_time is not null "
            'and last_error_key is null and last_error_message is null) or '
            "(publish_status = 'failed' and published_time is null "
            "and last_error_key is not null and btrim(last_error_key) <> '' "
            "and last_error_message is not null and btrim(last_error_message) <> '') or "
            "(publish_status in ('pending', 'publishing') and published_time is null "
            'and last_error_key is null and last_error_message is null)',
            name='ck_sg_submission_file_state',
        ),
        Index('uk_sg_submission_file_source', 'source_file_id', unique=True),
        Index('idx_sg_submission_file_status_order', 'submission_id', 'publish_status', 'sort_order'),
        {'comment': 'Shot Grid版本提交候选文件表'},
    )


class ShotGridVersion(Base):
    """
    Shot Grid 不可覆盖版本主表。
    """

    __tablename__ = 'sg_version'

    version_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='版本ID')
    project_id = Column(BigInteger, nullable=False, comment='项目ID')
    task_id = Column(BigInteger, nullable=False, comment='任务ID')
    submission_id = Column(BigInteger, nullable=False, comment='来源版本提交ID')
    version_no = Column(Integer, nullable=False, comment='任务内版本序号')
    version_status = Column(String(20), nullable=False, server_default='pending_review', comment='版本状态')
    changelog = Column(Text, nullable=False, comment='修改说明')
    ai_params = Column(SHOT_GRID_JSON, nullable=True, comment='AI生成参数快照')
    submitted_by = Column(
        BigInteger,
        ForeignKey('sys_user.user_id', ondelete='RESTRICT'),
        nullable=False,
        comment='提交用户ID',
    )
    submitted_time = Column(SHOT_GRID_DATETIME, nullable=False, default=datetime.now, comment='提交时间')
    generated_at_ms = Column(BigInteger, nullable=False, comment='业务文件名服务端时间戳')
    selected_candidate_id = Column(BigInteger, nullable=True, comment='本轮最佳候选ID，单候选由系统自动设置')
    selected_by = Column(
        BigInteger,
        ForeignKey('sys_user.user_id', ondelete='RESTRICT'),
        nullable=True,
        comment='最近选择候选的审核用户ID',
    )
    selected_time = Column(SHOT_GRID_DATETIME, nullable=True, comment='最近选择候选时间')
    lock_version = Column(Integer, nullable=False, server_default='0', comment='审核乐观锁版本')

    __table_args__ = (
        ForeignKeyConstraint(
            ['submission_id', 'project_id', 'task_id'],
            [
                'sg_version_submission.submission_id',
                'sg_version_submission.project_id',
                'sg_version_submission.task_id',
            ],
            name='fk_sg_version_submission_project_task',
            ondelete='RESTRICT',
        ),
        ForeignKeyConstraint(
            ['selected_candidate_id', 'version_id'],
            ['sg_version_candidate.candidate_id', 'sg_version_candidate.version_id'],
            name='fk_sg_version_selected_candidate',
            ondelete='RESTRICT',
            use_alter=True,
        ),
        UniqueConstraint('version_id', 'project_id', name='uk_sg_version_id_project'),
        UniqueConstraint('task_id', 'version_no', name='uk_sg_version_task_no'),
        UniqueConstraint('submission_id', name='uk_sg_version_submission'),
        CheckConstraint('version_no > 0', name='ck_sg_version_no'),
        CheckConstraint(
            "version_status in ('pending_review', 'rejected', 'final')",
            name='ck_sg_version_status',
        ),
        CheckConstraint("btrim(changelog) <> ''", name='ck_sg_version_changelog'),
        CheckConstraint('generated_at_ms > 0', name='ck_sg_version_generated_at'),
        CheckConstraint(
            '(selected_candidate_id is null and selected_by is null and selected_time is null) or '
            '(selected_candidate_id is not null and '
            '((selected_by is null and selected_time is null) or '
            '(selected_by is not null and selected_time is not null)))',
            name='ck_sg_version_selected_candidate_state',
        ),
        CheckConstraint('lock_version >= 0', name='ck_sg_version_lock_version'),
        Index(
            'uk_sg_version_task_final',
            'task_id',
            unique=True,
            postgresql_where=text("version_status = 'final'"),
        ),
        Index('idx_sg_version_task_version_no', 'task_id', 'version_no'),
        {'comment': 'Shot Grid不可覆盖版本主表'},
    )


class ShotGridVersionCandidate(ShotGridCreateAuditMixin, Base):
    """正式版本轮次中不可变的候选作品。"""

    __tablename__ = 'sg_version_candidate'

    candidate_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='版本候选ID')
    project_id = Column(BigInteger, nullable=False, comment='项目ID')
    version_id = Column(BigInteger, nullable=False, comment='版本轮次ID')
    submission_file_id = Column(BigInteger, nullable=False, comment='来源提交文件ID')
    candidate_no = Column(Integer, nullable=False, comment='本轮候选小编号')
    candidate_note = Column(String(500), nullable=True, comment='制作人候选说明')
    sort_order = Column(Integer, nullable=False, comment='展示顺序')

    __table_args__ = (
        ForeignKeyConstraint(
            ['version_id', 'project_id'],
            ['sg_version.version_id', 'sg_version.project_id'],
            name='fk_sg_candidate_version_project',
            ondelete='RESTRICT',
        ),
        ForeignKeyConstraint(
            ['submission_file_id'],
            ['sg_version_submission_file.submission_file_id'],
            name='fk_sg_candidate_submission_file',
            ondelete='RESTRICT',
        ),
        UniqueConstraint('candidate_id', 'version_id', name='uk_sg_candidate_id_version'),
        UniqueConstraint('candidate_id', 'project_id', name='uk_sg_candidate_id_project'),
        UniqueConstraint('version_id', 'candidate_no', name='uk_sg_candidate_version_no'),
        UniqueConstraint('submission_file_id', name='uk_sg_candidate_submission_file'),
        CheckConstraint('candidate_no > 0', name='ck_sg_candidate_no'),
        CheckConstraint('sort_order >= 0', name='ck_sg_candidate_sort_order'),
        Index('idx_sg_candidate_version_order', 'version_id', 'sort_order', 'candidate_no'),
        {'comment': 'Shot Grid版本候选作品表'},
    )


class ShotGridVersionFile(ShotGridCreateAuditMixin, Base):
    """
    Shot Grid 版本文件用途关系表。
    """

    __tablename__ = 'sg_version_file'

    version_id = Column(
        BigInteger,
        ForeignKey('sg_version.version_id', ondelete='RESTRICT'),
        primary_key=True,
        nullable=False,
        comment='版本ID',
    )
    candidate_id = Column(BigInteger, nullable=False, comment='所属版本候选ID')
    file_id = Column(
        String(36),
        ForeignKey('sys_file_info.file_id', ondelete='RESTRICT'),
        primary_key=True,
        nullable=False,
        comment='平台文件ID',
    )
    file_role = Column(String(30), primary_key=True, nullable=False, comment='文件用途')
    business_file_name = Column(String(255), nullable=False, comment='业务展示和下载文件名')
    nas_relative_path = Column(String(1200), nullable=True, comment='NAS相对项目根目录路径')
    nas_sha256 = Column(CHAR(64), nullable=True, comment='NAS文件SHA-256摘要')
    nas_file_size = Column(BigInteger, nullable=True, comment='NAS文件大小')
    published_time = Column(SHOT_GRID_DATETIME, nullable=True, comment='NAS发布时间')
    is_primary = Column(CHAR(1), nullable=False, server_default='0', comment='是否主文件')
    sort_order = Column(Integer, nullable=False, server_default='0', comment='展示顺序')

    __table_args__ = (
        ForeignKeyConstraint(
            ['candidate_id', 'version_id'],
            ['sg_version_candidate.candidate_id', 'sg_version_candidate.version_id'],
            name='fk_sg_version_file_candidate_version',
            ondelete='RESTRICT',
        ),
        CheckConstraint(
            "file_role in ('review_media', 'thumbnail', 'proxy_media', 'source_original', "
            "'source_repaired', 'first_frame', 'last_frame', 'reference')",
            name='ck_sg_version_file_role',
        ),
        CheckConstraint("btrim(business_file_name) <> ''", name='ck_sg_version_file_business_name'),
        CheckConstraint('nas_file_size is null or nas_file_size >= 0', name='ck_sg_version_file_size'),
        CheckConstraint("is_primary in ('0', '1')", name='ck_sg_version_file_primary'),
        CheckConstraint(
            "is_primary = '0' or file_role = 'review_media'",
            name='ck_sg_version_file_primary_role',
        ),
        CheckConstraint('sort_order >= 0', name='ck_sg_version_file_sort_order'),
        CheckConstraint(
            "not (file_role = 'review_media' and is_primary = '1') or "
            '(nas_relative_path is not null and nas_sha256 is not null and '
            'nas_file_size is not null and published_time is not null)',
            name='ck_sg_version_file_review_nas',
        ),
        Index(
            'uk_sg_version_file_primary_review',
            'candidate_id',
            unique=True,
            postgresql_where=text("file_role = 'review_media' AND is_primary = '1'"),
        ),
        Index(
            'uk_sg_version_file_business_name',
            'business_file_name',
            unique=True,
            postgresql_where=text("file_role = 'review_media' AND is_primary = '1'"),
        ),
        Index('idx_sg_version_file_file', 'file_id'),
        Index('idx_sg_version_file_version_candidate', 'version_id', 'candidate_id', 'sort_order'),
        {'comment': 'Shot Grid版本文件用途关系表'},
    )


class ShotGridMediaDerivation(Base):
    """每个不可覆盖版本候选唯一的媒体派生任务。"""

    __tablename__ = 'sg_media_derivation'

    candidate_id = Column(
        BigInteger,
        primary_key=True,
        nullable=False,
        comment='版本候选ID',
    )
    version_id = Column(BigInteger, nullable=False, comment='版本轮次ID')
    source_file_id = Column(
        String(36),
        ForeignKey('sys_file_info.file_id', ondelete='RESTRICT'),
        nullable=False,
        comment='主审核源文件ID',
    )
    media_kind = Column(String(10), nullable=False, comment='媒体类型')
    derivation_status = Column(String(20), nullable=False, server_default='pending', comment='派生状态')
    attempt_count = Column(Integer, nullable=False, server_default='0', comment='尝试次数')
    lease_owner = Column(String(100), nullable=True, comment='Worker租约持有者')
    lease_until = Column(SHOT_GRID_DATETIME, nullable=True, comment='Worker租约到期时间')
    next_retry_time = Column(SHOT_GRID_DATETIME, nullable=True, comment='下次重试时间')
    last_error_key = Column(String(100), nullable=True, comment='最近错误键')
    last_error_message = Column(String(500), nullable=True, comment='已净化错误摘要')
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
            ['candidate_id', 'version_id'],
            ['sg_version_candidate.candidate_id', 'sg_version_candidate.version_id'],
            name='fk_sg_media_derivation_candidate_version',
            ondelete='RESTRICT',
        ),
        CheckConstraint("media_kind in ('image', 'video')", name='ck_sg_media_derivation_kind'),
        CheckConstraint(
            "derivation_status in ('pending', 'processing', 'completed', 'failed')",
            name='ck_sg_media_derivation_status',
        ),
        CheckConstraint('attempt_count >= 0', name='ck_sg_media_derivation_attempt_count'),
        CheckConstraint(
            "(derivation_status = 'processing' and lease_owner is not null and lease_until is not null) or "
            "(derivation_status <> 'processing' and lease_owner is null and lease_until is null)",
            name='ck_sg_media_derivation_lease',
        ),
        CheckConstraint(
            "(derivation_status = 'failed' and last_error_key is not null and last_error_message is not null) or "
            "(derivation_status <> 'failed' and last_error_key is null and last_error_message is null)",
            name='ck_sg_media_derivation_error',
        ),
        Index('idx_sg_media_derivation_due', 'derivation_status', 'next_retry_time', 'update_time'),
        Index('idx_sg_media_derivation_version', 'version_id'),
        {'comment': 'Shot Grid媒体派生任务'},
    )

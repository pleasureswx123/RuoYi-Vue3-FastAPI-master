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
from module_shot_grid.entity.do.base_do import (
    SHOT_GRID_DATETIME,
    ShotGridCreateAuditMixin,
    ShotGridMutableAuditMixin,
)


class ShotGridAsset(ShotGridMutableAuditMixin, Base):
    """
    Shot Grid 资产主表。
    """

    __tablename__ = 'sg_asset'

    asset_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='资产ID')
    project_id = Column(
        BigInteger,
        ForeignKey('sg_project.project_id', ondelete='RESTRICT'),
        nullable=False,
        comment='项目ID',
    )
    asset_name = Column(String(200), nullable=False, comment='资产名称')
    asset_name_key = Column(String(200), nullable=False, comment='资产名称规范化匹配键')
    asset_type = Column(String(20), nullable=False, comment='资产类型')
    storage_dir_name = Column(String(240), nullable=False, comment='NAS资产子目录名快照')
    storage_path_key = Column(String(500), nullable=False, comment='项目内规范化存储路径键')
    description = Column(Text, nullable=True, comment='资产说明')
    sort_order = Column(Integer, nullable=False, server_default='0', comment='项目内排序')
    lifecycle_status = Column(String(20), nullable=False, server_default='active', comment='生命周期状态')

    __table_args__ = (
        UniqueConstraint('asset_id', 'project_id', name='uk_sg_asset_id_project'),
        UniqueConstraint('asset_id', 'project_id', 'asset_type', name='uk_sg_asset_id_project_type'),
        CheckConstraint("btrim(asset_name) <> ''", name='ck_sg_asset_name'),
        CheckConstraint("btrim(asset_name_key) <> ''", name='ck_sg_asset_name_key'),
        CheckConstraint(
            "asset_type in ('Character', 'Environment', 'Prop')",
            name='ck_sg_asset_type',
        ),
        CheckConstraint("btrim(storage_dir_name) <> ''", name='ck_sg_asset_storage_dir'),
        CheckConstraint("btrim(storage_path_key) <> ''", name='ck_sg_asset_storage_key'),
        CheckConstraint('sort_order >= 0', name='ck_sg_asset_sort_order'),
        CheckConstraint("lifecycle_status in ('active', 'archived')", name='ck_sg_asset_lifecycle'),
        CheckConstraint('lock_version >= 0', name='ck_sg_asset_lock_version'),
        CheckConstraint("del_flag in ('0', '2')", name='ck_sg_asset_del_flag'),
        Index(
            'uk_sg_asset_name_active',
            'project_id',
            'asset_type',
            'asset_name_key',
            unique=True,
            postgresql_where=text("lifecycle_status = 'active' AND del_flag = '0'"),
        ),
        Index(
            'uk_sg_asset_storage_path',
            'project_id',
            'storage_path_key',
            unique=True,
            postgresql_where=text("del_flag = '0'"),
        ),
        Index(
            'idx_sg_asset_project_type_lifecycle_sort',
            'project_id',
            'asset_type',
            'lifecycle_status',
            'sort_order',
        ),
        {'comment': 'Shot Grid资产主表'},
    )


class ShotGridAssetItem(ShotGridMutableAuditMixin, Base):
    """
    Shot Grid 资产制作分项表。
    """

    __tablename__ = 'sg_asset_item'

    asset_item_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='制作分项ID')
    project_id = Column(BigInteger, nullable=False, comment='项目ID')
    asset_id = Column(BigInteger, nullable=False, comment='资产ID')
    production_item = Column(String(240), nullable=True, comment='制作分项名称')
    production_item_key = Column(String(240), nullable=True, comment='制作分项规范化匹配键')
    description = Column(Text, nullable=True, comment='制作分项描述')
    sort_order = Column(Integer, nullable=False, server_default='0', comment='资产内稳定顺序')
    source_import_batch_id = Column(BigInteger, nullable=True, comment='来源资产导入批次ID')
    source_row_no = Column(Integer, nullable=True, comment='来源Sheet明细行号')
    import_row_key = Column(CHAR(64), nullable=True, comment='导入行幂等键')
    lifecycle_status = Column(String(20), nullable=False, server_default='active', comment='生命周期状态')

    __table_args__ = (
        ForeignKeyConstraint(
            ['asset_id', 'project_id'],
            ['sg_asset.asset_id', 'sg_asset.project_id'],
            name='fk_sg_asset_item_asset_project',
            ondelete='RESTRICT',
        ),
        ForeignKeyConstraint(
            ['source_import_batch_id', 'project_id'],
            ['sg_import_batch.batch_id', 'sg_import_batch.project_id'],
            name='fk_sg_asset_item_import_project',
            ondelete='RESTRICT',
        ),
        UniqueConstraint('asset_item_id', 'project_id', name='uk_sg_asset_item_id_project'),
        CheckConstraint(
            '((production_item is null and production_item_key is null) or '
            "(production_item is not null and btrim(production_item) <> '' and production_item_key is not null and "
            "btrim(production_item_key) <> ''))",
            name='ck_sg_asset_item_name_key',
        ),
        CheckConstraint('sort_order >= 0', name='ck_sg_asset_item_sort_order'),
        CheckConstraint('source_row_no is null or source_row_no > 0', name='ck_sg_asset_item_source_row'),
        CheckConstraint(
            '(source_import_batch_id is null and source_row_no is null and import_row_key is null) or '
            '(source_import_batch_id is not null and source_row_no is not null and import_row_key is not null)',
            name='ck_sg_asset_item_import_source',
        ),
        CheckConstraint("lifecycle_status in ('active', 'archived')", name='ck_sg_asset_item_lifecycle'),
        CheckConstraint('lock_version >= 0', name='ck_sg_asset_item_lock_version'),
        CheckConstraint("del_flag in ('0', '2')", name='ck_sg_asset_item_del_flag'),
        Index(
            'uk_sg_asset_item_name_active',
            'asset_id',
            'production_item_key',
            unique=True,
            postgresql_where=text("production_item_key IS NOT NULL AND lifecycle_status = 'active' AND del_flag = '0'"),
        ),
        Index(
            'uk_sg_asset_item_import_row',
            'project_id',
            'import_row_key',
            unique=True,
            postgresql_where=text("import_row_key IS NOT NULL AND del_flag = '0'"),
        ),
        Index(
            'idx_sg_asset_item_project_asset_lifecycle_sort',
            'project_id',
            'asset_id',
            'lifecycle_status',
            'sort_order',
        ),
        {'comment': 'Shot Grid资产制作分项表'},
    )


class ShotGridShotAsset(ShotGridCreateAuditMixin, Base):
    """
    Shot Grid 镜头与资产关系表。
    """

    __tablename__ = 'sg_shot_asset'

    project_id = Column(BigInteger, nullable=False, comment='项目ID')
    shot_id = Column(BigInteger, primary_key=True, nullable=False, comment='镜头ID')
    asset_id = Column(BigInteger, primary_key=True, nullable=False, comment='资产ID')
    usage_note = Column(String(500), nullable=True, comment='使用说明')

    __table_args__ = (
        ForeignKeyConstraint(
            ['shot_id', 'project_id'],
            ['sg_shot.shot_id', 'sg_shot.project_id'],
            name='fk_sg_shot_asset_shot_project',
            ondelete='RESTRICT',
        ),
        ForeignKeyConstraint(
            ['asset_id', 'project_id'],
            ['sg_asset.asset_id', 'sg_asset.project_id'],
            name='fk_sg_shot_asset_asset_project',
            ondelete='RESTRICT',
        ),
        Index('idx_sg_shot_asset_project_asset', 'project_id', 'asset_id'),
        {'comment': 'Shot Grid镜头与资产关系表'},
    )


class ShotGridShotAssetRequirement(Base):
    """
    Shot Grid 镜头资产待匹配需求表。
    """

    __tablename__ = 'sg_shot_asset_requirement'

    requirement_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='需求ID')
    project_id = Column(BigInteger, nullable=False, comment='项目ID')
    shot_id = Column(BigInteger, nullable=False, comment='来源镜头ID')
    asset_type = Column(String(20), nullable=False, comment='资产类型')
    raw_name = Column(String(200), nullable=False, comment='Excel原始资产名称')
    normalized_name = Column(String(200), nullable=False, comment='规范化匹配名称')
    resolution_status = Column(String(20), nullable=False, server_default='pending', comment='解析状态')
    asset_id = Column(BigInteger, nullable=True, comment='匹配资产ID')
    source_import_batch_id = Column(BigInteger, nullable=False, comment='来源镜头导入批次ID')
    resolved_by = Column(
        BigInteger,
        ForeignKey('sys_user.user_id', ondelete='RESTRICT'),
        nullable=True,
        comment='人工解决用户ID',
    )
    resolved_time = Column(SHOT_GRID_DATETIME, nullable=True, comment='解决时间')
    resolution_reason = Column(String(500), nullable=True, comment='解决或忽略原因')
    create_by = Column(String(64), nullable=False, server_default=text("''"), comment='创建者')
    create_time = Column(SHOT_GRID_DATETIME, nullable=False, default=datetime.now, comment='创建时间')
    update_by = Column(String(64), nullable=True, comment='更新者')
    update_time = Column(SHOT_GRID_DATETIME, nullable=True, comment='更新时间')

    __table_args__ = (
        ForeignKeyConstraint(
            ['shot_id', 'project_id'],
            ['sg_shot.shot_id', 'sg_shot.project_id'],
            name='fk_sg_requirement_shot_project',
            ondelete='RESTRICT',
        ),
        ForeignKeyConstraint(
            ['asset_id', 'project_id', 'asset_type'],
            ['sg_asset.asset_id', 'sg_asset.project_id', 'sg_asset.asset_type'],
            name='fk_sg_requirement_asset_project_type',
            ondelete='RESTRICT',
        ),
        ForeignKeyConstraint(
            ['source_import_batch_id', 'project_id'],
            ['sg_import_batch.batch_id', 'sg_import_batch.project_id'],
            name='fk_sg_requirement_import_project',
            ondelete='RESTRICT',
        ),
        CheckConstraint(
            "asset_type in ('Character', 'Environment', 'Prop')",
            name='ck_sg_requirement_asset_type',
        ),
        CheckConstraint("btrim(raw_name) <> ''", name='ck_sg_requirement_raw_name'),
        CheckConstraint("btrim(normalized_name) <> ''", name='ck_sg_requirement_normalized_name'),
        CheckConstraint(
            "resolution_status in ('pending', 'matched', 'conflict', 'ignored')",
            name='ck_sg_requirement_status',
        ),
        CheckConstraint(
            "(resolution_status = 'matched' and asset_id is not null) or "
            "(resolution_status <> 'matched' and asset_id is null)",
            name='ck_sg_requirement_matched_asset',
        ),
        Index(
            'uk_sg_shot_asset_requirement_key',
            'shot_id',
            'asset_type',
            'normalized_name',
            unique=True,
        ),
        Index(
            'idx_sg_requirement_project_status_type_name',
            'project_id',
            'resolution_status',
            'asset_type',
            'normalized_name',
        ),
        {'comment': 'Shot Grid镜头资产待匹配需求表'},
    )

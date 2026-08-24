from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)

from config.database import Base
from module_shot_grid.entity.do.base_do import (
    SHOT_GRID_DATETIME,
    ShotGridCreateAuditMixin,
    ShotGridMutableAuditMixin,
)


class ShotGridProject(ShotGridMutableAuditMixin, Base):
    """
    Shot Grid 项目主表。
    """

    __tablename__ = 'sg_project'

    project_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='项目ID')
    project_code = Column(String(12), nullable=False, comment='项目代号及产出文件前缀')
    project_name = Column(String(200), nullable=False, comment='项目名称')
    project_type = Column(
        String(50),
        nullable=False,
        server_default='ai_short_film',
        comment='项目类型代码',
    )
    project_description = Column(Text, nullable=True, comment='项目描述')
    aspect_ratio = Column(String(20), nullable=False, server_default='16:9', comment='画幅')
    planned_duration_ms = Column(BigInteger, nullable=True, comment='计划总时长（毫秒）')
    delivery_date = Column(Date, nullable=True, comment='交付日期')
    project_status = Column(String(20), nullable=False, server_default='preparing', comment='项目状态')
    current_phase = Column(String(50), nullable=False, server_default='planning', comment='当前阶段')

    __table_args__ = (
        CheckConstraint("project_code ~ '^[A-Z0-9]{2,12}$'", name='ck_sg_project_code_format'),
        CheckConstraint("project_type in ('ai_short_film')", name='ck_sg_project_type'),
        CheckConstraint(
            "aspect_ratio in ('16:9', '21:9', '2.39:1', '9:16', '1:1')",
            name='ck_sg_project_aspect_ratio',
        ),
        CheckConstraint(
            "project_status in ('preparing', 'active', 'completed', 'archived')",
            name='ck_sg_project_status',
        ),
        CheckConstraint(
            "current_phase in ('planning', 'asset_production', 'shot_production', 'review', 'delivery', 'completed')",
            name='ck_sg_project_phase',
        ),
        CheckConstraint('planned_duration_ms is null or planned_duration_ms >= 0', name='ck_sg_project_duration'),
        CheckConstraint('lock_version >= 0', name='ck_sg_project_lock_version'),
        CheckConstraint("del_flag in ('0', '2')", name='ck_sg_project_del_flag'),
        Index(
            'uk_sg_project_code_active',
            func.lower(project_code),
            unique=True,
            postgresql_where=text("project_status <> 'archived' AND del_flag = '0'"),
        ),
        {'comment': 'Shot Grid项目主表'},
    )


class ShotGridProjectMember(Base):
    """
    Shot Grid 项目成员表。
    """

    __tablename__ = 'sg_project_member'

    project_id = Column(
        BigInteger,
        ForeignKey('sg_project.project_id', ondelete='RESTRICT'),
        primary_key=True,
        nullable=False,
        comment='项目ID',
    )
    user_id = Column(
        BigInteger,
        ForeignKey('sys_user.user_id', ondelete='RESTRICT'),
        primary_key=True,
        nullable=False,
        comment='用户ID',
    )
    project_role = Column(String(20), nullable=False, comment='项目角色')
    producer_code = Column(String(12), nullable=True, comment='制作人文件名缩写')
    member_status = Column(String(20), nullable=False, server_default='active', comment='成员状态')
    joined_time = Column(SHOT_GRID_DATETIME, nullable=False, default=datetime.now, comment='加入时间')
    removed_by = Column(
        BigInteger,
        ForeignKey('sys_user.user_id', name='fk_sg_project_member_removed_by', ondelete='RESTRICT'),
        nullable=True,
        comment='移除操作用户ID',
    )
    removed_time = Column(SHOT_GRID_DATETIME, nullable=True, comment='移除时间')
    create_by = Column(String(64), nullable=False, server_default=text("''"), comment='创建者')
    create_time = Column(SHOT_GRID_DATETIME, nullable=False, default=datetime.now, comment='创建时间')

    __table_args__ = (
        CheckConstraint("project_role in ('director', 'creator')", name='ck_sg_project_member_role'),
        CheckConstraint(
            "producer_code is null or producer_code ~ '^[A-Z0-9]{2,12}$'",
            name='ck_sg_project_member_producer_code',
        ),
        CheckConstraint(
            "member_status in ('active', 'removed')",
            name='ck_sg_project_member_status',
        ),
        CheckConstraint(
            "(member_status = 'active' and removed_by is null and removed_time is null) or "
            "(member_status = 'removed' and removed_by is not null and removed_time is not null)",
            name='ck_sg_project_member_removal',
        ),
        Index(
            'uk_sg_project_member_producer_code',
            project_id,
            func.lower(producer_code),
            unique=True,
            postgresql_where=text("producer_code IS NOT NULL AND member_status = 'active'"),
        ),
        Index('idx_sg_project_member_user_project', 'user_id', 'project_id'),
        {'comment': 'Shot Grid项目成员表'},
    )


class ShotGridManagedUserRole(ShotGridCreateAuditMixin, Base):
    """由 Shot Grid 创建并负责生命周期回收的平台用户角色关系。"""

    __tablename__ = 'sg_managed_user_role'

    user_id = Column(BigInteger, primary_key=True, nullable=False, comment='平台用户ID')
    role_id = Column(BigInteger, primary_key=True, nullable=False, comment='平台角色ID')

    __table_args__ = (
        ForeignKeyConstraint(
            ['user_id', 'role_id'],
            ['sys_user_role.user_id', 'sys_user_role.role_id'],
            name='fk_sg_managed_user_role_user_role',
            ondelete='CASCADE',
        ),
        {'comment': 'Shot Grid受管平台用户角色来源标记'},
    )


class ShotGridEpisode(ShotGridMutableAuditMixin, Base):
    """
    Shot Grid 集主表。
    """

    __tablename__ = 'sg_episode'

    episode_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='集ID')
    project_id = Column(
        BigInteger,
        ForeignKey('sg_project.project_id', ondelete='RESTRICT'),
        nullable=False,
        comment='项目ID',
    )
    episode_no = Column(Integer, nullable=False, comment='集号')
    storage_dir_name = Column(String(32), nullable=False, comment='NAS集目录快照')
    episode_name = Column(String(200), nullable=True, comment='集名称')
    description = Column(Text, nullable=True, comment='集说明')
    sort_order = Column(Integer, nullable=False, server_default='0', comment='项目内排序')
    lifecycle_status = Column(String(20), nullable=False, server_default='active', comment='生命周期状态')

    __table_args__ = (
        UniqueConstraint('episode_id', 'project_id', name='uk_sg_episode_id_project'),
        CheckConstraint('episode_no > 0', name='ck_sg_episode_no'),
        CheckConstraint('sort_order >= 0', name='ck_sg_episode_sort_order'),
        CheckConstraint("lifecycle_status in ('active', 'archived')", name='ck_sg_episode_lifecycle'),
        CheckConstraint('lock_version >= 0', name='ck_sg_episode_lock_version'),
        CheckConstraint("del_flag in ('0', '2')", name='ck_sg_episode_del_flag'),
        Index(
            'uk_sg_episode_no_active',
            'project_id',
            'episode_no',
            unique=True,
            postgresql_where=text("del_flag = '0'"),
        ),
        Index('idx_sg_episode_project_lifecycle_sort', 'project_id', 'lifecycle_status', 'sort_order'),
        {'comment': 'Shot Grid集主表'},
    )


class ShotGridScene(ShotGridMutableAuditMixin, Base):
    """
    Shot Grid 场次主表。
    """

    __tablename__ = 'sg_scene'

    scene_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='场次ID')
    project_id = Column(BigInteger, nullable=False, comment='项目ID')
    episode_id = Column(BigInteger, nullable=False, comment='集ID')
    scene_no = Column(Integer, nullable=False, comment='集内场次号')
    scene_name = Column(String(200), nullable=True, comment='场次名称')
    description = Column(Text, nullable=True, comment='场次描述')
    sort_order = Column(Integer, nullable=False, server_default='0', comment='集内排序')
    lifecycle_status = Column(String(20), nullable=False, server_default='active', comment='生命周期状态')

    __table_args__ = (
        ForeignKeyConstraint(
            ['episode_id', 'project_id'],
            ['sg_episode.episode_id', 'sg_episode.project_id'],
            name='fk_sg_scene_episode_project',
            ondelete='RESTRICT',
        ),
        UniqueConstraint('scene_id', 'project_id', 'episode_id', name='uk_sg_scene_id_project_episode'),
        CheckConstraint('scene_no >= 0', name='ck_sg_scene_no'),
        CheckConstraint(
            "(scene_no = 0 and scene_name is not null and scene_name = '序') or "
            "(scene_no > 0 and (scene_name is null or scene_name <> '序'))",
            name='ck_sg_scene_prologue_name',
        ),
        CheckConstraint('sort_order >= 0', name='ck_sg_scene_sort_order'),
        CheckConstraint("lifecycle_status in ('active', 'archived')", name='ck_sg_scene_lifecycle'),
        CheckConstraint('lock_version >= 0', name='ck_sg_scene_lock_version'),
        CheckConstraint("del_flag in ('0', '2')", name='ck_sg_scene_del_flag'),
        Index(
            'uk_sg_scene_no_active',
            'episode_id',
            'scene_no',
            unique=True,
            postgresql_where=text("del_flag = '0'"),
        ),
        Index('idx_sg_scene_episode_lifecycle_sort', 'episode_id', 'lifecycle_status', 'sort_order'),
        {'comment': 'Shot Grid场次主表'},
    )


class ShotGridShot(ShotGridMutableAuditMixin, Base):
    """
    Shot Grid 镜头主表。
    """

    __tablename__ = 'sg_shot'

    shot_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='镜头ID')
    project_id = Column(BigInteger, nullable=False, comment='项目ID')
    episode_id = Column(BigInteger, nullable=False, comment='集ID')
    scene_id = Column(BigInteger, nullable=False, comment='场次ID')
    shot_no = Column(Integer, nullable=False, comment='场内镜头号')
    storage_dir_name = Column(
        String(32),
        nullable=True,
        comment='开始制作时冻结的含场次代码NAS镜头目录快照；未开始时为空',
    )
    duration_ms = Column(BigInteger, nullable=False, server_default='0', comment='镜头时长（毫秒）')
    shot_size = Column(String(40), nullable=True, comment='景别')
    camera_position = Column(String(100), nullable=True, comment='机位')
    camera_movement = Column(String(100), nullable=True, comment='镜头运动')
    focal_length = Column(String(50), nullable=True, comment='焦段原始文本')
    description = Column(Text, nullable=False, comment='镜头描述')
    dialogue = Column(Text, nullable=True, comment='台词或对白')
    sound_effect = Column(Text, nullable=True, comment='音效说明')
    color_reference = Column(Text, nullable=True, comment='色调参考说明')
    sort_order = Column(Integer, nullable=False, server_default='0', comment='兼容排序键，固定等于场内镜头号乘10')
    lifecycle_status = Column(String(20), nullable=False, server_default='active', comment='生命周期状态')

    __table_args__ = (
        ForeignKeyConstraint(
            ['scene_id', 'project_id', 'episode_id'],
            ['sg_scene.scene_id', 'sg_scene.project_id', 'sg_scene.episode_id'],
            name='fk_sg_shot_scene_project_episode',
            ondelete='RESTRICT',
        ),
        UniqueConstraint('shot_id', 'project_id', name='uk_sg_shot_id_project'),
        CheckConstraint('shot_no > 0', name='ck_sg_shot_no'),
        CheckConstraint('duration_ms >= 0', name='ck_sg_shot_duration'),
        CheckConstraint('sort_order >= 0', name='ck_sg_shot_sort_order'),
        CheckConstraint("lifecycle_status in ('active', 'archived')", name='ck_sg_shot_lifecycle'),
        CheckConstraint('lock_version >= 0', name='ck_sg_shot_lock_version'),
        CheckConstraint("del_flag in ('0', '2')", name='ck_sg_shot_del_flag'),
        Index(
            'uk_sg_shot_scene_no_active',
            'scene_id',
            'shot_no',
            unique=True,
            postgresql_where=text("del_flag = '0'"),
        ),
        Index(
            'idx_sg_shot_project_episode_scene_lifecycle_sort',
            'project_id',
            'episode_id',
            'scene_id',
            'lifecycle_status',
            'sort_order',
        ),
        {'comment': 'Shot Grid镜头主表'},
    )

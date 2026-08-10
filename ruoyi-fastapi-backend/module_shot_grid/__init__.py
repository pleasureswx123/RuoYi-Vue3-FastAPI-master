"""Shot Grid 业务模块。"""

from config.env import DataBaseConfig

SHOT_GRID_DATABASE_SUPPORTED = DataBaseConfig.db_type == 'postgresql'

if SHOT_GRID_DATABASE_SUPPORTED:
    # 路由自动注册发生在平台 ``create_all`` 之前；在包加载时显式注册领域元数据，
    # 避免只有 Alembic 文件扫描能发现模型、实际应用启动却漏建元数据的情况。
    from module_shot_grid.entity import do as _shot_grid_do  # noqa: F401

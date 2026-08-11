from importlib.util import find_spec
from urllib.parse import quote_plus

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config.env import DataBaseConfig

DATABASE_DRIVERS = {
    'mysql': (('asyncmy', '异步'), ('pymysql', '同步')),
    'postgresql': (('asyncpg', '异步'), ('psycopg2', '同步')),
}


def validate_database_drivers() -> None:
    """在创建 Engine 前校验当前数据库模式所需驱动，并给出可执行的安装提示。"""
    missing_drivers = [
        f'{driver}（{usage}）'
        for driver, usage in DATABASE_DRIVERS[DataBaseConfig.db_type]
        if find_spec(driver) is None
    ]
    if not missing_drivers:
        return

    if DataBaseConfig.db_type == 'postgresql':
        install_command = 'python -m pip install -r requirements-pg.txt'
        test_command = 'python -m pip install -r requirements-test-pg.txt'
    else:
        install_command = 'python -m pip install -r requirements.txt'
        test_command = install_command
    missing_text = '、'.join(missing_drivers)
    raise RuntimeError(
        f'数据库模式 {DataBaseConfig.db_type!r} 缺少驱动：{missing_text}。'
        f'运行环境请执行 `{install_command}`；测试环境请执行 `{test_command}`。'
    )


def build_async_sqlalchemy_database_url() -> str:
    """
    构建异步 SQLAlchemy 数据库连接 URL

    :return: 异步 SQLAlchemy 数据库连接 URL
    """
    if DataBaseConfig.db_type == 'postgresql':
        return (
            f'postgresql+asyncpg://{DataBaseConfig.db_username}:{quote_plus(DataBaseConfig.db_password)}@'
            f'{DataBaseConfig.db_host}:{DataBaseConfig.db_port}/{DataBaseConfig.db_database}'
        )
    return (
        f'mysql+asyncmy://{DataBaseConfig.db_username}:{quote_plus(DataBaseConfig.db_password)}@'
        f'{DataBaseConfig.db_host}:{DataBaseConfig.db_port}/{DataBaseConfig.db_database}'
    )


validate_database_drivers()

ASYNC_SQLALCHEMY_DATABASE_URL = build_async_sqlalchemy_database_url()


def build_sync_sqlalchemy_database_url() -> str:
    """
    构建同步 SQLAlchemy 数据库连接 URL

    :return: 同步 SQLAlchemy 数据库连接 URL
    """
    if DataBaseConfig.db_type == 'postgresql':
        return (
            f'postgresql+psycopg2://{DataBaseConfig.db_username}:{quote_plus(DataBaseConfig.db_password)}@'
            f'{DataBaseConfig.db_host}:{DataBaseConfig.db_port}/{DataBaseConfig.db_database}'
        )
    return (
        f'mysql+pymysql://{DataBaseConfig.db_username}:{quote_plus(DataBaseConfig.db_password)}@'
        f'{DataBaseConfig.db_host}:{DataBaseConfig.db_port}/{DataBaseConfig.db_database}'
    )


SYNC_SQLALCHEMY_DATABASE_URL = build_sync_sqlalchemy_database_url()


def create_async_db_engine(echo: bool | None = None) -> AsyncEngine:
    """
    创建异步 SQLAlchemy Engine

    :param echo: 可选，是否输出 SQLAlchemy SQL 日志
    :return: 异步 SQLAlchemy Engine
    """
    return create_async_engine(
        ASYNC_SQLALCHEMY_DATABASE_URL,
        echo=DataBaseConfig.db_echo if echo is None else echo,
        max_overflow=DataBaseConfig.db_max_overflow,
        pool_size=DataBaseConfig.db_pool_size,
        pool_recycle=DataBaseConfig.db_pool_recycle,
        pool_timeout=DataBaseConfig.db_pool_timeout,
    )


def create_sync_db_engine(echo: bool | None = None) -> Engine:
    """
    创建同步 SQLAlchemy Engine

    :param echo: 可选，是否输出 SQLAlchemy SQL 日志
    :return: 同步 SQLAlchemy Engine
    """
    return create_engine(
        SYNC_SQLALCHEMY_DATABASE_URL,
        echo=DataBaseConfig.db_echo if echo is None else echo,
        max_overflow=DataBaseConfig.db_max_overflow,
        pool_size=DataBaseConfig.db_pool_size,
        pool_recycle=DataBaseConfig.db_pool_recycle,
        pool_timeout=DataBaseConfig.db_pool_timeout,
    )


def create_async_session_local(engine: AsyncEngine) -> async_sessionmaker:
    """
    创建异步 Session 工厂

    :param engine: 异步 SQLAlchemy Engine
    :return: 异步 Session 工厂
    """
    return async_sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_sync_session_local(engine: Engine) -> sessionmaker:
    """
    创建同步 Session 工厂

    :param engine: 同步 SQLAlchemy Engine
    :return: 同步 Session 工厂
    """
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


async_engine = create_async_db_engine()
AsyncSessionLocal = create_async_session_local(async_engine)


class Base(AsyncAttrs, DeclarativeBase):
    pass

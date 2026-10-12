"""在随机 PostgreSQL 数据库验证多角色迁移和真实角色查询，不接触业务库。"""

import asyncio
import os
import runpy
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import URL, Connection, select, text, true
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import aliased

from module_admin.entity.do.user_do import SysUser
from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.dao.platform_role_dao import ShotGridPlatformRoleDao
from module_shot_grid.dao.project_member_dao import ShotGridProjectMemberDao
from module_shot_grid.entity.do.project_do import ShotGridProject, ShotGridProjectMember
from module_shot_grid.entity.vo.project_member_vo import ShotGridProjectMemberUpdateModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.project_member_service import ShotGridProjectMemberService
from tests.module_shot_grid.test_asset_manager_start_pg import isolated_pg_url  # noqa: F401

BACKEND_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_MEMBERS = 2
pytestmark = pytest.mark.skipif(
    os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='设置 SHOT_GRID_RUN_PG_TESTS=1 才创建随机隔离 PostgreSQL 测试库'
)


@pytest.mark.asyncio
async def test_migration_roundtrip_and_dual_role_queries(isolated_pg_url: URL) -> None:  # noqa: F811
    engine = create_async_engine(isolated_pg_url, echo=False)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    migration = runpy.run_path(
        str(BACKEND_ROOT / 'alembic/versions/2026_10_12_1000-20261012_37_member_multiple_roles.py')
    )

    def migrate(connection: Connection, direction: str) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration[direction]()

    try:
        async with sessions() as db:
            db.add(SysUser(user_id=99001, user_name='role-test', nick_name='角色测试'))
            db.add_all(
                [
                    ShotGridProject(project_id=99001, project_code='ROLE1', project_name='角色测试一'),
                    ShotGridProject(project_id=99002, project_code='ROLE2', project_name='角色测试二'),
                ]
            )
            await db.flush()
            db.add_all(
                [
                    ShotGridProjectMember(project_id=99001, user_id=99001, project_role='creator'),
                    ShotGridProjectMember(project_id=99002, user_id=99001, project_role='director'),
                ]
            )
            await db.commit()
        # create_all 已提前建表时，迁移也必须回填旧成员。
        async with engine.begin() as connection:
            await connection.run_sync(migrate, 'upgrade')
            assert (
                await connection.execute(text('SELECT count(*) FROM sg_project_member_role'))
            ).scalar_one() == EXPECTED_MEMBERS
        # 模拟旧版库，只删除本例随机测试库内尚为空的新增表。
        async with engine.begin() as connection:
            await connection.execute(text('DROP TABLE sg_project_member_role'))
            await connection.run_sync(migrate, 'upgrade')
        async with sessions() as db:
            assert (await ShotGridProjectMemberDao.get_member(db, 99001, 99001)).project_roles == ['creator']
            await ShotGridProjectMemberDao.replace_roles(db, 99001, 99001, ['director', 'creator'], '测试')
            await db.commit()
            member = await ShotGridProjectMemberDao.get_member(db, 99001, 99001)
            assert member.has_role('director') and member.has_role('creator')
            assert len(await ShotGridProjectMemberDao.list_members(db, 99001, 'creator')) == 1
            assert len(await ShotGridProjectMemberDao.list_members(db, 99001, 'director')) == 1
            assert await ShotGridProjectMemberDao.count_directors(db, 99001) == 1
            roles = await ShotGridPlatformRoleDao.list_active_membership_roles(db, {99001})
            assert set(roles) == {(99001, 'director'), (99001, 'creator')}
            # 使用 ORM 别名的相关子查询仍按当前成员限定项目，不能串项目。

            alias = aliased(ShotGridProjectMember)
            assert len((await db.scalars(select(alias).where(alias.has_role('creator')))).all()) == 1
        with pytest.raises(RuntimeError, match='禁止降级'):
            async with engine.begin() as connection:
                await connection.run_sync(migrate, 'downgrade')
        async with sessions() as db:
            await ShotGridProjectMemberDao.replace_roles(db, 99001, 99001, ['creator'], '测试')
            await db.commit()
            # 一个项目撤销管理身份，另一个项目仍保留依赖。
            assert set(await ShotGridPlatformRoleDao.list_active_membership_roles(db, {99001})) == {
                (99001, 'director'),
                (99001, 'creator'),
            }
        async with engine.begin() as connection:
            await connection.run_sync(migrate, 'downgrade')
            assert (
                await connection.execute(text('SELECT project_role FROM sg_project_member WHERE project_id=99001'))
            ).scalar_one() == 'creator'
            await connection.run_sync(migrate, 'upgrade')
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_demotion_keeps_one_director(isolated_pg_url: URL, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811

    # 本例验证成员锁与事务，平台角色包配置由独立角色同步测试负责。
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridPlatformRoleService.synchronize_user_roles',
        AsyncMock(return_value=[]),
    )
    engine = create_async_engine(isolated_pg_url, echo=False)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as db:
            db.add_all(
                [
                    SysUser(user_id=user_id, user_name=f'role-{user_id}', nick_name=f'测试{user_id}')
                    for user_id in (99001, 99002)
                ]
            )
            db.add(
                ShotGridProject(
                    project_id=99001, project_code='RACE', project_name='并发角色测试', project_status='active'
                )
            )
            await db.flush()
            for user_id in (99001, 99002):
                db.add(ShotGridProjectMember(project_id=99001, user_id=user_id, project_role='director'))
            await db.flush()
            for user_id in (99001, 99002):
                await ShotGridProjectMemberDao.replace_roles(db, 99001, user_id, ['director', 'creator'], '测试')
            await db.commit()
        actor = CurrentUserModel(
            user=UserInfoModel(userId=99001, userName='role-99001'), roles=[], permissions=['*:*:*']
        )

        async def demote(user_id: int) -> str:
            async with sessions() as db:
                try:
                    await ShotGridProjectMemberService.update_member(
                        db, 99001, user_id, ShotGridProjectMemberUpdateModel(projectRoles=['creator']), actor, true()
                    )
                    return 'ok'
                except ShotGridDomainException as error:
                    return error.error_key

        results = await asyncio.gather(demote(99001), demote(99002))
        assert sorted(results) == ['SG_LAST_DIRECTOR_REQUIRED', 'ok']
        async with sessions() as db:
            assert await ShotGridProjectMemberDao.count_directors(db, 99001) == 1
            assert len(await ShotGridProjectMemberDao.list_members(db, 99001, 'creator')) == EXPECTED_MEMBERS
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_project_creator_migration_and_ordering(isolated_pg_url: URL) -> None:  # noqa: F811
    engine = create_async_engine(isolated_pg_url, echo=False)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    migration = runpy.run_path(str(BACKEND_ROOT / 'alembic/versions/2026_10_12_1400-20261012_38_project_creator.py'))

    def migrate(connection: Connection, direction: str) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration[direction]()

    try:
        async with sessions() as db:
            db.add_all(
                [
                    SysUser(user_id=99001, user_name='peer', nick_name='管理人'),
                    SysUser(user_id=99002, user_name='owner', nick_name='创建者'),
                ]
            )
            db.add(
                ShotGridProject(project_id=99001, project_code='OWNER', project_name='创建者测试', create_by='owner')
            )
            await db.flush()
            for user_id in (99001, 99002):
                db.add(ShotGridProjectMember(project_id=99001, user_id=user_id, project_role='director'))
            await db.flush()
            for user_id in (99001, 99002):
                await ShotGridProjectMemberDao.replace_roles(db, 99001, user_id, ['director'], '测试')
            await db.execute(
                text(
                    'UPDATE sg_project_member SET create_time=(SELECT create_time FROM sg_project WHERE project_id=99001) WHERE project_id=99001'
                )
            )
            await db.commit()
        async with engine.begin() as conn:
            await conn.execute(text('ALTER TABLE sg_project DROP COLUMN creator_user_id'))
            await conn.run_sync(migrate, 'upgrade')
        async with sessions() as db:
            members = await ShotGridProjectMemberDao.list_members(db, 99001)
            assert members[0]['user_name'] == 'owner'
            assert members[0]['is_project_creator'] is True
            assert members[1]['is_project_creator'] is False
            # 创建者身份不随平台账号改名变化。
            await db.execute(text("UPDATE sys_user SET user_name='renamed' WHERE user_id=99002"))
            await db.commit()
            assert (await ShotGridProjectMemberDao.get_member_detail(db, 99001, 99002))['is_project_creator'] is True
        async with engine.begin() as conn:
            await conn.run_sync(migrate, 'downgrade')
    finally:
        await engine.dispose()

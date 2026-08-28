"""资产管理员开工的真实 PostgreSQL 门禁；每例独立数据库，绝不复用业务库。"""

import asyncio
import json
import os
import re
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg2
import pytest
import pytest_asyncio
from dotenv import dotenv_values
from psycopg2 import sql
from sqlalchemy import URL, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from module_admin.entity.do.user_do import SysUser
from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.dao.storage_operation_dao import ShotGridStorageOperationDao
from module_shot_grid.dao.task_dao import ShotGridTaskDao
from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridAssetItem
from module_shot_grid.entity.do.project_do import ShotGridProject, ShotGridProjectMember
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageRoot
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.vo.asset_crud_vo import ShotGridAssetListQueryModel
from module_shot_grid.entity.vo.task_vo import ShotGridTaskDetailModel, ShotGridTaskStartModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.asset_crud_service import ShotGridAssetCrudService
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.storage_path_adapter import StorageOperationPathContext
from module_shot_grid.service.storage_worker_service import ShotGridStorageWorkerService
from module_shot_grid.service.task_service import ShotGridTaskService

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1',
        reason='设置 SHOT_GRID_RUN_PG_TESTS=1 才允许创建临时 PostgreSQL 数据库',
    ),
]

BACKEND = Path(__file__).resolve().parents[2]
PROJECT_ID = 901
ASSET_ID = 902
FIRST_ITEM_ID = 910
FIRST_TASK_ID = 920
DIRECTOR_ID = 930
CREATOR_ID = 931
OUTSIDER_ID = 932
STARTED_ITEM_COUNT = 2
ARCHIVED_ITEM_INDEX = 4
DELETED_ITEM_INDEX = 5
SessionFactory = async_sessionmaker[AsyncSession]
EXPECTED_COUNTS = {
    'unassigned': 1,
    'not_started': 2,
    'preparing': 1,
    'in_progress': 0,
    'reviewing': 0,
    'revision': 0,
    'completed': 0,
}


@pytest.fixture
def isolated_pg_url() -> Iterator[URL]:
    """仅连接回环 PG 管理库，创建随机数据库；加载基线前再次核对物理目标。"""
    config = dotenv_values(BACKEND / '.env.dev')
    assert config.get('DB_TYPE') == 'postgresql'
    host = config.get('DB_HOST', '127.0.0.1')
    assert host in {'127.0.0.1', 'localhost', '::1'}, 'PG 门禁只允许使用回环开发实例'
    params = {
        'host': host,
        'port': int(config.get('DB_PORT', '5432')),
        'user': config['DB_USERNAME'],
        'password': config['DB_PASSWORD'],
        'connect_timeout': 5,
    }
    name = f'sg_asset_start_test_{uuid4().hex}'
    assert re.fullmatch(r'sg_asset_start_test_[0-9a-f]{32}', name)
    assert name != config.get('DB_DATABASE')
    admin = psycopg2.connect(dbname='postgres', **params)
    admin.autocommit = True
    created = False
    try:
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
            created = True
        connection = psycopg2.connect(dbname=name, **params)
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT current_database(), current_schema()')
                assert cursor.fetchone() == (name, 'public')
                cursor.execute("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
                assert cursor.fetchone()[0] == 0
                cursor.execute((BACKEND / 'sql' / 'ruoyi-fastapi-pg.sql').read_text(encoding='utf-8'))
            connection.commit()
        finally:
            connection.close()
        yield URL.create(
            'postgresql+asyncpg',
            username=params['user'],
            password=params['password'],
            host=host,
            port=params['port'],
            database=name,
        )
    finally:
        if created:
            with admin.cursor() as cursor:
                # 不使用 FORCE，不终止任何既有会话；资源泄漏会直接导致清理门禁失败。
                cursor.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
                cursor.execute('SELECT count(*) FROM pg_database WHERE datname = %s', (name,))
                assert cursor.fetchone()[0] == 0
            print(f'PG_ISOLATION database={name} cleaned=true')
        admin.close()


@pytest_asyncio.fixture
async def pg_sessions(isolated_pg_url: URL) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        isolated_pg_url,
        echo=False,
        connect_args={'server_settings': {'statement_timeout': '10000', 'lock_timeout': '8000'}},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        async with sessions() as db:
            assert (await db.execute(text('SELECT current_database()'))).scalar_one() == isolated_pg_url.database
            await _seed(db)
        yield sessions
    finally:
        await engine.dispose()


async def _seed(db: AsyncSession) -> None:
    """所有测试数据只写入本例临时库，保留正式表、约束、索引及外键。"""
    db.add_all(
        [
            SysUser(user_id=user_id, user_name=f'pg-user-{user_id}', nick_name=f'PG{user_id}')
            for user_id in (DIRECTOR_ID, CREATOR_ID, OUTSIDER_ID)
        ]
    )
    db.add(
        ShotGridProject(
            project_id=PROJECT_ID, project_code='PGASSET', project_name='PG隔离测试', project_status='active'
        )
    )
    db.add(
        ShotGridStorageRoot(
            storage_root_id=900,
            root_code='PGONLY',
            root_name='不可访问的测试根',
            unc_root_path=r'\\invalid.test\no-network',
            root_path_key=r'\\invalid.test\no-network',
            last_probe_status='healthy',
        )
    )
    await db.flush()
    db.add_all(
        [
            ShotGridProjectMember(project_id=PROJECT_ID, user_id=DIRECTOR_ID, project_role='director'),
            ShotGridProjectMember(project_id=PROJECT_ID, user_id=CREATOR_ID, project_role='creator'),
        ]
    )
    db.add(
        ShotGridProjectStorage(
            project_id=PROJECT_ID,
            storage_root_id=900,
            root_path_snapshot=r'\\invalid.test\no-network',
            project_type_dir_snapshot='TEST',
            project_dir_name_snapshot='PGASSET',
            project_relative_path=r'TEST\PGASSET',
            project_path_snapshot=r'\\invalid.test\no-network\TEST\PGASSET',
            project_path_key=r'\\invalid.test\no-network\test\pgasset',
            storage_status='ready',
        )
    )
    db.add(
        ShotGridAsset(
            asset_id=ASSET_ID,
            project_id=PROJECT_ID,
            asset_name='同资产分项',
            asset_name_key='同资产分项',
            asset_type='Prop',
            storage_dir_name='fixture_asset',
            storage_path_key=r'asset\prop\fixture_asset',
        )
    )
    await db.flush()
    db.add_all(
        [
            ShotGridAssetItem(
                asset_item_id=FIRST_ITEM_ID + index,
                project_id=PROJECT_ID,
                asset_id=ASSET_ID,
                production_item=f'分项{index}',
                production_item_key=f'分项{index}',
                lifecycle_status='archived' if index == ARCHIVED_ITEM_INDEX else 'active',
                del_flag='2' if index == DELETED_ITEM_INDEX else '0',
            )
            for index in range(6)
        ]
    )
    await db.flush()
    db.add_all(
        [
            ShotGridTask(
                task_id=FIRST_TASK_ID + index,
                project_id=PROJECT_ID,
                asset_item_id=FIRST_ITEM_ID + index,
                task_name=f'隔离分项{index}',
                task_kind='asset_image',
                assignee_user_id=CREATOR_ID,
            )
            for index in range(3)
        ]
    )
    await db.commit()


def _user(user_id: int = DIRECTOR_ID, permissions: list[str] | None = None) -> CurrentUserModel:
    return CurrentUserModel(
        permissions=['shotgrid:task:start', 'shotgrid:asset:list', 'shotgrid:asset:query']
        if permissions is None
        else permissions,
        roles=[],
        user=UserInfoModel(userId=user_id, userName=f'pg-user-{user_id}'),
    )


def _command(**overrides: object) -> ShotGridTaskStartModel:
    return ShotGridTaskStartModel.model_validate(
        {
            'lockVersion': 0,
            'assetLockVersion': 0,
            'assetItemLockVersion': 0,
            'startConfirmed': True,
            **overrides,
        }
    )


async def _start(
    sessions: SessionFactory,
    task_id: int = FIRST_TASK_ID,
    user: CurrentUserModel | None = None,
    command: ShotGridTaskStartModel | None = None,
) -> ShotGridTaskDetailModel:
    async with sessions() as db:
        return await ShotGridTaskService.start_task(db, task_id, command or _command(), user or _user())


async def _snapshot(sessions: SessionFactory) -> dict[str, Any]:
    """直接查询持久化状态，避免用 mock 调用次数冒充事务证据。"""
    async with sessions() as db:
        return {
            name: (await db.execute(text(statement))).mappings().all()
            for name, statement in {
                'tasks': 'SELECT task_id, task_status, lock_version, update_by FROM sg_task ORDER BY task_id',
                'assets': 'SELECT asset_id, lock_version FROM sg_asset ORDER BY asset_id',
                'items': 'SELECT asset_item_id, lock_version FROM sg_asset_item ORDER BY asset_item_id',
                'operations': 'SELECT operation_id, operation_status, attempt_count FROM sg_storage_operation ORDER BY operation_id',
                'audit': 'SELECT oper_id, oper_param, json_result FROM sys_oper_log ORDER BY oper_id',
            }.items()
        }


async def _concurrent_starts(sessions: SessionFactory, task_ids: list[int]) -> list[Any]:
    """先持有项目行锁，实际观察两个会话等待锁后放行，确保测试真实竞争。"""
    jobs = []
    async with sessions() as blocker:
        await blocker.execute(select(ShotGridProject).where(ShotGridProject.project_id == PROJECT_ID).with_for_update())
        try:
            jobs = [asyncio.create_task(_start(sessions, task_id)) for task_id in task_ids]
            async with sessions() as observer:
                deadline = asyncio.get_running_loop().time() + 5
                while True:
                    waiting = (
                        await observer.execute(
                            text(
                                'SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() '
                                "AND wait_event_type = 'Lock'"
                            )
                        )
                    ).scalar_one()
                    if waiting >= len(task_ids):
                        break
                    assert asyncio.get_running_loop().time() < deadline, '未观察到两个请求同时等待项目行锁'
                    # 结束观察事务，下一轮重新取得 PostgreSQL 活动统计快照。
                    await observer.rollback()
                    await asyncio.sleep(0.01)
            print(f'PG_LOCK_CONTENTION waiting_sessions={waiting}')
        finally:
            await blocker.rollback()
            results = await asyncio.gather(*jobs, return_exceptions=True)
    return results


async def test_same_item_concurrent_start_commits_only_once(pg_sessions: SessionFactory) -> None:
    results = await _concurrent_starts(pg_sessions, [FIRST_TASK_ID, FIRST_TASK_ID])
    successes = [item for item in results if not isinstance(item, Exception)]
    failures = [item for item in results if isinstance(item, ShotGridDomainException)]
    assert len(successes) == len(failures) == 1
    assert failures[0].http_status == HTTPStatus.CONFLICT
    state = await _snapshot(pg_sessions)
    assert [row['task_status'] for row in state['tasks']] == ['preparing', 'not_started', 'not_started']
    assert len(state['operations']) == len(state['audit']) == 1
    payload = json.loads(state['audit'][0]['oper_param'])
    assert payload['startConfirmed'] is True
    assert payload['assetLockVersion'] == payload['assetItemLockVersion'] == 0


async def test_different_items_concurrent_start_share_single_directory(pg_sessions: SessionFactory) -> None:
    results = await _concurrent_starts(pg_sessions, [FIRST_TASK_ID, FIRST_TASK_ID + 1])
    assert [result.task_status for result in results] == ['preparing', 'preparing']
    state = await _snapshot(pg_sessions)
    assert [row['task_status'] for row in state['tasks']] == ['preparing', 'preparing', 'not_started']
    assert len(state['operations']) == 1
    assert len(state['audit']) == STARTED_ITEM_COUNT


async def test_worker_advances_only_started_items_and_reuses_ready_directory(pg_sessions: SessionFactory) -> None:
    await _start(pg_sessions)

    class NoNetworkAdapter:
        async def ensure_directories(self, context: StorageOperationPathContext) -> None:
            # 只替换真实 NAS I/O；领取、租约、结果 fencing 和任务 SQL 都实际执行。
            assert context.operation_type == 'ensure_asset_directory'
            assert context.aggregate_id == ASSET_ID

    async with pg_sessions() as db:
        result = await ShotGridStorageWorkerService.run_once(db, worker_id='pg-gate', adapter=NoNetworkAdapter())
    assert result.outcome == 'succeeded'
    state = await _snapshot(pg_sessions)
    assert [row['task_status'] for row in state['tasks']] == ['in_progress', 'not_started', 'not_started']
    assert state['operations'][0]['operation_status'] == 'succeeded'
    next_result = await _start(pg_sessions, FIRST_TASK_ID + 1)
    assert next_result.task_status == 'in_progress'
    assert len((await _snapshot(pg_sessions))['operations']) == 1


async def _wait_for_worker_commit_or_lock(
    sessions: SessionFactory, worker_job: asyncio.Task[None], worker_pid: int | None
) -> None:
    async with sessions() as observer:
        deadline = asyncio.get_running_loop().time() + 5
        while not worker_job.done():
            wait_type = (
                await observer.execute(
                    text('SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid'), {'pid': worker_pid}
                )
            ).scalar_one_or_none()
            if wait_type == 'Lock':
                # 正确实现允许 Worker 在项目协调锁上等待；此时放行 B，不制造测试死锁。
                print('PG_SHARED_COMPLETION worker_waited_for_start_lock=true')
                break
            assert asyncio.get_running_loop().time() < deadline, 'Worker 既未提交，也未进入可观察的行锁等待'
            await observer.rollback()
            await asyncio.sleep(0.01)
        else:
            print('PG_SHARED_COMPLETION worker_committed_before_start=true')


async def test_shared_directory_completion_cannot_miss_concurrent_item_start(
    pg_sessions: SessionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """真实结果回写与第二分项开工交错时，不能留下已无后续目录操作的 preparing。"""
    await _start(pg_sessions)
    now = datetime.now().replace(microsecond=0)
    async with pg_sessions() as db:
        operation = await ShotGridStorageOperationDao.claim_next_operation(
            db, worker_id='pg-shared-completion', now=now, lease_until=now + timedelta(seconds=60)
        )
        assert operation is not None
        operation_id = operation.operation_id
        attempt_count = operation.attempt_count
        await db.commit()

    status_read = asyncio.Event()
    release_start = asyncio.Event()
    worker_ready = asyncio.Event()
    worker_pid = None
    original_status_query = ShotGridTaskDao.get_latest_asset_directory_operation_status

    async def pause_after_real_status_query(db: AsyncSession, project_id: int, asset_id: int) -> str | None:
        # 只协调真实 SQL 返回后的时点；不替换查询结果、Service 或事务。
        status = await original_status_query(db, project_id, asset_id)
        assert status == 'processing'
        status_read.set()
        await release_start.wait()
        return status

    monkeypatch.setattr(
        ShotGridTaskDao, 'get_latest_asset_directory_operation_status', staticmethod(pause_after_real_status_query)
    )

    async def complete_directory() -> None:
        nonlocal worker_pid
        async with pg_sessions() as db:
            worker_pid = (await db.execute(text('SELECT pg_backend_pid()'))).scalar_one()
            worker_ready.set()
            assert await ShotGridStorageOperationDao.mark_succeeded(
                db,
                operation_id=operation_id,
                worker_id='pg-shared-completion',
                expected_attempt_count=attempt_count,
                now=datetime.now().replace(microsecond=0),
            )
            await db.commit()

    start_job = asyncio.create_task(_start(pg_sessions, FIRST_TASK_ID + 1))
    worker_job = None
    try:
        await asyncio.wait_for(status_read.wait(), timeout=5)
        worker_job = asyncio.create_task(complete_directory())
        await asyncio.wait_for(worker_ready.wait(), timeout=5)
        await _wait_for_worker_commit_or_lock(pg_sessions, worker_job, worker_pid)
    finally:
        release_start.set()
        results = await asyncio.gather(
            start_job, *([worker_job] if worker_job is not None else []), return_exceptions=True
        )
    assert not [result for result in results if isinstance(result, Exception)]
    state = await _snapshot(pg_sessions)
    statuses = [row['task_status'] for row in state['tasks']]
    assert len(state['operations']) == 1
    assert state['operations'][0]['operation_status'] == 'succeeded'
    print(f'PG_SHARED_COMPLETION task_statuses={statuses} operation_status=succeeded')
    assert statuses == ['in_progress', 'in_progress', 'not_started']


@pytest.mark.parametrize('field', ['lockVersion', 'assetLockVersion', 'assetItemLockVersion'])
async def test_three_stale_versions_leave_no_side_effects(pg_sessions: SessionFactory, field: str) -> None:
    before = await _snapshot(pg_sessions)
    with pytest.raises(ShotGridDomainException) as caught:
        await _start(pg_sessions, command=_command(**{field: 9}))
    assert caught.value.http_status == HTTPStatus.CONFLICT
    assert await _snapshot(pg_sessions) == before


@pytest.mark.parametrize('actor', ['creator', 'no_permission', 'outsider'])
async def test_permission_denial_leaves_no_side_effects(pg_sessions: SessionFactory, actor: str) -> None:
    user = {'creator': _user(CREATOR_ID), 'no_permission': _user(permissions=[]), 'outsider': _user(OUTSIDER_ID)}[actor]
    before = await _snapshot(pg_sessions)
    with pytest.raises(ShotGridDomainException) as caught:
        await _start(pg_sessions, user=user)
    assert caught.value.http_status == HTTPStatus.FORBIDDEN
    assert await _snapshot(pg_sessions) == before


async def test_all_scope_manager_without_membership_can_start(pg_sessions: SessionFactory) -> None:
    user = _user(OUTSIDER_ID, permissions=['shotgrid:task:start', 'shotgrid:project:all'])
    result = await _start(pg_sessions, user=user)
    assert result.task_status == 'preparing'


@pytest.mark.parametrize(
    'invalid_state', ['creator_disabled', 'creator_role_changed', 'project_archived', 'asset_archived', 'item_archived']
)
async def test_invalid_context_leaves_no_side_effects(pg_sessions: SessionFactory, invalid_state: str) -> None:
    async with pg_sessions() as db:
        statements = {
            'creator_disabled': update(SysUser).where(SysUser.user_id == CREATOR_ID).values(status='1'),
            'creator_role_changed': update(ShotGridProjectMember)
            .where(ShotGridProjectMember.user_id == CREATOR_ID)
            .values(project_role='director'),
            'project_archived': update(ShotGridProject)
            .where(ShotGridProject.project_id == PROJECT_ID)
            .values(project_status='archived'),
            'asset_archived': update(ShotGridAsset)
            .where(ShotGridAsset.asset_id == ASSET_ID)
            .values(lifecycle_status='archived'),
            'item_archived': update(ShotGridAssetItem)
            .where(ShotGridAssetItem.asset_item_id == FIRST_ITEM_ID)
            .values(lifecycle_status='archived'),
        }
        await db.execute(statements[invalid_state])
        await db.commit()
    before = await _snapshot(pg_sessions)
    with pytest.raises(ShotGridDomainException):
        await _start(pg_sessions)
    assert await _snapshot(pg_sessions) == before


@pytest.mark.parametrize('confirmation', [False, None])
async def test_missing_confirmation_leaves_no_side_effects(
    pg_sessions: SessionFactory, confirmation: bool | None
) -> None:
    payload = {'lockVersion': 0, 'assetLockVersion': 0, 'assetItemLockVersion': 0}
    if confirmation is not None:
        payload['startConfirmed'] = confirmation
    before = await _snapshot(pg_sessions)
    with pytest.raises(ShotGridDomainException) as caught:
        await _start(pg_sessions, command=ShotGridTaskStartModel.model_validate(payload))
    assert caught.value.http_status == HTTPStatus.UNPROCESSABLE_ENTITY
    assert await _snapshot(pg_sessions) == before


async def test_audit_database_failure_rolls_back_start_and_outbox(pg_sessions: SessionFactory) -> None:
    async with pg_sessions() as db:
        # 故障注入只安装于本例临时库，通过真实 PostgreSQL 审计 INSERT 失败触发回滚。
        await db.execute(
            text(
                'CREATE FUNCTION reject_test_audit() RETURNS trigger LANGUAGE plpgsql AS $$ '
                "BEGIN RAISE EXCEPTION 'PG_GATE_AUDIT_REJECTED'; END $$"
            )
        )
        await db.execute(
            text(
                'CREATE TRIGGER reject_test_audit BEFORE INSERT ON sys_oper_log '
                'FOR EACH ROW EXECUTE FUNCTION reject_test_audit()'
            )
        )
        await db.commit()
    before = await _snapshot(pg_sessions)
    with pytest.raises(DBAPIError, match='PG_GATE_AUDIT_REJECTED'):
        await _start(pg_sessions)
    assert await _snapshot(pg_sessions) == before


async def test_list_and_detail_execute_preparing_counts_projection(pg_sessions: SessionFactory) -> None:
    await _start(pg_sessions)
    async with pg_sessions() as db:
        access = await ShotGridProjectAccessService.resolve_access(db, _user(), PROJECT_ID)
        page = await ShotGridAssetCrudService.get_asset_page(
            db,
            PROJECT_ID,
            ShotGridAssetListQueryModel(assetStatus='preparing'),
            _user(),
            access,
        )
        detail = await ShotGridAssetCrudService.get_asset_detail(db, PROJECT_ID, ASSET_ID, _user(), access)
        actual_states = dict((await db.execute(select(ShotGridTask.task_id, ShotGridTask.task_status))).all())
    assert page.total == 1
    assert page.rows[0].asset_status == detail.asset_status == 'preparing'
    assert page.rows[0].model_dump(by_alias=True)['itemStatusCounts'] == EXPECTED_COUNTS
    assert detail.model_dump(by_alias=True)['itemStatusCounts'] == EXPECTED_COUNTS
    assert actual_states[FIRST_TASK_ID + 1] == 'not_started'
    assert 'task.start' in page.rows[0].allowed_actions
    assert 'task.start' in detail.allowed_actions
    actions = {item.asset_item_id: item.allowed_actions for item in detail.items}
    assert 'task.start' not in actions[FIRST_ITEM_ID]
    assert 'task.start' in actions[FIRST_ITEM_ID + 1]
    assert 'task.start' in actions[FIRST_ITEM_ID + 2]
    assert 'task.start' not in actions[FIRST_ITEM_ID + 3]


@pytest.mark.parametrize('actor', ['creator', 'no_permission'])
async def test_list_and_detail_hide_start_when_not_authorized(pg_sessions: SessionFactory, actor: str) -> None:
    user = _user(CREATOR_ID) if actor == 'creator' else _user(permissions=[])
    async with pg_sessions() as db:
        access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
        page = await ShotGridAssetCrudService.get_asset_page(
            db, PROJECT_ID, ShotGridAssetListQueryModel(), user, access
        )
        detail = await ShotGridAssetCrudService.get_asset_detail(db, PROJECT_ID, ASSET_ID, user, access)
        task = await ShotGridTaskService.get_task_detail(db, FIRST_TASK_ID, user)
    assert 'task.start' not in page.rows[0].allowed_actions
    assert 'task.start' not in detail.allowed_actions
    assert all('task.start' not in item.allowed_actions for item in detail.items)
    assert 'task.start' not in task.allowed_actions

"""使用提交后过期的真实异步会话验证人工审核单创建响应。"""

import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from module_shot_grid.entity.do.target_purge_do import ShotGridTargetPurge
from module_shot_grid.entity.vo.review_vo import ShotGridManualReviewListCreateModel
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.review_service import ShotGridReviewService
from module_shot_grid.service.target_purge_service import ShotGridTargetPurgeService
from tests.module_shot_grid.test_asset_manager_start_pg import (
    PROJECT_ID,
    SessionFactory,
    _user,
    isolated_pg_url,  # noqa: F401
    pg_sessions,  # noqa: F401
)
from tests.module_shot_grid.test_review_all_candidates_pg import prepare_round

# ruff: noqa: F811
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='仅显式启用隔离 PostgreSQL'),
]


async def test_create_manual_review_returns_detail_after_commit(pg_sessions: SessionFactory) -> None:
    version_id, _ = await prepare_round(pg_sessions)
    sessions = async_sessionmaker(pg_sessions.kw['bind'], expire_on_commit=True, autoflush=False)
    async with sessions() as db:
        user = _user()
        access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
        result = await ShotGridReviewService.create_manual_review_list(
            db,
            PROJECT_ID,
            ShotGridManualReviewListCreateModel(reviewListName='提交过期回归', versionIds=[version_id]),
            user,
            access,
        )
        assert result.review_status == 'draft'
        assert [version.version_id for version in result.versions] == [version_id]
        review_list_id = result.review_list_id
    async with sessions() as db:
        persisted = await ShotGridReviewService.get_review_list_detail(db, review_list_id, _user())
        assert persisted.review_list_name == '提交过期回归'
        assert [version.version_id for version in persisted.versions] == [version_id]


async def test_purge_retry_returns_status_after_commit_without_running_cleanup(pg_sessions: SessionFactory) -> None:
    # 只验证随机隔离库内的队列事务，不启动清理 Worker，不访问任何 NAS。
    async with pg_sessions() as db:
        row = ShotGridTargetPurge(
            project_id=PROJECT_ID,
            target_kind='shot',
            target_id=999999,
            target_label='过期响应测试',
            root_path_snapshot='//invalid/isolated-test',
            project_relative_path='test',
            project_path_snapshot='//invalid/isolated-test/test',
            nas_manifest=[],
            file_manifest=[],
            requested_by_user_id=1,
            requested_by='test',
            reason='仅验证重试事务',
            purge_status='failed',
            attempt_count=2,
            last_error_key='TEST',
            last_error_message='测试失败',
        )
        db.add(row)
        await db.commit()
        purge_id = row.purge_id
    sessions = async_sessionmaker(pg_sessions.kw['bind'], expire_on_commit=True, autoflush=False)
    async with sessions() as db:
        user = _user(permissions=['shotgrid:shot:forceDelete'])
        access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
        result = await ShotGridTargetPurgeService.retry(db, PROJECT_ID, purge_id, user, access)
        assert result.purge_status == 'pending'
        assert result.can_retry is False
        assert result.last_error_key is None
    async with sessions() as db:
        row = await db.get(ShotGridTargetPurge, purge_id)
        assert row.purge_status == 'pending'
        assert row.attempt_count == 0

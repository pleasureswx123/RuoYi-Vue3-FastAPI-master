"""显式启用的本地 PostgreSQL 验证，外层事务回滚所有业务记录。"""

import os
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from config.database import async_engine
from config.env import DataBaseConfig
from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.entity.do.review_do import ShotGridIssueComment, ShotGridNote
from module_shot_grid.entity.vo.review_vo import ShotGridIssueCommentCreateModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service import review_service
from module_shot_grid.service.review_service import ShotGridReviewService

LOCAL_TEST_PORT = 15432

pytestmark = pytest.mark.skipif(os.getenv('SHOT_GRID_LOCAL_COMMENT_TEST') != '1', reason='需显式启用本地数据库验证')


@pytest.mark.asyncio
async def test_real_postgres_comment_roundtrip_idempotency_and_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    assert DataBaseConfig.db_host == '127.0.0.1' and DataBaseConfig.db_port == LOCAL_TEST_PORT
    async_engine.echo = False
    monkeypatch.setattr(review_service, 'publish_version_changed', AsyncMock())
    note_id = None
    async with async_engine.connect() as connection:
        outer = await connection.begin()
        try:
            assert (
                await connection.execute(text('SELECT version_num FROM alembic_version'))
            ).scalar_one() == '20261030_41'
            target = (
                (
                    await connection.execute(
                        text(
                            "SELECT v.version_id,v.project_id FROM sg_version v JOIN sg_project p USING(project_id) WHERE p.project_code='LOCALDEMO' ORDER BY v.version_id LIMIT 1"
                        )
                    )
                )
                .mappings()
                .one()
            )
            user = CurrentUserModel(
                user=UserInfoModel(userId=1, userName='admin', nickName='集成验证', admin=True),
                permissions=['*:*:*'],
                roles=[],
            )
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode='create_savepoint'
            ) as db:
                note = ShotGridNote(
                    project_id=target['project_id'],
                    version_id=target['version_id'],
                    reviewer_user_id=1,
                    content='仅限事务内的评论集成验证',
                    note_status='open',
                    create_time=datetime.now(),
                    update_time=datetime.now(),
                )
                db.add(note)
                await db.flush()
                note_id = note.note_id
                await db.commit()
                command = ShotGridIssueCommentCreateModel(content='第一条\n记录', requestId='pg-rollback-test')
                first = await ShotGridReviewService.add_issue_comment(db, target['version_id'], note_id, command, user)
                second = await ShotGridReviewService.add_issue_comment(db, target['version_id'], note_id, command, user)
                assert first.comment_id == second.comment_id
                with pytest.raises(ShotGridDomainException):
                    await ShotGridReviewService.add_issue_comment(
                        db,
                        target['version_id'],
                        note_id,
                        command.model_copy(update={'content': '不能冒充同一请求'}),
                        user,
                    )
                rows = await ShotGridReviewService.get_issue_comments(db, target['version_id'], note_id, None, 20, user)
                assert len(rows.rows) == 1 and rows.rows[0].content == command.content
                assert rows.rows[0].author_name == '集成验证'
                with pytest.raises(ShotGridDomainException):
                    await ShotGridReviewService.get_issue_comments(
                        db, target['version_id'] + 100000, note_id, None, 20, user
                    )
                stranger = CurrentUserModel(
                    user=UserInfoModel(userId=999999, userName='outsider'),
                    permissions=['shotgrid:note:list', 'shotgrid:note:comment'],
                    roles=[],
                )
                with pytest.raises(ShotGridDomainException):
                    await ShotGridReviewService.get_issue_comments(
                        db, target['version_id'], note_id, None, 20, stranger
                    )
                await db.rollback()
        finally:
            await outer.rollback()
    async with async_engine.connect() as connection:
        assert (
            await connection.scalar(
                select(func.count()).select_from(ShotGridNote).where(ShotGridNote.note_id == note_id)
            )
        ) == 0
        assert (
            await connection.scalar(
                select(func.count()).select_from(ShotGridIssueComment).where(ShotGridIssueComment.note_id == note_id)
            )
        ) == 0
    await async_engine.dispose()

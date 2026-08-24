from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from module_shot_grid.dao.review_dao import ShotGridReviewDao
from module_shot_grid.entity.do.review_do import (
    ShotGridReviewAction,
    ShotGridReviewIssueDraft,
    ShotGridReviewList,
    ShotGridReviewListVersion,
)

REVIEW_LIST_ID = 7001
EXPECTED_FLUSH_COUNT = 2


def test_review_action_schema_has_durable_idempotency_contract() -> None:
    sql = str(CreateTable(ShotGridReviewAction.__table__).compile(dialect=postgresql.dialect()))

    assert 'idempotency_key VARCHAR(100) NOT NULL' in sql
    assert 'request_hash CHAR(64) NOT NULL' in sql
    assert 'result_snapshot JSONB NOT NULL' in sql
    assert 'uk_sg_review_action_idempotency' in sql
    assert "request_hash ~ '^[0-9a-f]{64}$'" in sql
    assert 'ck_sg_review_action_transition' in sql


def test_auto_review_list_schema_keeps_mode_version_and_unique_guards() -> None:
    constraint_names = {constraint.name for constraint in ShotGridReviewList.__table__.constraints}
    index_names = {index.name for index in ShotGridReviewList.__table__.indexes}

    assert 'ck_sg_review_list_mode_version' in constraint_names
    assert 'ck_sg_review_list_auto_status' in constraint_names
    assert 'uk_sg_review_list_auto_version' in index_names
    assert 'uk_sg_review_list_version_sort' in {
        constraint.name for constraint in ShotGridReviewListVersion.__table__.constraints
    }


@pytest.mark.asyncio
async def test_add_auto_review_list_only_flushes_and_never_commits() -> None:
    db = SimpleNamespace(add=Mock(), flush=AsyncMock(), commit=AsyncMock())
    review_list = SimpleNamespace(review_list_id=REVIEW_LIST_ID)
    relation = SimpleNamespace(review_list_id=None)

    result = await ShotGridReviewDao.add_auto_review_list(db, review_list, relation)

    assert result is review_list
    assert relation.review_list_id == REVIEW_LIST_ID
    assert db.add.call_args_list[0].args == (review_list,)
    assert db.add.call_args_list[1].args == (relation,)
    assert db.flush.await_count == EXPECTED_FLUSH_COUNT
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_issue_draft_reviewer_uses_user_name_instead_of_nick_name() -> None:
    draft = ShotGridReviewIssueDraft(
        draft_id=9001,
        project_id=1001,
        review_list_id=REVIEW_LIST_ID,
        version_id=8001,
        reviewer_user_id=1,
        content='画面需要调整',
        lock_version=0,
        create_time=datetime(2026, 8, 21, 17, 44),
        update_time=datetime(2026, 8, 21, 17, 44),
    )
    result = SimpleNamespace(all=Mock(return_value=[(draft, '场景锋')]))
    db = SimpleNamespace(execute=AsyncMock(return_value=result))

    rows = await ShotGridReviewDao.get_issue_drafts(
        db,
        project_id=1001,
        version_id=8001,
    )

    statement = str(db.execute.await_args.args[0])
    assert 'sys_user.user_name AS reviewer_name' in statement
    assert rows[0]['reviewer_name'] == '场景锋'

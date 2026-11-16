from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.review_vo import ShotGridIssueCommentCreateModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service import review_service as module
from module_shot_grid.service.review_service import ShotGridReviewService as Service


def actor(permissions: list[str] | None = None) -> CurrentUserModel:
    return CurrentUserModel(
        user=UserInfoModel(userId=7, userName='creator', nickName='制作人'),
        roles=[],
        permissions=permissions if permissions is not None else ['shotgrid:note:list', 'shotgrid:note:comment'],
    )


def saved(**values: str) -> SimpleNamespace:
    return SimpleNamespace(
        comment_id=1,
        project_id=8,
        note_id=51,
        author_id=7,
        author_name='制作人',
        content=values.get('content', '已补充'),
        request_id='request-1',
        create_time=datetime(2026, 10, 30),
    )


@pytest.fixture
def setup(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    access = ShotGridProjectAccessModel(projectId=8, userId=7, projectRole='creator')
    context = {'project_id': 8, 'task_id': 71, 'version_id': 2}
    monkeypatch.setattr(Service, '_resolve_note_access', AsyncMock(return_value=(context, access)))
    monkeypatch.setattr(Service, '_lock_version_graph', AsyncMock(return_value=(8, object(), object(), access)))
    monkeypatch.setattr(module.ShotGridReviewDao, 'get_note_for_update', AsyncMock(return_value=object()))
    monkeypatch.setattr(module.ShotGridReviewDao, 'get_issue_comment_request', AsyncMock(return_value=None))
    monkeypatch.setattr(module.ShotGridReviewDao, 'add_issue_comment', AsyncMock(return_value=saved()))
    monkeypatch.setattr(Service, '_audit', AsyncMock())
    monkeypatch.setattr(module, 'publish_version_changed', AsyncMock())
    return AsyncMock()


@pytest.mark.asyncio
async def test_creator_comment_commits_audit_and_publishes_without_review_transition(setup: AsyncMock) -> None:
    command = ShotGridIssueCommentCreateModel(content=' 已补充 ', requestId='request-1')
    result = await Service.add_issue_comment(setup, 2, 51, command, actor())
    assert result.content == '已补充'
    setup.commit.assert_awaited_once()
    Service._audit.assert_awaited_once()
    module.publish_version_changed.assert_awaited_once_with(2, 'issue.comment.added')
    row = module.ShotGridReviewDao.add_issue_comment.call_args.args[1]
    assert (row.author_id, row.project_id, row.note_id) == (7, 8, 51)


@pytest.mark.asyncio
async def test_same_request_replays_but_changed_content_conflicts(setup: AsyncMock) -> None:
    module.ShotGridReviewDao.get_issue_comment_request.return_value = saved()
    command = ShotGridIssueCommentCreateModel(content='已补充', requestId='request-1')
    assert (await Service.add_issue_comment(setup, 2, 51, command, actor())).comment_id == 1
    module.ShotGridReviewDao.add_issue_comment.assert_not_awaited()
    Service._audit.assert_not_awaited()
    with pytest.raises(ShotGridDomainException):
        await Service.add_issue_comment(setup, 2, 51, command.model_copy(update={'content': '改变内容'}), actor())
    setup.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['permission', 'version', 'membership', 'archived', 'missing-note', 'audit'])
async def test_access_failure_and_transaction_failure_never_commit(setup: AsyncMock, failure: str) -> None:
    user = actor()
    version = 2
    if failure == 'permission':
        user = actor(['shotgrid:note:list'])
    elif failure == 'version':
        version = 99
    elif failure == 'membership':
        Service._resolve_note_access.side_effect = module.shot_grid_error(
            403, 'SG_PROJECT_ACCESS_DENIED', '无权访问项目'
        )
    elif failure == 'archived':
        Service._lock_version_graph.side_effect = module.shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '归档只读')
    elif failure == 'missing-note':
        module.ShotGridReviewDao.get_note_for_update.return_value = None
    else:
        Service._audit.side_effect = RuntimeError('audit failed')
    with pytest.raises((ShotGridDomainException, RuntimeError)):
        await Service.add_issue_comment(
            setup, version, 51, ShotGridIssueCommentCreateModel(content='已补充', requestId='request-1'), user
        )
    setup.commit.assert_not_awaited()
    module.publish_version_changed.assert_not_awaited()


@pytest.mark.parametrize('content', ['', '  ', 'a\x00b', 'x' * 2001])
def test_comment_content_validation(content: str) -> None:
    with pytest.raises(ValidationError):
        ShotGridIssueCommentCreateModel(content=content, requestId='request-1')


@pytest.mark.asyncio
async def test_comment_cursor_page_has_scope_and_limit(setup: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module.ShotGridReviewDao, 'get_issue_comments', AsyncMock(return_value=[saved(), saved()]))
    result = await Service.get_issue_comments(setup, 2, 51, 100, 1, actor())
    assert result.has_next and len(result.rows) == 1 and result.next_cursor == 1
    module.ShotGridReviewDao.get_issue_comments.assert_awaited_once_with(setup, 8, 51, 100, 2)

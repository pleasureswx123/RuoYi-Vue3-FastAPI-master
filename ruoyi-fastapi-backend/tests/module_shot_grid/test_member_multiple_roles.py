from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.project_member_vo import ShotGridProjectMemberAddModel, ShotGridProjectMemberUpdateModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.version_submission_service import ShotGridVersionSubmissionService


def test_multiple_roles_are_normalized_without_losing_creator() -> None:
    member = ShotGridProjectMemberAddModel(userId=2, projectRoles=['creator', 'director', 'creator'])
    assert member.project_roles == ['director', 'creator']
    assert member.project_role == 'director'


def test_legacy_request_becomes_one_role() -> None:
    member = ShotGridProjectMemberUpdateModel(projectRole='creator')
    assert member.project_roles == ['creator']
    assert 'project_roles' in member.model_fields_set


@pytest.mark.parametrize(
    'payload',
    [
        {'projectRoles': []},
        {'projectRoles': None},
        {'projectRoles': ['other']},
        {'projectRoles': ['creator'], 'projectRole': 'creator'},
    ],
)
def test_invalid_role_changes_are_rejected(payload: dict) -> None:
    with pytest.raises(ValidationError):
        ShotGridProjectMemberUpdateModel(**payload)


def test_dual_role_access_allows_both_capabilities() -> None:
    access = ShotGridProjectAccessModel(projectId=1, userId=2, projectRoles=['director', 'creator'])
    assert ShotGridProjectAccessService.require_roles(access, {'director'}) is access
    assert ShotGridProjectAccessService.require_roles(access, {'creator'}) is access


def test_explicit_empty_roles_does_not_restore_legacy_authority() -> None:

    access = ShotGridProjectAccessModel(projectId=1, userId=2, projectRole='director', projectRoles=[])
    with pytest.raises(ShotGridDomainException):
        ShotGridProjectAccessService.require_roles(access, {'director'})


def test_dual_role_member_cannot_submit_another_members_task() -> None:

    access = ShotGridProjectAccessModel(projectId=1, userId=2, projectRoles=['director', 'creator'])
    ShotGridVersionSubmissionService._require_submit_access(access, SimpleNamespace(assignee_user_id=2), 2)
    with pytest.raises(ShotGridDomainException):
        ShotGridVersionSubmissionService._require_submit_access(access, SimpleNamespace(assignee_user_id=3), 2)

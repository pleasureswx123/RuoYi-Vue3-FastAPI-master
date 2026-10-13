"""路由权限和公开状态契约，不冒充真实登录验收。"""

from types import SimpleNamespace

import pytest

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.controller.target_purge_controller import target_purge_controller
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.target_purge_service import ShotGridTargetPurgeService as Service


def test_routes_require_either_force_delete_permission() -> None:
    for route in target_purge_controller.routes:
        checks = [dep.dependency for dep in route.dependencies if isinstance(dep.dependency, CheckUserInterfaceAuth)]
        assert len(checks) == 1
        assert set(checks[0].perm) == {'shotgrid:shot:forceDelete', 'shotgrid:asset:forceDelete'}
        assert not checks[0].is_strict


@pytest.mark.parametrize(
    ('kind', 'project', 'role', 'allowed'),
    [
        ('shot', 10, 'director', True),
        ('asset', 10, 'director', False),
        ('shot', 11, 'director', False),
        ('shot', 10, 'creator', False),
    ],
)
def test_status_permission_does_not_expand_kind_or_project(kind: str, project: int, role: str, allowed: bool) -> None:
    user = CurrentUserModel(
        roles=[], user=UserInfoModel(userId=9, userName='tester'), permissions=['shotgrid:shot:forceDelete']
    )
    access = ShotGridProjectAccessModel(projectId=10, userId=9, projectRole=role)
    if allowed:
        Service.authorize(project, kind, user, access)
    else:
        with pytest.raises(ShotGridDomainException):
            Service.authorize(project, kind, user, access)


@pytest.mark.parametrize('status', ['pending', 'processing', 'retry_wait', 'failed', 'succeeded'])
def test_public_state_never_exposes_paths(status: str) -> None:
    row = SimpleNamespace(
        purge_id=1,
        target_kind='shot',
        target_id=2,
        target_label='0010',
        purge_status=status,
        root_path_snapshot='private',
        nas_manifest=['private'],
        file_manifest=[],
        lease_until=None,
        last_error_key=None,
        last_error_message=None,
    )
    result = Service.status(row).model_dump(by_alias=True)
    assert 'rootPathSnapshot' not in result and 'nasManifest' not in result
    assert result['canRetry'] == (status in {'failed', 'retry_wait'})

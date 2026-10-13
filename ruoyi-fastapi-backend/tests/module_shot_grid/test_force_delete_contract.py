"""强制删除请求必须显式说明原因，保持原批量与乐观锁边界。"""

import pytest
from pydantic import BaseModel, ValidationError

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.asset_crud_vo import ShotGridAssetBatchForceDeleteModel
from module_shot_grid.entity.vo.shot_crud_vo import ShotGridShotBatchForceDeleteModel
from module_shot_grid.service.asset_crud_service import ShotGridAssetCrudService
from module_shot_grid.service.shot_crud_service import ShotGridShotCrudService


@pytest.mark.parametrize(
    ('model', 'key'),
    [(ShotGridShotBatchForceDeleteModel, 'shotId'), (ShotGridAssetBatchForceDeleteModel, 'assetId')],
)
def test_force_delete_requires_explicit_reason_and_unique_targets(model: type[BaseModel], key: str) -> None:
    item = {key: 1, 'lockVersion': 0}
    for payload in (
        {'items': [item]},
        {'items': [item], 'reason': '   '},
        {'items': [], 'reason': '清理测试'},
        {'items': [item, item], 'reason': '清理测试'},
        {'items': [item], 'reason': '清' * 501},
        {'items': [{key: n + 1, 'lockVersion': 0} for n in range(201)], 'reason': '清理测试'},
    ):
        with pytest.raises(ValidationError):
            model.model_validate(payload)
    command = model.model_validate({'items': [item], 'reason': ' 清理测试 '})
    assert command.reason == '清理测试'


@pytest.mark.parametrize('storage_status', [None, 'pending', 'failed', 'migrating'])
@pytest.mark.parametrize('role', ['director', 'creator'])
@pytest.mark.parametrize('project_status', ['active', 'completed', 'archived'])
def test_force_delete_action_matches_storage_and_project_boundary(
    storage_status: str | None, role: str, project_status: str
) -> None:
    user = CurrentUserModel(
        roles=[],
        user=UserInfoModel(userId=9, userName='tester'),
        permissions=[
            'shotgrid:shot:forceDelete',
            'shotgrid:asset:forceDelete',
        ],
    )
    access = ShotGridProjectAccessModel(projectId=10, userId=9, projectRole=role)
    shot_actions = ShotGridShotCrudService._allowed_actions(
        {'lifecycle_status': 'active', 'project_status': project_status, 'storage_status': storage_status},
        user,
        access,
    )
    asset_actions = ShotGridAssetCrudService._asset_allowed_actions(
        user,
        access,
        project_id=10,
        project_status=project_status,
        storage_status=storage_status,
        lifecycle_status='active',
        has_archive_blockers=True,
        can_assign_items=False,
    )
    allowed = role == 'director' and project_status == 'active' and storage_status != 'migrating'
    assert shot_actions == (['shot.forceDelete'] if allowed else [])
    assert asset_actions == (['asset.forceDelete'] if allowed else [])

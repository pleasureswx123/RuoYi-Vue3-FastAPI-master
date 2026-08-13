from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import true

from module_shot_grid.entity.vo.project_option_vo import (
    ShotGridAssetAssigneeOptionQueryModel,
    ShotGridMemberCandidateQueryModel,
    ShotGridProjectPathPreviewRequestModel,
    ShotGridShotAssigneeOptionQueryModel,
)
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.project_option_service import ShotGridProjectOptionService

SERVICE_UNAVAILABLE_STATUS = 503
CANDIDATE_USER_ID = 2


@pytest.mark.asyncio
async def test_storage_root_options_return_only_safe_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    list_options = AsyncMock(
        return_value=[
            {
                'storage_root_id': 10,
                'root_code': 'PLAN',
                'root_name': '策划部',
                'protocol': 'smb_unc',
                'unc_root_path': r'\\192.168.10.64\策划部',
                'last_probe_status': 'healthy',
                'last_probe_time': datetime(2026, 8, 11, 10, 0),
            }
        ]
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_option_service.ShotGridProjectOptionDao.list_storage_root_options',
        list_options,
    )

    result = await ShotGridProjectOptionService.get_storage_root_options(AsyncMock())

    assert result[0].model_dump(by_alias=True) == {
        'storageRootId': 10,
        'rootCode': 'PLAN',
        'rootName': '策划部',
        'protocol': 'smb_unc',
        'uncRootPath': r'\\192.168.10.64\策划部',
        'lastProbeStatus': 'healthy',
        'lastProbeTime': datetime(2026, 8, 11, 10, 0),
    }


@pytest.mark.asyncio
async def test_path_preview_uses_frozen_path_rules_and_reports_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.project_option_service.ShotGridProjectOptionDao.get_storage_root',
        AsyncMock(
            return_value=SimpleNamespace(
                storage_root_id=10,
                root_name='策划部',
                unc_root_path=r'\\192.168.10.64\策划部',
                root_status='enabled',
                last_probe_status='healthy',
            )
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_option_service.ShotGridProjectOptionDao.storage_path_exists',
        AsyncMock(return_value=True),
    )

    result = await ShotGridProjectOptionService.preview_project_path(
        AsyncMock(),
        10,
        ShotGridProjectPathPreviewRequestModel(
            projectName='罗刹夫人',
        ),
    )

    assert result.project_relative_path == r'AI影视短片\罗刹夫人'
    assert result.project_path_preview == r'\\192.168.10.64\策划部\AI影视短片\罗刹夫人'
    assert result.path_conflict is True


@pytest.mark.asyncio
async def test_path_preview_rejects_unhealthy_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.project_option_service.ShotGridProjectOptionDao.get_storage_root',
        AsyncMock(
            return_value=SimpleNamespace(
                storage_root_id=10,
                root_name='策划部',
                unc_root_path=r'\\192.168.10.64\策划部',
                root_status='enabled',
                last_probe_status='unreachable',
            )
        ),
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectOptionService.preview_project_path(
            AsyncMock(),
            10,
            ShotGridProjectPathPreviewRequestModel(
                projectName='罗刹夫人',
            ),
        )

    assert exc_info.value.http_status == SERVICE_UNAVAILABLE_STATUS
    assert exc_info.value.error_key == 'SG_STORAGE_ROOT_UNAVAILABLE'


@pytest.mark.asyncio
async def test_member_candidates_return_page_without_contact_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.project_option_service.ShotGridProjectOptionDao.get_member_candidate_page',
        AsyncMock(
            return_value=(
                [
                    {
                        'user_id': 2,
                        'user_name': 'creator',
                        'nick_name': '制作人员',
                        'avatar': '',
                        'dept_id': 100,
                        'dept_name': '策划部',
                    }
                ],
                1,
            )
        ),
    )

    result = await ShotGridProjectOptionService.get_member_candidate_page(
        AsyncMock(),
        ShotGridMemberCandidateQueryModel(pageNum=1, pageSize=20),
        true(),
    )

    assert result.total == 1
    dumped = result.rows[0].model_dump(by_alias=True)
    assert dumped['userId'] == CANDIDATE_USER_ID
    assert 'email' not in dumped
    assert 'phonenumber' not in dumped


@pytest.mark.asyncio
async def test_shot_assignee_options_return_project_role_and_producer_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.project_option_service.ShotGridProjectOptionDao.get_shot_assignee_option_page',
        AsyncMock(
            return_value=(
                [
                    {
                        'user_id': 7,
                        'user_name': 'yangjingfeng',
                        'nick_name': '杨景锋',
                        'avatar': '',
                        'dept_id': 100,
                        'dept_name': '策划部',
                        'project_role': 'creator',
                        'producer_code': 'YJF',
                    }
                ],
                1,
            )
        ),
    )

    result = await ShotGridProjectOptionService.get_shot_assignee_option_page(
        AsyncMock(),
        1001,
        ShotGridShotAssigneeOptionQueryModel(pageNum=1, pageSize=20),
    )

    assert result.model_dump(by_alias=True) == {
        'rows': [
            {
                'userId': 7,
                'userName': 'yangjingfeng',
                'nickName': '杨景锋',
                'avatar': '',
                'deptId': 100,
                'deptName': '策划部',
                'projectRole': 'creator',
                'producerCode': 'YJF',
            }
        ],
        'pageNum': 1,
        'pageSize': 20,
        'total': 1,
        'hasNext': False,
    }


@pytest.mark.asyncio
async def test_asset_assignee_options_return_the_same_safe_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.project_option_service.ShotGridProjectOptionDao.get_asset_assignee_option_page',
        AsyncMock(
            return_value=(
                [
                    {
                        'user_id': 8,
                        'user_name': 'asset_creator',
                        'nick_name': '资产制作人',
                        'avatar': '',
                        'dept_id': 100,
                        'dept_name': '策划部',
                        'project_role': 'creator',
                        'producer_code': 'AC',
                    }
                ],
                1,
            )
        ),
    )

    result = await ShotGridProjectOptionService.get_asset_assignee_option_page(
        AsyncMock(),
        1001,
        ShotGridAssetAssigneeOptionQueryModel(pageNum=1, pageSize=20),
    )

    assert result.rows[0].model_dump(by_alias=True) == {
        'userId': 8,
        'userName': 'asset_creator',
        'nickName': '资产制作人',
        'avatar': '',
        'deptId': 100,
        'deptName': '策划部',
        'projectRole': 'creator',
        'producerCode': 'AC',
    }

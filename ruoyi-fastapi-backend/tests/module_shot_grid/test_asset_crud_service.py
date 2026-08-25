from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.dao.asset_crud_dao import ShotGridAssetCrudDao
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.asset_crud_vo import (
    ShotGridAssetArchiveModel,
    ShotGridAssetCreateModel,
    ShotGridAssetItemUpdateModel,
    ShotGridAssetUpdateModel,
)
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.asset_crud_service import ShotGridAssetCrudService

PROJECT_ID = 10
ASSET_ID = 20
ASSET_ITEM_ID = 30
ASSIGNEE_USER_ID = 2
UPDATED_SORT_ORDER = 20
RENAMED_TASK_LOCK_VERSION = 3


def _current_user() -> CurrentUserModel:
    return CurrentUserModel(
        permissions=[
            'shotgrid:asset:add',
            'shotgrid:asset:edit',
            'shotgrid:asset:archive',
            'shotgrid:task:assign',
        ],
        roles=[],
        user=UserInfoModel(userId=1, userName='director'),
    )


def _access(*, role: str = 'director', project_id: int = PROJECT_ID) -> ShotGridProjectAccessModel:
    return ShotGridProjectAccessModel(
        projectId=project_id,
        userId=1,
        projectRole=role,
        hasAllScope=False,
    )


def _command() -> ShotGridAssetCreateModel:
    item: dict[str, object] = {
        'productionItem': '主视角',
        'description': '制作分项描述',
        'sortOrder': 10,
    }
    return ShotGridAssetCreateModel(
        assetType='Environment',
        assetName='动力舱室内',
        description='场景资产',
        sortOrder=10,
        items=[item],
    )


def _patch_create_dependencies(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    async def add_asset(_db: Any, asset: Any) -> Any:
        asset.asset_id = ASSET_ID
        return asset

    async def add_item(_db: Any, item: Any) -> Any:
        item.asset_item_id = ASSET_ITEM_ID
        return item

    mocks = {
        'project': AsyncMock(return_value=SimpleNamespace(project_status='active')),
        'access': AsyncMock(return_value=_access()),
        'storage': AsyncMock(return_value='ready'),
        'conflict': AsyncMock(return_value=False),
        'add_asset': AsyncMock(side_effect=add_asset),
        'add_item': AsyncMock(side_effect=add_item),
        'audit': AsyncMock(),
        'detail': AsyncMock(return_value=object()),
    }
    targets = {
        'project': 'ShotGridProjectDao.get_project_by_id',
        'access': 'ShotGridProjectAccessService.resolve_access',
        'storage': 'ShotGridAssetCrudDao.get_project_storage_status',
        'conflict': 'ShotGridAssetCrudDao.asset_name_or_path_exists',
        'add_asset': 'ShotGridAssetCrudDao.add_asset',
        'add_item': 'ShotGridAssetCrudDao.add_item',
        'audit': 'ShotGridProjectAuditDao.add_success_log',
        'detail': 'ShotGridAssetCrudService._build_asset_detail',
    }
    for key, target in targets.items():
        monkeypatch.setattr(f'module_shot_grid.service.asset_crud_service.{target}', mocks[key])
    return mocks


@pytest.mark.asyncio
async def test_create_asset_persists_items_and_audit_without_directory_or_task_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_create_dependencies(monkeypatch)
    db = AsyncMock()

    result = await ShotGridAssetCrudService.create_asset(
        db,
        PROJECT_ID,
        _command(),
        _current_user(),
        _access(),
    )

    assert result is mocks['detail'].return_value
    mocks['project'].assert_awaited_once_with(db, PROJECT_ID, for_update=True)
    asset = mocks['add_asset'].await_args.args[1]
    assert asset.asset_name_key == '动力舱室内'
    assert asset.storage_path_key == 'asset\\environment\\动力舱室内'
    assert not hasattr(ShotGridAssetCrudDao, 'add_storage_operation')
    mocks['audit'].assert_awaited_once()
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_item_has_no_task_creation_or_assignment_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_create_dependencies(monkeypatch)
    db = AsyncMock()

    await ShotGridAssetCrudService.create_asset(
        db,
        PROJECT_ID,
        _command(),
        _current_user(),
        _access(),
    )

    assert not hasattr(ShotGridAssetCrudDao, 'add_task')
    assert not hasattr(ShotGridAssetCrudDao, 'get_assignable_member')
    db.commit.assert_awaited_once()


def test_asset_write_service_revalidates_project_role_and_scope() -> None:
    with pytest.raises(ShotGridDomainException) as creator_error:
        ShotGridAssetCrudService._require_write_access(_access(role='creator'), PROJECT_ID, 1)
    with pytest.raises(ShotGridDomainException) as cross_project_error:
        ShotGridAssetCrudService._require_write_access(_access(project_id=99), PROJECT_ID, 1)
    with pytest.raises(ShotGridDomainException) as actor_mismatch_error:
        ShotGridAssetCrudService._require_write_access(_access(), PROJECT_ID, 2)

    assert creator_error.value.error_key == 'SG_PROJECT_ACCESS_DENIED'
    assert cross_project_error.value.error_key == 'SG_PROJECT_ACCESS_DENIED'
    assert actor_mismatch_error.value.error_key == 'SG_PROJECT_ACCESS_DENIED'


@pytest.mark.asyncio
async def test_asset_update_changes_only_non_identity_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = SimpleNamespace(
        asset_id=ASSET_ID,
        project_id=PROJECT_ID,
        asset_type='Environment',
        asset_name='动力舱室内',
        asset_name_key='动力舱室内',
        storage_dir_name='动力舱室内',
        storage_path_key='asset\\environment\\动力舱室内',
        description='旧描述',
        sort_order=10,
        remark=None,
        lifecycle_status='active',
        lock_version=0,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudService._lock_writable_project',
        AsyncMock(),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudService._lock_active_asset',
        AsyncMock(return_value=asset),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridProjectAuditDao.add_success_log',
        AsyncMock(),
    )
    detail = object()
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudService._build_asset_detail',
        AsyncMock(return_value=detail),
    )
    db = AsyncMock()

    result = await ShotGridAssetCrudService.update_asset(
        db,
        PROJECT_ID,
        ASSET_ID,
        ShotGridAssetUpdateModel(
            description='新描述',
            sortOrder=UPDATED_SORT_ORDER,
            lockVersion=0,
        ),
        _current_user(),
        _access(),
    )

    assert result is detail
    assert asset.asset_type == 'Environment'
    assert asset.asset_name == '动力舱室内'
    assert asset.storage_dir_name == '动力舱室内'
    assert asset.storage_path_key == 'asset\\environment\\动力舱室内'
    assert asset.description == '新描述'
    assert asset.sort_order == UPDATED_SORT_ORDER
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_item_update_preserves_omitted_fields_and_freezes_all_metadata_after_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = SimpleNamespace(asset_id=ASSET_ID)
    item = SimpleNamespace(
        asset_item_id=ASSET_ITEM_ID,
        production_item='主视角',
        production_item_key='主视角',
        description='旧描述',
        sort_order=10,
        remark='旧备注',
    )
    has_versions = AsyncMock(return_value=True)
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudDao.has_versions_for_item',
        has_versions,
    )

    unchanged = await ShotGridAssetCrudService._resolve_item_update(
        AsyncMock(),
        project_id=PROJECT_ID,
        asset=asset,
        item=item,
        command=ShotGridAssetItemUpdateModel(lockVersion=0),
    )
    assert unchanged == ('主视角', '主视角', '旧描述', 10, '旧备注')
    has_versions.assert_not_awaited()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridAssetCrudService._resolve_item_update(
            AsyncMock(),
            project_id=PROJECT_ID,
            asset=asset,
            item=item,
            command=ShotGridAssetItemUpdateModel(description='新描述', lockVersion=0),
        )

    assert exc_info.value.error_key == 'SG_ASSET_VERSIONED_METADATA_IMMUTABLE'
    has_versions.assert_awaited_once()


@pytest.mark.asyncio
async def test_item_rename_without_versions_syncs_existing_task_name_and_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = SimpleNamespace(asset_id=ASSET_ID, asset_name='动力舱室内')
    item = SimpleNamespace(
        asset_item_id=ASSET_ITEM_ID,
        asset_id=ASSET_ID,
        lifecycle_status='active',
        lock_version=0,
        production_item='主视角',
        production_item_key='主视角',
        description='旧描述',
        sort_order=10,
        remark=None,
        update_by='old',
        update_time=None,
    )
    task = SimpleNamespace(
        assignee_user_id=ASSIGNEE_USER_ID,
        requirements='原要求',
        task_name='动力舱室内 - 主视角',
        task_status='not_started',
        lock_version=2,
        update_by='old',
        update_time=None,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudService._lock_writable_project',
        AsyncMock(),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudService._lock_active_asset',
        AsyncMock(return_value=asset),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudDao.get_asset_item',
        AsyncMock(return_value=item),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudService._resolve_item_update',
        AsyncMock(return_value=('恐怖气氛主视角', '恐怖气氛主视角', '旧描述', 10, None)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudService._get_item_task_for_update',
        AsyncMock(return_value=task),
    )
    audit = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudService._audit',
        audit,
    )
    expected = object()
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudService._get_item_model',
        AsyncMock(return_value=expected),
    )
    db = AsyncMock()

    result = await ShotGridAssetCrudService.update_asset_item(
        db,
        PROJECT_ID,
        ASSET_ITEM_ID,
        ShotGridAssetItemUpdateModel(
            productionItem='恐怖气氛主视角',
            lockVersion=0,
        ),
        _current_user(),
        _access(),
    )

    assert result is expected
    assert item.production_item == '恐怖气氛主视角'
    assert item.lock_version == 1
    assert task.task_name == '动力舱室内 - 恐怖气氛主视角'
    assert task.lock_version == RENAMED_TASK_LOCK_VERSION
    assert task.update_by == 'director'
    assert task.update_time == item.update_time
    assert audit.await_args.kwargs['result']['taskLockVersion'] == RENAMED_TASK_LOCK_VERSION
    db.flush.assert_awaited_once()
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_started_asset_item_cannot_be_edited_even_before_first_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = SimpleNamespace(asset_id=ASSET_ID, asset_name='动力舱室内')
    item = SimpleNamespace(asset_item_id=ASSET_ITEM_ID, asset_id=ASSET_ID, lifecycle_status='active', lock_version=0)
    resolve_update = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudService._lock_writable_project',
        AsyncMock(),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudService._lock_active_asset',
        AsyncMock(return_value=asset),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudDao.get_asset_item',
        AsyncMock(return_value=item),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudService._get_item_task_for_update',
        AsyncMock(return_value=SimpleNamespace(task_status='in_progress')),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudService._resolve_item_update',
        resolve_update,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridAssetCrudService.update_asset_item(
            db,
            PROJECT_ID,
            ASSET_ITEM_ID,
            ShotGridAssetItemUpdateModel(description='不应保存', lockVersion=0),
            _current_user(),
            _access(),
        )

    assert exc_info.value.error_key == 'SG_ASSET_ITEM_PRODUCTION_STARTED'
    resolve_update.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.parametrize(
    ('operation_status', 'directory_status'),
    [
        ('pending', 'pending'),
        ('processing', 'pending'),
        ('retry_wait', 'pending'),
        ('succeeded', 'ready'),
        ('failed', 'failed'),
        (None, 'not_created'),
    ],
)
def test_directory_status_is_read_only_mapping(operation_status: str | None, directory_status: str) -> None:
    assert ShotGridAssetCrudService._directory_status(operation_status) == directory_status


@pytest.mark.asyncio
async def test_asset_archive_rejects_started_item_task_and_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    asset = SimpleNamespace(
        asset_id=ASSET_ID,
        project_id=PROJECT_ID,
        lifecycle_status='active',
        lock_version=0,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudService._lock_writable_project',
        AsyncMock(),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudService._lock_active_asset',
        AsyncMock(return_value=asset),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudDao.get_usage_shot_count',
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudDao.get_active_items_for_update',
        AsyncMock(return_value=[SimpleNamespace(asset_item_id=ASSET_ITEM_ID)]),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudDao.get_task_for_item',
        AsyncMock(return_value=SimpleNamespace(task_status='in_progress')),
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridAssetCrudService.archive_asset(
            db,
            PROJECT_ID,
            ASSET_ID,
            ShotGridAssetArchiveModel(reason='不再使用', lockVersion=0),
            _current_user(),
            _access(),
        )

    assert exc_info.value.error_key == 'SG_ASSET_TASK_ALREADY_STARTED'
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('project_status', ['completed', 'archived'])
async def test_asset_writes_reject_terminal_project_before_access_or_storage_checks(
    monkeypatch: pytest.MonkeyPatch,
    project_status: str,
) -> None:
    resolve_access = AsyncMock()
    storage_status = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridProjectDao.get_project_by_id',
        AsyncMock(return_value=SimpleNamespace(project_status=project_status)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridProjectAccessService.resolve_access',
        resolve_access,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudDao.get_project_storage_status',
        storage_status,
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridAssetCrudService._lock_writable_project(
            AsyncMock(),
            PROJECT_ID,
            _current_user(),
            1,
        )

    assert exc_info.value.error_key == 'SG_INVALID_STATE_TRANSITION'
    resolve_access.assert_not_awaited()
    storage_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_asset_write_rechecks_director_after_project_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridProjectDao.get_project_by_id',
        AsyncMock(return_value=SimpleNamespace(project_status='active')),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridProjectAccessService.resolve_access',
        AsyncMock(return_value=_access(role='creator')),
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridAssetCrudService._lock_writable_project(
            AsyncMock(),
            PROJECT_ID,
            _current_user(),
            1,
        )

    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'


def test_asset_thumbnail_uses_latest_version_and_parent_uses_first_sorted_item_with_thumbnail() -> None:
    task_refs = [
        {'asset_id': ASSET_ID, 'asset_item_id': 31, 'sort_order': 20, 'task_id': 201},
        {'asset_id': ASSET_ID, 'asset_item_id': 30, 'sort_order': 10, 'task_id': 200},
    ]
    version_rows = [
        {
            'task_id': 200,
            'version_id': 20,
            'version_status': 'pending_review',
            'submitted_time': None,
            'thumbnail_file_id': None,
            'thumbnail_business_file_name': None,
        },
        {
            'task_id': 200,
            'version_id': 19,
            'version_status': 'final',
            'submitted_time': None,
            'thumbnail_file_id': 'old-thumbnail',
            'thumbnail_business_file_name': '旧缩略图.jpg',
        },
        {
            'task_id': 201,
            'version_id': 21,
            'version_status': 'pending_review',
            'submitted_time': None,
            'thumbnail_file_id': 'current-thumbnail',
            'thumbnail_business_file_name': '当前缩略图.jpg',
        },
    ]

    thumbnails = ShotGridAssetCrudService._representative_thumbnail_map(task_refs, version_rows)

    assert thumbnails[ASSET_ID].model_dump(by_alias=True) == {
        'fileId': 'current-thumbnail',
        'name': '当前缩略图.jpg',
        'url': '/shot-grid/versions/21/files/current-thumbnail/download',
    }


def test_asset_and_item_allowed_actions_are_server_side_state_mirrors() -> None:
    asset_actions = ShotGridAssetCrudService._asset_allowed_actions(
        _current_user(),
        _access(),
        project_id=PROJECT_ID,
        project_status='active',
        storage_status='ready',
        lifecycle_status='active',
        has_archive_blockers=False,
        can_assign_items=True,
    )
    item_actions = ShotGridAssetCrudService._item_allowed_actions(
        _current_user(),
        _access(),
        project_id=PROJECT_ID,
        project_status='active',
        storage_status='ready',
        asset_lifecycle_status='active',
        item_lifecycle_status='active',
        production_item='主视角',
        has_versions=False,
        task_status=None,
        has_uncommitted_submission=False,
    )

    assert asset_actions == ['asset.edit', 'asset.archive', 'assetItem.add', 'task.assign']
    assert item_actions == ['assetItem.edit', 'assetItem.archive', 'task.assign']
    assert ShotGridAssetCrudService._item_allowed_actions(
        _current_user(),
        _access(),
        project_id=PROJECT_ID,
        project_status='active',
        storage_status='ready',
        asset_lifecycle_status='active',
        item_lifecycle_status='active',
        production_item='主视角',
        has_versions=False,
        task_status='in_progress',
        has_uncommitted_submission=False,
    ) == ['task.assign']

    assert (
        ShotGridAssetCrudService._asset_allowed_actions(
            _current_user(),
            _access(),
            project_id=PROJECT_ID,
            project_status='completed',
            storage_status='ready',
            lifecycle_status='active',
            has_archive_blockers=False,
            can_assign_items=False,
        )
        == []
    )
    assert (
        ShotGridAssetCrudService._item_allowed_actions(
            _current_user(),
            _access(),
            project_id=PROJECT_ID,
            project_status='active',
            storage_status='ready',
            asset_lifecycle_status='active',
            item_lifecycle_status='active',
            production_item='主视角',
            has_versions=True,
            task_status='in_progress',
            has_uncommitted_submission=True,
        )
        == []
    )

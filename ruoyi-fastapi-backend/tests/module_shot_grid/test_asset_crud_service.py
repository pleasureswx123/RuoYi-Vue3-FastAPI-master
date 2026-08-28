from datetime import datetime
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
    ShotGridAssetItemDeleteModel,
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
DELETED_ITEM_LOCK_VERSION = 1
CONFLICT_STATUS = 409


def test_preparing_item_and_mixed_asset_status_keep_directory_preparation_visible() -> None:
    task = SimpleNamespace(task_status='preparing')
    assert ShotGridAssetCrudService._item_status(task, False) == 'preparing'
    assert ShotGridAssetCrudService._aggregate_asset_status(['unassigned', 'not_started', 'preparing']) == 'preparing'
    assert ShotGridAssetCrudService._aggregate_asset_status(['preparing', 'in_progress']) == 'in_progress'


def test_item_time_groups_compress_equal_task_inputs_without_changing_time_or_status() -> None:
    end = datetime(2026, 8, 30, 12)
    groups = ShotGridAssetCrudService._item_time_groups(
        [('in_progress', end), (None, None), ('in_progress', end), ('completed', end), (None, None)]
    )
    assert [group.model_dump(by_alias=True) for group in groups] == [
        {'taskStatus': 'in_progress', 'expectedEndTime': end, 'itemCount': 2},
        {'taskStatus': None, 'expectedEndTime': None, 'itemCount': 2},
        {'taskStatus': 'completed', 'expectedEndTime': end, 'itemCount': 1},
    ]
    assert ShotGridAssetCrudService._item_time_groups([]) == []


@pytest.mark.parametrize(
    ('role', 'permitted', 'valid_assignee', 'can_start'),
    [
        ('director', True, True, True),
        ('creator', True, True, False),
        ('director', False, True, False),
        ('director', True, False, False),
    ],
)
def test_asset_item_start_action_requires_manager_permission_and_valid_assignee(
    role: str, *, permitted: bool, valid_assignee: bool, can_start: bool
) -> None:
    user = _current_user()
    user.user = UserInfoModel(userId=9, userName='director')
    access = _access(role=role)
    access.user_id = 9
    if permitted:
        user.permissions.append('shotgrid:task:start')
    actions = ShotGridAssetCrudService._item_allowed_actions(
        user,
        access,
        project_id=PROJECT_ID,
        project_status='active',
        storage_status='ready',
        asset_lifecycle_status='active',
        item_lifecycle_status='active',
        production_item='主视角',
        has_versions=False,
        task_status='not_started',
        has_uncommitted_submission=False,
        assignee_valid=valid_assignee,
    )
    assert ('task.start' in actions) is can_start


def test_asset_parent_start_action_only_opens_selection_when_a_startable_item_exists() -> None:
    user = _current_user()
    for has_startable_item in [True, False]:
        actions = ShotGridAssetCrudService._asset_allowed_actions(
            user,
            _access(),
            project_id=PROJECT_ID,
            project_status='active',
            storage_status='ready',
            lifecycle_status='active',
            has_archive_blockers=True,
            can_assign_items=False,
            can_start_items=has_startable_item,
        )
        assert ('task.start' in actions) is has_startable_item


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
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudDao.has_started_tasks_for_asset',
        AsyncMock(return_value=False),
    )
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
@pytest.mark.parametrize(
    ('blocker', 'error_key'),
    [
        ('started', 'SG_ASSET_TASK_ALREADY_STARTED'),
        ('version', 'SG_ASSET_HAS_VERSION'),
        ('submission', 'SG_ASSET_ITEM_SUBMISSION_IN_PROGRESS'),
    ],
)
async def test_asset_archive_rejects_item_blockers_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch, blocker: str, error_key: str
) -> None:
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
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudDao.get_items_for_update',
        AsyncMock(return_value=[SimpleNamespace(asset_item_id=ASSET_ITEM_ID)]),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudDao.get_task_for_item',
        AsyncMock(
            return_value=SimpleNamespace(
                task_id=71, task_status='in_progress' if blocker == 'started' else 'not_started'
            )
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudDao.has_versions_for_item',
        AsyncMock(return_value=blocker == 'version'),
    )
    monkeypatch.setattr(
        'module_shot_grid.dao.task_dao.ShotGridTaskDao.get_uncommitted_submission_for_update',
        AsyncMock(return_value=SimpleNamespace(submission_status='failed') if blocker == 'submission' else None),
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

    assert exc_info.value.error_key == error_key
    assert asset.lifecycle_status == 'active'
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


def _patch_item_delete_dependencies(monkeypatch: pytest.MonkeyPatch) -> tuple[SimpleNamespace, dict[str, AsyncMock]]:
    mocks = _patch_create_dependencies(monkeypatch)
    asset = SimpleNamespace(asset_id=ASSET_ID, lifecycle_status='active', del_flag='0')
    item = SimpleNamespace(
        asset_item_id=ASSET_ITEM_ID,
        asset_id=ASSET_ID,
        project_id=PROJECT_ID,
        lifecycle_status='active',
        del_flag='0',
        lock_version=0,
        production_item='误建分项',
        update_by='old',
        update_time=None,
    )
    for name, target, result in [
        ('asset', 'get_asset', asset),
        ('item', 'get_asset_item', item),
        ('task', 'get_task_for_item', None),
        ('versions', 'has_versions_for_item', False),
        ('delete_task', 'delete_not_started_task', True),
    ]:
        mocks[name] = AsyncMock(return_value=result)
        monkeypatch.setattr(ShotGridAssetCrudDao, target, mocks[name])
    mocks['submission'] = AsyncMock(return_value=None)
    monkeypatch.setattr(
        'module_shot_grid.dao.task_dao.ShotGridTaskDao.get_uncommitted_submission_for_update', mocks['submission']
    )
    return item, mocks


@pytest.mark.asyncio
@pytest.mark.parametrize('with_task', [False, True])
async def test_delete_item_soft_deletes_only_target_and_unstarted_task_with_audit(
    monkeypatch: pytest.MonkeyPatch, *, with_task: bool
) -> None:
    item, mocks = _patch_item_delete_dependencies(monkeypatch)
    if with_task:
        mocks['task'].return_value = SimpleNamespace(task_id=71, task_status='not_started')
    db = AsyncMock()

    result = await ShotGridAssetCrudService.delete_asset_item(
        db,
        PROJECT_ID,
        ASSET_ITEM_ID,
        ShotGridAssetItemDeleteModel(reason='误建分项', lockVersion=0),
        _current_user(),
        _access(),
    )

    assert result.deleted_asset_item_id == ASSET_ITEM_ID
    assert result.asset_id == ASSET_ID
    assert item.del_flag == '2'
    assert item.lifecycle_status == 'archived'
    assert item.lock_version == DELETED_ITEM_LOCK_VERSION
    assert mocks['asset'].return_value.del_flag == '0'
    assert mocks['audit'].await_args.kwargs['result']['deletedAssetItemId'] == ASSET_ITEM_ID
    if with_task:
        mocks['delete_task'].assert_awaited_once_with(db, task_id=71, actor_name='director', now=item.update_time)
    else:
        mocks['delete_task'].assert_not_awaited()
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('task_status', ['preparing', 'in_progress', 'pending_review', 'revision', 'completed'])
async def test_delete_item_rejects_any_task_that_has_started(monkeypatch: pytest.MonkeyPatch, task_status: str) -> None:
    item, mocks = _patch_item_delete_dependencies(monkeypatch)
    mocks['task'].return_value = SimpleNamespace(task_id=71, task_status=task_status)
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as error:
        await ShotGridAssetCrudService.delete_asset_item(
            db,
            PROJECT_ID,
            ASSET_ITEM_ID,
            ShotGridAssetItemDeleteModel(reason='误建', lockVersion=0),
            _current_user(),
            _access(),
        )

    assert error.value.error_key == 'SG_ASSET_TASK_ALREADY_STARTED'
    assert item.del_flag == '0'
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('blocker', 'error_key'),
    [
        ('versions', 'SG_ASSET_HAS_VERSION'),
        ('submission', 'SG_ASSET_ITEM_SUBMISSION_IN_PROGRESS'),
        ('lock', 'SG_OPTIMISTIC_LOCK_CONFLICT'),
        ('archived', 'SG_INVALID_STATE_TRANSITION'),
        ('task_changed', 'SG_OPTIMISTIC_LOCK_CONFLICT'),
    ],
)
async def test_delete_item_rechecks_version_submission_and_lock_before_mutation(
    monkeypatch: pytest.MonkeyPatch, blocker: str, error_key: str
) -> None:
    item, mocks = _patch_item_delete_dependencies(monkeypatch)
    mocks['task'].return_value = SimpleNamespace(task_id=71, task_status='not_started')
    if blocker in {'versions', 'submission'}:
        mocks[blocker].return_value = True
    elif blocker == 'lock':
        item.lock_version = 1
    elif blocker == 'archived':
        item.lifecycle_status = 'archived'
    else:
        mocks['delete_task'].return_value = False
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as error:
        await ShotGridAssetCrudService.delete_asset_item(
            db,
            PROJECT_ID,
            ASSET_ITEM_ID,
            ShotGridAssetItemDeleteModel(reason='误建', lockVersion=0),
            _current_user(),
            _access(),
        )

    assert error.value.error_key == error_key
    assert error.value.http_status == CONFLICT_STATUS
    assert item.del_flag == '0'
    mocks['audit'].assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('blocker', ['completed', 'archived', 'storage', 'role', 'asset_archived', 'missing'])
async def test_delete_item_preserves_project_scope_and_lifecycle_guards(
    monkeypatch: pytest.MonkeyPatch, blocker: str
) -> None:
    item, mocks = _patch_item_delete_dependencies(monkeypatch)
    if blocker in {'completed', 'archived'}:
        mocks['project'].return_value.project_status = blocker
    elif blocker == 'storage':
        mocks['storage'].return_value = 'failed'
    elif blocker == 'role':
        mocks['access'].return_value = _access(role='creator')
    elif blocker == 'asset_archived':
        mocks['asset'].return_value.lifecycle_status = 'archived'
    else:
        mocks['item'].return_value = None
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException):
        await ShotGridAssetCrudService.delete_asset_item(
            db,
            PROJECT_ID,
            ASSET_ITEM_ID,
            ShotGridAssetItemDeleteModel(reason='误建', lockVersion=0),
            _current_user(),
            _access(),
        )

    assert item.del_flag == '0'
    mocks['delete_task'].assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_item_rolls_back_when_audit_cannot_be_persisted(monkeypatch: pytest.MonkeyPatch) -> None:
    _item, mocks = _patch_item_delete_dependencies(monkeypatch)
    mocks['audit'].side_effect = RuntimeError('审计写入失败')
    db = AsyncMock()
    with pytest.raises(RuntimeError, match='审计写入失败'):
        await ShotGridAssetCrudService.delete_asset_item(
            db,
            PROJECT_ID,
            ASSET_ITEM_ID,
            ShotGridAssetItemDeleteModel(reason='误建', lockVersion=0),
            _current_user(),
            _access(),
        )
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.parametrize(
    ('task_status', 'has_versions', 'has_submission', 'can_delete'),
    [
        (None, False, False, True),
        ('not_started', False, False, True),
        ('preparing', False, False, False),
        ('in_progress', False, False, False),
        ('pending_review', False, False, False),
        ('revision', False, False, False),
        ('completed', False, False, False),
        ('not_started', True, False, False),
        ('not_started', False, True, False),
    ],
)
def test_item_delete_action_is_limited_to_unstarted_items_without_versions_or_submissions(
    task_status: str | None, *, has_versions: bool, has_submission: bool, can_delete: bool
) -> None:
    actions = ShotGridAssetCrudService._item_allowed_actions(
        _current_user(),
        _access(),
        project_id=PROJECT_ID,
        project_status='active',
        storage_status='ready',
        asset_lifecycle_status='active',
        item_lifecycle_status='active',
        production_item='误建分项',
        has_versions=has_versions,
        task_status=task_status,
        has_uncommitted_submission=has_submission,
    )
    assert ('assetItem.delete' in actions) is can_delete


@pytest.mark.parametrize(
    ('task_status', 'can_assign'),
    [
        (None, True),
        ('not_started', True),
        ('preparing', False),
        ('in_progress', False),
        ('pending_review', False),
        ('revision', False),
        ('completed', False),
    ],
)
def test_item_assignment_action_is_only_available_before_start(task_status: str | None, *, can_assign: bool) -> None:
    actions = ShotGridAssetCrudService._item_allowed_actions(
        _current_user(),
        _access(),
        project_id=PROJECT_ID,
        project_status='active',
        storage_status='ready',
        asset_lifecycle_status='active',
        item_lifecycle_status='active',
        production_item='主视角',
        has_versions=False,
        task_status=task_status,
        has_uncommitted_submission=False,
    )
    assert ('task.assign' in actions) is can_assign


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
    assert item_actions == ['assetItem.edit', 'assetItem.archive', 'assetItem.delete', 'task.assign']
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
            has_versions=False,
            task_status='in_progress',
            has_uncommitted_submission=False,
        )
        == []
    )

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

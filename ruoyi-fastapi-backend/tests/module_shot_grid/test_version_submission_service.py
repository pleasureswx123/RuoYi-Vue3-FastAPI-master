from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.controller.version_submission_controller import version_submission_controller
from module_shot_grid.dao.version_submission_dao import ShotGridVersionSubmissionDao
from module_shot_grid.entity.do.version_do import ShotGridVersionSubmission
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.version_submission_vo import (
    ShotGridVersionSubmissionCreateModel,
    ShotGridVersionSubmissionPreflightModel,
)
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.version_publish_path_adapter import VersionPublishPathAdapterError
from module_shot_grid.service.version_submission_service import ShotGridVersionSubmissionService

PROJECT_ID = 10
TASK_ID = 20
SUBMISSION_ID = 30
VERSION_ID = 40
REVIEW_LIST_ID = 50
USER_ID = 60
FILE_ID = '5ed39e04-2f29-45ab-a58c-4f8168f5131a'
FILE_HASH = 'a' * 64
MAX_BUSINESS_FILENAME_LENGTH = 255
MAX_PLATFORM_AUDIT_METHOD_LENGTH = 100
PREFLIGHT_ROLLBACK_COUNT = 2
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE_ENTITY = 422
HTTP_SERVICE_UNAVAILABLE = 503


def _shot_context() -> dict[str, object]:
    return {
        'task_kind': 'shot_video',
        'project_code': 'WGZR',
        'producer_code': 'YJF',
        'episode_no': 1,
        'scene_no': 1,
        'shot_no': 1,
        'episode_storage_dir_name': 'EP01',
        'shot_storage_dir_name': 'S001',
    }


def _ready_shot_context() -> dict[str, object]:
    return {
        **_shot_context(),
        'assignee_user_id': USER_ID,
        'project_status': 'active',
        'task_status': 'in_progress',
        'storage_status': 'ready',
        'directory_operation_status': 'succeeded',
        'member_status': 'active',
        'assignee_user_status': '0',
        'assignee_user_del_flag': '0',
        'episode_lifecycle_status': 'active',
        'scene_lifecycle_status': 'active',
        'shot_lifecycle_status': 'active',
    }


def _current_user() -> CurrentUserModel:
    return CurrentUserModel(
        permissions=['shotgrid:version:add'],
        roles=[],
        user=UserInfoModel(userId=USER_ID, userName='producer'),
    )


def _asset_context(*, production_item: str | None = '动力舱恐怖气氛主视角') -> dict[str, object]:
    return {
        'task_kind': 'asset_image',
        'project_code': 'WGZR',
        'producer_code': 'YJF',
        'asset_type': 'Environment',
        'asset_name': '动力舱室内',
        'production_item': production_item,
        'asset_storage_dir_name': '动力舱室内',
    }


def _ready_asset_context(*, production_item: str | None = '动力舱恐怖气氛主视角') -> dict[str, object]:
    return {
        **_asset_context(production_item=production_item),
        'assignee_user_id': USER_ID,
        'project_status': 'active',
        'task_status': 'in_progress',
        'storage_status': 'ready',
        'directory_operation_status': 'succeeded',
        'member_status': 'active',
        'assignee_user_status': '0',
        'assignee_user_del_flag': '0',
        'asset_lifecycle_status': 'active',
        'asset_item_lifecycle_status': 'active',
    }


class _RollbackExpiringSource:
    """模拟 AsyncSession.rollback 后禁止同步读取的持久 ORM 文件对象。"""

    def __init__(self, storage_key: str) -> None:
        self._storage_key = storage_key
        self.expired = False

    @property
    def storage_key(self) -> str:
        if self.expired:
            raise AssertionError('rollback 后不得再次读取预检 ORM 对象')
        return self._storage_key


def _patch_submit_preflight(
    monkeypatch: pytest.MonkeyPatch,
    *,
    context: dict[str, object],
    access: ShotGridProjectAccessModel | None = None,
    unresolved: bool = False,
) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.get_task_project_id',
        AsyncMock(return_value=PROJECT_ID),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridProjectAccessService.resolve_access',
        AsyncMock(
            return_value=access
            or ShotGridProjectAccessModel(
                projectId=PROJECT_ID,
                userId=USER_ID,
                projectRole='creator',
                hasAllScope=False,
            )
        ),
    )
    monkeypatch.setattr(
        ShotGridVersionSubmissionService,
        '_require_task_context',
        AsyncMock(return_value=context),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.has_unresolved_submission',
        AsyncMock(return_value=unresolved),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.next_reserved_version_no',
        AsyncMock(return_value=2),
    )


@pytest.mark.asyncio
async def test_submit_preflight_returns_stable_ready_contract_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_submit_preflight(monkeypatch, context=_ready_shot_context())
    db = AsyncMock()

    result = await ShotGridVersionSubmissionService.preflight_submission(
        db,
        TASK_ID,
        ShotGridVersionSubmissionPreflightModel(
            fileName='result.MOV',
            fileSize=8,
            changelog='完成首版',
        ),
        _current_user(),
    )

    assert result.model_dump(by_alias=True) == {
        'ready': True,
        'taskId': TASK_ID,
        'taskKind': 'shot_video',
        'taskStatus': 'in_progress',
        'fileExtension': 'mov',
        'allowedActions': ['version.add'],
    }
    db.commit.assert_not_awaited()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_preflight_returns_404_before_access_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    resolve_access = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.get_task_project_id',
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridProjectAccessService.resolve_access',
        resolve_access,
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridVersionSubmissionService.preflight_submission(
            AsyncMock(),
            TASK_ID,
            ShotGridVersionSubmissionPreflightModel(fileName='result.mov', fileSize=8, changelog='完成首版'),
            _current_user(),
        )

    assert exc_info.value.http_status == HTTP_NOT_FOUND
    assert exc_info.value.error_key == 'SG_TASK_NOT_FOUND'
    resolve_access.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_preflight_rejects_non_assignee_creator_with_403(monkeypatch: pytest.MonkeyPatch) -> None:
    context = {**_ready_shot_context(), 'assignee_user_id': USER_ID + 1}
    _patch_submit_preflight(monkeypatch, context=context)

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridVersionSubmissionService.preflight_submission(
            AsyncMock(),
            TASK_ID,
            ShotGridVersionSubmissionPreflightModel(fileName='result.mov', fileSize=8, changelog='完成首版'),
            _current_user(),
        )

    assert exc_info.value.http_status == HTTP_FORBIDDEN
    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'


@pytest.mark.asyncio
async def test_submit_preflight_rejects_unresolved_submission_with_409(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_submit_preflight(monkeypatch, context=_ready_shot_context(), unresolved=True)

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridVersionSubmissionService.preflight_submission(
            AsyncMock(),
            TASK_ID,
            ShotGridVersionSubmissionPreflightModel(fileName='result.mov', fileSize=8, changelog='完成首版'),
            _current_user(),
        )

    assert exc_info.value.http_status == HTTP_CONFLICT
    assert exc_info.value.error_key == 'SG_VERSION_SUBMISSION_ACTIVE'


@pytest.mark.asyncio
async def test_submit_preflight_reuses_context_422_and_does_not_check_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_submit_preflight(monkeypatch, context=_ready_asset_context(production_item=None))

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridVersionSubmissionService.preflight_submission(
            AsyncMock(),
            TASK_ID,
            ShotGridVersionSubmissionPreflightModel(fileName='result.png', fileSize=8, changelog='完成首版'),
            _current_user(),
        )

    assert exc_info.value.http_status == HTTP_UNPROCESSABLE_ENTITY
    assert exc_info.value.error_key == 'SG_ASSET_PRODUCTION_ITEM_REQUIRED'
    ShotGridVersionSubmissionDao.has_unresolved_submission.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('context_patch', 'file_name', 'http_status', 'error_key'),
    [
        ({}, 'result.png', HTTP_UNPROCESSABLE_ENTITY, 'SG_TASK_FILE_TYPE_INVALID'),
        ({'shot_storage_dir_name': None}, 'result.mov', HTTP_CONFLICT, 'SG_VERSION_TARGET_PATH_CONFLICT'),
    ],
)
async def test_submit_preflight_validates_declared_extension_and_target_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    context_patch: dict[str, object],
    file_name: str,
    http_status: int,
    error_key: str,
) -> None:
    _patch_submit_preflight(monkeypatch, context={**_ready_shot_context(), **context_patch})

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridVersionSubmissionService.preflight_submission(
            AsyncMock(),
            TASK_ID,
            ShotGridVersionSubmissionPreflightModel(fileName=file_name, fileSize=8, changelog='完成首版'),
            _current_user(),
        )

    assert exc_info.value.http_status == http_status
    assert exc_info.value.error_key == error_key


def test_business_filename_uses_frozen_shot_rule() -> None:
    result = ShotGridVersionSubmissionService.build_business_file_name(
        _shot_context(),
        version_no=1,
        generated_at_ms=1_786_094_626_499,
        extension='mp4',
    )

    assert result == 'WGZR_EP001_001_S001_YJF_V001_1786094626499.mp4'


def test_asset_filename_contains_production_item_and_stably_shortens_long_values() -> None:
    context = _asset_context(production_item='主视角' * 100)
    context['asset_name'] = '动力舱室内' * 100

    first = ShotGridVersionSubmissionService.build_business_file_name(
        context,
        version_no=12,
        generated_at_ms=1_786_094_626_499,
        extension='png',
    )
    second = ShotGridVersionSubmissionService.build_business_file_name(
        context,
        version_no=12,
        generated_at_ms=1_786_094_626_499,
        extension='png',
    )

    assert first == second
    assert len(first) <= MAX_BUSINESS_FILENAME_LENGTH
    assert first.startswith('WGZR_Asset_Environment_')
    assert first.endswith('_YJF_V012_1786094626499.png')


def test_asset_filename_fails_closed_without_production_item() -> None:
    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridVersionSubmissionService.build_business_file_name(
            _asset_context(production_item=None),
            version_no=1,
            generated_at_ms=1,
            extension='jpg',
        )

    assert exc_info.value.error_key == 'SG_ASSET_PRODUCTION_ITEM_REQUIRED'


def test_incomplete_target_directory_snapshot_uses_conflict_error() -> None:
    context = _shot_context()
    context['shot_storage_dir_name'] = None

    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridVersionSubmissionService.build_target_relative_path(context, 'business.mp4')

    assert exc_info.value.http_status == HTTP_CONFLICT
    assert exc_info.value.error_key == 'SG_VERSION_TARGET_PATH_CONFLICT'


@pytest.mark.parametrize('value', [None, '', '   ', 'key\x00bad', 'x' * 101])
def test_idempotency_key_is_validated_by_service(value: str | None) -> None:
    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridVersionSubmissionService._normalize_idempotency_key(value)

    assert exc_info.value.http_status == HTTP_UNPROCESSABLE_ENTITY
    assert exc_info.value.error_key == 'SG_IDEMPOTENCY_KEY_INVALID'


def test_actor_rejects_missing_or_empty_user_name() -> None:
    current_user = CurrentUserModel(
        permissions=[],
        roles=[],
        user=UserInfoModel(userId=USER_ID, userName=''),
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridVersionSubmissionService._actor(current_user)

    assert exc_info.value.http_status == HTTP_UNAUTHORIZED
    assert exc_info.value.error_key == 'SG_CURRENT_USER_INVALID'


def test_create_controller_leaves_idempotency_validation_to_service() -> None:
    route = next(
        route
        for route in version_submission_controller.routes
        if route.path == '/shot-grid/tasks/{taskId}/version-submissions'
    )
    header = next(parameter for parameter in route.dependant.header_params if parameter.alias == 'X-Idempotency-Key')

    assert not header.field_info.is_required()
    assert header.default is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('error_key', 'expected_status'),
    [
        ('SG_TASK_FILE_TYPE_INVALID', 422),
        ('SG_STORAGE_PATH_INVALID', 422),
        ('SG_VERSION_SOURCE_FILE_CHANGED', 409),
        ('SG_NAS_TARGET_CONTENT_CONFLICT', 409),
        ('SG_VERSION_SOURCE_FILE_UNAVAILABLE', 503),
        ('SG_STORAGE_ROOT_UNAVAILABLE', 503),
    ],
)
async def test_source_adapter_errors_keep_their_contract_status(
    error_key: str,
    expected_status: int,
) -> None:
    adapter = SimpleNamespace(
        inspect_source=AsyncMock(
            side_effect=VersionPublishPathAdapterError(
                error_key=error_key,
                safe_message='安全错误',
                retryable=False,
            )
        )
    )
    file_info = SimpleNamespace(storage_key='2026/08/file.mp4', extension='mp4', file_hash=FILE_HASH, file_size=1)

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridVersionSubmissionService._inspect_source(adapter, file_info, 'shot_video')

    assert exc_info.value.http_status == expected_status
    assert exc_info.value.error_key == error_key


@pytest.mark.asyncio
async def test_unknown_source_adapter_error_maps_to_internal_submission_failure() -> None:
    adapter = SimpleNamespace(
        inspect_source=AsyncMock(
            side_effect=VersionPublishPathAdapterError(
                error_key='SG_UNEXPECTED_ADAPTER_KEY',
                safe_message='不能透出的未知错误',
                retryable=False,
            )
        )
    )
    file_info = SimpleNamespace(storage_key='2026/08/file.mp4', extension='mp4', file_hash=FILE_HASH, file_size=1)

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridVersionSubmissionService._inspect_source(adapter, file_info, 'shot_video')

    assert exc_info.value.http_status == HTTP_SERVICE_UNAVAILABLE
    assert exc_info.value.error_key == 'SG_VERSION_SUBMISSION_FAILED'


@pytest.mark.asyncio
async def test_create_freezes_source_storage_key_before_preflight_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _RollbackExpiringSource('2026/08/source.mp4')
    rollback_count = 0

    async def rollback() -> None:
        nonlocal rollback_count
        rollback_count += 1
        if rollback_count >= PREFLIGHT_ROLLBACK_COUNT:
            source.expired = True

    db = SimpleNamespace(rollback=AsyncMock(side_effect=rollback), commit=AsyncMock())
    access = ShotGridProjectAccessModel(
        projectId=PROJECT_ID,
        userId=USER_ID,
        projectRole='creator',
        hasAllScope=False,
    )
    project = SimpleNamespace(project_id=PROJECT_ID, project_status='active')
    task = SimpleNamespace(task_id=TASK_ID, assignee_user_id=USER_ID, task_status='in_progress')
    inspection = SimpleNamespace(extension='mp4', sha256=FILE_HASH, file_size=10)
    locked_file = SimpleNamespace(
        file_id=FILE_ID,
        storage_key='2026/08/source.mp4',
        status='active',
        del_flag='0',
        storage_type='local',
        access_type='private',
        file_hash=FILE_HASH,
        file_size=10,
    )

    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.get_task_project_id',
        AsyncMock(return_value=PROJECT_ID),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridProjectAccessService.resolve_access',
        AsyncMock(return_value=access),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.lock_project',
        AsyncMock(return_value=project),
    )
    monkeypatch.setattr(
        ShotGridVersionSubmissionService,
        '_refresh_locked_access',
        AsyncMock(return_value=access),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.lock_task',
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.get_idempotent_submission_for_update',
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(ShotGridVersionSubmissionService, '_require_submit_access', lambda *_args: None)
    monkeypatch.setattr(ShotGridVersionSubmissionService, '_require_mutable_project_task', lambda *_args: None)
    monkeypatch.setattr(
        ShotGridVersionSubmissionService,
        '_require_task_context',
        AsyncMock(return_value=_shot_context()),
    )
    monkeypatch.setattr(ShotGridVersionSubmissionService, '_require_context_ready', lambda *_args: None)
    monkeypatch.setattr(ShotGridVersionSubmissionService, '_task_access_view', lambda _context: task)
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.FileInfoDao.get_file_info_by_id',
        AsyncMock(return_value=source),
    )
    monkeypatch.setattr(
        ShotGridVersionSubmissionService,
        '_require_source_file_access',
        AsyncMock(),
    )
    monkeypatch.setattr(ShotGridVersionSubmissionService, '_inspect_source', AsyncMock(return_value=inspection))
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.get_unresolved_submission_for_update',
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.FileInfoDao.get_file_info_by_id_for_update',
        AsyncMock(return_value=locked_file),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.CommonService.check_private_file_download_permission_services',
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.source_file_is_bound',
        AsyncMock(return_value=True),
    )

    command = ShotGridVersionSubmissionCreateModel(fileId=FILE_ID, changelog='完成首版')
    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridVersionSubmissionService.create_submission(
            db,
            TASK_ID,
            command,
            'create-freezes-source',
            _current_user(),
        )

    assert exc_info.value.error_key == 'SG_VERSION_FILE_ALREADY_BOUND'
    assert source.expired
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_version_audit_method_names_fit_platform_column(monkeypatch: pytest.MonkeyPatch) -> None:
    add_log = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridProjectAuditDao.add_success_log',
        add_log,
    )

    await ShotGridVersionSubmissionService._audit(
        SimpleNamespace(),
        method='create_submission',
        business_type=1,
        request_method='POST',
        actor_name='producer',
        current_user=_current_user(),
        oper_url=f'/shot-grid/tasks/{TASK_ID}/version-submissions',
        payload={'taskId': TASK_ID},
        result={'submissionId': SUBMISSION_ID},
    )
    await ShotGridVersionSubmissionService._audit_worker_commit(
        SimpleNamespace(),
        submission=SimpleNamespace(submission_id=SUBMISSION_ID),
        version_id=VERSION_ID,
        review_list_id=REVIEW_LIST_ID,
        actor_name='producer',
    )

    methods = [call.kwargs['method'] for call in add_log.await_args_list]
    assert methods == [
        'ShotGridVersionSubmissionService.create_submission()',
        'ShotGridVersionSubmissionService.commit_published_submission()',
    ]
    assert all(len(method) <= MAX_PLATFORM_AUDIT_METHOD_LENGTH for method in methods)


@pytest.mark.asyncio
async def test_current_submission_status_restores_refreshable_unresolved_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = ShotGridProjectAccessModel(
        projectId=PROJECT_ID,
        userId=USER_ID,
        projectRole='creator',
        hasAllScope=False,
    )
    row = {
        'submission_id': SUBMISSION_ID,
        'project_id': PROJECT_ID,
        'task_id': TASK_ID,
        'source_file_id': FILE_ID,
        'submission_status': 'failed',
        'reserved_version_no': 1,
        'business_file_name': 'WGZR_EP001_001_S001_YJF_V001_1786094626499.mp4',
        'attempt_count': 2,
        'last_error_key': 'SG_VERSION_SUBMISSION_FAILED',
        'last_error_message': '发布失败',
        'submitted_by': USER_ID,
        'create_time': ShotGridVersionSubmissionService._now(),
        'update_time': ShotGridVersionSubmissionService._now(),
        'assignee_user_id': USER_ID,
        'task_status': 'in_progress',
        'version_id': None,
        'version_status': None,
        'review_list_id': None,
    }
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.get_task_project_id',
        AsyncMock(return_value=PROJECT_ID),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridProjectAccessService.resolve_access',
        AsyncMock(return_value=access),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.get_current_submission_status_row',
        AsyncMock(return_value=row),
    )

    result = await ShotGridVersionSubmissionService.get_current_submission_status(
        AsyncMock(),
        TASK_ID,
        _current_user(),
    )

    assert result is not None
    assert result.submission_id == SUBMISSION_ID
    assert result.submission_status == 'failed'
    assert result.last_error_key == 'SG_VERSION_SUBMISSION_FAILED'


@pytest.mark.asyncio
async def test_current_submission_status_returns_none_after_worker_commits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.get_task_project_id',
        AsyncMock(return_value=PROJECT_ID),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridProjectAccessService.resolve_access',
        AsyncMock(
            return_value=ShotGridProjectAccessModel(
                projectId=PROJECT_ID,
                userId=USER_ID,
                projectRole='creator',
            )
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.get_current_submission_status_row',
        AsyncMock(return_value=None),
    )

    result = await ShotGridVersionSubmissionService.get_current_submission_status(
        AsyncMock(),
        TASK_ID,
        _current_user(),
    )

    assert result is None


@pytest.mark.asyncio
async def test_current_submission_status_returns_task_not_found_before_access_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolve_access = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.get_task_project_id',
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridProjectAccessService.resolve_access',
        resolve_access,
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridVersionSubmissionService.get_current_submission_status(
            AsyncMock(),
            TASK_ID,
            _current_user(),
        )

    assert exc_info.value.http_status == HTTP_NOT_FOUND
    assert exc_info.value.error_key == 'SG_TASK_NOT_FOUND'
    resolve_access.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_submission_status_rejects_creator_who_is_not_submitter_and_assignee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = {
        'submission_id': SUBMISSION_ID,
        'project_id': PROJECT_ID,
        'task_id': TASK_ID,
        'submitted_by': USER_ID + 1,
        'assignee_user_id': USER_ID + 2,
    }
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.get_task_project_id',
        AsyncMock(return_value=PROJECT_ID),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridProjectAccessService.resolve_access',
        AsyncMock(
            return_value=ShotGridProjectAccessModel(
                projectId=PROJECT_ID,
                userId=USER_ID,
                projectRole='creator',
            )
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.get_current_submission_status_row',
        AsyncMock(return_value=row),
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridVersionSubmissionService.get_current_submission_status(
            AsyncMock(),
            TASK_ID,
            _current_user(),
        )

    assert exc_info.value.http_status == HTTP_FORBIDDEN
    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'


def test_inactive_existing_assignee_is_state_conflict() -> None:
    context = {
        **_shot_context(),
        'project_status': 'active',
        'task_status': 'in_progress',
        'storage_status': 'ready',
        'directory_operation_status': 'succeeded',
        'member_status': 'removed',
        'assignee_user_status': '0',
        'assignee_user_del_flag': '0',
        'episode_lifecycle_status': 'active',
        'scene_lifecycle_status': 'active',
        'shot_lifecycle_status': 'active',
    }

    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridVersionSubmissionService._require_context_ready(context)

    assert exc_info.value.http_status == HTTP_CONFLICT
    assert exc_info.value.error_key == 'SG_TASK_ASSIGNEE_STATE_INVALID'


@pytest.mark.asyncio
async def test_concurrent_idempotency_unique_conflict_replays_same_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = AsyncMock()
    task = SimpleNamespace(task_status='in_progress', assignee_user_id=USER_ID)
    existing = SimpleNamespace(
        submission_id=SUBMISSION_ID,
        source_file_id=FILE_ID,
        changelog='修改完成',
        ai_params={'seed': 1},
        submission_status='pending',
        reserved_version_no=1,
        business_file_name='WGZR_EP001_001_S001_YJF_V001_1786094626499.mp4',
    )
    command = ShotGridVersionSubmissionCreateModel(
        fileId=FILE_ID,
        changelog='修改完成',
        aiParams={'seed': 1},
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.lock_project',
        AsyncMock(return_value=SimpleNamespace(project_status='active')),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.lock_task',
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.get_idempotent_submission_for_update',
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(
        ShotGridVersionSubmissionService,
        '_refresh_locked_access',
        AsyncMock(
            return_value=ShotGridProjectAccessModel(
                projectId=PROJECT_ID,
                userId=USER_ID,
                projectRole='director',
            )
        ),
    )

    result = await ShotGridVersionSubmissionService._recover_idempotency_replay(
        db,
        project_id=PROJECT_ID,
        task_id=TASK_ID,
        actor_id=USER_ID,
        idempotency_key='same-key',
        command=command,
        current_user=_current_user(),
    )

    assert result.replayed
    assert result.submission_id == SUBMISSION_ID
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


def test_unknown_integrity_constraint_is_not_disguised_as_version_conflict() -> None:
    assert ShotGridVersionSubmissionService._map_integrity_error(None) is None
    assert ShotGridVersionSubmissionService._map_integrity_error('unknown_constraint') is None


@pytest.mark.asyncio
async def test_formal_commit_switches_temp_reference_and_commits_whole_review_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = AsyncMock()
    task = SimpleNamespace(
        task_id=TASK_ID,
        task_name='镜头任务',
        task_status='revision',
        update_by='old',
        update_time=None,
        lock_version=2,
    )
    submission = ShotGridVersionSubmission(
        submission_id=SUBMISSION_ID,
        project_id=PROJECT_ID,
        task_id=TASK_ID,
        source_file_id=FILE_ID,
        reserved_version_no=3,
        generated_at_ms=1_786_094_626_499,
        business_file_name='WGZR_EP001_001_S001_YJF_V003_1786094626499.mp4',
        target_relative_path='VIDEO\\EP01\\S001\\WGZR_EP001_001_S001_YJF_V003_1786094626499.mp4',
        temporary_relative_path='VIDEO\\EP01\\S001\\.sgtmp-30-a1-temp.part',
        source_sha256=FILE_HASH,
        source_file_size=123,
        changelog='按意见修改',
        ai_params=None,
        submission_status='committing',
        submitted_by=USER_ID,
        idempotency_key='request-1',
        attempt_count=1,
        lease_owner='worker:claim',
        lease_until=None,
    )
    source_file = SimpleNamespace(
        status='active',
        del_flag='0',
        storage_type='local',
        access_type='private',
        file_hash=FILE_HASH,
        file_size=123,
    )

    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.get_submission_status_row',
        AsyncMock(return_value={'project_id': PROJECT_ID, 'task_id': TASK_ID}),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.lock_project',
        AsyncMock(return_value=SimpleNamespace(project_status='active')),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.lock_task',
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.lock_submission',
        AsyncMock(return_value=submission),
    )
    monkeypatch.setattr(
        ShotGridVersionSubmissionService,
        '_require_task_context',
        AsyncMock(return_value=_shot_context()),
    )
    monkeypatch.setattr(ShotGridVersionSubmissionService, '_require_context_ready', lambda _context: None)
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.FileInfoDao.get_file_info_by_id_for_update',
        AsyncMock(return_value=source_file),
    )

    async def add_version(_db: object, version: object) -> object:
        version.version_id = VERSION_ID
        return version

    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.add_version',
        AsyncMock(side_effect=add_version),
    )
    add_version_file = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.add_version_file',
        add_version_file,
    )
    replace_reference = AsyncMock()
    remove_reference = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.FileReferenceService.replace_business_file_references_services',
        replace_reference,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.FileReferenceService.remove_business_file_references_services',
        remove_reference,
    )

    async def add_review(_db: object, review_list: object, _relation: object) -> object:
        review_list.review_list_id = REVIEW_LIST_ID
        return review_list

    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.ShotGridReviewDao.add_auto_review_list',
        AsyncMock(side_effect=add_review),
    )
    monkeypatch.setattr(ShotGridVersionSubmissionService, '_get_submitter_name', AsyncMock(return_value='producer'))
    audit = AsyncMock()
    monkeypatch.setattr(ShotGridVersionSubmissionService, '_audit_worker_commit', audit)

    result = await ShotGridVersionSubmissionService.commit_published_submission(
        db,
        submission_id=SUBMISSION_ID,
        worker_id='worker:claim',
        attempt_count=1,
        published_sha256=FILE_HASH,
        published_file_size=123,
    )

    assert result == (VERSION_ID, REVIEW_LIST_ID)
    assert task.task_status == 'pending_review'
    assert submission.submission_status == 'committed'
    replace_reference.assert_awaited_once()
    assert replace_reference.await_args.args[1:4] == ('shotgrid_version', str(VERSION_ID), [FILE_ID])
    remove_reference.assert_awaited_once_with(
        db,
        'shotgrid_version_submission',
        str(SUBMISSION_ID),
    )
    add_version_file.assert_awaited_once()
    audit.assert_awaited_once()
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()

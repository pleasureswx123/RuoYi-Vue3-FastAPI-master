from collections import defaultdict
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from common.enums import BusinessType
from module_shot_grid.dao.asset_import_dao import AssetImportDao
from module_shot_grid.dao.import_batch_dao import ShotGridImportBatchDao
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.asset_import_vo import (
    AssetImportCommitRequestModel,
    AssetImportCommitResultModel,
    AssetImportNormalizedRowModel,
    AssetImportPreviewRowModel,
)
from module_shot_grid.entity.vo.import_common_vo import ImportPreviewTokenPayloadModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.asset_import_service import AssetImportService
from module_shot_grid.service.import_preview_store import ImportPreviewStore

BATCH_ID = 11
ASSIGNEE_USER_ID = 7
CONFLICT_STATUS = 409
UNPROCESSABLE_ENTITY_STATUS = 422


def _row(
    row_number: int = 2,
    *,
    production_item: str | None = '主视角',
    can_import: bool = True,
) -> AssetImportPreviewRowModel:
    production_key = production_item.casefold() if production_item else None
    return AssetImportPreviewRowModel(
        sheetName='Sheet1',
        rowNumber=row_number,
        rowKey=f'{row_number:064x}',
        normalized=AssetImportNormalizedRowModel(
            assetType='Environment',
            assetName='控制室',
            assetNameKey='控制室',
            assetGroupKey='a' * 64,
            productionItem=production_item,
            productionItemKey=production_key,
            importRowKey=f'{row_number:064x}',
        ),
        canImport=can_import,
    )


def _payload(rows: list[AssetImportPreviewRowModel]) -> ImportPreviewTokenPayloadModel:
    return ImportPreviewTokenPayloadModel(
        batchId=BATCH_ID,
        projectId=2,
        importType='asset',
        previewedBy=3,
        fileSha256='f' * 64,
        templateVersion='asset-v1',
        expiresAt=datetime.now() + timedelta(minutes=5),
        rows=[row.model_dump(mode='json', by_alias=True) for row in rows],
    )


def _result_snapshot() -> dict[str, Any]:
    return AssetImportCommitResultModel(
        batchId=BATCH_ID,
        committedRows=1,
        createdAssetsByType={'Character': 0, 'Environment': 1, 'Prop': 0},
        createdAssetItems=1,
        createdTasks=0,
        missingProductionItemWarnings=0,
        autoMatchedRequirements=1,
        pendingRequirements=0,
        conflictRequirements=0,
    ).model_dump(mode='json', by_alias=True)


def _current_user() -> SimpleNamespace:
    return SimpleNamespace(
        user=SimpleNamespace(
            user_id=3,
            user_name='director',
            dept=SimpleNamespace(dept_name='策划部'),
        )
    )


def test_selection_hash_is_order_independent_but_sheet_sensitive() -> None:
    first = AssetImportCommitRequestModel(
        importToken='token',
        selectedRows=[
            {'sheetName': 'Sheet1', 'rowNumber': 2},
            {'sheetName': 'Sheet2', 'rowNumber': 2},
        ],
    )
    reversed_request = AssetImportCommitRequestModel(
        importToken='token',
        selectedRows=list(reversed(first.selected_rows)),
    )
    changed_sheet = AssetImportCommitRequestModel(
        importToken='token',
        selectedRows=[
            {'sheetName': 'Sheet1', 'rowNumber': 2},
            {'sheetName': 'Sheet1', 'rowNumber': 3},
        ],
    )

    assert AssetImportService._selection_hash(first) == AssetImportService._selection_hash(reversed_request)
    assert AssetImportService._selection_hash(first) != AssetImportService._selection_hash(changed_sheet)


@pytest.mark.parametrize('value', [None, '', '   ', 'x' * 101, 'line\nbreak'])
def test_invalid_idempotency_key_uses_stable_domain_error(value: str | None) -> None:
    with pytest.raises(ShotGridDomainException) as exc_info:
        AssetImportService._normalize_idempotency_key(value)

    assert exc_info.value.error_key == 'SG_IDEMPOTENCY_KEY_INVALID'
    assert exc_info.value.http_status == UNPROCESSABLE_ENTITY_STATUS


def test_partial_parent_selection_is_self_contained() -> None:
    rows = [_row(2), _row(3, production_item='细节视角')]
    selected = AssetImportService._select_rows(
        _payload(rows),
        AssetImportCommitRequestModel(
            importToken='token',
            selectedRows=[{'sheetName': 'Sheet1', 'rowNumber': 3}],
        ),
    )

    assert [(row.sheet_name, row.row_number) for row in selected] == [('Sheet1', 3)]
    assert selected[0].normalized.asset_name == '控制室'


def test_replay_requires_same_token_and_selection_snapshot() -> None:
    token = 'same-token'
    command = AssetImportCommitRequestModel(
        importToken=token,
        selectedRows=[{'sheetName': 'Sheet1', 'rowNumber': 2}],
    )
    batch = SimpleNamespace(
        preview_token_hash=ImportPreviewStore.token_hash(token),
        selection_hash=AssetImportService._selection_hash(command),
        batch_status='committed',
        result_summary=_result_snapshot(),
    )

    result = AssetImportService._replay_result(
        batch,
        ImportPreviewStore.token_hash(token),
        AssetImportService._selection_hash(command),
    )
    assert result.batch_id == BATCH_ID

    with pytest.raises(ShotGridDomainException) as exc_info:
        AssetImportService._replay_result(
            batch,
            ImportPreviewStore.token_hash('different-token'),
            AssetImportService._selection_hash(command),
        )
    assert exc_info.value.error_key == 'SG_IDEMPOTENCY_CONFLICT'


@pytest.mark.asyncio
async def test_idempotent_replay_rolls_back_advisory_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    token = 'same-token'
    command = AssetImportCommitRequestModel(
        importToken=token,
        selectedRows=[{'sheetName': 'Sheet1', 'rowNumber': 2}],
    )
    existing = SimpleNamespace(
        preview_token_hash=ImportPreviewStore.token_hash(token),
        selection_hash=AssetImportService._selection_hash(command),
        batch_status='committed',
        result_summary=_result_snapshot(),
    )
    events: list[str] = []

    async def lock_idempotency(_db: Any, _lock_id: int) -> None:
        events.append('lock')

    async def find_by_idempotency(*_args: Any, **_kwargs: Any) -> Any:
        events.append('find')
        return existing

    class FakeDb:
        async def rollback(self) -> None:
            events.append('rollback')

    monkeypatch.setattr(ShotGridImportBatchDao, 'lock_idempotency', lock_idempotency)
    monkeypatch.setattr(ShotGridImportBatchDao, 'find_by_idempotency', find_by_idempotency)

    result = await AssetImportService.commit(
        FakeDb(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        2,
        command,
        'request-1',
        _current_user(),  # type: ignore[arg-type]
    )

    assert result.batch_id == BATCH_ID
    assert events == ['lock', 'find', 'rollback']


@pytest.mark.asyncio
async def test_missing_token_rolls_back_advisory_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    async def lock_idempotency(_db: Any, _lock_id: int) -> None:
        events.append('lock')

    async def find_by_idempotency(*_args: Any, **_kwargs: Any) -> None:
        events.append('find')

    async def get_token(*_args: Any, **_kwargs: Any) -> None:
        events.append('get-token')

    async def find_by_token_hash(*_args: Any, **_kwargs: Any) -> None:
        events.append('find-token')

    class FakeDb:
        async def rollback(self) -> None:
            events.append('rollback')

    monkeypatch.setattr(ShotGridImportBatchDao, 'lock_idempotency', lock_idempotency)
    monkeypatch.setattr(ShotGridImportBatchDao, 'find_by_idempotency', find_by_idempotency)
    monkeypatch.setattr(ShotGridImportBatchDao, 'find_by_token_hash', find_by_token_hash)
    monkeypatch.setattr(ImportPreviewStore, 'get', get_token)

    with pytest.raises(ShotGridDomainException) as exc_info:
        await AssetImportService.commit(
            FakeDb(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            2,
            AssetImportCommitRequestModel(
                importToken='expired-token',
                selectedRows=[{'sheetName': 'Sheet1', 'rowNumber': 2}],
            ),
            'request-2',
            _current_user(),  # type: ignore[arg-type]
        )

    assert exc_info.value.error_key == 'SG_IMPORT_TOKEN_INVALID'
    assert events == ['lock', 'find', 'get-token', 'find-token', 'rollback']


@pytest.mark.asyncio
async def test_missing_redis_token_uses_database_expiry_to_return_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    expired_batch = SimpleNamespace(
        batch_id=BATCH_ID,
        preview_expires_time=datetime.now() - timedelta(seconds=1),
    )

    async def find_by_token_hash(*_args: Any, **_kwargs: Any) -> Any:
        events.append('find-token')
        return expired_batch

    async def expire_preview(*_args: Any, **_kwargs: Any) -> None:
        events.append('expire')

    class FakeDb:
        async def commit(self) -> None:
            events.append('commit')

    monkeypatch.setattr(ShotGridImportBatchDao, 'find_by_token_hash', find_by_token_hash)
    monkeypatch.setattr(ShotGridImportBatchDao, 'expire_preview', expire_preview)

    with pytest.raises(ShotGridDomainException) as exc_info:
        await AssetImportService._raise_missing_token(
            FakeDb(),  # type: ignore[arg-type]
            project_id=2,
            token='expired-token',
        )

    assert exc_info.value.error_key == 'SG_IMPORT_TOKEN_EXPIRED'
    assert events == ['find-token', 'expire', 'commit']


@pytest.mark.asyncio
async def test_commit_transaction_audits_before_database_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    result = AssetImportCommitResultModel.model_validate(_result_snapshot())
    batch = SimpleNamespace(batch_id=BATCH_ID)

    class FakeDb:
        async def commit(self) -> None:
            events.append('commit')

    monkeypatch.setattr(AssetImportService, '_require_ready_storage', AsyncMock())
    monkeypatch.setattr(AssetImportService, '_validate_storage_segments', Mock())
    monkeypatch.setattr(AssetImportService, '_resolve_assignees', AsyncMock())
    monkeypatch.setattr(AssetImportService, '_raise_selected_row_errors', Mock())
    monkeypatch.setattr(AssetImportService, '_persist_selected_rows', AsyncMock(return_value=result))

    async def audit(*_args: Any, **_kwargs: Any) -> None:
        events.append('audit')

    def mark_committed(*_args: Any, **_kwargs: Any) -> None:
        events.append('mark-committed')

    audit_mock = AsyncMock(side_effect=audit)
    monkeypatch.setattr(ShotGridProjectAuditDao, 'add_success_log', audit_mock)
    monkeypatch.setattr(ShotGridImportBatchDao, 'mark_committed', mark_committed)

    committed = await AssetImportService._commit_transaction(
        FakeDb(),  # type: ignore[arg-type]
        project_id=2,
        batch=batch,  # type: ignore[arg-type]
        rows=[_row()],
        actor_name='director',
        dept_name='策划部',
        selection_hash='a' * 64,
        current_user=_current_user(),  # type: ignore[arg-type]
    )

    assert committed == result
    assert events == ['audit', 'mark-committed', 'commit']
    audit_parameters = audit_mock.await_args.kwargs
    assert audit_parameters['business_type'] == BusinessType.IMPORT.value
    assert audit_parameters['oper_param'] == {
        'projectId': 2,
        'batchId': BATCH_ID,
        'selectedRows': [{'sheetName': 'Sheet1', 'rowNumber': 2}],
    }
    assert 'importToken' not in audit_parameters['oper_param']


@pytest.mark.asyncio
@pytest.mark.parametrize('project_status', ['completed', 'archived'])
async def test_completed_or_archived_project_rejects_asset_preview_and_commit(
    monkeypatch: pytest.MonkeyPatch,
    project_status: str,
) -> None:
    monkeypatch.setattr(
        AssetImportDao,
        'get_project_storage',
        AsyncMock(
            return_value=(
                SimpleNamespace(project_status=project_status),
                SimpleNamespace(storage_status='ready'),
            )
        ),
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await AssetImportService._require_ready_storage(AsyncMock(), 2)

    assert exc_info.value.error_key == 'SG_INVALID_STATE_TRANSITION'
    assert exc_info.value.http_status == CONFLICT_STATUS


@pytest.mark.asyncio
async def test_asset_commit_rechecks_director_role_after_project_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        AssetImportDao,
        'get_project_storage',
        AsyncMock(
            return_value=(
                SimpleNamespace(project_status='active'),
                SimpleNamespace(storage_status='ready'),
            )
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.asset_import_service.ShotGridProjectAccessService.resolve_access',
        AsyncMock(
            return_value=ShotGridProjectAccessModel(
                projectId=2,
                userId=3,
                projectRole='creator',
                hasAllScope=False,
            )
        ),
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await AssetImportService._require_ready_storage(
            AsyncMock(),
            2,
            for_update=True,
            current_user=_current_user(),  # type: ignore[arg-type]
        )

    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'


def test_locked_batch_revalidates_type_template_and_database_expiry() -> None:
    payload = _payload([_row()])
    token_hash = 'b' * 64

    def batch(**overrides: Any) -> SimpleNamespace:
        values = {
            'batch_status': 'previewed',
            'import_type': 'asset',
            'preview_token_hash': token_hash,
            'file_sha256': payload.file_sha256,
            'template_version': payload.template_version,
            'preview_expires_time': payload.expires_at,
            'previewed_by': payload.previewed_by,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    AssetImportService._validate_batch(
        batch(),
        payload,
        token_hash=token_hash,
        user_id=payload.previewed_by,
        has_all_scope=False,
    )
    for invalid_batch, error_key in [
        (batch(import_type='shot'), 'SG_IMPORT_TOKEN_INVALID'),
        (batch(template_version='asset-v0'), 'SG_IMPORT_TEMPLATE_VERSION_MISMATCH'),
        (batch(preview_expires_time=datetime.now() - timedelta(seconds=1)), 'SG_IMPORT_TOKEN_EXPIRED'),
    ]:
        with pytest.raises(ShotGridDomainException) as exc_info:
            AssetImportService._validate_batch(
                invalid_batch,
                payload,
                token_hash=token_hash,
                user_id=payload.previewed_by,
                has_all_scope=False,
            )
        assert exc_info.value.error_key == error_key


def test_only_owner_or_all_scope_can_commit_preview_token() -> None:
    payload = _payload([_row()])

    with pytest.raises(ShotGridDomainException) as exc_info:
        AssetImportService._validate_token_payload(
            payload,
            project_id=payload.project_id,
            user_id=99,
            has_all_scope=False,
        )
    assert exc_info.value.error_key == 'SG_IMPORT_TOKEN_FORBIDDEN'

    AssetImportService._validate_token_payload(
        payload,
        project_id=payload.project_id,
        user_id=99,
        has_all_scope=True,
    )


@pytest.mark.asyncio
async def test_missing_item_still_persists_remark_and_creates_one_main_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _row(production_item=None)
    row.normalized.remark = '后续补充分项'
    row.normalized.task_description = '先完成主视角'
    row.normalized.assignee_user_id = ASSIGNEE_USER_ID
    captured: dict[str, Any] = {}

    async def add_item(_db: Any, item: Any) -> Any:
        captured['item'] = item
        item.asset_item_id = 21
        return item

    async def add_task(_db: Any, task: Any) -> Any:
        captured['task'] = task
        return task

    monkeypatch.setattr(AssetImportDao, 'add_asset_item', add_item)
    monkeypatch.setattr(AssetImportDao, 'add_task', add_task)

    task_count, warning_count = await AssetImportService._create_asset_items(
        object(),  # type: ignore[arg-type]
        project_id=2,
        batch=SimpleNamespace(batch_id=BATCH_ID),  # type: ignore[arg-type]
        rows=[row],
        assets={('Environment', '控制室'): SimpleNamespace(asset_id=5, asset_name='控制室')},  # type: ignore[dict-item]
        existing_item_keys=set(),
        max_item_sort_order=defaultdict(int),
        actor_name='director',
        now=datetime.now(),
    )

    assert (task_count, warning_count) == (1, 1)
    assert captured['item'].production_item is None
    assert captured['item'].remark == '后续补充分项'
    assert captured['task'].task_kind == 'asset_image'
    assert captured['task'].assignee_user_id == ASSIGNEE_USER_ID
    assert captured['task'].requirements == '先完成主视角'

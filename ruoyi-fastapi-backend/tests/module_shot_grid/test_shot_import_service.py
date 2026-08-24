from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from module_shot_grid.dao.import_batch_dao import ShotGridImportBatchDao
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.shot_import_dao import ShotGridShotImportDao
from module_shot_grid.entity.vo.import_common_vo import ImportPreviewTokenPayloadModel
from module_shot_grid.entity.vo.shot_import_vo import (
    ShotImportCommitRequestModel,
    ShotImportCommitResultModel,
    ShotImportPreviewRowModel,
    ShotImportSelectedRowModel,
)
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.import_preview_store import ImportPreviewStore
from module_shot_grid.service.shot_import_service import ShotGridShotImportService

CONFLICT_STATUS = 409
UNPROCESSABLE_STATUS = 422
IMPORT_BUSINESS_TYPE = 6


def _preview_row(sheet_name: str, row_number: int, *, can_import: bool = True) -> ShotImportPreviewRowModel:
    row = ShotImportPreviewRowModel(
        sheetName=sheet_name,
        rowNumber=row_number,
        normalized=None,
        canImport=can_import,
    )
    row.row_key = ShotGridShotImportService._row_key('a' * 64, sheet_name, row_number)
    return row


def _payload(rows: list[ShotImportPreviewRowModel]) -> ImportPreviewTokenPayloadModel:
    return ImportPreviewTokenPayloadModel(
        batchId=1,
        projectId=2,
        importType='shot',
        previewedBy=3,
        fileSha256='a' * 64,
        templateVersion='shot-v2',
        expiresAt='2999-01-01T00:00:00',
        rows=[row.model_dump(mode='json', by_alias=True) for row in rows],
    )


def _commit_snapshot() -> dict[str, Any]:
    return ShotImportCommitResultModel(
        batchId=1,
        committedRows=1,
        createdEpisodes=1,
        reusedEpisodes=0,
        createdScenes=1,
        reusedScenes=0,
        createdShots=1,
        createdAssetLinks=0,
        createdAssetRequirements=1,
        createdStorageOperations=2,
    ).model_dump(mode='json', by_alias=True)


def test_row_key_and_selection_hash_are_stable_and_sheet_sensitive() -> None:
    ep1 = _preview_row('EP001', 2)
    ep2 = _preview_row('EP002', 2)

    assert ep1.row_key != ep2.row_key
    assert ShotGridShotImportService._selection_hash([ep1, ep2]) == ShotGridShotImportService._selection_hash(
        [ep2, ep1]
    )


def test_selected_rows_use_sheet_and_row_and_keep_workbook_order() -> None:
    rows = [_preview_row('EP001', 2), _preview_row('EP001', 3), _preview_row('EP002', 2)]
    selections = [
        ShotImportSelectedRowModel(sheetName='EP002', rowNumber=2),
        ShotImportSelectedRowModel(sheetName='EP001', rowNumber=2),
    ]

    selected = ShotGridShotImportService._select_rows(_payload(rows), selections)

    assert [(row.sheet_name, row.row_number) for row in selected] == [('EP001', 2), ('EP002', 2)]


def test_selected_rows_reject_unknown_or_invalid_preview_rows() -> None:
    payload = _payload([_preview_row('EP001', 2, can_import=False)])
    with pytest.raises(ShotGridDomainException) as invalid_exc:
        ShotGridShotImportService._select_rows(
            payload,
            [ShotImportSelectedRowModel(sheetName='EP001', rowNumber=2)],
        )
    assert invalid_exc.value.error_key == 'SG_IMPORT_HAS_ERRORS'

    with pytest.raises(ShotGridDomainException) as missing_exc:
        ShotGridShotImportService._select_rows(
            payload,
            [ShotImportSelectedRowModel(sheetName='EP002', rowNumber=2)],
        )
    assert missing_exc.value.error_key == 'SG_IMPORT_SELECTED_ROW_INVALID'


def test_idempotency_lock_id_is_stable_and_scoped() -> None:
    first = ShotGridShotImportService._idempotency_lock_id(1, 2, 'same-key')
    assert first == ShotGridShotImportService._idempotency_lock_id(1, 2, 'same-key')
    assert first != ShotGridShotImportService._idempotency_lock_id(2, 2, 'same-key')
    assert first != ShotGridShotImportService._idempotency_lock_id(1, 3, 'same-key')
    assert -(2**63) <= first < 2**63


def test_selection_rejects_assignment_override_and_hashes_only_row_identity() -> None:
    first = ShotImportSelectedRowModel(sheetName='EP001', rowNumber=2)
    second = ShotImportSelectedRowModel(sheetName='EP002', rowNumber=2)

    with pytest.raises(ValidationError):
        ShotImportSelectedRowModel(sheetName='EP001', rowNumber=2, assigneeUserId=7)

    assert ShotGridShotImportService._selection_hash_from_request(
        'a' * 64, [first, second]
    ) == ShotGridShotImportService._selection_hash_from_request('a' * 64, [second, first])


@pytest.mark.parametrize('file_name', ['bad\x00.xlsx', 'bad\x1f.xlsx'])
def test_shot_import_rejects_control_characters_in_original_file_name(file_name: str) -> None:
    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridShotImportService._safe_original_file_name(file_name)

    assert exc_info.value.http_status == UNPROCESSABLE_STATUS
    assert exc_info.value.error_key == 'SG_IMPORT_FILE_NAME_INVALID'


def test_existing_committed_result_is_replayed_from_snapshot() -> None:
    batch = SimpleNamespace(batch_status='committed', result_summary=_commit_snapshot())

    result = ShotGridShotImportService._existing_result(batch)

    assert result.idempotent_replay is True
    assert result.batch_id == 1


@pytest.mark.asyncio
async def test_idempotent_replay_releases_advisory_transaction_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    token = 'same-token'
    selection = ShotImportSelectedRowModel(sheetName='EP001', rowNumber=2)
    existing = SimpleNamespace(
        preview_token_hash=ImportPreviewStore.token_hash(token),
        file_sha256='a' * 64,
        selection_hash=ShotGridShotImportService._selection_hash_from_request('a' * 64, [selection]),
        batch_status='committed',
        result_summary=_commit_snapshot(),
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
    result = await ShotGridShotImportService.commit(
        FakeDb(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        project_id=2,
        request_model=ShotImportCommitRequestModel(importToken=token, selectedRows=[selection]),
        idempotency_key='request-1',
        current_user=SimpleNamespace(user=SimpleNamespace(user_id=3, user_name='maker')),  # type: ignore[arg-type]
    )

    assert result.idempotent_replay is True
    assert events == ['lock', 'find', 'rollback']


@pytest.mark.asyncio
async def test_idempotency_token_conflict_rolls_back_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    existing = SimpleNamespace(preview_token_hash='b' * 64)

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

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridShotImportService.commit(
            FakeDb(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            project_id=2,
            request_model=ShotImportCommitRequestModel(
                importToken='different-token',
                selectedRows=[{'sheetName': 'EP001', 'rowNumber': 2}],
            ),
            idempotency_key='request-1',
            current_user=SimpleNamespace(user=SimpleNamespace(user_id=3, user_name='maker')),  # type: ignore[arg-type]
        )

    assert exc_info.value.error_key == 'SG_IDEMPOTENCY_CONFLICT'
    assert events == ['lock', 'find', 'rollback']


@pytest.mark.asyncio
async def test_successful_commit_audits_before_commit_then_deletes_preview_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    token = 'commit-token'
    row = _preview_row('EP001', 2)
    payload = _payload([row])
    batch = SimpleNamespace(
        batch_id=1,
        batch_status='previewed',
        valid_rows=1,
        import_type='shot',
        preview_token_hash=ImportPreviewStore.token_hash(token),
        file_sha256='a' * 64,
        template_version='shot-v2',
        preview_expires_time=payload.expires_at,
        previewed_by=3,
    )

    class FakeDb:
        async def flush(self) -> None:
            events.append('flush')

        async def commit(self) -> None:
            events.append('commit')

        async def rollback(self) -> None:
            events.append('rollback')

    lock_mock = AsyncMock()
    find_mock = AsyncMock(return_value=None)
    get_batch_mock = AsyncMock(return_value=batch)
    get_payload_mock = AsyncMock(return_value=payload)
    get_project_mock = AsyncMock(
        return_value=(
            SimpleNamespace(project_id=2, project_status='active'),
            SimpleNamespace(storage_status='ready'),
        )
    )
    revalidate_mock = AsyncMock()
    write_mock = AsyncMock(return_value=ShotImportCommitResultModel.model_validate(_commit_snapshot()))

    async def audit_side_effect(*_args: Any, **_kwargs: Any) -> None:
        events.append('audit')

    async def delete_side_effect(*_args: Any, **_kwargs: Any) -> None:
        events.append('delete')

    audit_mock = AsyncMock(side_effect=audit_side_effect)
    delete_mock = AsyncMock(side_effect=delete_side_effect)
    monkeypatch.setattr(ShotGridImportBatchDao, 'lock_idempotency', lock_mock)
    monkeypatch.setattr(ShotGridImportBatchDao, 'find_by_idempotency', find_mock)
    monkeypatch.setattr(ShotGridImportBatchDao, 'get_for_update', get_batch_mock)
    monkeypatch.setattr(ImportPreviewStore, 'get', get_payload_mock)
    monkeypatch.setattr(ImportPreviewStore, 'delete', delete_mock)
    monkeypatch.setattr(ShotGridShotImportDao, 'get_project_storage', get_project_mock)
    monkeypatch.setattr(ShotGridShotImportService, '_revalidate_selected_rows', revalidate_mock)
    monkeypatch.setattr(ShotGridShotImportService, '_write_selected_rows', write_mock)
    monkeypatch.setattr(ShotGridProjectAuditDao, 'add_success_log', audit_mock)

    result = await ShotGridShotImportService.commit(
        FakeDb(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        project_id=2,
        request_model=ShotImportCommitRequestModel(
            importToken=token,
            selectedRows=[{'sheetName': 'EP001', 'rowNumber': 2}],
        ),
        idempotency_key='request-2',
        current_user=SimpleNamespace(  # type: ignore[arg-type]
            user=SimpleNamespace(
                user_id=3,
                user_name='maker',
                dept=SimpleNamespace(dept_name='制作部'),
            )
        ),
    )

    assert result.committed_rows == 1
    assert events == ['flush', 'audit', 'commit', 'delete']
    audit_parameters = audit_mock.await_args.kwargs
    assert audit_parameters['business_type'] == IMPORT_BUSINESS_TYPE
    assert audit_parameters['dept_name'] == '制作部'
    assert audit_parameters['oper_param'] == {
        'batchId': 1,
        'selectedRows': [{'sheetName': 'EP001', 'rowNumber': 2}],
    }
    assert 'importToken' not in audit_parameters['oper_param']


def test_locked_batch_revalidates_database_type_template_and_expiry() -> None:
    token_hash = 'b' * 64
    payload = _payload([_preview_row('EP001', 2)])

    def batch(**overrides: Any) -> SimpleNamespace:
        values = {
            'batch_status': 'previewed',
            'import_type': 'shot',
            'preview_token_hash': token_hash,
            'file_sha256': payload.file_sha256,
            'template_version': payload.template_version,
            'preview_expires_time': payload.expires_at,
            'previewed_by': payload.previewed_by,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    ShotGridShotImportService._validate_locked_batch(
        batch(),
        payload,
        token_hash,
        payload.previewed_by,
        False,
    )

    cases = [
        (batch(import_type='asset'), 'SG_IMPORT_TOKEN_INVALID'),
        (batch(template_version='shot-v0'), 'SG_IMPORT_TEMPLATE_VERSION_MISMATCH'),
        (batch(preview_expires_time=datetime.now() - timedelta(seconds=1)), 'SG_IMPORT_TOKEN_EXPIRED'),
        (batch(preview_expires_time=payload.expires_at - timedelta(seconds=1)), 'SG_IMPORT_TOKEN_INVALID'),
        (batch(previewed_by=99), 'SG_IMPORT_TOKEN_INVALID'),
    ]
    for invalid_batch, expected_error_key in cases:
        with pytest.raises(ShotGridDomainException) as exc_info:
            ShotGridShotImportService._validate_locked_batch(
                invalid_batch,
                payload,
                token_hash,
                payload.previewed_by,
                False,
            )
        assert exc_info.value.error_key == expected_error_key


def test_archived_episode_and_scene_cannot_be_reused_by_import() -> None:
    with pytest.raises(ShotGridDomainException) as episode_exc:
        ShotGridShotImportService._assert_active_existing_episodes(
            [SimpleNamespace(episode_no=1, lifecycle_status='archived')]
        )
    assert episode_exc.value.error_key == 'SG_EPISODE_NO_CONFLICT'

    with pytest.raises(ShotGridDomainException) as scene_exc:
        ShotGridShotImportService._assert_active_existing_scenes(
            [SimpleNamespace(episode_id=10, scene_no=2, lifecycle_status='archived')],
            {(10, 2)},
        )
    assert scene_exc.value.error_key == 'SG_SCENE_NO_CONFLICT'


def test_project_storage_not_ready_uses_frozen_error_key() -> None:
    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridShotImportService._require_ready_project(
            SimpleNamespace(project_id=1, project_status='active'),
            SimpleNamespace(storage_status='initializing'),
        )
    assert exc_info.value.error_key == 'SG_PROJECT_NOT_READY'
    assert exc_info.value.http_status == CONFLICT_STATUS


@pytest.mark.parametrize('project_status', ['completed', 'archived'])
def test_completed_or_archived_project_cannot_preview_or_commit_import(project_status: str) -> None:
    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridShotImportService._require_ready_project(
            SimpleNamespace(project_id=1, project_status=project_status),
            SimpleNamespace(storage_status='ready'),
        )

    assert exc_info.value.error_key == 'SG_INVALID_STATE_TRANSITION'
    assert exc_info.value.http_status == CONFLICT_STATUS

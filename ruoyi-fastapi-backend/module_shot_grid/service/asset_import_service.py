import hashlib
import json
from collections import defaultdict
from datetime import datetime
from functools import partial
from typing import Any

from redis import asyncio as aioredis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import BusinessType
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.config import ASSET_TEMPLATE_VERSION, SHOT_GRID_IMPORT_CONFIG, ShotGridImportConfig
from module_shot_grid.dao.asset_import_dao import AssetImportDao, AssetKey
from module_shot_grid.dao.import_batch_dao import ShotGridImportBatchDao
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridAssetItem, ShotGridShotAsset
from module_shot_grid.entity.do.import_do import ShotGridImportBatch
from module_shot_grid.entity.do.storage_do import ShotGridStorageOperation
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.vo.asset_import_vo import (
    AssetImportCommitRequestModel,
    AssetImportCommitResultModel,
    AssetImportPreviewResponseModel,
    AssetImportPreviewRowModel,
)
from module_shot_grid.entity.vo.import_common_vo import ImportIssueModel, ImportPreviewTokenPayloadModel
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.asset_excel_parser import AssetExcelParser
from module_shot_grid.service.excel_security_service import ExcelSecurityService
from module_shot_grid.service.import_preview_store import ImportPreviewStore
from module_shot_grid.service.project_path_service import ShotGridProjectPathService
from utils.log_util import logger

MAX_IDEMPOTENCY_KEY_LENGTH = 100
MAX_ORIGINAL_FILE_NAME_LENGTH = 255
MAX_TASK_NAME_LENGTH = 240
FIRST_PRINTABLE_CODEPOINT = 32


class AssetImportService:
    """资产 Excel 预检查和正式提交的事务编排。"""

    @classmethod
    async def preview(
        cls,
        db: AsyncSession,
        redis: aioredis.Redis,
        project_id: int,
        file_name: str,
        contents: bytes,
        current_user: CurrentUserModel,
        *,
        config: ShotGridImportConfig = SHOT_GRID_IMPORT_CONFIG,
    ) -> AssetImportPreviewResponseModel:
        user_id, _, _ = cls._actor(current_user)
        original_file_name = cls._normalize_original_file_name(file_name)
        file_sha256 = await ExcelSecurityService.validate_and_hash_in_thread(original_file_name, contents, config)
        await cls._require_ready_storage(db, project_id)
        parser = AssetExcelParser(config)
        parsed = await ExcelSecurityService.parse_in_thread(
            partial(parser.parse, file_sha256=file_sha256),
            contents,
        )

        cls._validate_storage_segments(parsed.rows)
        await cls._resolve_assignees(db, project_id, parsed.rows)
        estimated_matches = await cls._apply_database_checks(db, project_id, parsed.rows)
        parsed.summary = parser.build_summary(
            parsed.rows,
            estimated_auto_matches=estimated_matches,
        )

        token = ImportPreviewStore.new_token()
        token_hash = ImportPreviewStore.token_hash(token)
        expires_at = ImportPreviewStore.expires_at(config)
        token_saved = False
        try:
            batch = await ShotGridImportBatchDao.create_preview_batch(
                db,
                project_id=project_id,
                import_type='asset',
                original_file_name=original_file_name,
                file_sha256=file_sha256,
                template_version=ASSET_TEMPLATE_VERSION,
                total_rows=parsed.summary.total_rows,
                valid_rows=parsed.summary.valid_rows,
                warning_rows=parsed.summary.warning_rows,
                error_rows=parsed.summary.error_rows,
                preview_token_hash=token_hash,
                preview_expires_time=expires_at,
                previewed_by=user_id,
            )
            batch_id = batch.batch_id
            payload = ImportPreviewTokenPayloadModel(
                batchId=batch_id,
                projectId=project_id,
                importType='asset',
                previewedBy=user_id,
                fileSha256=file_sha256,
                templateVersion=ASSET_TEMPLATE_VERSION,
                expiresAt=expires_at,
                rows=[row.model_dump(mode='json', by_alias=True) for row in parsed.rows],
            )
            preview_result = AssetImportPreviewResponseModel(
                batchId=batch_id,
                importToken=token,
                expiresAt=expires_at,
                summary=parsed.summary,
                rows=parsed.rows,
                workbookWarnings=parsed.workbook_warnings,
            )
            serialized_payload = ImportPreviewStore.serialize_json(payload, config)
            ImportPreviewStore.serialize_json(preview_result, config)
            await ImportPreviewStore.save(
                redis,
                token,
                payload,
                config,
                serialized_payload=serialized_payload,
            )
            token_saved = True
            await db.commit()
        except Exception:
            await db.rollback()
            if token_saved:
                await cls._delete_token_best_effort(
                    redis,
                    token,
                    config,
                    project_id=project_id,
                    batch_id=batch_id,
                )
            raise

        return preview_result

    @classmethod
    async def commit(  # noqa: PLR0915
        cls,
        db: AsyncSession,
        redis: aioredis.Redis,
        project_id: int,
        command: AssetImportCommitRequestModel,
        idempotency_key: str,
        current_user: CurrentUserModel,
        *,
        has_all_scope: bool = False,
        config: ShotGridImportConfig = SHOT_GRID_IMPORT_CONFIG,
    ) -> AssetImportCommitResultModel:
        user_id, actor_name, dept_name = cls._actor(current_user)
        stable_idempotency_key = cls._normalize_idempotency_key(idempotency_key)
        selection_hash, token_hash = cls._commit_hashes(command)
        lock_id = cls._idempotency_lock_id(project_id, user_id, stable_idempotency_key)

        batch_id: int | None = None
        selected_rows: list[AssetImportPreviewRowModel] = []
        try:
            await ShotGridImportBatchDao.lock_idempotency(db, lock_id)
            existing = await ShotGridImportBatchDao.find_by_idempotency(
                db,
                project_id,
                'asset',
                user_id,
                stable_idempotency_key,
            )
            if existing is not None:
                result = cls._replay_result(existing, token_hash, selection_hash)
                await db.rollback()
                return result

            payload = await ImportPreviewStore.get(redis, command.import_token, config)
            if payload is None:
                await cls._raise_missing_token(db, project_id, command.import_token)
            assert payload is not None
            cls._validate_token_payload(payload, project_id, user_id, has_all_scope)
            batch_id = payload.batch_id
            selected_rows = cls._select_rows(payload, command)

            batch = await ShotGridImportBatchDao.get_for_update(db, project_id, payload.batch_id)
            if batch is None or batch.import_type != 'asset':
                raise shot_grid_error(404, 'SG_IMPORT_BATCH_NOT_FOUND', '资产导入批次不存在或不可见')
            cls._validate_batch(
                batch,
                payload,
                token_hash=token_hash,
                user_id=user_id,
                has_all_scope=has_all_scope,
            )
            ShotGridImportBatchDao.mark_committing(
                batch,
                committed_by=user_id,
                idempotency_key=stable_idempotency_key,
                selection_hash=selection_hash,
            )
        except Exception:
            await db.rollback()
            raise

        try:
            result = await cls._commit_transaction(
                db,
                project_id=project_id,
                batch=batch,
                rows=selected_rows,
                actor_name=actor_name,
                dept_name=dept_name,
                selection_hash=selection_hash,
            )
        except IntegrityError as exc:
            await db.rollback()
            replay = await cls._resolve_integrity_race(
                db,
                project_id=project_id,
                user_id=user_id,
                idempotency_key=stable_idempotency_key,
                lock_id=lock_id,
                token_hash=token_hash,
                selection_hash=selection_hash,
            )
            if replay is not None:
                await cls._delete_token_best_effort(
                    redis,
                    command.import_token,
                    config,
                    project_id=project_id,
                    batch_id=batch_id or 0,
                )
                return replay
            mapped = cls._map_integrity_error(exc)
            if batch_id is not None:
                await cls._record_failed(
                    db,
                    project_id=project_id,
                    batch_id=batch_id,
                    user_id=user_id,
                    idempotency_key=stable_idempotency_key,
                    selection_hash=selection_hash,
                    error=mapped,
                    lock_id=lock_id,
                    lock_already_held=True,
                )
            else:
                await db.rollback()
            raise mapped from exc
        except ShotGridDomainException as exc:
            await db.rollback()
            if batch_id is not None:
                await cls._record_failed(
                    db,
                    project_id=project_id,
                    batch_id=batch_id,
                    user_id=user_id,
                    idempotency_key=stable_idempotency_key,
                    selection_hash=selection_hash,
                    error=exc,
                    lock_id=lock_id,
                )
            raise
        except Exception as exc:
            await db.rollback()
            mapped = shot_grid_error(500, 'SG_IMPORT_COMMIT_FAILED', '资产导入提交失败，请稍后重试')
            if batch_id is not None:
                await cls._record_failed(
                    db,
                    project_id=project_id,
                    batch_id=batch_id,
                    user_id=user_id,
                    idempotency_key=stable_idempotency_key,
                    selection_hash=selection_hash,
                    error=mapped,
                    lock_id=lock_id,
                )
            raise mapped from exc

        assert batch_id is not None
        return await cls._finish_commit(
            redis,
            command.import_token,
            config,
            result,
            project_id=project_id,
            batch_id=batch_id,
        )

    @classmethod
    async def _commit_transaction(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        batch: ShotGridImportBatch,
        rows: list[AssetImportPreviewRowModel],
        actor_name: str,
        dept_name: str | None,
        selection_hash: str,
    ) -> AssetImportCommitResultModel:
        await cls._require_ready_storage(db, project_id, for_update=True)
        cls._validate_storage_segments(rows)
        await cls._resolve_assignees(db, project_id, rows)
        cls._raise_selected_row_errors(rows)
        result = await cls._persist_selected_rows(
            db,
            project_id=project_id,
            batch=batch,
            rows=rows,
            actor_name=actor_name,
        )
        await ShotGridProjectAuditDao.add_success_log(
            db,
            title='Shot Grid 资产导入',
            business_type=BusinessType.IMPORT.value,
            method='module_shot_grid.service.asset_import_service.AssetImportService.commit()',
            request_method='POST',
            oper_name=actor_name,
            dept_name=dept_name,
            oper_url=f'/shot-grid/projects/{project_id}/assets/import/commit',
            oper_param={
                'projectId': project_id,
                'batchId': batch.batch_id,
                'selectedRows': [{'sheetName': row.sheet_name, 'rowNumber': row.row_number} for row in rows],
            },
            result=result.model_dump(mode='json', by_alias=True),
        )
        ShotGridImportBatchDao.mark_committed(
            batch,
            committed_rows=len(rows),
            selection_hash=selection_hash,
            result_summary=result.model_dump(mode='json', by_alias=True),
        )
        await db.commit()
        return result

    @classmethod
    async def _persist_selected_rows(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        batch: ShotGridImportBatch,
        rows: list[AssetImportPreviewRowModel],
        actor_name: str,
    ) -> AssetImportCommitResultModel:
        cls._ensure_selected_consistency(rows)
        ordered_rows = sorted(rows, key=lambda item: (item.sheet_name, item.row_number))
        grouped_rows: dict[AssetKey, list[AssetImportPreviewRowModel]] = defaultdict(list)
        for row in ordered_rows:
            normalized = row.normalized
            grouped_rows[(normalized.asset_type, normalized.asset_name_key)].append(row)  # type: ignore[arg-type]

        keys = list(grouped_rows)
        existing_assets = await AssetImportDao.get_active_assets_by_keys(
            db,
            project_id,
            keys,
            for_update=True,
        )
        assets_by_key: dict[AssetKey, list[ShotGridAsset]] = defaultdict(list)
        for asset in existing_assets:
            assets_by_key[(asset.asset_type, asset.asset_name_key)].append(asset)
        if any(len(values) > 1 for values in assets_by_key.values()):
            raise shot_grid_error(409, 'SG_ASSET_NAME_CONFLICT', '存在多个同类型同名资产，禁止自动选择')

        existing_items = await AssetImportDao.get_asset_items(
            db,
            [asset.asset_id for asset in existing_assets],
            for_update=True,
        )
        existing_import_rows = await AssetImportDao.get_asset_items_by_import_keys(
            db,
            project_id,
            [row.normalized.import_row_key for row in ordered_rows if row.normalized.import_row_key],
            for_update=True,
        )
        if existing_import_rows:
            raise shot_grid_error(409, 'SG_IMPORT_BATCH_STATE_CONFLICT', '选择的资产行已经提交过')

        existing_item_keys = {
            (item.asset_id, item.production_item_key) for item in existing_items if item.production_item_key is not None
        }
        max_item_sort_order: dict[int, int] = defaultdict(int)
        for item in existing_items:
            max_item_sort_order[item.asset_id] = max(max_item_sort_order[item.asset_id], item.sort_order)

        now = datetime.now()
        selected_assets, created_assets_by_type, reused_assets = await cls._resolve_assets(
            db,
            project_id=project_id,
            grouped_rows=grouped_rows,
            assets_by_key=assets_by_key,
            actor_name=actor_name,
            now=now,
        )
        created_tasks, missing_production_items = await cls._create_asset_items(
            db,
            project_id=project_id,
            batch=batch,
            rows=ordered_rows,
            assets=selected_assets,
            existing_item_keys=existing_item_keys,
            max_item_sort_order=max_item_sort_order,
            actor_name=actor_name,
            now=now,
        )
        auto_matched = await cls._match_requirements(
            db,
            project_id=project_id,
            assets=selected_assets,
            actor_name=actor_name,
            now=now,
        )
        await db.flush()
        requirement_counts = await AssetImportDao.count_requirements_by_status(
            db,
            project_id,
            ('pending', 'conflict'),
        )
        return AssetImportCommitResultModel(
            batchId=batch.batch_id,
            committedRows=len(rows),
            createdAssetsByType=created_assets_by_type,
            reusedAssets=reused_assets,
            createdAssetItems=len(rows),
            createdTasks=created_tasks,
            missingProductionItemWarnings=missing_production_items,
            autoMatchedRequirements=auto_matched,
            pendingRequirements=requirement_counts.get('pending', 0),
            conflictRequirements=requirement_counts.get('conflict', 0),
        )

    @classmethod
    async def _resolve_assets(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        grouped_rows: dict[AssetKey, list[AssetImportPreviewRowModel]],
        assets_by_key: dict[AssetKey, list[ShotGridAsset]],
        actor_name: str,
        now: datetime,
    ) -> tuple[dict[AssetKey, ShotGridAsset], dict[str, int], int]:
        created_assets_by_type = {'Character': 0, 'Environment': 0, 'Prop': 0}
        reused_assets = 0
        selected_assets: dict[AssetKey, ShotGridAsset] = {}
        for position, (key, parent_rows) in enumerate(grouped_rows.items(), start=1):
            matches = assets_by_key.get(key, [])
            if matches:
                asset = matches[0]
                cls._validate_existing_asset_fields(asset, parent_rows)
                reused_assets += 1
            else:
                first = parent_rows[0].normalized
                asset_description = next(
                    (
                        parent_row.normalized.asset_description
                        for parent_row in parent_rows
                        if parent_row.normalized.asset_description is not None
                    ),
                    None,
                )
                storage_dir_name = ShotGridProjectPathService.normalize_segment(first.asset_name)
                target_relative_path = f'ASSET\\{first.asset_type}\\{storage_dir_name}'
                asset = await AssetImportDao.add_asset(
                    db,
                    ShotGridAsset(
                        project_id=project_id,
                        asset_name=first.asset_name,
                        asset_name_key=first.asset_name_key,
                        asset_type=first.asset_type,
                        storage_dir_name=storage_dir_name,
                        storage_path_key=target_relative_path.casefold(),
                        description=asset_description,
                        sort_order=position * 10,
                        lifecycle_status='active',
                        create_by=actor_name,
                        create_time=now,
                        update_by=actor_name,
                        update_time=now,
                        lock_version=0,
                        del_flag='0',
                    ),
                )
                created_assets_by_type[asset.asset_type] += 1
                await AssetImportDao.add_storage_operation(
                    db,
                    ShotGridStorageOperation(
                        project_id=project_id,
                        operation_type='ensure_asset_directory',
                        aggregate_type='asset',
                        aggregate_id=asset.asset_id,
                        target_relative_path=target_relative_path,
                        operation_status='pending',
                        idempotency_key=f'asset-directory:{project_id}:{asset.asset_id}',
                        attempt_count=0,
                        create_by=actor_name,
                        create_time=now,
                        update_time=now,
                    ),
                )
            selected_assets[key] = asset
        return selected_assets, created_assets_by_type, reused_assets

    @classmethod
    async def _create_asset_items(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        batch: ShotGridImportBatch,
        rows: list[AssetImportPreviewRowModel],
        assets: dict[AssetKey, ShotGridAsset],
        existing_item_keys: set[tuple[int, str]],
        max_item_sort_order: dict[int, int],
        actor_name: str,
        now: datetime,
    ) -> tuple[int, int]:
        created_tasks = 0
        missing_production_items = 0
        for row in rows:
            normalized = row.normalized
            key = (normalized.asset_type, normalized.asset_name_key)
            asset = assets[key]  # type: ignore[index]
            if (
                normalized.production_item_key
                and (asset.asset_id, normalized.production_item_key) in existing_item_keys
            ):
                raise shot_grid_error(409, 'SG_ASSET_PRODUCTION_ITEM_CONFLICT', '资产制作分项已存在')
            if normalized.production_item is None:
                missing_production_items += 1
            max_item_sort_order[asset.asset_id] += 10
            item = await AssetImportDao.add_asset_item(
                db,
                ShotGridAssetItem(
                    project_id=project_id,
                    asset_id=asset.asset_id,
                    production_item=normalized.production_item,
                    production_item_key=normalized.production_item_key,
                    description=normalized.item_description,
                    remark=normalized.remark,
                    sort_order=max_item_sort_order[asset.asset_id],
                    source_import_batch_id=batch.batch_id,
                    source_row_no=row.row_number,
                    import_row_key=normalized.import_row_key,
                    lifecycle_status='active',
                    create_by=actor_name,
                    create_time=now,
                    update_by=actor_name,
                    update_time=now,
                    lock_version=0,
                    del_flag='0',
                ),
            )
            if normalized.assignee_user_id is not None:
                task_suffix = normalized.production_item or '待补制作分项'
                await AssetImportDao.add_task(
                    db,
                    ShotGridTask(
                        project_id=project_id,
                        asset_item_id=item.asset_item_id,
                        task_name=f'{asset.asset_name} - {task_suffix}'[:MAX_TASK_NAME_LENGTH],
                        task_kind='asset_image',
                        assignee_user_id=normalized.assignee_user_id,
                        task_status='not_started',
                        priority='normal',
                        requirements=normalized.task_description,
                        create_by=actor_name,
                        create_time=now,
                        update_by=actor_name,
                        update_time=now,
                        lock_version=0,
                        del_flag='0',
                    ),
                )
                created_tasks += 1
        return created_tasks, missing_production_items

    @classmethod
    async def _match_requirements(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        assets: dict[AssetKey, ShotGridAsset],
        actor_name: str,
        now: datetime,
    ) -> int:
        requirements = await AssetImportDao.get_requirements_for_keys(
            db,
            project_id,
            list(assets),
            for_update=True,
        )
        pairs = [
            (requirement.shot_id, assets[(requirement.asset_type, requirement.normalized_name)].asset_id)
            for requirement in requirements
        ]
        existing_pairs = await AssetImportDao.get_existing_shot_asset_pairs(db, project_id, pairs)
        matched = 0
        for requirement in requirements:
            asset = assets[(requirement.asset_type, requirement.normalized_name)]
            pair = (requirement.shot_id, asset.asset_id)
            if pair not in existing_pairs:
                AssetImportDao.add_shot_asset(
                    db,
                    ShotGridShotAsset(
                        project_id=project_id,
                        shot_id=requirement.shot_id,
                        asset_id=asset.asset_id,
                        create_by=actor_name,
                        create_time=now,
                    ),
                )
                existing_pairs.add(pair)
            requirement.resolution_status = 'matched'
            requirement.asset_id = asset.asset_id
            requirement.resolved_by = None
            requirement.resolved_time = now
            requirement.resolution_reason = '资产导入按类型和规范化名称精确匹配'
            requirement.update_by = actor_name
            requirement.update_time = now
            matched += 1
        return matched

    @classmethod
    async def _resolve_assignees(
        cls,
        db: AsyncSession,
        project_id: int,
        rows: list[AssetImportPreviewRowModel],
    ) -> None:
        names = {
            row.normalized.assignee_user_name for row in rows if row.normalized.assignee_user_name and not row.errors
        }
        candidates = await AssetImportDao.get_member_candidates(db, project_id, names)
        for row in rows:
            normalized = row.normalized
            name = normalized.assignee_user_name
            if not name or row.errors:
                row.refresh_can_import()
                continue
            username_matches = [candidate for candidate in candidates if candidate['user_name'] == name]
            matches = username_matches or [candidate for candidate in candidates if candidate['nick_name'] == name]
            if len(matches) != 1:
                error_key = 'SG_TASK_ASSIGNEE_AMBIGUOUS' if len(matches) > 1 else 'SG_TASK_ASSIGNEE_INVALID'
                message = '制作人匹配到多名项目成员' if len(matches) > 1 else '制作人不是有效的项目成员'
                cls._append_issue(row, error_key, message, 'assigneeUserName')
            elif not matches[0]['producer_code']:
                cls._append_issue(
                    row,
                    'SG_PRODUCER_CODE_REQUIRED',
                    '制作人尚未设置项目内制作人缩写',
                    'assigneeUserName',
                )
            else:
                normalized.assignee_user_id = matches[0]['user_id']
                normalized.producer_code = matches[0]['producer_code']
            row.refresh_can_import()

    @classmethod
    async def _apply_database_checks(
        cls,
        db: AsyncSession,
        project_id: int,
        rows: list[AssetImportPreviewRowModel],
    ) -> int:
        keys = sorted(
            {
                (row.normalized.asset_type, row.normalized.asset_name_key)
                for row in rows
                if row.normalized.asset_type and row.normalized.asset_name_key
            }
        )
        assets = await AssetImportDao.get_active_assets_by_keys(db, project_id, keys)
        by_key: dict[AssetKey, list[ShotGridAsset]] = defaultdict(list)
        for asset in assets:
            by_key[(asset.asset_type, asset.asset_name_key)].append(asset)
        items = await AssetImportDao.get_asset_items(db, [asset.asset_id for asset in assets])
        item_keys = {
            (item.asset_id, item.production_item_key) for item in items if item.production_item_key is not None
        }
        imported = await AssetImportDao.get_asset_items_by_import_keys(
            db,
            project_id,
            [row.normalized.import_row_key for row in rows if row.normalized.import_row_key],
        )
        imported_keys = {item.import_row_key for item in imported}

        for row in rows:
            normalized = row.normalized
            key = (normalized.asset_type, normalized.asset_name_key)
            parent_matches = by_key.get(key, [])  # type: ignore[arg-type]
            if len(parent_matches) > 1:
                cls._append_issue(row, 'SG_ASSET_NAME_CONFLICT', '存在多个同类型同名资产', 'assetName')
            elif parent_matches:
                asset = parent_matches[0]
                if normalized.production_item_key and (asset.asset_id, normalized.production_item_key) in item_keys:
                    cls._append_issue(
                        row,
                        'SG_ASSET_PRODUCTION_ITEM_CONFLICT',
                        '数据库中已存在同名制作分项',
                        'productionItem',
                    )
                if normalized.asset_description is not None and cls._display(asset.description) != cls._display(
                    normalized.asset_description
                ):
                    cls._append_issue(row, 'SG_ASSET_NAME_CONFLICT', '已有资产的描述与导入值不一致', 'assetDescription')
            if normalized.import_row_key in imported_keys:
                cls._append_issue(row, 'SG_IMPORT_BATCH_STATE_CONFLICT', '该来源行已经提交过', None)
            row.refresh_can_import()

        importable_keys = {
            (row.normalized.asset_type, row.normalized.asset_name_key)
            for row in rows
            if row.can_import and row.normalized.asset_type and row.normalized.asset_name_key
        }
        requirements = await AssetImportDao.get_requirements_for_keys(db, project_id, list(importable_keys))
        return sum(
            len(by_key.get(key, [])) <= 1 for key in [(item.asset_type, item.normalized_name) for item in requirements]
        )

    @classmethod
    def _validate_storage_segments(cls, rows: list[AssetImportPreviewRowModel]) -> None:
        for row in rows:
            asset_name = row.normalized.asset_name
            if not asset_name:
                continue
            try:
                ShotGridProjectPathService.normalize_segment(asset_name)
            except ShotGridDomainException:
                cls._append_issue(
                    row,
                    'SG_STORAGE_PATH_INVALID',
                    '资产名称不能作为安全的 NAS 目录名称',
                    'assetName',
                )
                row.refresh_can_import()

    @staticmethod
    async def _require_ready_storage(
        db: AsyncSession,
        project_id: int,
        *,
        for_update: bool = False,
    ) -> None:
        project, storage = await AssetImportDao.get_project_storage(db, project_id, for_update=for_update)
        if project is None or storage is None or storage.storage_status != 'ready':
            raise shot_grid_error(409, 'SG_PROJECT_NOT_READY', '项目 NAS 存储尚未就绪，禁止导入资产')

    @classmethod
    def _ensure_selected_consistency(cls, rows: list[AssetImportPreviewRowModel]) -> None:
        production_keys: set[tuple[str, str, str]] = set()
        descriptions: dict[AssetKey, str | None] = {}
        for row in rows:
            normalized = row.normalized
            if not normalized.asset_type or not normalized.asset_name or not normalized.asset_name_key:
                raise shot_grid_error(422, 'SG_IMPORT_HAS_ERRORS', '选中行缺少资产主数据')
            parent_key = (normalized.asset_type, normalized.asset_name_key)
            if normalized.asset_description is not None:
                current = cls._display(normalized.asset_description)
                if parent_key in descriptions and descriptions[parent_key] != current:
                    raise shot_grid_error(409, 'SG_ASSET_NAME_CONFLICT', '同一资产的资产描述不一致')
                descriptions[parent_key] = current
            if normalized.production_item_key:
                item_key = (*parent_key, normalized.production_item_key)
                if item_key in production_keys:
                    raise shot_grid_error(409, 'SG_ASSET_PRODUCTION_ITEM_CONFLICT', '选中行包含重复制作分项')
                production_keys.add(item_key)

    @classmethod
    def _validate_existing_asset_fields(
        cls,
        asset: ShotGridAsset,
        rows: list[AssetImportPreviewRowModel],
    ) -> None:
        for row in rows:
            description = row.normalized.asset_description
            if description is not None and cls._display(asset.description) != cls._display(description):
                raise shot_grid_error(409, 'SG_ASSET_NAME_CONFLICT', '已有资产的描述与导入值不一致')

    @staticmethod
    def _select_rows(
        payload: ImportPreviewTokenPayloadModel,
        command: AssetImportCommitRequestModel,
    ) -> list[AssetImportPreviewRowModel]:
        rows = [AssetImportPreviewRowModel.model_validate(item) for item in payload.rows]
        by_identity = {(row.sheet_name, row.row_number): row for row in rows}
        selected: list[AssetImportPreviewRowModel] = []
        invalid: list[dict[str, Any]] = []
        for identity in command.selected_rows:
            row = by_identity.get(identity.key())
            if row is None or not row.can_import or row.errors:
                invalid.append({'sheetName': identity.sheet_name, 'rowNumber': identity.row_number})
            else:
                selected.append(row)
        if invalid:
            raise shot_grid_error(
                422,
                'SG_IMPORT_HAS_ERRORS',
                '选中行不存在或仍有错误',
                details={'rows': invalid},
            )
        return selected

    @staticmethod
    def _raise_selected_row_errors(rows: list[AssetImportPreviewRowModel]) -> None:
        invalid = [
            {'sheetName': row.sheet_name, 'rowNumber': row.row_number}
            for row in rows
            if row.errors or not row.can_import
        ]
        if invalid:
            raise shot_grid_error(
                422, 'SG_IMPORT_HAS_ERRORS', '提交前重新检查发现选中行存在错误', details={'rows': invalid}
            )

    @classmethod
    def _validate_token_payload(
        cls,
        payload: ImportPreviewTokenPayloadModel,
        project_id: int,
        user_id: int,
        has_all_scope: bool,
    ) -> None:
        if payload.import_type != 'asset' or payload.project_id != project_id:
            raise shot_grid_error(400, 'SG_IMPORT_TOKEN_INVALID', '导入 Token 与当前项目或类型不匹配')
        if payload.previewed_by != user_id and not has_all_scope:
            raise shot_grid_error(403, 'SG_IMPORT_TOKEN_FORBIDDEN', '只能提交本人创建的导入预检查')
        if payload.template_version != ASSET_TEMPLATE_VERSION:
            raise shot_grid_error(
                409,
                'SG_IMPORT_TEMPLATE_VERSION_MISMATCH',
                '资产导入模板版本已经变化，请重新预检查',
            )
        if cls._is_expired(payload.expires_at):
            raise shot_grid_error(410, 'SG_IMPORT_TOKEN_EXPIRED', '导入 Token 已过期，请重新预检查')

    @classmethod
    def _validate_batch(
        cls,
        batch: ShotGridImportBatch,
        payload: ImportPreviewTokenPayloadModel,
        *,
        token_hash: str,
        user_id: int,
        has_all_scope: bool,
    ) -> None:
        if batch.preview_token_hash != token_hash:
            raise shot_grid_error(400, 'SG_IMPORT_TOKEN_INVALID', '导入 Token 与批次不匹配')
        if batch.import_type != 'asset':
            raise shot_grid_error(400, 'SG_IMPORT_TOKEN_INVALID', '导入批次类型不是资产导入')
        if batch.file_sha256 != payload.file_sha256:
            raise shot_grid_error(409, 'SG_IMPORT_FILE_HASH_MISMATCH', '导入批次与预检查文件摘要不一致')
        if batch.template_version != ASSET_TEMPLATE_VERSION or batch.template_version != payload.template_version:
            raise shot_grid_error(
                409,
                'SG_IMPORT_TEMPLATE_VERSION_MISMATCH',
                '资产导入模板版本已经变化，请重新预检查',
            )
        if batch.batch_status != 'previewed':
            raise shot_grid_error(409, 'SG_IMPORT_BATCH_STATE_CONFLICT', '导入批次当前状态不可提交')
        if batch.preview_expires_time is None or cls._is_expired(batch.preview_expires_time):
            raise shot_grid_error(410, 'SG_IMPORT_TOKEN_EXPIRED', '导入批次预览已经过期')
        if batch.preview_expires_time != payload.expires_at:
            raise shot_grid_error(400, 'SG_IMPORT_TOKEN_INVALID', '导入 Token 与批次到期时间不匹配')
        if batch.previewed_by != payload.previewed_by:
            raise shot_grid_error(400, 'SG_IMPORT_TOKEN_INVALID', '导入 Token 与批次创建用户不匹配')
        if batch.previewed_by != user_id and not has_all_scope:
            raise shot_grid_error(403, 'SG_IMPORT_TOKEN_FORBIDDEN', '只能提交本人创建的导入预检查')

    @classmethod
    def _replay_result(
        cls,
        batch: ShotGridImportBatch,
        token_hash: str,
        selection_hash: str,
    ) -> AssetImportCommitResultModel:
        if batch.preview_token_hash != token_hash or batch.selection_hash != selection_hash:
            raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '同一幂等键对应了不同的 Token 或选择行')
        if batch.batch_status == 'failed':
            raise shot_grid_error(
                409,
                batch.last_error_key or 'SG_IMPORT_BATCH_STATE_CONFLICT',
                batch.last_error_message or '该幂等请求此前提交失败，请重新预检查',
            )
        if batch.batch_status != 'committed' or not isinstance(batch.result_summary, dict):
            raise shot_grid_error(409, 'SG_IMPORT_BATCH_STATE_CONFLICT', '幂等提交尚未成功或已失败')
        try:
            return AssetImportCommitResultModel.model_validate(batch.result_summary)
        except Exception as exc:
            raise shot_grid_error(409, 'SG_IMPORT_BATCH_STATE_CONFLICT', '导入结果快照已损坏') from exc

    @classmethod
    async def _resolve_integrity_race(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        user_id: int,
        idempotency_key: str,
        lock_id: int,
        token_hash: str,
        selection_hash: str,
    ) -> AssetImportCommitResultModel | None:
        try:
            await ShotGridImportBatchDao.lock_idempotency(db, lock_id)
            existing = await ShotGridImportBatchDao.find_by_idempotency(
                db,
                project_id,
                'asset',
                user_id,
                idempotency_key,
            )
            if existing is None:
                return None
            result = cls._replay_result(existing, token_hash, selection_hash)
            await db.rollback()
            return result
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def _record_failed(
        db: AsyncSession,
        *,
        project_id: int,
        batch_id: int,
        user_id: int,
        idempotency_key: str,
        selection_hash: str,
        error: ShotGridDomainException,
        lock_id: int,
        lock_already_held: bool = False,
    ) -> None:
        try:
            if not lock_already_held:
                await ShotGridImportBatchDao.lock_idempotency(db, lock_id)
            existing = await ShotGridImportBatchDao.find_by_idempotency(
                db,
                project_id,
                'asset',
                user_id,
                idempotency_key,
            )
            if existing is not None and existing.batch_id != batch_id:
                await db.commit()
                return
            await ShotGridImportBatchDao.mark_failed(
                db,
                project_id=project_id,
                batch_id=batch_id,
                committed_by=user_id,
                idempotency_key=idempotency_key,
                selection_hash=selection_hash,
                error_key=error.error_key,
                error_message=error.message,
            )
            await db.commit()
        except Exception:
            await db.rollback()

    @staticmethod
    async def _delete_token_best_effort(
        redis: aioredis.Redis,
        token: str,
        config: ShotGridImportConfig,
        *,
        project_id: int,
        batch_id: int,
    ) -> None:
        try:
            await ImportPreviewStore.delete(redis, token, config)
        except Exception as exc:
            logger.warning(
                '清理资产导入预览 Token 失败：project_id={} batch_id={} error={}',
                project_id,
                batch_id,
                type(exc).__name__,
            )

    @classmethod
    async def _finish_commit(
        cls,
        redis: aioredis.Redis,
        token: str,
        config: ShotGridImportConfig,
        result: AssetImportCommitResultModel,
        *,
        project_id: int,
        batch_id: int,
    ) -> AssetImportCommitResultModel:
        await cls._delete_token_best_effort(
            redis,
            token,
            config,
            project_id=project_id,
            batch_id=batch_id,
        )
        return result

    @staticmethod
    async def _raise_missing_token(db: AsyncSession, project_id: int, token: str) -> None:
        token_hash = ImportPreviewStore.token_hash(token)
        batch = await ShotGridImportBatchDao.find_by_token_hash(db, project_id, 'asset', token_hash)
        if (
            batch is not None
            and batch.preview_expires_time is not None
            and AssetImportService._is_expired(batch.preview_expires_time)
        ):
            await ShotGridImportBatchDao.expire_preview(db, project_id, batch.batch_id)
            await db.commit()
            raise shot_grid_error(410, 'SG_IMPORT_TOKEN_EXPIRED', '导入 Token 已过期，请重新预检查')
        raise shot_grid_error(400, 'SG_IMPORT_TOKEN_INVALID', '导入 Token 不合法或预览数据已失效')

    @staticmethod
    def _selection_hash(command: AssetImportCommitRequestModel) -> str:
        selected = sorted(
            ({'sheetName': item.sheet_name, 'rowNumber': item.row_number} for item in command.selected_rows),
            key=lambda item: (item['sheetName'], item['rowNumber']),
        )
        canonical = json.dumps(selected, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    @classmethod
    def _commit_hashes(cls, command: AssetImportCommitRequestModel) -> tuple[str, str]:
        return cls._selection_hash(command), ImportPreviewStore.token_hash(command.import_token)

    @staticmethod
    def _idempotency_lock_id(project_id: int, user_id: int, idempotency_key: str) -> int:
        material = f'{project_id}\0asset\0{user_id}\0{idempotency_key}'.encode()
        return int.from_bytes(hashlib.sha256(material).digest()[:8], byteorder='big', signed=True)

    @staticmethod
    def _normalize_idempotency_key(value: str) -> str:
        normalized = value.strip() if value else ''
        if (
            not normalized
            or len(normalized) > MAX_IDEMPOTENCY_KEY_LENGTH
            or any(ord(character) < FIRST_PRINTABLE_CODEPOINT for character in normalized)
        ):
            raise shot_grid_error(422, 'SG_IDEMPOTENCY_KEY_INVALID', 'X-Idempotency-Key 长度必须为1到100个字符')
        return normalized

    @staticmethod
    def _normalize_original_file_name(file_name: str) -> str:
        normalized = (file_name or '').replace('\\', '/').rsplit('/', 1)[-1].strip()
        if (
            not normalized
            or len(normalized) > MAX_ORIGINAL_FILE_NAME_LENGTH
            or any(ord(character) < FIRST_PRINTABLE_CODEPOINT for character in normalized)
        ):
            raise shot_grid_error(422, 'SG_IMPORT_FILE_NAME_INVALID', '导入文件名不能为空且不能超过255个字符')
        return normalized

    @staticmethod
    def _actor(current_user: CurrentUserModel) -> tuple[int, str, str | None]:
        user = current_user.user
        if user is None or user.user_id is None or not user.user_name:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '无法识别当前用户')
        dept_name = user.dept.dept_name if user.dept is not None else None
        return user.user_id, user.user_name, dept_name

    @staticmethod
    def _append_issue(
        row: AssetImportPreviewRowModel,
        error_key: str,
        message: str,
        field_name: str | None,
    ) -> None:
        if any(issue.error_key == error_key and issue.field_name == field_name for issue in row.errors):
            return
        row.errors.append(
            ImportIssueModel(
                errorKey=error_key,
                message=message,
                fieldName=field_name,
                sheetName=row.sheet_name,
                rowNumber=row.row_number,
            )
        )

    @staticmethod
    def _display(value: object) -> str | None:
        return AssetExcelParser.normalize_display_text(value)

    @staticmethod
    def _is_expired(value: datetime) -> bool:
        now = datetime.now(value.tzinfo) if value.tzinfo else datetime.now()
        return value <= now

    @staticmethod
    def _map_integrity_error(exc: IntegrityError) -> ShotGridDomainException:
        message = str(exc.orig).lower()
        if 'uk_sg_import_batch_idempotency' in message:
            return shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '同一幂等键已被其他资产导入占用')
        if 'uk_sg_asset_item_name_active' in message:
            return shot_grid_error(409, 'SG_ASSET_PRODUCTION_ITEM_CONFLICT', '资产制作分项已存在')
        if 'uk_sg_task_asset_item' in message:
            return shot_grid_error(409, 'SG_TASK_ALREADY_EXISTS', '资产制作分项任务已存在')
        if 'uk_sg_asset_item_import_row' in message:
            return shot_grid_error(409, 'SG_IMPORT_BATCH_STATE_CONFLICT', '选择的来源行已经提交过')
        if 'uk_sg_asset_name_active' in message or 'uk_sg_asset_storage_path' in message:
            return shot_grid_error(409, 'SG_ASSET_NAME_CONFLICT', '项目内同类型资产名称或目录冲突')
        return shot_grid_error(409, 'SG_IMPORT_BATCH_STATE_CONFLICT', '资产导入发生并发冲突，请重新预检查')

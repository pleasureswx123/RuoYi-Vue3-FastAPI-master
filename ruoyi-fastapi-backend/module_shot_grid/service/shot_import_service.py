import hashlib
from collections import defaultdict
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from redis import asyncio as aioredis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import BusinessType
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.config import SHOT_GRID_IMPORT_CONFIG, SHOT_TEMPLATE_VERSION, ShotGridImportConfig
from module_shot_grid.dao.import_batch_dao import ShotGridImportBatchDao
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.shot_import_dao import ShotGridShotImportDao
from module_shot_grid.entity.do.asset_do import ShotGridShotAsset, ShotGridShotAssetRequirement
from module_shot_grid.entity.do.project_do import ShotGridEpisode, ShotGridScene, ShotGridShot
from module_shot_grid.entity.do.storage_do import ShotGridStorageOperation
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.vo.import_common_vo import (
    ImportIssueModel,
    ImportPreviewTokenPayloadModel,
    ImportSelectedRowModel,
)
from module_shot_grid.entity.vo.shot_import_vo import (
    ShotImportCommitRequestModel,
    ShotImportCommitResultModel,
    ShotImportNormalizedRowModel,
    ShotImportPreviewResultModel,
    ShotImportPreviewRowModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.excel_security_service import ExcelSecurityService
from module_shot_grid.service.import_preview_store import ImportPreviewStore
from module_shot_grid.service.shot_excel_parser import ShotExcelParser
from utils.log_util import logger


class ShotGridShotImportService:
    """镜头 Excel 预检查、Token 绑定和全事务正式提交。"""

    IDEMPOTENCY_KEY_MAX_LENGTH = 100
    ORIGINAL_FILE_NAME_MAX_LENGTH = 255
    FIRST_PRINTABLE_CODEPOINT = 32

    @classmethod
    async def preview(
        cls,
        db: AsyncSession,
        redis: aioredis.Redis,
        *,
        project_id: int,
        file_name: str,
        contents: bytes,
        current_user: CurrentUserModel,
        config: ShotGridImportConfig = SHOT_GRID_IMPORT_CONFIG,
    ) -> ShotImportPreviewResultModel:
        user_id, _ = cls._current_user_identity(current_user)
        safe_file_name = cls._safe_original_file_name(file_name)
        file_sha256 = await ExcelSecurityService.validate_and_hash_in_thread(safe_file_name, contents, config)
        project, storage = await ShotGridShotImportDao.get_project_storage(db, project_id)
        cls._require_ready_project(project, storage)

        parse_result = await ExcelSecurityService.parse_in_thread(ShotExcelParser(config).parse, contents)
        cls._assign_row_keys(parse_result.rows, file_sha256)
        await cls._enrich_rows_from_database(db, project_id, parse_result.rows)
        parse_result.summary = ShotExcelParser.build_summary(parse_result.rows)

        token = ImportPreviewStore.new_token()
        token_hash = ImportPreviewStore.token_hash(token)
        expires_at = ImportPreviewStore.expires_at(config)
        batch = await ShotGridImportBatchDao.create_preview_batch(
            db,
            project_id=project_id,
            import_type='shot',
            original_file_name=safe_file_name,
            file_sha256=file_sha256,
            template_version=SHOT_TEMPLATE_VERSION,
            total_rows=parse_result.summary.total_rows,
            valid_rows=parse_result.summary.valid_rows,
            warning_rows=parse_result.summary.warning_rows,
            error_rows=parse_result.summary.error_rows,
            preview_token_hash=token_hash,
            preview_expires_time=expires_at,
            previewed_by=user_id,
        )
        batch_id = batch.batch_id
        payload = ImportPreviewTokenPayloadModel(
            batchId=batch_id,
            projectId=project_id,
            importType='shot',
            previewedBy=user_id,
            fileSha256=file_sha256,
            templateVersion=SHOT_TEMPLATE_VERSION,
            expiresAt=expires_at,
            rows=[row.model_dump(mode='json', by_alias=True) for row in parse_result.rows],
        )
        preview_result = ShotImportPreviewResultModel(
            batchId=batch_id,
            importToken=token,
            expiresAt=expires_at,
            summary=parse_result.summary,
            rows=parse_result.rows,
            workbookWarnings=parse_result.workbook_warnings,
        )
        saved_to_redis = False
        try:
            serialized_payload = ImportPreviewStore.serialize_json(payload, config)
            ImportPreviewStore.serialize_json(preview_result, config)
            await ImportPreviewStore.save(
                redis,
                token,
                payload,
                config,
                serialized_payload=serialized_payload,
            )
            saved_to_redis = True
            await db.commit()
        except Exception:
            await db.rollback()
            if saved_to_redis:
                await cls._delete_preview_token_best_effort(
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
        *,
        project_id: int,
        request_model: ShotImportCommitRequestModel,
        idempotency_key: str,
        current_user: CurrentUserModel,
        has_all_scope: bool = False,
        config: ShotGridImportConfig = SHOT_GRID_IMPORT_CONFIG,
    ) -> ShotImportCommitResultModel:
        user_id, user_name = cls._current_user_identity(current_user)
        clean_idempotency_key = idempotency_key.strip()
        if not clean_idempotency_key or len(clean_idempotency_key) > cls.IDEMPOTENCY_KEY_MAX_LENGTH:
            raise shot_grid_error(422, 'SG_IDEMPOTENCY_KEY_INVALID', 'X-Idempotency-Key 长度必须为 1—100')

        token_hash = ImportPreviewStore.token_hash(request_model.import_token)
        try:
            await ShotGridImportBatchDao.lock_idempotency(
                db,
                cls._idempotency_lock_id(project_id, user_id, clean_idempotency_key),
            )
            existing = await ShotGridImportBatchDao.find_by_idempotency(
                db,
                project_id,
                'shot',
                user_id,
                clean_idempotency_key,
            )
            if existing is not None:
                if existing.preview_token_hash != token_hash:
                    raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '幂等键已用于不同的导入 Token')
                expected_selection_hash = cls._selection_hash_from_request(
                    existing.file_sha256, request_model.selected_rows
                )
                if existing.selection_hash != expected_selection_hash:
                    raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '幂等键已用于不同的选中行')
                replay_result = cls._existing_result(existing)
                await db.rollback()
                return replay_result

            payload = await ImportPreviewStore.get(redis, request_model.import_token, config)
            if payload is None:
                await cls._raise_missing_token(
                    db,
                    project_id,
                    request_model.import_token,
                    config,
                )
            assert payload is not None
            cls._validate_payload(payload, project_id, user_id, has_all_scope)

            selected_rows = cls._select_rows(payload, request_model.selected_rows)
            selection_hash = cls._selection_hash(selected_rows)
        except Exception:
            await db.rollback()
            raise
        started_commit = False
        batch_id = payload.batch_id

        try:
            batch = await ShotGridImportBatchDao.get_for_update(db, project_id, batch_id)
            if batch is None:
                raise shot_grid_error(404, 'SG_IMPORT_BATCH_NOT_FOUND', '导入批次不存在或不可见')
            cls._validate_locked_batch(
                batch,
                payload,
                token_hash,
                user_id,
                has_all_scope,
            )
            ShotGridImportBatchDao.mark_committing(
                batch,
                committed_by=user_id,
                idempotency_key=clean_idempotency_key,
                selection_hash=selection_hash,
            )
            started_commit = True
            await db.flush()

            project, storage = await ShotGridShotImportDao.get_project_storage(db, project_id, for_update=True)
            cls._require_ready_project(project, storage)
            await cls._revalidate_selected_rows(db, project_id, selected_rows)
            result = await cls._write_selected_rows(
                db,
                project_id=project_id,
                batch_id=batch_id,
                rows=selected_rows,
                audit_user=user_name,
            )
            result.batch_id = batch_id
            result.committed_rows = len(selected_rows)
            result_summary = result.model_dump(mode='json', by_alias=True)
            ShotGridImportBatchDao.mark_committed(
                batch,
                committed_rows=len(selected_rows),
                selection_hash=selection_hash,
                result_summary=result_summary,
            )
            await ShotGridProjectAuditDao.add_success_log(
                db,
                title='Shot Grid镜头导入',
                business_type=BusinessType.IMPORT.value,
                method='module_shot_grid.service.shot_import_service.ShotGridShotImportService.commit()',
                request_method='POST',
                oper_name=user_name,
                dept_name=cls._current_user_dept_name(current_user),
                oper_url=f'/shot-grid/projects/{project_id}/shots/import/commit',
                oper_param={
                    'batchId': batch_id,
                    'selectedRows': [row.model_dump(by_alias=True) for row in request_model.selected_rows],
                },
                result=result_summary,
            )
            await db.commit()
            await cls._delete_preview_token_best_effort(
                redis,
                request_model.import_token,
                config,
                project_id=project_id,
                batch_id=batch_id,
            )
            return result
        except Exception as exc:
            await db.rollback()
            if started_commit:
                await cls._record_failed_batch(
                    db,
                    project_id=project_id,
                    batch_id=batch_id,
                    committed_by=user_id,
                    idempotency_key=clean_idempotency_key,
                    selection_hash=selection_hash,
                    exc=exc,
                )
            if isinstance(exc, ShotGridDomainException):
                raise
            if isinstance(exc, IntegrityError):
                raise shot_grid_error(409, 'SG_IMPORT_DATABASE_CONFLICT', '导入数据与数据库当前状态冲突') from exc
            raise shot_grid_error(500, 'SG_IMPORT_COMMIT_FAILED', '镜头导入提交失败') from exc

    @classmethod
    async def _write_selected_rows(  # noqa: PLR0915
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        batch_id: int,
        rows: list[ShotImportPreviewRowModel],
        audit_user: str,
    ) -> ShotImportCommitResultModel:
        normalized_rows = [row.normalized for row in rows if row.normalized is not None]
        episode_numbers = {row.episode_no for row in normalized_rows}
        existing_episodes = await ShotGridShotImportDao.list_episodes(db, project_id, episode_numbers)
        cls._assert_active_existing_episodes(existing_episodes)
        episodes = {episode.episode_no: episode for episode in existing_episodes}
        created_episodes: list[ShotGridEpisode] = []
        for episode_sort, episode_no in enumerate(dict.fromkeys(row.episode_no for row in normalized_rows), start=1):
            if episode_no in episodes:
                continue
            episode = ShotGridEpisode(
                project_id=project_id,
                episode_no=episode_no,
                storage_dir_name=f'EP{episode_no:02d}',
                sort_order=episode_sort * 10,
                lifecycle_status='active',
                create_by=audit_user,
                update_by=audit_user,
            )
            db.add(episode)
            episodes[episode_no] = episode
            created_episodes.append(episode)
        await ShotGridShotImportDao.flush(db)

        scene_numbers = {row.scene_no for row in normalized_rows}
        existing_scenes = await ShotGridShotImportDao.list_scenes(
            db,
            (episode.episode_id for episode in episodes.values()),
            scene_numbers,
        )
        selected_scene_keys = {(episodes[row.episode_no].episode_id, row.scene_no) for row in normalized_rows}
        cls._assert_active_existing_scenes(existing_scenes, selected_scene_keys)
        scenes = {
            (scene.episode_id, scene.scene_no): scene
            for scene in existing_scenes
            if (scene.episode_id, scene.scene_no) in selected_scene_keys
        }
        reused_scene_count = len(scenes)
        created_scenes: list[ShotGridScene] = []
        scene_sort_by_episode: dict[int, int] = defaultdict(int)
        for row in normalized_rows:
            episode = episodes[row.episode_no]
            key = (episode.episode_id, row.scene_no)
            if key in scenes:
                continue
            scene_sort_by_episode[episode.episode_id] += 1
            scene = ShotGridScene(
                project_id=project_id,
                episode_id=episode.episode_id,
                scene_no=row.scene_no,
                scene_name=row.scene_name,
                sort_order=scene_sort_by_episode[episode.episode_id] * 10,
                lifecycle_status='active',
                create_by=audit_user,
                update_by=audit_user,
            )
            db.add(scene)
            scenes[key] = scene
            created_scenes.append(scene)
        await ShotGridShotImportDao.flush(db)

        existing_shots = await ShotGridShotImportDao.list_shots(
            db,
            (episode.episode_id for episode in episodes.values()),
            {row.shot_no for row in normalized_rows},
        )
        existing_shot_keys = {(shot.episode_id, shot.shot_no) for shot in existing_shots}
        conflicting_rows = [
            row for row in normalized_rows if (episodes[row.episode_no].episode_id, row.shot_no) in existing_shot_keys
        ]
        if conflicting_rows:
            raise shot_grid_error(
                409,
                'SG_SHOT_NO_CONFLICT',
                '提交前检测到集内镜头号已存在',
                details={'shotCodes': [row.shot_code for row in conflicting_rows]},
            )

        created_shots: list[tuple[ShotGridShot, ShotImportNormalizedRowModel]] = []
        for row in normalized_rows:
            episode = episodes[row.episode_no]
            scene = scenes[(episode.episode_id, row.scene_no)]
            shot = ShotGridShot(
                project_id=project_id,
                episode_id=episode.episode_id,
                scene_id=scene.scene_id,
                shot_no=row.shot_no,
                storage_dir_name=row.shot_code,
                duration_ms=row.duration_ms,
                shot_size=row.shot_size,
                camera_position=row.camera_position,
                camera_movement=row.camera_movement,
                focal_length=row.focal_length,
                description=row.description,
                dialogue=row.dialogue,
                sound_effect=row.sound_effect,
                color_reference=row.color_reference,
                sort_order=row.sort_order,
                lifecycle_status='active',
                remark=row.remark,
                create_by=audit_user,
                update_by=audit_user,
            )
            db.add(shot)
            created_shots.append((shot, row))
        await ShotGridShotImportDao.flush(db)

        created_tasks = 0
        created_asset_links = 0
        created_asset_requirements = 0
        storage_operations: list[ShotGridStorageOperation] = [
            cls._storage_operation(
                project_id=project_id,
                operation_type='ensure_episode_directory',
                aggregate_type='episode',
                aggregate_id=episode.episode_id,
                target_relative_path=f'VIDEO\\{episode.storage_dir_name}',
                audit_user=audit_user,
            )
            for episode in created_episodes
        ]

        for shot, row in created_shots:
            episode = episodes[row.episode_no]
            storage_operations.append(
                cls._storage_operation(
                    project_id=project_id,
                    operation_type='ensure_shot_directory',
                    aggregate_type='shot',
                    aggregate_id=shot.shot_id,
                    target_relative_path=f'VIDEO\\{episode.storage_dir_name}\\{shot.storage_dir_name}',
                    audit_user=audit_user,
                )
            )
            if row.assignee_user_id is not None:
                db.add(
                    ShotGridTask(
                        project_id=project_id,
                        shot_id=shot.shot_id,
                        task_name=f'{row.episode_code}-{row.scene_code}-{row.shot_code} 镜头视频制作',
                        task_kind='shot_video',
                        assignee_user_id=row.assignee_user_id,
                        task_status='not_started',
                        priority='normal',
                        requirements=row.description,
                        create_by=audit_user,
                        update_by=audit_user,
                    )
                )
                created_tasks += 1

            for requirement in row.asset_requirements:
                if requirement.matched_asset_id is not None:
                    db.add(
                        ShotGridShotAsset(
                            project_id=project_id,
                            shot_id=shot.shot_id,
                            asset_id=requirement.matched_asset_id,
                            create_by=audit_user,
                        )
                    )
                    created_asset_links += 1
                else:
                    db.add(
                        ShotGridShotAssetRequirement(
                            project_id=project_id,
                            shot_id=shot.shot_id,
                            asset_type='Environment',
                            raw_name=requirement.raw_name,
                            normalized_name=requirement.normalized_name,
                            resolution_status='pending',
                            source_import_batch_id=batch_id,
                            create_by=audit_user,
                        )
                    )
                    created_asset_requirements += 1

        db.add_all(storage_operations)
        await ShotGridShotImportDao.flush(db)
        return ShotImportCommitResultModel(
            batchId=batch_id,
            committedRows=len(rows),
            createdEpisodes=len(created_episodes),
            reusedEpisodes=len(episodes) - len(created_episodes),
            createdScenes=len(created_scenes),
            reusedScenes=reused_scene_count,
            createdShots=len(created_shots),
            createdTasks=created_tasks,
            createdAssetLinks=created_asset_links,
            createdAssetRequirements=created_asset_requirements,
            createdStorageOperations=len(storage_operations),
        )

    @classmethod
    async def _enrich_rows_from_database(  # noqa: PLR0912
        cls,
        db: AsyncSession,
        project_id: int,
        rows: list[ShotImportPreviewRowModel],
    ) -> None:
        names = {
            row.normalized.assignee_user_name
            for row in rows
            if row.normalized is not None and row.normalized.assignee_user_name
        }
        member_records = await ShotGridShotImportDao.list_assignable_members(db, project_id, names)
        by_login = {record[1]: record for record in member_records}
        by_nickname: dict[str, list[tuple[int, str, str, str | None]]] = defaultdict(list)
        for record in member_records:
            by_nickname[record[2]].append(record)

        environment_names = {
            requirement.normalized_name
            for row in rows
            if row.normalized is not None
            for requirement in row.normalized.asset_requirements
        }
        assets = await ShotGridShotImportDao.list_environment_assets(db, project_id, environment_names)
        assets_by_name: dict[str, list[Any]] = defaultdict(list)
        for asset in assets:
            assets_by_name[asset.asset_name_key].append(asset)

        for row in rows:
            normalized = row.normalized
            if normalized is None:
                row.can_import = False
                continue
            assignee_name = normalized.assignee_user_name
            if assignee_name:
                member = by_login.get(assignee_name)
                if member is None:
                    nickname_matches = by_nickname.get(assignee_name, [])
                    if len(nickname_matches) == 1:
                        member = nickname_matches[0]
                    elif len(nickname_matches) > 1:
                        row.errors.append(
                            cls._row_issue(
                                'SG_TASK_ASSIGNEE_AMBIGUOUS',
                                '制作人昵称匹配到多个项目成员，请改用登录账号',
                                'assigneeUserName',
                                row,
                            )
                        )
                    else:
                        row.errors.append(
                            cls._row_issue(
                                'SG_TASK_ASSIGNEE_INVALID',
                                '制作人不存在、已停用或不是项目成员',
                                'assigneeUserName',
                                row,
                            )
                        )
                if member is not None:
                    if not member[3]:
                        row.errors.append(
                            cls._row_issue(
                                'SG_PRODUCER_CODE_REQUIRED',
                                '制作人尚未设置项目内文件名缩写',
                                'assigneeUserName',
                                row,
                            )
                        )
                    else:
                        normalized.assignee_user_id = member[0]

            for requirement in normalized.asset_requirements:
                candidates = assets_by_name.get(requirement.normalized_name, [])
                if len(candidates) == 1:
                    requirement.matched_asset_id = candidates[0].asset_id
                elif len(candidates) > 1:
                    row.errors.append(
                        cls._row_issue(
                            'SG_ASSET_REQUIREMENT_CONFLICT',
                            '场景名称匹配到多个正式资产，禁止自动选择',
                            'environmentAssetNames',
                            row,
                        )
                    )
            row.can_import = not row.errors

    @classmethod
    async def _revalidate_selected_rows(
        cls,
        db: AsyncSession,
        project_id: int,
        rows: list[ShotImportPreviewRowModel],
    ) -> None:
        for row in rows:
            row.errors = []
            if row.normalized is not None:
                row.normalized.assignee_user_id = None
                for requirement in row.normalized.asset_requirements:
                    requirement.matched_asset_id = None
        await cls._enrich_rows_from_database(db, project_id, rows)
        errors = [row for row in rows if not row.can_import]
        if errors:
            raise shot_grid_error(
                422,
                'SG_IMPORT_HAS_ERRORS',
                '提交前重新校验发现选中行存在错误',
                details={
                    'rows': [
                        {
                            'sheetName': row.sheet_name,
                            'rowNumber': row.row_number,
                            'errors': [issue.model_dump(by_alias=True) for issue in row.errors],
                        }
                        for row in errors
                    ]
                },
            )

    @staticmethod
    def _assign_row_keys(rows: list[ShotImportPreviewRowModel], file_sha256: str) -> None:
        for row in rows:
            row.row_key = ShotGridShotImportService._row_key(file_sha256, row.sheet_name, row.row_number)

    @staticmethod
    def _row_key(file_sha256: str, sheet_name: str, row_number: int) -> str:
        source = f'{file_sha256}\0{sheet_name}\0{row_number}'
        return hashlib.sha256(source.encode('utf-8')).hexdigest()

    @classmethod
    def _selection_hash(cls, rows: list[ShotImportPreviewRowModel]) -> str:
        keys = sorted(row.row_key for row in rows if row.row_key is not None)
        if len(keys) != len(rows):
            raise shot_grid_error(409, 'SG_IMPORT_TOKEN_INVALID', '预检查行缺少稳定标识，请重新预检查')
        return hashlib.sha256('\n'.join(keys).encode('utf-8')).hexdigest()

    @classmethod
    def _selection_hash_from_request(
        cls,
        file_sha256: str,
        selected_rows: list[ImportSelectedRowModel],
    ) -> str:
        keys = sorted(cls._row_key(file_sha256, row.sheet_name, row.row_number) for row in selected_rows)
        return hashlib.sha256('\n'.join(keys).encode('utf-8')).hexdigest()

    @staticmethod
    def _idempotency_lock_id(project_id: int, user_id: int, idempotency_key: str) -> int:
        source = f'shot-import\0{project_id}\0{user_id}\0{idempotency_key}'.encode()
        return int.from_bytes(hashlib.sha256(source).digest()[:8], 'big', signed=True)

    @staticmethod
    def _select_rows(
        payload: ImportPreviewTokenPayloadModel,
        selections: list[ImportSelectedRowModel],
    ) -> list[ShotImportPreviewRowModel]:
        rows = [ShotImportPreviewRowModel.model_validate(row) for row in payload.rows]
        rows_by_key = {(row.sheet_name, row.row_number): row for row in rows}
        selected: list[ShotImportPreviewRowModel] = []
        missing: list[dict[str, Any]] = []
        for selection in selections:
            row = rows_by_key.get(selection.key())
            if row is None:
                missing.append(selection.model_dump(by_alias=True))
            else:
                selected.append(row)
        if missing:
            raise shot_grid_error(
                422,
                'SG_IMPORT_SELECTED_ROW_INVALID',
                '选中行不属于当前预检查结果',
                details={'rows': missing},
            )
        invalid = [row for row in selected if not row.can_import]
        if invalid:
            raise shot_grid_error(
                422,
                'SG_IMPORT_HAS_ERRORS',
                '选中行仍包含预检查错误',
                details={'rows': [{'sheetName': row.sheet_name, 'rowNumber': row.row_number} for row in invalid]},
            )
        selected_keys = {selection.key() for selection in selections}
        return [row for row in rows if (row.sheet_name, row.row_number) in selected_keys]

    @staticmethod
    def _validate_payload(
        payload: ImportPreviewTokenPayloadModel,
        project_id: int,
        user_id: int,
        has_all_scope: bool,
    ) -> None:
        if payload.import_type != 'shot' or payload.project_id != project_id:
            raise shot_grid_error(400, 'SG_IMPORT_TOKEN_INVALID', '导入 Token 与项目或导入类型不匹配')
        if payload.previewed_by != user_id and not has_all_scope:
            raise shot_grid_error(403, 'SG_IMPORT_TOKEN_FORBIDDEN', '只能提交本人创建的导入预检查')
        if payload.expires_at <= datetime.now():
            raise shot_grid_error(410, 'SG_IMPORT_TOKEN_EXPIRED', '导入 Token 已过期，请重新预检查')
        if payload.template_version != SHOT_TEMPLATE_VERSION:
            raise shot_grid_error(409, 'SG_IMPORT_TEMPLATE_VERSION_MISMATCH', '镜头模板版本已变化，请重新预检查')

    @staticmethod
    def _validate_locked_batch(
        batch: Any,
        payload: ImportPreviewTokenPayloadModel,
        token_hash: str,
        user_id: int,
        has_all_scope: bool,
    ) -> None:
        if batch.batch_status != 'previewed':
            raise shot_grid_error(409, 'SG_IMPORT_BATCH_STATE_CONFLICT', '导入批次当前状态不可提交')
        if batch.import_type != 'shot':
            raise shot_grid_error(400, 'SG_IMPORT_TOKEN_INVALID', '导入批次类型与镜头导入不匹配')
        if batch.preview_token_hash != token_hash:
            raise shot_grid_error(400, 'SG_IMPORT_TOKEN_INVALID', '导入 Token 与批次不匹配')
        if batch.file_sha256 != payload.file_sha256:
            raise shot_grid_error(409, 'SG_IMPORT_FILE_HASH_MISMATCH', '导入 Token 绑定的文件摘要不一致')
        if batch.template_version != SHOT_TEMPLATE_VERSION or batch.template_version != payload.template_version:
            raise shot_grid_error(409, 'SG_IMPORT_TEMPLATE_VERSION_MISMATCH', '镜头模板版本已变化，请重新预检查')
        if batch.preview_expires_time is None or batch.preview_expires_time <= datetime.now():
            raise shot_grid_error(410, 'SG_IMPORT_TOKEN_EXPIRED', '导入 Token 已过期，请重新预检查')
        if batch.preview_expires_time != payload.expires_at:
            raise shot_grid_error(400, 'SG_IMPORT_TOKEN_INVALID', '导入 Token 与批次到期时间不匹配')
        if batch.previewed_by != payload.previewed_by:
            raise shot_grid_error(400, 'SG_IMPORT_TOKEN_INVALID', '导入 Token 与批次创建用户不匹配')
        if batch.previewed_by != user_id and not has_all_scope:
            raise shot_grid_error(403, 'SG_IMPORT_TOKEN_FORBIDDEN', '只能提交本人创建的导入预检查')

    @staticmethod
    def _assert_active_existing_episodes(episodes: list[ShotGridEpisode]) -> None:
        archived_numbers = sorted({episode.episode_no for episode in episodes if episode.lifecycle_status != 'active'})
        if archived_numbers:
            raise shot_grid_error(
                409,
                'SG_EPISODE_NO_CONFLICT',
                '集号已被归档集占用，不能通过导入复用',
                details={'episodeNumbers': archived_numbers},
            )

    @staticmethod
    def _assert_active_existing_scenes(
        scenes: list[ShotGridScene],
        selected_scene_keys: set[tuple[int, int]],
    ) -> None:
        archived_numbers = sorted(
            {
                scene.scene_no
                for scene in scenes
                if (scene.episode_id, scene.scene_no) in selected_scene_keys and scene.lifecycle_status != 'active'
            }
        )
        if archived_numbers:
            raise shot_grid_error(
                409,
                'SG_SCENE_NO_CONFLICT',
                '场次号已被归档场次占用，不能通过导入复用',
                details={'sceneNumbers': archived_numbers},
            )

    @staticmethod
    def _existing_result(batch: Any) -> ShotImportCommitResultModel:
        if batch.batch_status == 'committed' and batch.result_summary:
            result = ShotImportCommitResultModel.model_validate(batch.result_summary)
            result.idempotent_replay = True
            return result
        if batch.batch_status == 'failed':
            raise shot_grid_error(
                409,
                batch.last_error_key or 'SG_IMPORT_BATCH_STATE_CONFLICT',
                batch.last_error_message or '该幂等请求此前提交失败，请重新预检查',
            )
        raise shot_grid_error(409, 'SG_IMPORT_BATCH_STATE_CONFLICT', '相同幂等请求正在处理')

    @classmethod
    async def _raise_missing_token(
        cls,
        db: AsyncSession,
        project_id: int,
        token: str,
        config: ShotGridImportConfig,
    ) -> None:
        token_hash = ImportPreviewStore.token_hash(token)
        batch = await ShotGridImportBatchDao.find_by_token_hash(db, project_id, 'shot', token_hash)
        if (
            batch is not None
            and batch.preview_expires_time is not None
            and batch.preview_expires_time <= datetime.now()
        ):
            await ShotGridImportBatchDao.expire_preview(db, project_id, batch.batch_id)
            await db.commit()
            raise shot_grid_error(410, 'SG_IMPORT_TOKEN_EXPIRED', '导入 Token 已过期，请重新预检查')
        raise shot_grid_error(400, 'SG_IMPORT_TOKEN_INVALID', '导入 Token 不合法或预览数据已失效')

    @staticmethod
    async def _record_failed_batch(
        db: AsyncSession,
        *,
        project_id: int,
        batch_id: int,
        committed_by: int,
        idempotency_key: str,
        selection_hash: str,
        exc: Exception,
    ) -> None:
        if isinstance(exc, ShotGridDomainException):
            error_key = exc.error_key
            error_message = exc.message
        elif isinstance(exc, IntegrityError):
            error_key = 'SG_IMPORT_DATABASE_CONFLICT'
            error_message = '导入数据与数据库当前状态冲突'
        else:
            error_key = 'SG_IMPORT_COMMIT_FAILED'
            error_message = '镜头导入提交失败'
        try:
            await ShotGridImportBatchDao.mark_failed(
                db,
                project_id=project_id,
                batch_id=batch_id,
                committed_by=committed_by,
                idempotency_key=idempotency_key,
                selection_hash=selection_hash,
                error_key=error_key,
                error_message=error_message,
            )
            await db.commit()
        except Exception:
            await db.rollback()

    @staticmethod
    def _storage_operation(
        *,
        project_id: int,
        operation_type: str,
        aggregate_type: str,
        aggregate_id: int,
        target_relative_path: str,
        audit_user: str,
    ) -> ShotGridStorageOperation:
        return ShotGridStorageOperation(
            project_id=project_id,
            operation_type=operation_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            target_relative_path=target_relative_path,
            operation_status='pending',
            idempotency_key=f'shotgrid:dir:{aggregate_type}:{project_id}:{aggregate_id}',
            attempt_count=0,
            create_by=audit_user,
        )

    @staticmethod
    def _row_issue(
        error_key: str,
        message: str,
        field_name: str,
        row: ShotImportPreviewRowModel,
    ) -> ImportIssueModel:
        return ImportIssueModel(
            errorKey=error_key,
            message=message,
            fieldName=field_name,
            sheetName=row.sheet_name,
            rowNumber=row.row_number,
        )

    @staticmethod
    def _require_ready_project(project: Any, storage: Any) -> None:
        if project is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
        if storage is None or storage.storage_status != 'ready':
            raise shot_grid_error(409, 'SG_PROJECT_NOT_READY', '项目存储尚未就绪，不能导入镜头')

    @staticmethod
    def _safe_original_file_name(file_name: str) -> str:
        normalized = (file_name or '').replace('\\', '/')
        name = PurePosixPath(normalized).name.strip()
        if (
            not name
            or len(name) > ShotGridShotImportService.ORIGINAL_FILE_NAME_MAX_LENGTH
            or any(ord(character) < ShotGridShotImportService.FIRST_PRINTABLE_CODEPOINT for character in name)
        ):
            raise shot_grid_error(422, 'SG_IMPORT_FILE_NAME_INVALID', '导入文件名不合法')
        return name

    @staticmethod
    def _current_user_identity(current_user: CurrentUserModel) -> tuple[int, str]:
        user = current_user.user
        if user is None or user.user_id is None or not user.user_name:
            raise shot_grid_error(401, 'SG_CURRENT_USER_INVALID', '无法识别当前用户')
        return user.user_id, user.user_name

    @staticmethod
    def _current_user_dept_name(current_user: CurrentUserModel) -> str | None:
        user = current_user.user
        if user is None or user.dept is None:
            return None
        return user.dept.dept_name

    @staticmethod
    async def _delete_preview_token_best_effort(
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
                '清理镜头导入预览 Token 失败：project_id={} batch_id={} error={}',
                project_id,
                batch_id,
                type(exc).__name__,
            )

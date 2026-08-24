from collections import defaultdict
from collections.abc import Iterable
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.dao.production_history_dao import ShotGridProductionHistoryDao
from module_shot_grid.entity.vo.production_history_vo import (
    ProductionHistoryLaneType,
    ProductionHistoryStage,
    ProductionHistorySubjectType,
    ShotGridProductionHistoryActorModel,
    ShotGridProductionHistoryEventModel,
    ShotGridProductionHistoryFileModel,
    ShotGridProductionHistoryImportBatchModel,
    ShotGridProductionHistoryIssueModel,
    ShotGridProductionHistoryIssueResponseModel,
    ShotGridProductionHistoryIssueVerificationModel,
    ShotGridProductionHistoryLaneModel,
    ShotGridProductionHistoryModel,
    ShotGridProductionHistoryResourceRefModel,
    ShotGridProductionHistoryReviewActionModel,
    ShotGridProductionHistoryReviewListModel,
    ShotGridProductionHistorySubjectModel,
    ShotGridProductionHistorySummaryModel,
    ShotGridProductionHistoryTaskModel,
    ShotGridProductionHistoryVersionCycleModel,
    ShotGridProductionHistoryVersionRefModel,
)
from module_shot_grid.exceptions import shot_grid_error


class ShotGridProductionHistoryService:
    """镜头与资产制作履历读模型。"""

    @classmethod
    async def get_shot_history(
        cls,
        db: AsyncSession,
        project_id: int,
        shot_id: int,
    ) -> ShotGridProductionHistoryModel:
        subject_row = await ShotGridProductionHistoryDao.get_shot_subject(db, project_id, shot_id)
        if subject_row is None:
            raise shot_grid_error(404, 'SG_SHOT_NOT_FOUND', '镜头不存在或不属于当前项目')
        lane_rows = await ShotGridProductionHistoryDao.get_shot_lanes(db, project_id, shot_id)
        code = cls._shot_code(subject_row)
        return await cls._build_history(
            db,
            subject_type='shot',
            subject_row=subject_row,
            lane_type='shot',
            lane_rows=lane_rows,
            subject_id=shot_id,
            subject_code=code,
            subject_name=str(subject_row['description']),
            subject_description=subject_row.get('dialogue'),
            asset_type=None,
        )

    @classmethod
    async def get_asset_history(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_id: int,
    ) -> ShotGridProductionHistoryModel:
        subject_row = await ShotGridProductionHistoryDao.get_asset_subject(db, project_id, asset_id)
        if subject_row is None:
            raise shot_grid_error(404, 'SG_ASSET_NOT_FOUND', '资产不存在或不可见')
        lane_rows = await ShotGridProductionHistoryDao.get_asset_lanes(db, project_id, asset_id)
        return await cls._build_history(
            db,
            subject_type='asset',
            subject_row=subject_row,
            lane_type='assetItem',
            lane_rows=lane_rows,
            subject_id=asset_id,
            subject_code=None,
            subject_name=str(subject_row['asset_name']),
            subject_description=subject_row.get('description'),
            asset_type=subject_row['asset_type'],
        )

    @classmethod
    async def _build_history(
        cls,
        db: AsyncSession,
        *,
        subject_type: ProductionHistorySubjectType,
        subject_row: dict[str, Any],
        lane_type: ProductionHistoryLaneType,
        lane_rows: list[dict[str, Any]],
        subject_id: int,
        subject_code: str | None,
        subject_name: str,
        subject_description: str | None,
        asset_type: Literal['Character', 'Environment', 'Prop'] | None,
    ) -> ShotGridProductionHistoryModel:
        task_ids = [int(row['task_id']) for row in lane_rows if row.get('task_id') is not None]
        version_rows = await ShotGridProductionHistoryDao.get_versions(
            db,
            int(subject_row['project_id']),
            task_ids,
        )
        version_ids = [int(row['version_id']) for row in version_rows]
        file_rows = await ShotGridProductionHistoryDao.get_version_files(db, version_ids)
        review_list_rows = await ShotGridProductionHistoryDao.get_auto_review_lists(db, version_ids)
        action_rows = await ShotGridProductionHistoryDao.get_review_actions(db, version_ids)
        issue_rows = await ShotGridProductionHistoryDao.get_source_issues(db, version_ids)
        issue_ids = [int(row['note_id']) for row in issue_rows]
        response_rows = await ShotGridProductionHistoryDao.get_issue_responses(db, issue_ids)
        verification_rows = await ShotGridProductionHistoryDao.get_issue_verifications(db, issue_ids)
        import_batch_ids = [
            int(row['source_import_batch_id']) for row in lane_rows if row.get('source_import_batch_id') is not None
        ]
        import_rows = await ShotGridProductionHistoryDao.get_import_batches(db, import_batch_ids)

        version_rows_by_task = cls._group_rows(version_rows, 'task_id')
        files_by_version = cls._group_rows(file_rows, 'version_id')
        review_lists_by_version = {int(row['version_id']): row for row in review_list_rows}
        actions_by_version = cls._group_rows(action_rows, 'version_id')
        issues_by_version = cls._group_rows(issue_rows, 'origin_version_id')
        responses_by_version = cls._group_rows(response_rows, 'version_id')
        verifications_by_version = cls._group_rows(verification_rows, 'checked_version_id')

        lane_models: list[ShotGridProductionHistoryLaneModel] = []
        lane_id_by_task: dict[int, int] = {}
        for lane_row in lane_rows:
            lane_id = int(lane_row['lane_id'])
            task_id = int(lane_row['task_id']) if lane_row.get('task_id') is not None else None
            lane_versions = version_rows_by_task.get(task_id, []) if task_id is not None else []
            lane_issues = [
                issue for version in lane_versions for issue in issues_by_version.get(int(version['version_id']), [])
            ]
            lane_actions = [
                action for version in lane_versions for action in actions_by_version.get(int(version['version_id']), [])
            ]
            latest_version_row = lane_versions[-1] if lane_versions else None
            final_version_row = next(
                (version for version in reversed(lane_versions) if version['version_status'] == 'final'),
                None,
            )
            current_stage, active_step = cls._resolve_stage(
                lane_row.get('task_status'),
                has_final_version=final_version_row is not None,
            )
            task_model = cls._build_task_model(lane_row) if task_id is not None else None
            lane_models.append(
                ShotGridProductionHistoryLaneModel(
                    laneId=lane_id,
                    laneType=lane_type,
                    name=cls._lane_name(lane_type, lane_row, subject_code),
                    sortOrder=int(lane_row['sort_order']),
                    lifecycleStatus=lane_row['lifecycle_status'],
                    sourceImportBatchId=lane_row.get('source_import_batch_id'),
                    currentStage=current_stage,
                    activeStep=active_step,
                    task=task_model,
                    latestVersion=cls._build_version_ref(latest_version_row),
                    finalVersion=cls._build_version_ref(final_version_row),
                    versionCount=len(lane_versions),
                    reviewActionCount=len(lane_actions),
                    rejectionCount=sum(action['action_type'] == 'reject' for action in lane_actions),
                    issueCount=len(lane_issues),
                    openIssueCount=sum(issue['note_status'] == 'open' for issue in lane_issues),
                )
            )
            if task_id is not None:
                lane_id_by_task[task_id] = lane_id

        version_cycles = cls._build_version_cycles(
            version_rows,
            files_by_version,
            review_lists_by_version,
            actions_by_version,
            issues_by_version,
            responses_by_version,
            verifications_by_version,
        )
        events = cls._build_events(
            subject_type=subject_type,
            subject_id=subject_id,
            subject_row=subject_row,
            lane_rows=lane_rows,
            lane_id_by_task=lane_id_by_task,
            import_rows=import_rows,
            version_rows=version_rows,
            version_cycles=version_cycles,
        )
        current_stage, active_step = cls._aggregate_stage(lane_models)
        final_versions = [row for row in version_rows if row['version_status'] == 'final']
        open_issue_count = sum(row['note_status'] == 'open' for row in issue_rows)
        thumbnail_file_id = cls._representative_thumbnail_file_id(
            lane_models,
            version_rows_by_task,
            files_by_version,
        )
        subject = ShotGridProductionHistorySubjectModel(
            subjectType=subject_type,
            subjectId=subject_id,
            projectId=int(subject_row['project_id']),
            projectCode=str(subject_row['project_code']),
            projectName=str(subject_row['project_name']),
            code=subject_code,
            name=subject_name,
            description=subject_description,
            lifecycleStatus=subject_row['lifecycle_status'],
            assetType=asset_type,
            thumbnailFileId=thumbnail_file_id,
            createdAt=subject_row['create_time'],
        )
        summary = ShotGridProductionHistorySummaryModel(
            currentStage=current_stage,
            activeStep=active_step,
            laneCount=len(lane_models),
            taskCount=len(task_ids),
            versionCount=len(version_rows),
            reviewActionCount=len(action_rows),
            rejectionCount=sum(row['action_type'] == 'reject' for row in action_rows),
            issueCount=len(issue_rows),
            openIssueCount=open_issue_count,
            resolvedIssueCount=len(issue_rows) - open_issue_count,
            finalVersionCount=len(final_versions),
        )
        return ShotGridProductionHistoryModel(
            subject=subject,
            summary=summary,
            lanes=lane_models,
            events=events,
        )

    @classmethod
    def _build_events(
        cls,
        *,
        subject_type: ProductionHistorySubjectType,
        subject_id: int,
        subject_row: dict[str, Any],
        lane_rows: list[dict[str, Any]],
        lane_id_by_task: dict[int, int],
        import_rows: list[dict[str, Any]],
        version_rows: list[dict[str, Any]],
        version_cycles: dict[int, ShotGridProductionHistoryVersionCycleModel],
    ) -> list[ShotGridProductionHistoryEventModel]:
        subject_resource_type = 'shot' if subject_type == 'shot' else 'asset'
        events = [
            ShotGridProductionHistoryEventModel(
                eventId=f'{subject_resource_type}:{subject_id}:created',
                eventType='subject_created',
                occurredAt=subject_row['create_time'],
                evidenceLevel='confirmed',
                title='镜头已创建' if subject_type == 'shot' else '资产已创建',
                actor=cls._actor_from_user_name(subject_row.get('create_by')),
                resourceRef=ShotGridProductionHistoryResourceRefModel(
                    resourceType=subject_resource_type,
                    resourceId=subject_id,
                ),
            )
        ]

        lane_ids_by_batch: dict[int, list[int]] = defaultdict(list)
        for lane_row in lane_rows:
            if lane_row.get('source_import_batch_id') is not None:
                lane_ids_by_batch[int(lane_row['source_import_batch_id'])].append(int(lane_row['lane_id']))
        for import_row in import_rows:
            committed_time = import_row.get('committed_time')
            batch_id = int(import_row['batch_id'])
            if committed_time is None or batch_id not in lane_ids_by_batch:
                continue
            committed_by = cls._actor(
                import_row.get('committed_by'),
                import_row.get('committed_user_name'),
                import_row.get('committed_nick_name'),
            )
            import_batch = ShotGridProductionHistoryImportBatchModel(
                batchId=batch_id,
                originalFileName=import_row['original_file_name'],
                importType=import_row['import_type'],
                batchStatus=import_row['batch_status'],
                committedBy=committed_by,
                committedTime=committed_time,
            )
            events.append(
                ShotGridProductionHistoryEventModel(
                    eventId=f'importBatch:{batch_id}:committed',
                    eventType='subject_imported',
                    occurredAt=committed_time,
                    evidenceLevel='confirmed',
                    title='从 Excel 导入制作分项',
                    description=str(import_row['original_file_name']),
                    laneIds=sorted(set(lane_ids_by_batch[batch_id])),
                    actor=committed_by,
                    resourceRef=ShotGridProductionHistoryResourceRefModel(
                        resourceType='importBatch',
                        resourceId=batch_id,
                    ),
                    importBatch=import_batch,
                )
            )

        if subject_type == 'asset':
            for lane_row in lane_rows:
                if lane_row.get('source_import_batch_id') is not None or lane_row.get('lane_create_time') is None:
                    continue
                lane_id = int(lane_row['lane_id'])
                events.append(
                    ShotGridProductionHistoryEventModel(
                        eventId=f'assetItem:{lane_id}:created',
                        eventType='lane_created',
                        occurredAt=lane_row['lane_create_time'],
                        evidenceLevel='confirmed',
                        title='制作分项已建立',
                        laneIds=[lane_id],
                        actor=cls._actor_from_user_name(lane_row.get('lane_create_by')),
                        resourceRef=ShotGridProductionHistoryResourceRefModel(
                            resourceType='assetItem',
                            resourceId=lane_id,
                        ),
                    )
                )

        for lane_row in lane_rows:
            if lane_row.get('task_id') is None or lane_row.get('task_create_time') is None:
                continue
            task_id = int(lane_row['task_id'])
            events.append(
                ShotGridProductionHistoryEventModel(
                    eventId=f'task:{task_id}:created',
                    eventType='task_created',
                    occurredAt=lane_row['task_create_time'],
                    evidenceLevel='inferred',
                    title='制作任务已建立',
                    description='该节点来自任务创建记录，不推断历史首次委派对象。',
                    laneIds=[int(lane_row['lane_id'])],
                    actor=cls._actor_from_user_name(lane_row.get('task_create_by')),
                    resourceRef=ShotGridProductionHistoryResourceRefModel(
                        resourceType='task',
                        resourceId=task_id,
                    ),
                )
            )

        for version_row in version_rows:
            version_id = int(version_row['version_id'])
            events.append(
                ShotGridProductionHistoryEventModel(
                    eventId=f'version:{version_id}:cycle',
                    eventType='version_cycle',
                    occurredAt=version_row['submitted_time'],
                    evidenceLevel='confirmed',
                    title=f'提交 {cls._version_number(version_row["version_no"])}',
                    description=version_row['changelog'],
                    laneIds=[lane_id_by_task[int(version_row['task_id'])]],
                    actor=cls._actor(
                        version_row.get('submitted_by'),
                        version_row.get('submitter_user_name'),
                        version_row.get('submitter_nick_name'),
                    ),
                    resourceRef=ShotGridProductionHistoryResourceRefModel(
                        resourceType='version',
                        resourceId=version_id,
                    ),
                    versionCycle=version_cycles[version_id],
                )
            )
        return sorted(events, key=lambda item: (item.occurred_at, item.event_id))

    @classmethod
    def _build_version_cycles(
        cls,
        version_rows: list[dict[str, Any]],
        files_by_version: dict[int, list[dict[str, Any]]],
        review_lists_by_version: dict[int, dict[str, Any]],
        actions_by_version: dict[int, list[dict[str, Any]]],
        issues_by_version: dict[int, list[dict[str, Any]]],
        responses_by_version: dict[int, list[dict[str, Any]]],
        verifications_by_version: dict[int, list[dict[str, Any]]],
    ) -> dict[int, ShotGridProductionHistoryVersionCycleModel]:
        cycles: dict[int, ShotGridProductionHistoryVersionCycleModel] = {}
        for version in version_rows:
            version_id = int(version['version_id'])
            files = files_by_version.get(version_id, [])
            primary_file_row = next(
                (row for row in files if row['file_role'] == 'review_media' and row['is_primary'] == '1'),
                None,
            )
            thumbnail_file_row = next((row for row in files if row['file_role'] == 'thumbnail'), None)
            review_list_row = review_lists_by_version.get(version_id)
            cycles[version_id] = ShotGridProductionHistoryVersionCycleModel(
                versionId=version_id,
                versionNo=int(version['version_no']),
                versionNumber=cls._version_number(version['version_no']),
                versionStatus=version['version_status'],
                changelog=version['changelog'],
                submittedTime=version['submitted_time'],
                submitter=cls._actor(
                    version.get('submitted_by'),
                    version.get('submitter_user_name'),
                    version.get('submitter_nick_name'),
                ),
                primaryFile=cls._build_file(primary_file_row),
                thumbnailFile=cls._build_file(thumbnail_file_row),
                autoReviewList=cls._build_review_list(review_list_row),
                reviewActions=[cls._build_review_action(row) for row in actions_by_version.get(version_id, [])],
                sourceIssues=[cls._build_issue(row) for row in issues_by_version.get(version_id, [])],
                issueResponses=[cls._build_issue_response(row) for row in responses_by_version.get(version_id, [])],
                issueVerifications=[
                    cls._build_issue_verification(row) for row in verifications_by_version.get(version_id, [])
                ],
            )
        return cycles

    @staticmethod
    def _build_task_model(row: dict[str, Any]) -> ShotGridProductionHistoryTaskModel:
        return ShotGridProductionHistoryTaskModel(
            taskId=int(row['task_id']),
            taskName=row['task_name'],
            taskKind=row['task_kind'],
            taskStatus=row['task_status'],
            priority=row['priority'],
            dueDate=row.get('due_date'),
            assignee=ShotGridProductionHistoryService._actor(
                row.get('assignee_user_id'),
                row.get('assignee_user_name'),
                row.get('assignee_nick_name'),
            ),
            createTime=row['task_create_time'],
            updateTime=row['task_update_time'],
        )

    @staticmethod
    def _build_version_ref(row: dict[str, Any] | None) -> ShotGridProductionHistoryVersionRefModel | None:
        if row is None:
            return None
        return ShotGridProductionHistoryVersionRefModel(
            versionId=int(row['version_id']),
            versionNo=int(row['version_no']),
            versionNumber=ShotGridProductionHistoryService._version_number(row['version_no']),
            versionStatus=row['version_status'],
            submittedTime=row['submitted_time'],
        )

    @staticmethod
    def _build_file(row: dict[str, Any] | None) -> ShotGridProductionHistoryFileModel | None:
        if row is None:
            return None
        return ShotGridProductionHistoryFileModel(
            fileId=row['file_id'],
            businessFileName=row['business_file_name'],
            fileRole=row['file_role'],
            isPrimary=row['is_primary'] == '1',
            contentType=row.get('content_type'),
            fileSize=int(row['file_size']),
        )

    @staticmethod
    def _build_review_list(row: dict[str, Any] | None) -> ShotGridProductionHistoryReviewListModel | None:
        if row is None:
            return None
        return ShotGridProductionHistoryReviewListModel(
            reviewListId=int(row['review_list_id']),
            reviewListName=row['review_list_name'],
            reviewStatus=row['review_status'],
        )

    @staticmethod
    def _build_review_action(row: dict[str, Any]) -> ShotGridProductionHistoryReviewActionModel:
        return ShotGridProductionHistoryReviewActionModel(
            actionId=int(row['action_id']),
            actionType=row['action_type'],
            fromStatus=row['from_status'],
            toStatus=row['to_status'],
            reason=row.get('reason'),
            reviewer=ShotGridProductionHistoryService._actor(
                row.get('reviewer_user_id'),
                row.get('reviewer_user_name'),
                row.get('reviewer_nick_name'),
            ),
            createTime=row['create_time'],
        )

    @staticmethod
    def _build_issue(row: dict[str, Any]) -> ShotGridProductionHistoryIssueModel:
        annotation_count = ShotGridProductionHistoryService._annotation_count(row.get('annotations'))
        return ShotGridProductionHistoryIssueModel(
            issueId=int(row['note_id']),
            originVersionId=int(row['origin_version_id']),
            originVersionNumber=ShotGridProductionHistoryService._version_number(row['origin_version_no']),
            reviewer=ShotGridProductionHistoryService._actor(
                row.get('reviewer_user_id'),
                row.get('reviewer_user_name'),
                row.get('reviewer_nick_name'),
            ),
            content=row.get('content'),
            mediaTimeMs=row.get('media_time_ms'),
            hasAnnotations=annotation_count > 0,
            annotationCount=annotation_count,
            status=row['note_status'],
            resolvedInVersionId=row.get('resolved_in_version_id'),
            resolvedInVersionNumber=(
                ShotGridProductionHistoryService._version_number(row['resolved_in_version_no'])
                if row.get('resolved_in_version_no') is not None
                else None
            ),
            createTime=row['create_time'],
            updateTime=row['update_time'],
        )

    @staticmethod
    def _build_issue_response(row: dict[str, Any]) -> ShotGridProductionHistoryIssueResponseModel:
        return ShotGridProductionHistoryIssueResponseModel(
            responseId=int(row['response_id']),
            issueId=int(row['issue_id']),
            originVersionId=int(row['origin_version_id']),
            originVersionNumber=ShotGridProductionHistoryService._version_number(row['origin_version_no']),
            responseText=row['response_text'],
            responder=ShotGridProductionHistoryService._actor(
                row.get('responded_by'),
                row.get('responder_user_name'),
                row.get('responder_nick_name'),
            ),
            createTime=row['create_time'],
        )

    @staticmethod
    def _build_issue_verification(row: dict[str, Any]) -> ShotGridProductionHistoryIssueVerificationModel:
        return ShotGridProductionHistoryIssueVerificationModel(
            verificationId=int(row['verification_id']),
            issueId=int(row['issue_id']),
            originVersionId=int(row['origin_version_id']),
            originVersionNumber=ShotGridProductionHistoryService._version_number(row['origin_version_no']),
            checkedVersionId=int(row['checked_version_id']),
            checkedVersionNumber=ShotGridProductionHistoryService._version_number(row['checked_version_no']),
            result=row['result'],
            comment=row.get('comment'),
            reviewer=ShotGridProductionHistoryService._actor(
                row.get('reviewer_user_id'),
                row.get('reviewer_user_name'),
                row.get('reviewer_nick_name'),
            ),
            createTime=row['create_time'],
        )

    @staticmethod
    def _actor(
        user_id: int | None,
        user_name: str | None,
        nick_name: str | None,
    ) -> ShotGridProductionHistoryActorModel:
        return ShotGridProductionHistoryActorModel(
            userId=int(user_id) if user_id is not None else None,
            userName=user_name,
            nickName=nick_name,
        )

    @staticmethod
    def _actor_from_user_name(user_name: str | None) -> ShotGridProductionHistoryActorModel | None:
        normalized = str(user_name).strip() if user_name is not None else ''
        return ShotGridProductionHistoryActorModel(userName=normalized) if normalized else None

    @staticmethod
    def _annotation_count(value: Any) -> int:
        if not isinstance(value, dict):
            return 0
        items = value.get('items')
        return len(items) if isinstance(items, list) else 0

    @staticmethod
    def _resolve_stage(task_status: str | None, *, has_final_version: bool) -> tuple[ProductionHistoryStage, int]:
        if has_final_version or task_status == 'completed':
            return 'final', 5
        if task_status == 'revision':
            return 'revision', 2
        if task_status == 'pending_review':
            return 'review', 4
        if task_status in {'preparing', 'in_progress'}:
            return 'production', 2
        if task_status == 'not_started':
            return 'assigned', 1
        return 'created', 0

    @staticmethod
    def _aggregate_stage(
        lanes: list[ShotGridProductionHistoryLaneModel],
    ) -> tuple[ProductionHistoryStage, int]:
        active_lanes = [lane for lane in lanes if lane.lifecycle_status == 'active']
        if not active_lanes:
            return 'created', 0
        if all(lane.current_stage == 'final' for lane in active_lanes):
            return 'final', 5
        if any(lane.current_stage == 'revision' for lane in active_lanes):
            return 'revision', 2
        incomplete_lanes = [lane for lane in active_lanes if lane.current_stage != 'final']
        minimum_step = min(lane.active_step for lane in incomplete_lanes)
        candidates = [lane.current_stage for lane in incomplete_lanes if lane.active_step == minimum_step]
        priority: tuple[ProductionHistoryStage, ...] = (
            'created',
            'assigned',
            'production',
            'review',
            'final',
        )
        return next(stage for stage in priority if stage in candidates), minimum_step

    @staticmethod
    def _lane_name(
        lane_type: ProductionHistoryLaneType,
        row: dict[str, Any],
        subject_code: str | None,
    ) -> str:
        if lane_type == 'shot':
            return subject_code or str(row['lane_name'])
        return str(row.get('lane_name') or f'制作分项 #{row["lane_id"]}')

    @staticmethod
    def _representative_thumbnail_file_id(
        lanes: list[ShotGridProductionHistoryLaneModel],
        versions_by_task: dict[int, list[dict[str, Any]]],
        files_by_version: dict[int, list[dict[str, Any]]],
    ) -> str | None:
        for lane in sorted(lanes, key=lambda item: (item.sort_order, item.lane_id)):
            if lane.lifecycle_status != 'active':
                continue
            if lane.task is None:
                continue
            versions = versions_by_task.get(lane.task.task_id, [])
            if not versions:
                continue
            files = files_by_version.get(int(versions[-1]['version_id']), [])
            thumbnail = next((row for row in files if row['file_role'] == 'thumbnail'), None)
            if thumbnail is not None:
                return str(thumbnail['file_id'])
        return None

    @staticmethod
    def _group_rows(rows: Iterable[dict[str, Any]], key: str) -> dict[int, list[dict[str, Any]]]:
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[int(row[key])].append(row)
        return dict(grouped)

    @staticmethod
    def _shot_code(row: dict[str, Any]) -> str:
        return f'EP{int(row["episode_no"]):03d} / {int(row["scene_no"]):03d} / S{int(row["shot_no"]):03d}'

    @staticmethod
    def _version_number(version_no: int) -> str:
        return f'V{int(version_no):03d}'

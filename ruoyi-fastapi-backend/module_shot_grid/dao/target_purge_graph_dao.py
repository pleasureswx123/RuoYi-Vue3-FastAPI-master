"""按冻结目标 ID 集合删除业务图；调用者负责项目协调锁和事务。"""

from dataclasses import dataclass

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.dao import project_purge_dao as models
from module_shot_grid.exceptions import shot_grid_error


@dataclass(frozen=True)
class TargetPurgeGraph:
    project_id: int
    kind: str
    target_id: int
    item_ids: list[int]
    task_ids: list[int]
    version_ids: list[int]
    submission_ids: list[int]
    review_ids: list[int]


class ShotGridTargetPurgeGraphDao:
    @staticmethod
    async def lock_target_graph(db: AsyncSession, project_id: int, kind: str, target_id: int) -> TargetPurgeGraph:
        if kind not in {'shot', 'asset'}:
            raise ValueError('目标类型无效')
        item_ids = (
            list(
                await db.scalars(
                    select(models.ShotGridAssetItem.asset_item_id)
                    .where(
                        models.ShotGridAssetItem.project_id == project_id,
                        models.ShotGridAssetItem.asset_id == target_id,
                    )
                    .with_for_update()
                )
            )
            if kind == 'asset'
            else []
        )
        task_scope = (
            models.ShotGridTask.shot_id == target_id
            if kind == 'shot'
            else models.ShotGridTask.asset_item_id.in_(item_ids)
        )
        task_ids = list(
            await db.scalars(
                select(models.ShotGridTask.task_id)
                .where(models.ShotGridTask.project_id == project_id, task_scope)
                .with_for_update()
            )
        )
        version_ids = list(
            await db.scalars(
                select(models.ShotGridVersion.version_id)
                .where(models.ShotGridVersion.project_id == project_id, models.ShotGridVersion.task_id.in_(task_ids))
                .with_for_update()
            )
        )
        submission_ids = list(
            await db.scalars(
                select(models.ShotGridVersionSubmission.submission_id)
                .where(
                    models.ShotGridVersionSubmission.project_id == project_id,
                    models.ShotGridVersionSubmission.task_id.in_(task_ids),
                )
                .with_for_update()
            )
        )
        review_ids = list(
            await db.scalars(
                select(models.ShotGridReviewList.review_list_id)
                .where(
                    models.ShotGridReviewList.project_id == project_id,
                    or_(
                        models.ShotGridReviewList.auto_version_id.in_(version_ids),
                        models.ShotGridReviewList.review_list_id.in_(
                            select(models.ShotGridReviewListVersion.review_list_id).where(
                                models.ShotGridReviewListVersion.version_id.in_(version_ids)
                            )
                        ),
                    ),
                )
                .with_for_update()
            )
        )
        return TargetPurgeGraph(
            project_id, kind, target_id, item_ids, task_ids, version_ids, submission_ids, review_ids
        )

    @staticmethod
    async def assert_targets_quiescent(db: AsyncSession, graph: TargetPurgeGraph) -> None:
        checks = (
            (
                models.ShotGridStorageOperation,
                [
                    models.ShotGridStorageOperation.aggregate_type == graph.kind,
                    models.ShotGridStorageOperation.aggregate_id == graph.target_id,
                ],
                'operation_status',
                {'processing', 'compensation_pending'},
            ),
            (
                models.ShotGridVersionSubmission,
                [models.ShotGridVersionSubmission.submission_id.in_(graph.submission_ids)],
                'submission_status',
                {'publishing', 'committing'},
            ),
            (
                models.ShotGridFinalDelivery,
                [models.ShotGridFinalDelivery.task_id.in_(graph.task_ids)],
                'delivery_status',
                {'publishing'},
            ),
            (
                models.ShotGridMediaDerivation,
                [models.ShotGridMediaDerivation.version_id.in_(graph.version_ids)],
                'derivation_status',
                {'processing'},
            ),
        )
        for model, conditions, status_field, running in checks:
            # 连同待领取行一起锁定，锁等待后读取状态，防止检查后被 Worker 领取。
            scoped_conditions = list(conditions)
            if hasattr(model, 'project_id'):
                scoped_conditions.append(model.project_id == graph.project_id)
            rows = await db.scalars(
                select(model).where(*scoped_conditions).execution_options(populate_existing=True).with_for_update()
            )
            if any(getattr(row, status_field) in running for row in rows):
                raise shot_grid_error(
                    409, 'SG_TARGET_PURGE_RUNTIME_ACTIVE', '目标仍有文件任务执行中，请等待其结束后重试'
                )

    @staticmethod
    async def delete_target_graph(db: AsyncSession, graph: TargetPurgeGraph) -> None:
        versions, submissions = graph.version_ids, graph.submission_ids
        note_ids = list(
            await db.scalars(select(models.ShotGridNote.note_id).where(models.ShotGridNote.version_id.in_(versions)))
        )
        scopes = (
            (models.ShotGridReviewIssueDraft, models.ShotGridReviewIssueDraft.version_id.in_(versions)),
            (
                models.ShotGridIssueVerification,
                or_(
                    models.ShotGridIssueVerification.note_id.in_(note_ids),
                    models.ShotGridIssueVerification.checked_version_id.in_(versions),
                ),
            ),
            (
                models.ShotGridVersionIssueResponse,
                or_(
                    models.ShotGridVersionIssueResponse.note_id.in_(note_ids),
                    models.ShotGridVersionIssueResponse.submission_id.in_(submissions),
                ),
            ),
            (models.ShotGridReviewAction, models.ShotGridReviewAction.version_id.in_(versions)),
            (models.ShotGridNote, models.ShotGridNote.note_id.in_(note_ids)),
            (
                models.ShotGridVersionCandidateSelection,
                models.ShotGridVersionCandidateSelection.version_id.in_(versions),
            ),
            (models.ShotGridReviewListVersion, models.ShotGridReviewListVersion.version_id.in_(versions)),
        )
        for model, scope in scopes:
            await db.execute(delete(model).where(scope))
        # 非目标问题可能引用当前解决版本，只解除引用，不删除其他目标的问题。
        await db.execute(
            update(models.ShotGridNote)
            .where(models.ShotGridNote.resolved_in_version_id.in_(versions))
            .values(resolved_in_version_id=None)
        )
        for review_id in graph.review_ids:
            remaining = await db.scalar(
                select(models.ShotGridReviewListVersion.version_id)
                .where(models.ShotGridReviewListVersion.review_list_id == review_id)
                .limit(1)
            )
            if remaining is None:
                await db.execute(
                    delete(models.ShotGridReviewList).where(models.ShotGridReviewList.review_list_id == review_id)
                )
            else:
                await db.execute(
                    update(models.ShotGridReviewList)
                    .where(models.ShotGridReviewList.review_list_id == review_id)
                    .values(lock_version=models.ShotGridReviewList.lock_version + 1)
                )
        await db.execute(
            delete(models.ShotGridFinalDelivery).where(models.ShotGridFinalDelivery.task_id.in_(graph.task_ids))
        )
        await db.execute(
            delete(models.ShotGridMediaDerivation).where(models.ShotGridMediaDerivation.version_id.in_(versions))
        )
        await db.execute(delete(models.ShotGridVersionFile).where(models.ShotGridVersionFile.version_id.in_(versions)))
        await db.execute(
            update(models.ShotGridVersion)
            .where(models.ShotGridVersion.version_id.in_(versions))
            .values(selected_candidate_id=None, selected_by=None, selected_time=None)
        )
        await db.execute(
            delete(models.ShotGridVersionCandidate).where(models.ShotGridVersionCandidate.version_id.in_(versions))
        )
        await db.execute(delete(models.ShotGridVersion).where(models.ShotGridVersion.version_id.in_(versions)))
        await db.execute(
            delete(models.ShotGridVersionSubmissionFile).where(
                models.ShotGridVersionSubmissionFile.submission_id.in_(submissions)
            )
        )
        await db.execute(
            delete(models.ShotGridVersionSubmission).where(
                models.ShotGridVersionSubmission.submission_id.in_(submissions)
            )
        )
        await db.execute(
            delete(models.ShotGridTaskScheduleChange).where(
                models.ShotGridTaskScheduleChange.task_id.in_(graph.task_ids)
            )
        )
        await db.execute(delete(models.ShotGridTask).where(models.ShotGridTask.task_id.in_(graph.task_ids)))
        if graph.kind == 'shot':
            await db.execute(
                delete(models.ShotGridShotAssetRequirement).where(
                    models.ShotGridShotAssetRequirement.shot_id == graph.target_id
                )
            )
            await db.execute(
                delete(models.ShotGridShotAsset).where(models.ShotGridShotAsset.shot_id == graph.target_id)
            )
            await db.execute(delete(models.ShotGridShot).where(models.ShotGridShot.shot_id == graph.target_id))
        else:
            await db.execute(
                update(models.ShotGridShotAssetRequirement)
                .where(models.ShotGridShotAssetRequirement.asset_id == graph.target_id)
                .values(asset_id=None, resolution_status='ignored', resolution_reason='关联资产已永久删除')
            )
            await db.execute(
                delete(models.ShotGridShotAsset).where(models.ShotGridShotAsset.asset_id == graph.target_id)
            )
            await db.execute(
                delete(models.ShotGridAssetItem).where(models.ShotGridAssetItem.asset_item_id.in_(graph.item_ids))
            )
            await db.execute(delete(models.ShotGridAsset).where(models.ShotGridAsset.asset_id == graph.target_id))
        await db.execute(
            delete(models.ShotGridStorageOperation).where(
                models.ShotGridStorageOperation.project_id == graph.project_id,
                models.ShotGridStorageOperation.aggregate_type == graph.kind,
                models.ShotGridStorageOperation.aggregate_id == graph.target_id,
            )
        )
        await db.flush()

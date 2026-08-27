from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import String, and_, asc, case, cast, delete, desc, exists, func, or_, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql import Select

from module_admin.entity.do.user_do import SysUser
from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridShotAsset
from module_shot_grid.entity.do.project_do import (
    ShotGridEpisode,
    ShotGridProject,
    ShotGridProjectMember,
    ShotGridScene,
    ShotGridShot,
)
from module_shot_grid.entity.do.review_do import ShotGridNote
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageOperation
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import (
    ShotGridVersion,
    ShotGridVersionCandidate,
    ShotGridVersionFile,
    ShotGridVersionSubmission,
)
from module_shot_grid.entity.vo.shot_crud_vo import ShotGridShotListQueryModel


class ShotGridShotCrudDao:
    """镜头普通管理的数据访问层，不提交业务事务。"""

    @classmethod
    def build_list_statement(
        cls,
        project_id: int,
        query: ShotGridShotListQueryModel,
        *,
        include_archived: bool = False,
    ) -> Select:
        """构造分页列表语句，排序字段只能来自 VO 白名单。"""

        task = aliased(ShotGridTask, name='shot_list_task')
        assignee = aliased(SysUser, name='shot_list_assignee')
        status_expression = cls._status_expression(task)
        latest_operation_status = cls._latest_operation_status()
        has_uncommitted_submission = exists(
            select(1).where(
                ShotGridVersionSubmission.task_id == task.task_id,
                ShotGridVersionSubmission.submission_status != 'committed',
            )
        )

        statement = (
            select(
                ShotGridShot.shot_id,
                ShotGridShot.project_id,
                ShotGridProject.project_status,
                ShotGridProjectStorage.storage_status,
                ShotGridShot.episode_id,
                ShotGridEpisode.episode_no,
                ShotGridShot.scene_id,
                ShotGridScene.scene_no,
                ShotGridScene.scene_name,
                ShotGridShot.shot_no,
                ShotGridShot.storage_dir_name,
                latest_operation_status.label('directory_operation_status'),
                ShotGridShot.duration_ms,
                ShotGridShot.shot_size,
                ShotGridShot.camera_position,
                ShotGridShot.camera_movement,
                ShotGridShot.focal_length,
                ShotGridShot.description,
                ShotGridShot.dialogue,
                ShotGridShot.sound_effect,
                ShotGridShot.color_reference,
                ShotGridShot.remark,
                ShotGridShot.sort_order,
                ShotGridShot.shot_no.label('sequence_position'),
                ShotGridShot.lifecycle_status,
                status_expression.label('status'),
                task.task_id,
                task.task_kind,
                task.task_status,
                has_uncommitted_submission.label('has_uncommitted_submission'),
                task.priority,
                task.due_date,
                task.lock_version.label('task_lock_version'),
                task.assignee_user_id,
                assignee.nick_name.label('assignee_nick_name'),
                func.upper(assignee.nick_name).label('assignee_producer_code'),
                ShotGridShot.create_by,
                ShotGridShot.create_time,
                ShotGridShot.update_by,
                ShotGridShot.update_time,
                ShotGridShot.lock_version,
            )
            .join(
                ShotGridProject,
                ShotGridProject.project_id == ShotGridShot.project_id,
            )
            .outerjoin(
                ShotGridProjectStorage,
                ShotGridProjectStorage.project_id == ShotGridShot.project_id,
            )
            .join(
                ShotGridEpisode,
                and_(
                    ShotGridEpisode.episode_id == ShotGridShot.episode_id,
                    ShotGridEpisode.project_id == ShotGridShot.project_id,
                ),
            )
            .join(
                ShotGridScene,
                and_(
                    ShotGridScene.scene_id == ShotGridShot.scene_id,
                    ShotGridScene.episode_id == ShotGridShot.episode_id,
                    ShotGridScene.project_id == ShotGridShot.project_id,
                ),
            )
            .outerjoin(
                task,
                and_(
                    task.shot_id == ShotGridShot.shot_id,
                    task.project_id == ShotGridShot.project_id,
                    task.task_kind == 'shot_video',
                    task.del_flag == '0',
                ),
            )
            .outerjoin(assignee, assignee.user_id == task.assignee_user_id)
            .outerjoin(
                ShotGridProjectMember,
                and_(
                    ShotGridProjectMember.project_id == ShotGridShot.project_id,
                    ShotGridProjectMember.user_id == task.assignee_user_id,
                ),
            )
            .where(
                ShotGridShot.project_id == project_id,
                ShotGridShot.del_flag == '0',
                ShotGridProject.del_flag == '0',
                ShotGridEpisode.del_flag == '0',
                ShotGridScene.del_flag == '0',
            )
        )
        if not include_archived:
            statement = statement.where(ShotGridShot.lifecycle_status == 'active')

        keyword = query.keyword.strip() if query.keyword else None
        if keyword:
            statement = statement.where(
                or_(
                    cast(ShotGridShot.shot_no, String).ilike(f'%{keyword}%'),
                    ShotGridShot.storage_dir_name.ilike(f'%{keyword}%'),
                    ShotGridShot.description.ilike(f'%{keyword}%'),
                    ShotGridShot.dialogue.ilike(f'%{keyword}%'),
                    ShotGridScene.scene_name.ilike(f'%{keyword}%'),
                )
            )
        if query.episode_id is not None:
            statement = statement.where(ShotGridShot.episode_id == query.episode_id)
        if query.scene_id is not None:
            statement = statement.where(ShotGridShot.scene_id == query.scene_id)
        if query.shot_status is not None:
            statement = statement.where(status_expression == query.shot_status)
        if query.assignee_user_id is not None:
            statement = statement.where(task.assignee_user_id == query.assignee_user_id)
        if query.asset_id is not None:
            statement = statement.where(
                exists(
                    select(1).where(
                        ShotGridShotAsset.project_id == project_id,
                        ShotGridShotAsset.shot_id == ShotGridShot.shot_id,
                        ShotGridShotAsset.asset_id == query.asset_id,
                    )
                )
            )

        order_columns = {
            'episodeNo': ShotGridEpisode.episode_no,
            'sceneNo': ShotGridScene.scene_no,
            'shotNo': ShotGridShot.shot_no,
            'sortOrder': ShotGridShot.sort_order,
            'durationMs': ShotGridShot.duration_ms,
            'updateTime': ShotGridShot.update_time,
        }
        order_column = order_columns[query.order_by_column]
        direction = asc if query.is_asc == 'ascending' else desc
        if query.order_by_column == 'sortOrder':
            return statement.order_by(
                ShotGridEpisode.sort_order,
                ShotGridEpisode.episode_no,
                ShotGridScene.sort_order,
                ShotGridScene.scene_no,
                direction(ShotGridShot.sort_order),
                ShotGridShot.shot_no,
                ShotGridShot.shot_id,
            )
        return statement.order_by(
            direction(order_column), ShotGridEpisode.episode_no, ShotGridShot.shot_no, ShotGridShot.shot_id
        )

    @classmethod
    async def get_shot_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridShotListQueryModel,
    ) -> tuple[list[dict[str, Any]], int]:
        statement = cls.build_list_statement(project_id, query)
        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        rows = (
            (await db.execute(statement.offset((query.page_num - 1) * query.page_size).limit(query.page_size)))
            .mappings()
            .all()
        )
        return [dict(row) for row in rows], total

    @classmethod
    async def get_shot_detail(cls, db: AsyncSession, project_id: int, shot_id: int) -> dict[str, Any] | None:
        query = ShotGridShotListQueryModel(pageNum=1, pageSize=1)
        statement = cls.build_list_statement(project_id, query, include_archived=True).where(
            ShotGridShot.shot_id == shot_id
        )
        row = (await db.execute(statement.limit(1))).mappings().one_or_none()
        return dict(row) if row is not None else None

    @staticmethod
    async def list_assets_for_shots(db: AsyncSession, project_id: int, shot_ids: Iterable[int]) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(shot_ids))
        if not ids:
            return []
        rows = (
            (
                await db.execute(
                    select(
                        ShotGridShotAsset.shot_id,
                        ShotGridAsset.asset_id,
                        ShotGridAsset.asset_name,
                        ShotGridAsset.asset_type,
                    )
                    .join(
                        ShotGridAsset,
                        and_(
                            ShotGridAsset.asset_id == ShotGridShotAsset.asset_id,
                            ShotGridAsset.project_id == ShotGridShotAsset.project_id,
                        ),
                    )
                    .where(
                        ShotGridShotAsset.project_id == project_id,
                        ShotGridShotAsset.shot_id.in_(ids),
                        ShotGridAsset.del_flag == '0',
                    )
                    .order_by(
                        ShotGridShotAsset.shot_id,
                        ShotGridAsset.asset_type,
                        ShotGridAsset.sort_order,
                        ShotGridAsset.asset_id,
                    )
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    @classmethod
    def build_read_projection_statement(cls, project_id: int, shot_ids: Iterable[int]) -> Select:
        """构造镜头列表批量只读投影；所有版本、文件和意见均限定在同一最新版本。"""

        ids = list(dict.fromkeys(shot_ids))
        task = aliased(ShotGridTask, name='shot_projection_task')
        latest_version = (
            select(
                ShotGridVersion.version_id,
                ShotGridVersion.version_no,
                ShotGridVersion.version_status,
                ShotGridVersion.selected_candidate_id,
            )
            .where(
                ShotGridVersion.project_id == project_id,
                ShotGridVersion.task_id == task.task_id,
            )
            .order_by(ShotGridVersion.version_no.desc(), ShotGridVersion.version_id.desc())
            .limit(1)
            .lateral('shot_latest_version')
        )
        display_candidate = (
            select(ShotGridVersionCandidate.candidate_id)
            .where(ShotGridVersionCandidate.version_id == latest_version.c.version_id)
            .order_by(
                case(
                    (ShotGridVersionCandidate.candidate_id == latest_version.c.selected_candidate_id, 0),
                    else_=1,
                ),
                ShotGridVersionCandidate.sort_order,
                ShotGridVersionCandidate.candidate_no,
                ShotGridVersionCandidate.candidate_id,
            )
            .limit(1)
            .lateral('shot_display_candidate')
        )
        display_review_media = (
            select(
                ShotGridVersionFile.file_id,
                ShotGridVersionFile.business_file_name,
            )
            .where(
                ShotGridVersionFile.version_id == latest_version.c.version_id,
                ShotGridVersionFile.candidate_id == display_candidate.c.candidate_id,
                ShotGridVersionFile.file_role == 'review_media',
            )
            .order_by(ShotGridVersionFile.sort_order, ShotGridVersionFile.file_id)
            .limit(1)
            .lateral('shot_display_review_media')
        )
        thumbnail = (
            select(
                ShotGridVersionFile.file_id,
                ShotGridVersionFile.business_file_name,
            )
            .where(
                ShotGridVersionFile.version_id == latest_version.c.version_id,
                ShotGridVersionFile.candidate_id == display_candidate.c.candidate_id,
                ShotGridVersionFile.file_role == 'thumbnail',
            )
            .order_by(ShotGridVersionFile.sort_order, ShotGridVersionFile.file_id)
            .limit(1)
            .lateral('shot_latest_thumbnail')
        )
        proxy_media = (
            select(
                ShotGridVersionFile.file_id,
                ShotGridVersionFile.business_file_name,
            )
            .where(
                ShotGridVersionFile.version_id == latest_version.c.version_id,
                ShotGridVersionFile.candidate_id == display_candidate.c.candidate_id,
                ShotGridVersionFile.file_role == 'proxy_media',
            )
            .order_by(ShotGridVersionFile.sort_order, ShotGridVersionFile.file_id)
            .limit(1)
            .lateral('shot_latest_proxy_media')
        )
        latest_feedback = (
            select(
                ShotGridNote.note_id,
                ShotGridNote.content,
                ShotGridNote.note_status,
                ShotGridNote.create_time,
            )
            .where(
                ShotGridNote.project_id == project_id,
                ShotGridNote.version_id == latest_version.c.version_id,
            )
            .order_by(
                case((ShotGridNote.note_status == 'open', 0), else_=1),
                ShotGridNote.create_time.desc(),
                ShotGridNote.note_id.desc(),
            )
            .limit(1)
            .lateral('shot_latest_feedback')
        )

        return (
            select(
                ShotGridShot.shot_id,
                latest_version.c.version_id.label('latest_version_id'),
                latest_version.c.version_no.label('latest_version_no'),
                latest_version.c.version_status.label('latest_version_status'),
                display_review_media.c.business_file_name.label('latest_business_file_name'),
                thumbnail.c.file_id.label('thumbnail_file_id'),
                thumbnail.c.business_file_name.label('thumbnail_business_file_name'),
                proxy_media.c.file_id.label('proxy_media_file_id'),
                proxy_media.c.business_file_name.label('proxy_media_business_file_name'),
                latest_feedback.c.note_id.label('latest_feedback_note_id'),
                latest_feedback.c.content.label('latest_feedback_content'),
                latest_feedback.c.note_status.label('latest_feedback_status'),
                latest_feedback.c.create_time.label('latest_feedback_create_time'),
            )
            .select_from(ShotGridShot)
            .outerjoin(
                task,
                and_(
                    task.project_id == ShotGridShot.project_id,
                    task.shot_id == ShotGridShot.shot_id,
                    task.task_kind == 'shot_video',
                    task.del_flag == '0',
                ),
            )
            .outerjoin(latest_version, true())
            .outerjoin(display_candidate, true())
            .outerjoin(display_review_media, true())
            .outerjoin(thumbnail, true())
            .outerjoin(proxy_media, true())
            .outerjoin(latest_feedback, true())
            .where(
                ShotGridShot.project_id == project_id,
                ShotGridShot.shot_id.in_(ids),
                ShotGridShot.del_flag == '0',
            )
            .order_by(ShotGridShot.shot_id)
        )

    @classmethod
    async def list_read_projections_for_shots(
        cls,
        db: AsyncSession,
        project_id: int,
        shot_ids: Iterable[int],
    ) -> list[dict[str, Any]]:
        """批量读取列表和详情共用的版本、缩略图及反馈投影。"""

        ids = list(dict.fromkeys(shot_ids))
        if not ids:
            return []
        rows = (await db.execute(cls.build_read_projection_statement(project_id, ids))).mappings().all()
        return [dict(row) for row in rows]

    @staticmethod
    async def lock_project_storage(
        db: AsyncSession,
        project_id: int,
    ) -> tuple[ShotGridProject | None, ShotGridProjectStorage | None]:
        row = (
            await db.execute(
                select(ShotGridProject, ShotGridProjectStorage)
                .outerjoin(ShotGridProjectStorage, ShotGridProjectStorage.project_id == ShotGridProject.project_id)
                .where(ShotGridProject.project_id == project_id, ShotGridProject.del_flag == '0')
                .with_for_update(of=ShotGridProject)
            )
        ).one_or_none()
        return (None, None) if row is None else (row[0], row[1])

    @staticmethod
    async def get_scene_context(
        db: AsyncSession,
        project_id: int,
        scene_id: int,
    ) -> tuple[ShotGridScene, ShotGridEpisode] | None:
        row = (
            await db.execute(
                select(ShotGridScene, ShotGridEpisode)
                .join(
                    ShotGridEpisode,
                    and_(
                        ShotGridEpisode.episode_id == ShotGridScene.episode_id,
                        ShotGridEpisode.project_id == ShotGridScene.project_id,
                    ),
                )
                .where(
                    ShotGridScene.scene_id == scene_id,
                    ShotGridScene.project_id == project_id,
                    ShotGridScene.del_flag == '0',
                    ShotGridScene.lifecycle_status == 'active',
                    ShotGridEpisode.del_flag == '0',
                    ShotGridEpisode.lifecycle_status == 'active',
                )
            )
        ).one_or_none()
        return None if row is None else (row[0], row[1])

    @staticmethod
    async def list_active_assets(db: AsyncSession, project_id: int, asset_ids: Iterable[int]) -> list[ShotGridAsset]:
        ids = list(dict.fromkeys(asset_ids))
        if not ids:
            return []
        return list(
            (
                await db.execute(
                    select(ShotGridAsset).where(
                        ShotGridAsset.project_id == project_id,
                        ShotGridAsset.asset_id.in_(ids),
                        ShotGridAsset.lifecycle_status == 'active',
                        ShotGridAsset.del_flag == '0',
                    )
                )
            )
            .scalars()
            .all()
        )

    @staticmethod
    async def shot_no_exists(
        db: AsyncSession,
        scene_id: int,
        shot_no: int,
        *,
        exclude_shot_id: int | None = None,
    ) -> bool:
        statement = select(func.count(ShotGridShot.shot_id)).where(
            ShotGridShot.scene_id == scene_id,
            ShotGridShot.shot_no == shot_no,
            ShotGridShot.del_flag == '0',
        )
        if exclude_shot_id is not None:
            statement = statement.where(ShotGridShot.shot_id != exclude_shot_id)
        return bool(await db.scalar(statement))

    @staticmethod
    async def add_shot(db: AsyncSession, shot: ShotGridShot) -> ShotGridShot:
        db.add(shot)
        await db.flush()
        return shot

    @staticmethod
    async def add_storage_operation(db: AsyncSession, operation: ShotGridStorageOperation) -> None:
        db.add(operation)
        await db.flush()

    @staticmethod
    async def get_shot_for_update(db: AsyncSession, project_id: int, shot_id: int) -> ShotGridShot | None:
        return (
            await db.execute(
                select(ShotGridShot)
                .where(
                    ShotGridShot.project_id == project_id,
                    ShotGridShot.shot_id == shot_id,
                    ShotGridShot.del_flag == '0',
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @staticmethod
    async def list_scene_shot_order_for_update(
        db: AsyncSession,
        project_id: int,
        scene_id: int,
    ) -> list[dict[str, Any]]:
        """锁定一个场次的活动镜头并返回稳定的场内顺序。"""

        rows = (
            (
                await db.execute(
                    select(
                        ShotGridShot.shot_id,
                        ShotGridShot.sort_order,
                        ShotGridShot.shot_no,
                        ShotGridShot.storage_dir_name,
                        ShotGridShot.lock_version,
                    )
                    .where(
                        ShotGridShot.project_id == project_id,
                        ShotGridShot.scene_id == scene_id,
                        ShotGridShot.lifecycle_status == 'active',
                        ShotGridShot.del_flag == '0',
                    )
                    .order_by(ShotGridShot.sort_order, ShotGridShot.shot_no, ShotGridShot.shot_id)
                    .with_for_update()
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    @staticmethod
    async def list_scene_shot_entities_for_update(
        db: AsyncSession,
        project_id: int,
        scene_id: int,
    ) -> list[ShotGridShot]:
        """按场内序号锁定活动镜头，供两阶段连续编号使用。"""

        return list(
            (
                await db.execute(
                    select(ShotGridShot)
                    .where(
                        ShotGridShot.project_id == project_id,
                        ShotGridShot.scene_id == scene_id,
                        ShotGridShot.lifecycle_status == 'active',
                        ShotGridShot.del_flag == '0',
                    )
                    .order_by(ShotGridShot.shot_no, ShotGridShot.shot_id)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )

    @classmethod
    async def list_scene_shots_for_renumber(
        cls,
        db: AsyncSession,
        project_id: int,
        scene_id: int,
    ) -> list[dict[str, Any]]:
        """锁定单场活动镜头，并按场内顺序返回重编号快照。"""

        rows = (
            (
                await db.execute(
                    select(
                        ShotGridShot.shot_id,
                        ShotGridShot.shot_no,
                        ShotGridShot.storage_dir_name,
                        ShotGridShot.lock_version,
                        ShotGridShot.episode_id,
                        ShotGridScene.scene_id,
                        ShotGridScene.scene_no,
                        ShotGridEpisode.storage_dir_name.label('episode_storage_dir_name'),
                        cls._latest_operation_status().label('directory_operation_status'),
                    )
                    .join(
                        ShotGridScene,
                        and_(
                            ShotGridScene.scene_id == ShotGridShot.scene_id,
                            ShotGridScene.episode_id == ShotGridShot.episode_id,
                            ShotGridScene.project_id == ShotGridShot.project_id,
                        ),
                    )
                    .join(
                        ShotGridEpisode,
                        and_(
                            ShotGridEpisode.episode_id == ShotGridShot.episode_id,
                            ShotGridEpisode.project_id == ShotGridShot.project_id,
                        ),
                    )
                    .where(
                        ShotGridShot.project_id == project_id,
                        ShotGridShot.scene_id == scene_id,
                        ShotGridShot.lifecycle_status == 'active',
                        ShotGridShot.del_flag == '0',
                        ShotGridScene.lifecycle_status == 'active',
                        ShotGridScene.del_flag == '0',
                        ShotGridEpisode.lifecycle_status == 'active',
                        ShotGridEpisode.del_flag == '0',
                    )
                    .order_by(
                        ShotGridShot.sort_order,
                        ShotGridShot.shot_no,
                        ShotGridShot.shot_id,
                    )
                    .with_for_update(of=ShotGridShot)
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    @staticmethod
    async def get_scene_for_update(
        db: AsyncSession,
        project_id: int,
        scene_id: int,
    ) -> tuple[ShotGridScene, ShotGridEpisode] | None:
        row = (
            await db.execute(
                select(ShotGridScene, ShotGridEpisode)
                .join(
                    ShotGridEpisode,
                    and_(
                        ShotGridEpisode.episode_id == ShotGridScene.episode_id,
                        ShotGridEpisode.project_id == ShotGridScene.project_id,
                    ),
                )
                .where(
                    ShotGridScene.project_id == project_id,
                    ShotGridScene.scene_id == scene_id,
                    ShotGridScene.lifecycle_status == 'active',
                    ShotGridScene.del_flag == '0',
                    ShotGridEpisode.lifecycle_status == 'active',
                    ShotGridEpisode.del_flag == '0',
                )
                .with_for_update(of=ShotGridScene)
            )
        ).one_or_none()
        return None if row is None else (row[0], row[1])

    @staticmethod
    async def list_scene_renumber_blockers(
        db: AsyncSession,
        project_id: int,
        shot_ids: Iterable[int],
    ) -> list[dict[str, Any]]:
        """检查已经开始的任务、版本和文件；仅未开始任务不阻止场内重排。"""

        ids = list(dict.fromkeys(shot_ids))
        if not ids:
            return []
        task = aliased(ShotGridTask, name='renumber_task')
        version = aliased(ShotGridVersion, name='renumber_version')
        version_file = aliased(ShotGridVersionFile, name='renumber_version_file')
        submission = aliased(ShotGridVersionSubmission, name='renumber_submission')
        rows = (
            (
                await db.execute(
                    select(
                        ShotGridShot.shot_id,
                        exists(
                            select(1).where(
                                task.project_id == project_id,
                                task.shot_id == ShotGridShot.shot_id,
                                task.del_flag == '0',
                            )
                        ).label('has_task'),
                        exists(
                            select(1).where(
                                task.project_id == project_id,
                                task.shot_id == ShotGridShot.shot_id,
                                task.del_flag == '0',
                                task.task_status != 'not_started',
                            )
                        ).label('has_started_task'),
                        exists(
                            select(1)
                            .select_from(version)
                            .join(task, task.task_id == version.task_id)
                            .where(task.project_id == project_id, task.shot_id == ShotGridShot.shot_id)
                        ).label('has_version'),
                        or_(
                            exists(
                                select(1)
                                .select_from(version_file)
                                .join(version, version.version_id == version_file.version_id)
                                .join(task, task.task_id == version.task_id)
                                .where(task.project_id == project_id, task.shot_id == ShotGridShot.shot_id)
                            ),
                            exists(
                                select(1)
                                .select_from(submission)
                                .join(task, task.task_id == submission.task_id)
                                .where(task.project_id == project_id, task.shot_id == ShotGridShot.shot_id)
                            ),
                        ).label('has_file'),
                    ).where(ShotGridShot.project_id == project_id, ShotGridShot.shot_id.in_(ids))
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows if row['has_started_task'] or row['has_version'] or row['has_file']]

    @staticmethod
    async def get_task_for_update(db: AsyncSession, project_id: int, shot_id: int) -> ShotGridTask | None:
        return (
            await db.execute(
                select(ShotGridTask)
                .where(
                    ShotGridTask.project_id == project_id,
                    ShotGridTask.shot_id == shot_id,
                    ShotGridTask.task_kind == 'shot_video',
                    ShotGridTask.del_flag == '0',
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @staticmethod
    async def shot_has_versions(db: AsyncSession, shot_id: int) -> bool:
        return bool(
            await db.scalar(
                select(func.count(ShotGridVersion.version_id))
                .join(ShotGridTask, ShotGridTask.task_id == ShotGridVersion.task_id)
                .where(ShotGridTask.shot_id == shot_id, ShotGridTask.del_flag == '0')
            )
        )

    @staticmethod
    async def update_shot(
        db: AsyncSession,
        *,
        project_id: int,
        shot_id: int,
        expected_lock_version: int,
        values: dict[str, Any],
    ) -> int | None:
        result = await db.execute(
            update(ShotGridShot)
            .where(
                ShotGridShot.project_id == project_id,
                ShotGridShot.shot_id == shot_id,
                ShotGridShot.lock_version == expected_lock_version,
                ShotGridShot.lifecycle_status == 'active',
                ShotGridShot.del_flag == '0',
            )
            .values(**values, lock_version=ShotGridShot.lock_version + 1)
            .returning(ShotGridShot.lock_version)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_shot_order(
        db: AsyncSession,
        *,
        project_id: int,
        shot_id: int,
        sort_order: int,
        actor_name: str,
        now: datetime,
    ) -> None:
        """更新已锁定镜头的内部排序键，并推进乐观锁版本。"""

        await db.execute(
            update(ShotGridShot)
            .where(
                ShotGridShot.project_id == project_id,
                ShotGridShot.shot_id == shot_id,
                ShotGridShot.lifecycle_status == 'active',
                ShotGridShot.del_flag == '0',
            )
            .values(
                sort_order=sort_order,
                update_by=actor_name,
                update_time=now,
                lock_version=ShotGridShot.lock_version + 1,
            )
        )

    @staticmethod
    async def move_shot_number_to_temporary(
        db: AsyncSession,
        *,
        project_id: int,
        scene_id: int,
        shot_id: int,
        source_shot_no: int,
        temporary_shot_no: int,
        expected_lock_version: int,
    ) -> bool:
        """连续编号第一阶段：只改为事务内临时编号，不推进业务锁版本。"""

        result = await db.execute(
            update(ShotGridShot)
            .where(
                ShotGridShot.project_id == project_id,
                ShotGridShot.scene_id == scene_id,
                ShotGridShot.shot_id == shot_id,
                ShotGridShot.shot_no == source_shot_no,
                ShotGridShot.lock_version == expected_lock_version,
                ShotGridShot.lifecycle_status == 'active',
                ShotGridShot.del_flag == '0',
            )
            .values(shot_no=temporary_shot_no)
        )
        return result.rowcount == 1

    @staticmethod
    async def finalize_shot_position(
        db: AsyncSession,
        *,
        project_id: int,
        scene_id: int,
        shot_id: int,
        temporary_shot_no: int,
        target_shot_no: int,
        storage_dir_name: str | None,
        expected_lock_version: int,
        actor_name: str,
        now: datetime,
    ) -> int | None:
        """连续编号第二阶段：写入最终 Sxxx，并让排序键与编号保持一致。"""

        result = await db.execute(
            update(ShotGridShot)
            .where(
                ShotGridShot.project_id == project_id,
                ShotGridShot.scene_id == scene_id,
                ShotGridShot.shot_id == shot_id,
                ShotGridShot.shot_no == temporary_shot_no,
                ShotGridShot.lock_version == expected_lock_version,
                ShotGridShot.lifecycle_status == 'active',
                ShotGridShot.del_flag == '0',
            )
            .values(
                shot_no=target_shot_no,
                storage_dir_name=storage_dir_name,
                sort_order=target_shot_no * 10,
                update_by=actor_name,
                update_time=now,
                lock_version=ShotGridShot.lock_version + 1,
            )
        )
        return expected_lock_version + 1 if result.rowcount == 1 else None

    @staticmethod
    async def sync_shot_assets(
        db: AsyncSession,
        *,
        project_id: int,
        shot_id: int,
        asset_ids: Iterable[int],
        actor_name: str,
        now: datetime,
    ) -> None:
        target_ids = set(asset_ids)
        existing_ids = set(
            (
                await db.execute(
                    select(ShotGridShotAsset.asset_id).where(
                        ShotGridShotAsset.project_id == project_id,
                        ShotGridShotAsset.shot_id == shot_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        removed_ids = existing_ids - target_ids
        if removed_ids:
            await db.execute(
                delete(ShotGridShotAsset).where(
                    ShotGridShotAsset.project_id == project_id,
                    ShotGridShotAsset.shot_id == shot_id,
                    ShotGridShotAsset.asset_id.in_(removed_ids),
                )
            )
        db.add_all(
            [
                ShotGridShotAsset(
                    project_id=project_id,
                    shot_id=shot_id,
                    asset_id=asset_id,
                    create_by=actor_name,
                    create_time=now,
                )
                for asset_id in sorted(target_ids - existing_ids)
            ]
        )
        await db.flush()

    @staticmethod
    async def archive_shot(
        db: AsyncSession,
        *,
        project_id: int,
        shot_id: int,
        expected_lock_version: int,
        actor_name: str,
        now: datetime,
    ) -> int | None:
        result = await db.execute(
            update(ShotGridShot)
            .where(
                ShotGridShot.project_id == project_id,
                ShotGridShot.shot_id == shot_id,
                ShotGridShot.lock_version == expected_lock_version,
                ShotGridShot.lifecycle_status == 'active',
                ShotGridShot.del_flag == '0',
            )
            .values(
                lifecycle_status='archived',
                del_flag='2',
                update_by=actor_name,
                update_time=now,
                lock_version=ShotGridShot.lock_version + 1,
            )
            .returning(ShotGridShot.lock_version)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_not_started_task(
        db: AsyncSession,
        *,
        task_id: int,
        actor_name: str,
        now: datetime,
    ) -> bool:
        result = await db.execute(
            update(ShotGridTask)
            .where(
                ShotGridTask.task_id == task_id,
                ShotGridTask.task_status == 'not_started',
                ShotGridTask.del_flag == '0',
            )
            .values(
                del_flag='2',
                update_by=actor_name,
                update_time=now,
                lock_version=ShotGridTask.lock_version + 1,
            )
        )
        return bool(result.rowcount)

    @staticmethod
    def _latest_operation_status() -> Any:
        return (
            select(ShotGridStorageOperation.operation_status)
            .where(
                ShotGridStorageOperation.project_id == ShotGridShot.project_id,
                ShotGridStorageOperation.aggregate_type == 'shot',
                ShotGridStorageOperation.aggregate_id == ShotGridShot.shot_id,
            )
            .order_by(ShotGridStorageOperation.operation_id.desc())
            .limit(1)
            .correlate(ShotGridShot)
            .scalar_subquery()
        )

    @staticmethod
    def _status_expression(task: Any) -> Any:
        final_exists = exists(
            select(1).where(
                ShotGridVersion.task_id == task.task_id,
                ShotGridVersion.version_status == 'final',
            )
        )
        return case(
            (task.task_id.is_(None), 'unassigned'),
            (task.task_status == 'pending_review', 'reviewing'),
            (and_(task.task_status == 'completed', final_exists), 'completed'),
            (task.task_status == 'completed', 'reviewing'),
            else_=task.task_status,
        )

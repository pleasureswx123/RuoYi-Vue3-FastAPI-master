"""冻结独占文件清单；共享资源和未到期保留文件不进入物理清理。"""

from datetime import datetime

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.file_do import SysFileInfo, SysFileReference
from module_shot_grid.dao import project_purge_dao as m
from module_shot_grid.dao.target_purge_graph_dao import TargetPurgeGraph
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.target_purge_paths import normalize_target_path, paths_overlap


class ShotGridTargetPurgeManifestDao:
    @staticmethod
    async def prepare_files(
        db: AsyncSession, graph: TargetPurgeGraph, actor: str, now: datetime
    ) -> list[dict[str, str]]:
        scopes = [
            and_(
                SysFileReference.business_type == 'shotgrid_version',
                SysFileReference.business_id.in_([str(i) for i in graph.version_ids]),
            ),
            and_(
                SysFileReference.business_type == 'shotgrid_version_submission',
                SysFileReference.business_id.in_([str(i) for i in graph.submission_ids]),
            ),
            and_(
                SysFileReference.business_type == 'shotgrid_task_reference',
                SysFileReference.business_id.in_([str(i) for i in graph.task_ids]),
            ),
        ]
        if graph.kind == 'shot':
            scopes.append(
                and_(
                    SysFileReference.business_type == 'shotgrid_shot_reference',
                    SysFileReference.business_id == str(graph.target_id),
                )
            )
        references = list(await db.scalars(select(SysFileReference).where(or_(*scopes))))
        file_ids = {r.file_id for r in references}
        file_ids.update(
            await db.scalars(
                select(m.ShotGridVersionFile.file_id).where(m.ShotGridVersionFile.version_id.in_(graph.version_ids))
            )
        )
        file_ids.update(
            await db.scalars(
                select(m.ShotGridVersionSubmissionFile.source_file_id).where(
                    m.ShotGridVersionSubmissionFile.submission_id.in_(graph.submission_ids)
                )
            )
        )
        file_ids.update(
            await db.scalars(
                select(m.ShotGridVersionSubmission.source_file_id).where(
                    m.ShotGridVersionSubmission.submission_id.in_(graph.submission_ids)
                )
            )
        )
        files = list(
            await db.scalars(
                select(SysFileInfo)
                .where(SysFileInfo.file_id.in_(file_ids))
                .order_by(SysFileInfo.file_id)
                .with_for_update()
            )
        )
        protected = {r.file_id for r in references if r.retention_expire_time and r.retention_expire_time > now}
        # 文件保留策略不能因永久删除业务而被移除。
        if protected:
            raise shot_grid_error(409, 'SG_TARGET_PURGE_RETENTION_ACTIVE', '目标附件仍在保留期内，暂不能永久删除')
        await db.execute(delete(SysFileReference).where(or_(*scopes)))
        shared = set(await db.scalars(select(SysFileReference.file_id).where(SysFileReference.file_id.in_(file_ids))))
        shared.update(
            await db.scalars(
                select(m.ShotGridVersionFile.file_id).where(
                    m.ShotGridVersionFile.file_id.in_(file_ids),
                    m.ShotGridVersionFile.version_id.not_in(graph.version_ids),
                )
            )
        )
        shared.update(
            await db.scalars(
                select(m.ShotGridVersionSubmissionFile.source_file_id).where(
                    m.ShotGridVersionSubmissionFile.source_file_id.in_(file_ids),
                    m.ShotGridVersionSubmissionFile.submission_id.not_in(graph.submission_ids),
                )
            )
        )
        shared.update(
            await db.scalars(
                select(m.ShotGridVersionSubmission.source_file_id).where(
                    m.ShotGridVersionSubmission.source_file_id.in_(file_ids),
                    m.ShotGridVersionSubmission.submission_id.not_in(graph.submission_ids),
                )
            )
        )
        shared.update(
            await db.scalars(
                select(m.ShotGridFinalDelivery.source_file_id).where(
                    m.ShotGridFinalDelivery.source_file_id.in_(file_ids),
                    m.ShotGridFinalDelivery.task_id.not_in(graph.task_ids),
                )
            )
        )
        result = []
        for file in files:
            if file.file_id in shared:
                continue
            if (
                file.storage_type != 'local'
                or file.access_type not in {'public', 'private'}
                or file.status == 'purging'
            ):
                raise shot_grid_error(409, 'SG_TARGET_PURGE_FILE_UNAVAILABLE', '目标独占文件当前无法安全清理')
            result.append(
                {
                    'fileId': file.file_id,
                    'storageType': file.storage_type,
                    'accessType': file.access_type,
                    'storageKey': file.storage_key,
                }
            )
            file.status, file.del_flag, file.update_by, file.update_time = 'purging', '1', actor, now
        return result

    @staticmethod
    async def prepare_paths(db: AsyncSession, graph: TargetPurgeGraph) -> list[str]:
        if graph.kind == 'shot':
            shot = await db.get(m.ShotGridShot, graph.target_id)
            episode = await db.get(m.ShotGridEpisode, shot.episode_id)
            scene = await db.get(m.ShotGridScene, shot.scene_id)
            directory = shot.storage_dir_name or f'{scene.scene_no:03d}_{shot.shot_no:04d}'
            current = f'VIDEO/{episode.storage_dir_name}/{directory}'
        else:
            asset = await db.get(m.ShotGridAsset, graph.target_id)
            current = f'ASSET/{asset.asset_type}/{asset.storage_dir_name}'
        normalize_target_path(current)
        # 旧目录可能因迁移留下不同归属，不能按历史字符串扩大递归删除范围。
        published_paths = list(
            await db.scalars(
                select(m.ShotGridVersionFile.nas_relative_path).where(
                    m.ShotGridVersionFile.version_id.in_(graph.version_ids),
                    m.ShotGridVersionFile.nas_relative_path.is_not(None),
                )
            )
        )
        for model, scope, fields in (
            (
                m.ShotGridVersionSubmission,
                m.ShotGridVersionSubmission.submission_id.in_(graph.submission_ids),
                ['target_relative_path', 'temporary_relative_path'],
            ),
            (
                m.ShotGridVersionSubmissionFile,
                m.ShotGridVersionSubmissionFile.submission_id.in_(graph.submission_ids),
                ['target_relative_path', 'temporary_relative_path'],
            ),
            (
                m.ShotGridFinalDelivery,
                m.ShotGridFinalDelivery.task_id.in_(graph.task_ids),
                ['source_nas_relative_path', 'final_nas_relative_path', 'manifest_nas_relative_path'],
            ),
        ):
            for field in fields:
                published_paths.extend(await db.scalars(select(getattr(model, field)).where(scope)))
        if any(
            not normalize_target_path(path).startswith(normalize_target_path(current) + '/') for path in published_paths
        ):
            raise shot_grid_error(
                409, 'SG_TARGET_PURGE_PATH_AMBIGUOUS', '历史文件路径不在当前目标目录内，需先核对存储归属'
            )
        other_paths = list(
            await db.scalars(
                select(m.ShotGridVersionFile.nas_relative_path)
                .join(m.ShotGridVersion, m.ShotGridVersion.version_id == m.ShotGridVersionFile.version_id)
                .where(
                    m.ShotGridVersion.project_id == graph.project_id,
                    m.ShotGridVersionFile.version_id.not_in(graph.version_ids),
                    m.ShotGridVersionFile.nas_relative_path.is_not(None),
                )
            )
        )
        if graph.kind == 'asset':
            other_assets = await db.scalars(
                select(m.ShotGridAsset).where(
                    m.ShotGridAsset.project_id == graph.project_id, m.ShotGridAsset.asset_id != graph.target_id
                )
            )
            other_paths.extend(f'ASSET/{other.asset_type}/{other.storage_dir_name}' for other in other_assets)
        else:
            rows = await db.execute(
                select(m.ShotGridShot, m.ShotGridEpisode.storage_dir_name, m.ShotGridScene.scene_no)
                .join(m.ShotGridEpisode, m.ShotGridEpisode.episode_id == m.ShotGridShot.episode_id)
                .join(m.ShotGridScene, m.ShotGridScene.scene_id == m.ShotGridShot.scene_id)
                .where(m.ShotGridShot.project_id == graph.project_id, m.ShotGridShot.shot_id != graph.target_id)
            )
            for other, episode_dir, scene_no in rows:
                directory = other.storage_dir_name or f'{scene_no:03d}_{other.shot_no:04d}'
                other_paths.append(f'VIDEO/{episode_dir}/{directory}')
        for path in other_paths:
            if paths_overlap(current, path):
                raise shot_grid_error(409, 'SG_TARGET_PURGE_PATH_SHARED', '目标目录被其他版本引用，不能永久清理')
        return [current]

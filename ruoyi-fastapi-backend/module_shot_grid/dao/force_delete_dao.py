"""强制永久删除的数据访问；不提交事务，不操作实际文件。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.dao.project_purge_dao import ShotGridProjectPurgeDao
from module_shot_grid.dao.target_purge_dao import ShotGridTargetPurgeDao
from module_shot_grid.dao.target_purge_graph_dao import ShotGridTargetPurgeGraphDao
from module_shot_grid.dao.target_purge_manifest_dao import ShotGridTargetPurgeManifestDao
from module_shot_grid.entity.do.asset_do import (
    ShotGridAsset,
)
from module_shot_grid.entity.do.project_do import ShotGridEpisode, ShotGridScene, ShotGridShot
from module_shot_grid.entity.do.target_purge_do import ShotGridTargetPurge, ShotGridTargetPurgePath
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.target_purge_paths import normalize_target_path


class ShotGridForceDeleteDao:
    """调用方必须已持有项目协调锁。"""

    @staticmethod
    async def delete_targets_permanently(
        db: AsyncSession,
        project_id: int,
        kind: str,
        items: list,
        actor: str,
        actor_id: int,
        reason: str,
        now: datetime,
    ) -> dict:
        """冻结清单、删除业务图与占用原路径必须在同一事务提交。"""
        if kind not in {'shot', 'asset'}:
            raise ValueError('目标类型无效')
        context = await ShotGridProjectPurgeDao.lock_project_context(db, project_id)
        if context is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目或存储快照不存在')
        model = ShotGridShot if kind == 'shot' else ShotGridAsset
        key = model.shot_id if kind == 'shot' else model.asset_id
        expected = {getattr(item, f'{kind}_id'): item.lock_version for item in items}
        targets = list(
            await db.scalars(
                select(model)
                .where(
                    model.project_id == project_id,
                    key.in_(expected),
                    model.del_flag == '0',
                )
                .order_by(key)
                .with_for_update()
            )
        )
        if len(targets) != len(expected):
            raise shot_grid_error(404, 'SG_TARGET_NOT_FOUND', '目标不存在、已删除或不属于当前项目')
        for row in targets:
            if row.lifecycle_status != 'active':
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '目标已归档')
            if row.lock_version != expected[getattr(row, f'{kind}_id')]:
                raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '目标已被修改，请刷新后重试')

        purges = []
        for target in targets:
            target_id = getattr(target, f'{kind}_id')
            graph = await ShotGridTargetPurgeGraphDao.lock_target_graph(db, project_id, kind, target_id)
            await ShotGridTargetPurgeGraphDao.assert_targets_quiescent(db, graph)
            paths = await ShotGridTargetPurgeManifestDao.prepare_paths(db, graph)
            reserved = set(paths)
            if kind == 'shot':
                episode = await db.get(ShotGridEpisode, target.episode_id)
                scene = await db.get(ShotGridScene, target.scene_id)
                reserved.add(f'VIDEO/{episode.storage_dir_name}/{scene.scene_no:03d}_{target.shot_no:04d}')
            if kind == 'asset':
                reserved.add(f'ASSET/{target.asset_type}/{target.asset_name_key}')
            await ShotGridTargetPurgeDao.assert_paths_available(db, project_id, list(reserved))
            files = await ShotGridTargetPurgeManifestDao.prepare_files(db, graph, actor, now)
            purge = ShotGridTargetPurge(
                project_id=project_id,
                target_kind=kind,
                target_id=target_id,
                target_label=target.asset_name if kind == 'asset' else str(target.shot_no),
                root_path_snapshot=context['root_path_snapshot'],
                project_relative_path=context['project_relative_path'],
                project_path_snapshot=context['project_path_snapshot'],
                nas_manifest=paths,
                file_manifest=files,
                purge_status='pending',
                attempt_count=0,
                requested_by_user_id=actor_id,
                requested_by=actor,
                reason=reason,
                create_time=now,
                update_time=now,
            )
            db.add(purge)
            await db.flush()
            for path in {normalize_target_path(path) for path in reserved}:
                db.add(ShotGridTargetPurgePath(purge_id=purge.purge_id, project_id=project_id, path_key=path))
            await ShotGridTargetPurgeGraphDao.delete_target_graph(db, graph)
            purges.append(
                {
                    'purgeId': purge.purge_id,
                    'targetKind': kind,
                    'targetId': target_id,
                    'targetLabel': purge.target_label,
                    'purgeStatus': 'pending',
                    'canRetry': False,
                }
            )
        await db.flush()
        return {'targetIds': sorted(expected), 'purges': purges}

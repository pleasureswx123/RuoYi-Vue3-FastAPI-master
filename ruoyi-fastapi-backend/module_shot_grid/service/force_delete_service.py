"""独立强制删除事务，保留普通删除规则。"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.force_delete_dao import ShotGridForceDeleteDao
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.target_purge_dao import ShotGridTargetPurgeDao
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.asset_crud_vo import (
    ShotGridAssetBatchDeleteResultModel,
    ShotGridAssetBatchForceDeleteModel,
)
from module_shot_grid.entity.vo.shot_crud_vo import (
    ShotGridShotBatchDeleteResultModel,
    ShotGridShotBatchForceDeleteModel,
)
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.shot_crud_service import ShotGridShotCrudService


class ShotGridForceDeleteService:
    @classmethod
    async def batch_delete_shots(
        cls,
        db: AsyncSession,
        project_id: int,
        command: ShotGridShotBatchForceDeleteModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridShotBatchDeleteResultModel:
        result = await cls._delete(db, project_id, 'shot', command, current_user, access)
        return ShotGridShotBatchDeleteResultModel(
            deletedShotIds=result['targetIds'], deletedCount=len(result['targetIds']), purges=result['purges']
        )

    @classmethod
    async def batch_delete_assets(
        cls,
        db: AsyncSession,
        project_id: int,
        command: ShotGridAssetBatchForceDeleteModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridAssetBatchDeleteResultModel:
        result = await cls._delete(db, project_id, 'asset', command, current_user, access)
        return ShotGridAssetBatchDeleteResultModel(
            deletedAssetIds=result['targetIds'], deletedCount=len(result['targetIds']), purges=result['purges']
        )

    @staticmethod
    async def _delete(
        db: AsyncSession,
        project_id: int,
        kind: str,
        command: ShotGridShotBatchForceDeleteModel | ShotGridAssetBatchForceDeleteModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> dict[str, Any]:
        rules = ShotGridShotCrudService
        try:
            actor_id, actor_name, dept_name = rules._actor(current_user)
            if not rules._has_permission(current_user, f'shotgrid:{kind}:forceDelete'):
                raise shot_grid_error(403, 'SG_PERMISSION_DENIED', '缺少对应的强制删除权限')
            rules._require_write_access(access, project_id, actor_id)
            await rules._lock_writable_project(db, project_id, require_storage_ready=False)
            locked_access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
            rules._require_write_access(locked_access, project_id, actor_id)
            await ShotGridTargetPurgeDao.require_schema(db)
            result = await ShotGridForceDeleteDao.delete_targets_permanently(
                db, project_id, kind, command.items, actor_name, actor_id, command.reason, rules._now()
            )
            await ShotGridProjectAuditDao.add_success_log(
                db,
                title='Shot Grid 强制删除',
                business_type=3,
                method=f'ShotGridForceDeleteService.batch_delete_{kind}s()',
                request_method='POST',
                oper_name=actor_name,
                dept_name=dept_name,
                oper_url=f'/shot-grid/projects/{project_id}/{kind}s/batch-force-delete',
                oper_param={'projectId': project_id, **command.model_dump(by_alias=True)},
                result=result,
            )
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise

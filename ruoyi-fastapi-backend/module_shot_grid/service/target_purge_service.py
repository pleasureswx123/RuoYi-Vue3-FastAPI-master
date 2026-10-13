"""永久清理状态查询和受控重试。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.target_purge_dao import ShotGridTargetPurgeDao
from module_shot_grid.entity.do.project_do import ShotGridProject
from module_shot_grid.entity.do.target_purge_do import ShotGridTargetPurge
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.target_purge_vo import ShotGridTargetPurgeQueryModel, ShotGridTargetPurgeStatusModel
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.shot_crud_service import ShotGridShotCrudService


class ShotGridTargetPurgeService:
    @staticmethod
    def authorize(project_id: int, kind: str, user: CurrentUserModel, access: ShotGridProjectAccessModel) -> None:
        rules = ShotGridShotCrudService
        if not rules._has_permission(user, f'shotgrid:{kind}:forceDelete'):
            raise shot_grid_error(403, 'SG_PERMISSION_DENIED', '缺少对应强制删除权限')
        actor_id, _, _ = rules._actor(user)
        rules._require_write_access(access, project_id, actor_id)

    @staticmethod
    def status(row: ShotGridTargetPurge) -> ShotGridTargetPurgeStatusModel:
        result = ShotGridTargetPurgeStatusModel.model_validate(row)
        result.can_retry = row.purge_status in {'failed', 'retry_wait'}
        if row.purge_status == 'processing' and row.lease_until and row.lease_until <= datetime.now():
            result.last_error_message = '清理执行中断，需管理员确认旧进程退出后恢复；原编号继续保留'
        return result

    @classmethod
    async def query(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridTargetPurgeQueryModel,
        user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> PageResponseModel:
        cls.authorize(project_id, query.target_kind, user, access)
        await ShotGridTargetPurgeDao.require_schema(db)
        rows, total = await ShotGridTargetPurgeDao.query_page(db, project_id, query)
        return PageResponseModel(
            rows=[cls.status(row) for row in rows],
            total=total,
            pageNum=query.page_num,
            pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def retry(
        cls,
        db: AsyncSession,
        project_id: int,
        purge_id: int,
        user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridTargetPurgeStatusModel:
        try:
            await db.scalar(select(ShotGridProject).where(ShotGridProject.project_id == project_id).with_for_update())
            access = await ShotGridProjectAccessService.resolve_access(db, user, project_id)
            row = await db.scalar(
                select(ShotGridTargetPurge)
                .where(ShotGridTargetPurge.project_id == project_id, ShotGridTargetPurge.purge_id == purge_id)
                .with_for_update()
            )
            if row is None:
                raise shot_grid_error(404, 'SG_TARGET_PURGE_NOT_FOUND', '清理记录不存在')
            cls.authorize(project_id, row.target_kind, user, access)
            if row.purge_status not in {'failed', 'retry_wait'}:
                raise shot_grid_error(409, 'SG_TARGET_PURGE_NOT_RETRYABLE', '当前状态不能重试，请刷新清理状态')
            row.purge_status = 'pending'
            row.attempt_count = 0
            row.next_retry_time = None
            row.last_error_key = None
            row.last_error_message = None
            row.update_time = datetime.now()
            _, actor_name, dept_name = ShotGridShotCrudService._actor(user)
            await ShotGridProjectAuditDao.add_success_log(
                db,
                title='Shot Grid 永久清理重试',
                business_type=2,
                method='ShotGridTargetPurgeService.retry()',
                request_method='POST',
                oper_name=actor_name,
                dept_name=dept_name,
                oper_url=f'/shot-grid/projects/{project_id}/target-purges/{purge_id}/retry',
                oper_param={'projectId': project_id, 'purgeId': purge_id},
                result={'purgeStatus': 'pending'},
            )
            await db.commit()
            return cls.status(row)
        except Exception:
            await db.rollback()
            raise

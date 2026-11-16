"""真实 PostgreSQL 验证镜头分配即制作；测试记录在外层事务回滚。"""

import os

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from config.database import async_engine
from config.env import DataBaseConfig
from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.dao.storage_operation_dao import ShotGridStorageOperationDao
from module_shot_grid.entity.do.project_do import ShotGridShot
from module_shot_grid.entity.do.storage_do import ShotGridStorageOperation
from module_shot_grid.entity.vo.task_vo import ShotGridTaskAssignModel
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.task_service import ShotGridTaskService
from module_shot_grid.service.version_submission_service import ShotGridVersionSubmissionService

pytestmark = pytest.mark.skipif(
    os.getenv('SHOT_GRID_LOCAL_AUTO_START_TEST') != '1', reason='需显式启用本地 PostgreSQL 验证'
)
LOCAL_PORT = 15432


@pytest.mark.asyncio
async def test_assignment_without_content_or_schedule_prepares_directory_and_allows_submission() -> None:
    assert DataBaseConfig.db_host == '127.0.0.1' and DataBaseConfig.db_port == LOCAL_PORT
    async_engine.echo = False
    async with async_engine.connect() as connection:
        outer = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode='create_savepoint'
            ) as db:
                source = (
                    (
                        await db.execute(
                            text(
                                "SELECT s.project_id,s.episode_id,s.scene_id FROM sg_shot s JOIN sg_project p USING(project_id) WHERE p.project_code='LOCALDEMO' LIMIT 1"
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                number = await db.scalar(
                    select(ShotGridShot.shot_no)
                    .where(ShotGridShot.scene_id == source['scene_id'])
                    .order_by(ShotGridShot.shot_no.desc())
                    .limit(1)
                )
                shot = ShotGridShot(
                    **dict(source), shot_no=number + 1, description='', duration_ms=0, sort_order=(number + 1) * 10
                )
                db.add(shot)
                await db.flush()
                shot_id = shot.shot_id
                await db.commit()
                user = CurrentUserModel(
                    user=UserInfoModel(userId=1, userName='admin', nickName='事务验证', admin=True),
                    roles=[],
                    permissions=['*:*:*'],
                )
                access = await ShotGridProjectAccessService.resolve_access(db, user, source['project_id'])
                task = await ShotGridTaskService.assign_shot(
                    db, source['project_id'], shot_id, ShotGridTaskAssignModel(assigneeUserId=1), user, access
                )
                assert task.task_status == 'preparing'
                assert task.expected_start_time is None and task.expected_end_time is None
                assert 'task.start' not in task.allowed_actions
                operation = (
                    await db.execute(
                        select(ShotGridStorageOperation).where(
                            ShotGridStorageOperation.aggregate_type == 'shot',
                            ShotGridStorageOperation.aggregate_id == shot_id,
                        )
                    )
                ).scalar_one()
                assert operation.operation_status == 'pending'
                # 在事务内应用 Worker 的同一状态回写语句；不执行真实 NAS I/O。
                operation.operation_status = 'succeeded'
                operation.attempt_count = 1
                operation.started_time = operation.completed_time = ShotGridTaskService._now()
                await db.execute(
                    ShotGridStorageOperationDao._advance_preparing_tasks_statement(
                        operation, ShotGridTaskService._now()
                    )
                )
                await db.flush()
                await db.commit()
                context = await ShotGridVersionSubmissionService._require_task_context(db, task.task_id)
                ShotGridVersionSubmissionService._require_context_ready(context)
                ready = await ShotGridTaskService.get_task_detail(db, task.task_id, user)
                assert ready.task_status == 'in_progress' and 'version.add' in ready.allowed_actions
        finally:
            await outer.rollback()
    await async_engine.dispose()

"""显式迁移指定项目的历史待开工任务；默认预览，先备份再加 --apply。"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from config.database import AsyncSessionLocal, async_engine
from module_admin.entity.do.user_do import SysUser
from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.vo.task_vo import ShotGridTaskAssignModel
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.task_service import ShotGridTaskService


async def activate(project_id: int, *, apply: bool, target_kind: str = 'shot') -> None:
    async_engine.echo = False
    async with AsyncSessionLocal() as db:
        # 服务器维护命令仅以系统管理员身份记录，不能由普通业务用户调用。
        account = await db.get(SysUser, 1)
        if account is None or account.status != '0' or account.del_flag != '0':
            raise RuntimeError('系统管理员不可用，停止维护')
        user = CurrentUserModel(
            user=UserInfoModel(
                userId=account.user_id,
                userName=account.user_name,
                nickName=account.nick_name,
                deptId=account.dept_id,
                admin=True,
            ),
            roles=[],
            permissions=['*:*:*'],
        )
        access = await ShotGridProjectAccessService.resolve_access(db, user, project_id)
        rows = (
            (
                await db.execute(
                    select(ShotGridTask)
                    .where(
                        ShotGridTask.project_id == project_id,
                        ShotGridTask.task_kind == ('asset_image' if target_kind == 'asset' else 'shot_video'),
                        ShotGridTask.task_status == 'not_started',
                        ShotGridTask.del_flag == '0',
                    )
                    .order_by(ShotGridTask.task_id)
                )
            )
            .scalars()
            .all()
        )
        snapshots = [
            (
                row.task_id,
                row.asset_item_id if target_kind == 'asset' else row.shot_id,
                row.assignee_user_id,
                row.lock_version,
            )
            for row in rows
        ]
        await db.rollback()
        print(f'项目 {project_id}，类型 {target_kind}，待转换任务 {len(snapshots)}，apply={apply}')
        for task_id, target_id, assignee, version in snapshots:
            print(f'taskId={task_id}, targetId={target_id}, assigneeUserId={assignee}, lockVersion={version}')
            if apply:
                # 复用原分配服务的项目锁、活动成员/存储复核、乐观锁、Outbox 与审计。
                # 每项独立事务；失败即停止，重跑只处理尚未转换的记录。
                assign = (
                    ShotGridTaskService.assign_asset_item if target_kind == 'asset' else ShotGridTaskService.assign_shot
                )
                result = await assign(
                    db,
                    project_id,
                    target_id,
                    ShotGridTaskAssignModel(assigneeUserId=assignee, taskLockVersion=version),
                    user,
                    access,
                )
                print(f'已转换 taskId={task_id}, taskStatus={result.task_status}')
    await async_engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-id', type=int, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--target-kind', choices=['shot', 'asset'], default='shot')
    args = parser.parse_args()
    asyncio.run(activate(args.project_id, apply=args.apply, target_kind=args.target_kind))

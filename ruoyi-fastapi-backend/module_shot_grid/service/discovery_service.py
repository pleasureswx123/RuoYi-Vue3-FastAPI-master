# ruff: noqa: ANN001, ANN202, ANN205
from sqlalchemy import select

from module_shot_grid.dao.discovery_dao import ShotGridDiscoveryDao
from module_shot_grid.entity.do.project_do import ShotGridProjectMember


class ShotGridDiscoveryService:
    @staticmethod
    async def search(db, query, user_id):
        rows, total = await ShotGridDiscoveryDao.search(db, query, user_id)
        return [dict(row) for row in rows], total

    @staticmethod
    async def files(db, query, user_id, *, has_all_scope=False):
        rows, total = await ShotGridDiscoveryDao.files(db, query, user_id)
        result = []
        for relation, version, task, project, file_info in rows:
            # 内部 NAS 相对路径只向管理员或该项目总监返回，绝不依赖前端隐藏。
            role = await db.execute(
                select(ShotGridProjectMember.project_role).where(
                    ShotGridProjectMember.project_id == project.project_id,
                    ShotGridProjectMember.user_id == user_id,
                    ShotGridProjectMember.member_status == 'active',
                )
            )
            can_view_path = has_all_scope or role.scalar_one_or_none() == 'director'
            result.append(
                {
                    'fileId': relation.file_id,
                    'businessFileName': relation.business_file_name,
                    'fileRole': relation.file_role,
                    'fileSize': file_info.file_size,
                    'versionId': version.version_id,
                    'versionNo': version.version_no,
                    'taskId': task.task_id,
                    'taskName': task.task_name,
                    'projectId': project.project_id,
                    'projectName': project.project_name,
                    'nasStatus': 'published' if relation.published_time else 'unpublished',
                    'nasPath': relation.nas_relative_path if can_view_path else None,
                    'canViewNasPath': can_view_path,
                    'downloadUrl': f'/shot-grid/projects/{project.project_id}/tasks/{task.task_id}/versions/{version.version_id}/files/{relation.file_id}/download',
                }
            )
        return result, total

    @staticmethod
    async def workbench(db, user_id, limit):
        mine, pending, revisions, recent, summary = await ShotGridDiscoveryDao.workbench(db, user_id, limit)

        def task(pair):
            return {
                'taskId': pair[0].task_id,
                'projectId': pair[0].project_id,
                'projectName': pair[1],
                'taskName': pair[0].task_name,
                'taskKind': pair[0].task_kind,
                'taskStatus': pair[0].task_status,
                'dueDate': pair[0].due_date,
            }

        return {
            'myTasks': [task(row) for row in mine],
            'pendingReviews': [task(row) for row in pending],
            'revisions': [task(row) for row in revisions],
            'recentSubmissions': [
                {
                    'versionId': v.version_id,
                    'versionNo': v.version_no,
                    'versionStatus': v.version_status,
                    'submittedTime': v.submitted_time,
                    'taskId': v.task_id,
                    'taskName': name,
                    'projectId': v.project_id,
                    'projectName': project,
                }
                for v, name, project in recent
            ],
            'projectSummaries': [
                {
                    'projectId': p.project_id,
                    'projectName': p.project_name,
                    'projectStatus': p.project_status,
                    'taskCount': count,
                }
                for p, count in [(row[0], row[3]) for row in summary]
            ],
        }

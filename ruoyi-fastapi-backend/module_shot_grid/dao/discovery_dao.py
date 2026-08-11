# ruff: noqa: ANN001, ANN202, ANN205, ANN206
from sqlalchemy import String, and_, cast, func, literal, or_, select, union_all

from module_admin.entity.do.file_do import SysFileInfo
from module_shot_grid.entity.do.asset_do import ShotGridAsset
from module_shot_grid.entity.do.project_do import ShotGridProject, ShotGridProjectMember, ShotGridShot
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion, ShotGridVersionFile


def _member_projects(user_id: int):
    return select(ShotGridProjectMember.project_id).where(
        ShotGridProjectMember.user_id == user_id,
        ShotGridProjectMember.member_status == 'active',
    )


class ShotGridDiscoveryDao:
    """所有发现查询都在 SQL 中应用项目成员范围，禁止先取全表再过滤。"""

    SORTS = {'updatedTime': 'updated_time', 'name': 'title', 'type': 'resource_type'}

    @classmethod
    def _search_union(cls, user_id: int, resource_type: str, keyword: str | None, project_id: int | None):
        member_projects = _member_projects(user_id)

        def common(model):
            return [model.project_id.in_(member_projects), *([model.project_id == project_id] if project_id else [])]

        queries = []
        if resource_type in {'all', 'shot'}:
            conditions = [*common(ShotGridShot), ShotGridShot.del_flag == '0']
            if keyword:
                conditions.append(
                    or_(
                        ShotGridShot.description.ilike(f'%{keyword}%'),
                        cast(ShotGridShot.shot_no, String).ilike(f'%{keyword}%'),
                    )
                )
            queries.append(
                select(
                    literal('shot').label('resource_type'),
                    cast(ShotGridShot.shot_id, String).label('resource_id'),
                    ShotGridShot.project_id,
                    ShotGridShot.description.label('title'),
                    literal(None, String).label('subtitle'),
                    ShotGridShot.update_time.label('updated_time'),
                ).where(*conditions)
            )
        if resource_type in {'all', 'asset'}:
            conditions = [*common(ShotGridAsset), ShotGridAsset.del_flag == '0']
            if keyword:
                conditions.append(
                    or_(ShotGridAsset.asset_name.ilike(f'%{keyword}%'), ShotGridAsset.asset_code.ilike(f'%{keyword}%'))
                )
            queries.append(
                select(
                    literal('asset'),
                    cast(ShotGridAsset.asset_id, String),
                    ShotGridAsset.project_id,
                    ShotGridAsset.asset_name,
                    ShotGridAsset.asset_code,
                    ShotGridAsset.update_time,
                ).where(*conditions)
            )
        if resource_type in {'all', 'task'}:
            conditions = [*common(ShotGridTask), ShotGridTask.del_flag == '0']
            if keyword:
                conditions.append(ShotGridTask.task_name.ilike(f'%{keyword}%'))
            queries.append(
                select(
                    literal('task'),
                    cast(ShotGridTask.task_id, String),
                    ShotGridTask.project_id,
                    ShotGridTask.task_name,
                    ShotGridTask.task_status,
                    ShotGridTask.update_time,
                ).where(*conditions)
            )
        if resource_type in {'all', 'version'}:
            conditions = common(ShotGridVersion)
            if keyword:
                conditions.append(
                    or_(
                        ShotGridVersion.changelog.ilike(f'%{keyword}%'),
                        cast(ShotGridVersion.version_no, String).ilike(f'%{keyword}%'),
                    )
                )
            queries.append(
                select(
                    literal('version'),
                    cast(ShotGridVersion.version_id, String),
                    ShotGridVersion.project_id,
                    (literal('V') + cast(ShotGridVersion.version_no, String)),
                    ShotGridVersion.changelog,
                    ShotGridVersion.submitted_time,
                ).where(*conditions)
            )
        if resource_type in {'all', 'file'}:
            conditions = [
                ShotGridVersion.project_id.in_(member_projects),
                SysFileInfo.status == 'active',
                SysFileInfo.del_flag == '0',
            ]
            if project_id:
                conditions.append(ShotGridVersion.project_id == project_id)
            if keyword:
                conditions.append(ShotGridVersionFile.business_file_name.ilike(f'%{keyword}%'))
            queries.append(
                select(
                    literal('file'),
                    ShotGridVersionFile.file_id,
                    ShotGridVersion.project_id,
                    ShotGridVersionFile.business_file_name,
                    ShotGridVersionFile.file_role,
                    ShotGridVersion.submitted_time,
                )
                .join(ShotGridVersion, ShotGridVersion.version_id == ShotGridVersionFile.version_id)
                .join(SysFileInfo, SysFileInfo.file_id == ShotGridVersionFile.file_id)
                .where(*conditions)
            )
        return union_all(*queries).subquery('discovery')

    @classmethod
    async def search(cls, db, query, user_id: int):
        union = cls._search_union(user_id, query.resource_type, query.keyword, query.project_id)
        total = int((await db.execute(select(func.count()).select_from(union))).scalar_one())
        column = getattr(union.c, cls.SORTS.get(query.order_by_column, 'updated_time'))
        ordering = column.asc() if query.is_asc == 'ascending' else column.desc()
        rows = (
            (
                await db.execute(
                    select(union)
                    .order_by(ordering, union.c.resource_type, union.c.resource_id.desc())
                    .offset((query.page_num - 1) * query.page_size)
                    .limit(query.page_size)
                )
            )
            .mappings()
            .all()
        )
        return list(rows), total

    @staticmethod
    async def files(db, query, user_id: int):
        member_projects = _member_projects(user_id)
        conditions = [
            ShotGridVersion.project_id.in_(member_projects),
            SysFileInfo.status == 'active',
            SysFileInfo.del_flag == '0',
        ]
        if query.project_id:
            conditions.append(ShotGridVersion.project_id == query.project_id)
        if query.keyword:
            conditions.append(
                or_(
                    ShotGridVersionFile.business_file_name.ilike(f'%{query.keyword}%'),
                    ShotGridTask.task_name.ilike(f'%{query.keyword}%'),
                    ShotGridProject.project_name.ilike(f'%{query.keyword}%'),
                )
            )
        base = (
            select(ShotGridVersionFile, ShotGridVersion, ShotGridTask, ShotGridProject, SysFileInfo)
            .join(ShotGridVersion, ShotGridVersion.version_id == ShotGridVersionFile.version_id)
            .join(
                ShotGridTask,
                and_(
                    ShotGridTask.task_id == ShotGridVersion.task_id,
                    ShotGridTask.project_id == ShotGridVersion.project_id,
                ),
            )
            .join(ShotGridProject, ShotGridProject.project_id == ShotGridVersion.project_id)
            .join(SysFileInfo, SysFileInfo.file_id == ShotGridVersionFile.file_id)
            .where(*conditions)
        )
        total = int((await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
        rows = (
            await db.execute(
                base.order_by(ShotGridVersion.submitted_time.desc(), ShotGridVersionFile.file_id)
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return list(rows), total

    @staticmethod
    async def workbench(db, user_id: int, limit: int):
        projects = _member_projects(user_id)
        task_conditions = [ShotGridTask.project_id.in_(projects), ShotGridTask.del_flag == '0']
        mine = (
            await db.execute(
                select(ShotGridTask, ShotGridProject.project_name)
                .join(ShotGridProject, ShotGridProject.project_id == ShotGridTask.project_id)
                .where(
                    *task_conditions, ShotGridTask.assignee_user_id == user_id, ShotGridTask.task_status != 'completed'
                )
                .order_by(ShotGridTask.due_date.asc().nullslast(), ShotGridTask.task_id.desc())
                .limit(limit)
            )
        ).all()
        roles = dict(
            (
                await db.execute(
                    select(ShotGridProjectMember.project_id, ShotGridProjectMember.project_role).where(
                        ShotGridProjectMember.user_id == user_id, ShotGridProjectMember.member_status == 'active'
                    )
                )
            ).all()
        )
        director_ids = [pid for pid, role in roles.items() if role == 'director']
        pending = []
        if director_ids:
            pending = (
                await db.execute(
                    select(ShotGridTask, ShotGridProject.project_name)
                    .join(ShotGridProject, ShotGridProject.project_id == ShotGridTask.project_id)
                    .where(
                        ShotGridTask.project_id.in_(director_ids),
                        ShotGridTask.del_flag == '0',
                        ShotGridTask.task_status == 'pending_review',
                    )
                    .order_by(ShotGridTask.update_time.desc(), ShotGridTask.task_id.desc())
                    .limit(limit)
                )
            ).all()
        revisions = (
            await db.execute(
                select(ShotGridTask, ShotGridProject.project_name)
                .join(ShotGridProject, ShotGridProject.project_id == ShotGridTask.project_id)
                .where(
                    *task_conditions, ShotGridTask.assignee_user_id == user_id, ShotGridTask.task_status == 'revision'
                )
                .order_by(ShotGridTask.update_time.desc())
                .limit(limit)
            )
        ).all()
        recent = (
            await db.execute(
                select(ShotGridVersion, ShotGridTask.task_name, ShotGridProject.project_name)
                .join(ShotGridTask, ShotGridTask.task_id == ShotGridVersion.task_id)
                .join(ShotGridProject, ShotGridProject.project_id == ShotGridVersion.project_id)
                .where(ShotGridVersion.project_id.in_(projects), ShotGridVersion.submitted_by == user_id)
                .order_by(ShotGridVersion.submitted_time.desc(), ShotGridVersion.version_id.desc())
                .limit(limit)
            )
        ).all()
        summary = (
            await db.execute(
                select(
                    ShotGridProject.project_id,
                    ShotGridProject.project_name,
                    ShotGridProject.project_status,
                    func.count(ShotGridTask.task_id).label('task_count'),
                )
                .outerjoin(
                    ShotGridTask,
                    and_(ShotGridTask.project_id == ShotGridProject.project_id, ShotGridTask.del_flag == '0'),
                )
                .where(ShotGridProject.project_id.in_(projects), ShotGridProject.del_flag == '0')
                .group_by(ShotGridProject.project_id)
                .order_by(ShotGridProject.project_name)
            )
        ).all()
        return mine, pending, revisions, recent, summary

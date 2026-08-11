# ruff: noqa: ANN001, ANN205, ANN206
import re
from datetime import datetime
from typing import NoReturn

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.dao.resource_dao import ShotGridResourceDao
from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridAssetItem
from module_shot_grid.entity.do.project_do import ShotGridEpisode, ShotGridScene, ShotGridShot
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error


class ShotGridResourceService:
    MODELS = {
        'episode': (ShotGridEpisode, ShotGridEpisode.episode_id),
        'scene': (ShotGridScene, ShotGridScene.scene_id),
        'shot': (ShotGridShot, ShotGridShot.shot_id),
        'asset': (ShotGridAsset, ShotGridAsset.asset_id),
        'assetItem': (ShotGridAssetItem, ShotGridAssetItem.asset_item_id),
    }

    @classmethod
    async def page(cls, db, kind, project_id, query, parents=None):
        model, _ = cls.MODELS[kind]
        rows, total = await ShotGridResourceDao.page(
            db,
            model,
            project_id,
            page_num=query.page_num,
            page_size=query.page_size,
            lifecycle_status=query.lifecycle_status,
            status=query.status,
            parents=parents,
        )
        return {'rows': [cls._dump_aggregate(kind, row) for row in rows], 'total': total}

    @classmethod
    async def detail(cls, db, kind, project_id, resource_id):
        model, pk = cls.MODELS[kind]
        row = await ShotGridResourceDao.get(db, model, pk, resource_id, project_id)
        if not row:
            raise shot_grid_error(404, 'SG_RESOURCE_NOT_FOUND', '资源不存在或不属于当前项目')
        return cls._dump(kind, row)

    @classmethod
    async def ensure_parent(cls, db, kind, project_id, resource_id) -> None:
        model, pk = cls.MODELS[kind]
        if not await ShotGridResourceDao.get(db, model, pk, resource_id, project_id):
            raise shot_grid_error(409, 'SG_RESOURCE_PROJECT_MISMATCH', '嵌套资源不属于同一项目')

    @classmethod
    async def create(cls, db: AsyncSession, kind: str, project_id: int, command, username: str):
        model, _ = cls.MODELS[kind]
        values = command.model_dump(exclude={'lock_version'})
        cls._discard_missing_parent(kind, values)
        await cls._validate_scope(db, kind, project_id, values)
        cls._derive_values(kind, values)
        row = model(project_id=project_id, lifecycle_status='active', create_by=username, update_by=username, **values)
        try:
            db.add(row)
            await db.flush()
            await db.commit()
            await db.refresh(row)
        except IntegrityError as exc:
            await db.rollback()
            raise cls._conflict(exc) from exc
        return cls._dump(kind, row)

    @classmethod
    async def update(cls, db: AsyncSession, kind: str, project_id: int, resource_id: int, command, username: str):
        model, pk = cls.MODELS[kind]
        values = command.model_dump(exclude={'lock_version'})
        cls._discard_missing_parent(kind, values)
        await cls._validate_scope(db, kind, project_id, values)
        cls._derive_values(kind, values)
        values.update(update_by=username, update_time=datetime.now())
        try:
            changed = await ShotGridResourceDao.optimistic_update(
                db, model, pk, resource_id, project_id, command.lock_version, values
            )
            if not changed:
                await cls._raise_missing_or_stale(db, model, pk, resource_id, project_id)
            await db.commit()
        except ShotGridDomainException:
            await db.rollback()
            raise
        except IntegrityError as exc:
            await db.rollback()
            raise cls._conflict(exc) from exc
        return await cls.detail(db, kind, project_id, resource_id)

    @classmethod
    async def archive(cls, db, kind, project_id, resource_id, lock_version, username):
        model, pk = cls.MODELS[kind]
        changed = await ShotGridResourceDao.optimistic_update(
            db,
            model,
            pk,
            resource_id,
            project_id,
            lock_version,
            {'lifecycle_status': 'archived', 'update_by': username, 'update_time': datetime.now(), 'del_flag': '0'},
        )
        if not changed:
            await cls._raise_missing_or_stale(db, model, pk, resource_id, project_id)
        await db.commit()
        return await cls.detail(db, kind, project_id, resource_id)

    @classmethod
    async def _validate_scope(cls, db, kind, project_id, values) -> None:
        checks = []
        if 'episode_id' in values:
            checks.append(('episode', values['episode_id']))
        if 'scene_id' in values:
            checks.append(('scene', values['scene_id']))
        if 'asset_id' in values:
            checks.append(('asset', values['asset_id']))
        for parent_kind, parent_id in checks:
            model, pk = cls.MODELS[parent_kind]
            if not await ShotGridResourceDao.get(db, model, pk, parent_id, project_id):
                raise shot_grid_error(409, 'SG_RESOURCE_PROJECT_MISMATCH', '嵌套资源不属于同一项目')
        if kind == 'shot':
            scene = await ShotGridResourceDao.get(
                db, ShotGridScene, ShotGridScene.scene_id, values['scene_id'], project_id
            )
            if scene and scene.episode_id != values['episode_id']:
                raise shot_grid_error(409, 'SG_RESOURCE_HIERARCHY_MISMATCH', '场次与集不匹配')

    @staticmethod
    def _derive_values(kind, values) -> None:
        if kind == 'episode':
            values['storage_dir_name'] = f'EP{values["episode_no"]:03d}'
        elif kind == 'shot':
            values['storage_dir_name'] = f'SH{values["shot_no"]:04d}'
        elif kind == 'asset':
            name = values['asset_name'].strip()
            key = name.casefold()
            values.update(
                asset_name=name,
                asset_name_key=key,
                storage_dir_name=name,
                storage_path_key=f'{values["asset_type"]}/{key}',
            )
        elif kind == 'assetItem':
            name = values.get('production_item')
            values['production_item_key'] = name.strip().casefold() if name else None

    @staticmethod
    def _discard_missing_parent(kind, values) -> None:
        parent_field = {'scene': 'episode_id', 'assetItem': 'asset_id'}.get(kind)
        if parent_field and values.get(parent_field) is None:
            values.pop(parent_field)

    @staticmethod
    async def _raise_missing_or_stale(db, model, pk, resource_id, project_id) -> NoReturn:
        row = await ShotGridResourceDao.get(db, model, pk, resource_id, project_id)
        if row:
            raise shot_grid_error(
                409,
                'SG_LOCK_VERSION_CONFLICT',
                '数据已被其他用户修改，请刷新后重试',
                details={'currentLockVersion': row.lock_version},
            )
        raise shot_grid_error(404, 'SG_RESOURCE_NOT_FOUND', '资源不存在或不属于当前项目')

    @staticmethod
    def _conflict(exc):
        name = getattr(getattr(exc, 'orig', None), 'diag', None)
        constraint = getattr(name, 'constraint_name', '') or ''
        key = (
            'SG_BUSINESS_KEY_CONFLICT'
            if re.search(r'(episode_no|scene_no|shot_no|asset_name|asset_item_name|storage_path)', constraint)
            else 'SG_RESOURCE_CONSTRAINT_CONFLICT'
        )
        return shot_grid_error(409, key, '业务键或资源约束冲突')

    @staticmethod
    def _dump(kind, row):
        data = {
            column.name: getattr(row, column.name)
            for column in row.__table__.columns
            if column.name
            not in {'project_id', 'lock_version', 'create_time', 'update_time', 'lifecycle_status', 'del_flag'}
        }
        pk = next(iter(row.__table__.primary_key.columns)).name
        data.pop(pk, None)
        return {
            'id': getattr(row, pk),
            'projectId': row.project_id,
            'lifecycleStatus': row.lifecycle_status,
            'lockVersion': row.lock_version,
            'createTime': row.create_time,
            'updateTime': row.update_time,
            'data': data,
        }

    @classmethod
    def _dump_aggregate(cls, kind, result):
        if kind not in {'shot', 'asset'}:
            return cls._dump(kind, result)
        row, aggregate_status, item_count = result
        payload = cls._dump(kind, row)
        payload['aggregateStatus'] = aggregate_status
        if kind == 'asset':
            payload['itemCount'] = int(item_count or 0)
        return payload

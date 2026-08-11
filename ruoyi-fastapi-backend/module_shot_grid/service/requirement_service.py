# ruff: noqa: ANN001, ANN205, ANN206
from datetime import datetime

from sqlalchemy import select

from module_shot_grid.dao.requirement_dao import ShotGridRequirementDao
from module_shot_grid.entity.do.asset_do import ShotGridAsset
from module_shot_grid.entity.do.project_do import ShotGridShot
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error


class ShotGridRequirementService:
    @classmethod
    async def page(cls, db, project_id, query):
        rows, total = await ShotGridRequirementDao.page(db, project_id, query)
        return {
            'rows': [cls._requirement(row, shot) for row, shot in rows],
            'total': total,
            'pageNum': query.page_num,
            'pageSize': query.page_size,
        }

    @classmethod
    async def candidates(cls, db, project_id, requirement_id, query):
        requirement = await cls._requirement_or_404(db, project_id, requirement_id)
        if requirement.resolution_status not in ('pending', 'conflict'):
            raise shot_grid_error(409, 'SG_REQUIREMENT_ALREADY_RESOLVED', '待匹配需求已被其他用户处理')
        rows, total = await ShotGridRequirementDao.candidates(db, requirement, query)
        return {
            'rows': [
                {
                    'assetId': row.asset_id,
                    'assetName': row.asset_name,
                    'assetType': row.asset_type,
                    'lockVersion': row.lock_version,
                }
                for row in rows
            ],
            'total': total,
            'pageNum': query.page_num,
            'pageSize': query.page_size,
        }

    @classmethod
    async def bind(cls, db, project_id, requirement_id, command, user_id, username):
        try:
            requirement = await cls._requirement_or_404(db, project_id, requirement_id)
            if requirement.resolution_status not in ('pending', 'conflict'):
                raise shot_grid_error(409, 'SG_REQUIREMENT_ALREADY_RESOLVED', '待匹配需求已被其他用户处理')
            shot = await db.scalar(
                select(ShotGridShot).where(
                    ShotGridShot.shot_id == requirement.shot_id,
                    ShotGridShot.project_id == project_id,
                    ShotGridShot.lifecycle_status == 'active',
                    ShotGridShot.del_flag == '0',
                )
            )
            asset = await db.scalar(
                select(ShotGridAsset).where(
                    ShotGridAsset.asset_id == command.asset_id,
                    ShotGridAsset.project_id == project_id,
                    ShotGridAsset.asset_type == requirement.asset_type,
                    ShotGridAsset.lifecycle_status == 'active',
                    ShotGridAsset.del_flag == '0',
                )
            )
            if not shot:
                raise shot_grid_error(409, 'SG_REQUIREMENT_SHOT_INVALID', '镜头已归档或失效')
            if not asset:
                raise shot_grid_error(
                    409, 'SG_REQUIREMENT_CANDIDATE_INVALID', '候选资产不属于当前项目、类型不符或已归档'
                )
            changed = await ShotGridRequirementDao.resolve(
                db,
                requirement_id,
                project_id,
                command.lock_version,
                {
                    'resolution_status': 'matched',
                    'asset_id': asset.asset_id,
                    'resolved_by': user_id,
                    'resolved_time': datetime.now(),
                    'resolution_reason': '人工绑定',
                    'update_by': username,
                    'update_time': datetime.now(),
                },
            )
            if not changed:
                raise shot_grid_error(409, 'SG_REQUIREMENT_VERSION_CONFLICT', '需求已变化，请刷新后重试')
            await ShotGridRequirementDao.add_link_if_missing(db, requirement, asset, username)
            await db.commit()
            return {
                'requirementId': requirement_id,
                'shotId': shot.shot_id,
                'assetId': asset.asset_id,
                'resolutionStatus': 'matched',
                'lockVersion': command.lock_version + 1,
            }
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def close(cls, db, project_id, requirement_id, command, user_id, username):
        try:
            await cls._requirement_or_404(db, project_id, requirement_id)
            changed = await ShotGridRequirementDao.resolve(
                db,
                requirement_id,
                project_id,
                command.lock_version,
                {
                    'resolution_status': 'ignored',
                    'asset_id': None,
                    'resolved_by': user_id,
                    'resolved_time': datetime.now(),
                    'resolution_reason': command.reason,
                    'update_by': username,
                    'update_time': datetime.now(),
                },
            )
            if not changed:
                raise shot_grid_error(409, 'SG_REQUIREMENT_VERSION_CONFLICT', '需求已被处理或版本已过期')
            await db.commit()
            return {
                'requirementId': requirement_id,
                'resolutionStatus': 'ignored',
                'lockVersion': command.lock_version + 1,
            }
        except ShotGridDomainException:
            await db.rollback()
            raise

    @staticmethod
    async def _requirement_or_404(db, project_id, requirement_id):
        row = await ShotGridRequirementDao.get(db, project_id, requirement_id)
        if not row:
            raise shot_grid_error(404, 'SG_REQUIREMENT_NOT_FOUND', '待匹配需求不存在')
        return row

    @staticmethod
    def _requirement(row, shot):
        return {
            'requirementId': row.requirement_id,
            'sourceSheet': row.source_sheet_name,
            'sourceRowNumber': row.source_row_no,
            'shotId': row.shot_id,
            'shotNo': shot.shot_no,
            'shotDescription': shot.description,
            'requirementName': row.raw_name,
            'assetType': row.asset_type,
            'resolutionStatus': row.resolution_status,
            'conflictReason': row.resolution_reason,
            'lockVersion': row.lock_version,
        }

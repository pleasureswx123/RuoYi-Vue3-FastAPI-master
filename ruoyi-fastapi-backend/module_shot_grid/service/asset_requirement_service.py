from collections import defaultdict
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import BusinessType
from common.vo import PageModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.asset_requirement_dao import ShotGridAssetRequirementDao
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.project_dao import ShotGridProjectDao
from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridShotAssetRequirement
from module_shot_grid.entity.vo.asset_requirement_vo import (
    ShotGridAssetRequirementActionResultModel,
    ShotGridAssetRequirementIgnoreModel,
    ShotGridAssetRequirementListQueryModel,
    ShotGridAssetRequirementModel,
    ShotGridAssetRequirementRematchResultModel,
    ShotGridAssetRequirementResolveModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.project_service import ShotGridProjectService

MAX_IDEMPOTENCY_KEY_LENGTH = 100


class ShotGridAssetRequirementService:
    """资产需求人工处理和项目级精确重新匹配。"""

    @classmethod
    async def get_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridAssetRequirementListQueryModel,
    ) -> PageModel[ShotGridAssetRequirementModel]:
        rows, total = await ShotGridAssetRequirementDao.get_page(db, project_id, query)
        return PageModel[ShotGridAssetRequirementModel](
            rows=[ShotGridAssetRequirementModel.model_validate(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def resolve(
        cls,
        db: AsyncSession,
        project_id: int,
        requirement_id: int,
        command: ShotGridAssetRequirementResolveModel,
        current_user: CurrentUserModel,
        idempotency_key: str | None,
    ) -> ShotGridAssetRequirementActionResultModel:
        user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        cls._require_idempotency_key(idempotency_key)
        try:
            await cls._lock_writable_project(db, project_id)
            requirement = await cls._require_requirement(db, project_id, requirement_id)
            if requirement.resolution_status == 'matched' and requirement.asset_id == command.asset_id:
                await db.rollback()
                return ShotGridAssetRequirementActionResultModel(
                    requirementId=requirement_id,
                    resolutionStatus='matched',
                    assetId=command.asset_id,
                    idempotentReplay=True,
                )
            cls._require_unresolved(requirement)
            asset = await ShotGridAssetRequirementDao.get_asset(db, project_id, command.asset_id)
            if asset is None:
                raise shot_grid_error(404, 'SG_ASSET_NOT_FOUND', '选择的正式资产不存在或不可见')
            if asset.asset_type != requirement.asset_type:
                raise shot_grid_error(409, 'SG_ASSET_REQUIREMENT_TYPE_MISMATCH', '选择资产的类型与需求类型不一致')

            now = datetime.now().replace(microsecond=0)
            await ShotGridAssetRequirementDao.ensure_relation(
                db,
                project_id=project_id,
                shot_id=requirement.shot_id,
                asset_id=asset.asset_id,
                actor_name=actor_name,
                now=now,
            )
            cls._mark_matched(requirement, asset, user_id, actor_name, now, command.reason)
            await db.flush()
            result = ShotGridAssetRequirementActionResultModel(
                requirementId=requirement_id,
                resolutionStatus='matched',
                assetId=asset.asset_id,
            )
            await cls._audit(
                db,
                actor_name,
                dept_name,
                'resolve',
                f'/shot-grid/projects/{project_id}/asset-requirements/{requirement_id}/resolve',
                {'projectId': project_id, 'requirementId': requirement_id, **command.model_dump(by_alias=True)},
                result.model_dump(by_alias=True),
            )
            await db.commit()
            return result
        except IntegrityError as exc:
            await db.rollback()
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '资产需求已被并发处理，请刷新后重试') from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def ignore(
        cls,
        db: AsyncSession,
        project_id: int,
        requirement_id: int,
        command: ShotGridAssetRequirementIgnoreModel,
        current_user: CurrentUserModel,
        idempotency_key: str | None,
    ) -> ShotGridAssetRequirementActionResultModel:
        user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        cls._require_idempotency_key(idempotency_key)
        try:
            await cls._lock_writable_project(db, project_id)
            requirement = await cls._require_requirement(db, project_id, requirement_id)
            if requirement.resolution_status == 'ignored' and requirement.resolution_reason == command.reason:
                await db.rollback()
                return ShotGridAssetRequirementActionResultModel(
                    requirementId=requirement_id,
                    resolutionStatus='ignored',
                    idempotentReplay=True,
                )
            cls._require_unresolved(requirement)
            now = datetime.now().replace(microsecond=0)
            requirement.resolution_status = 'ignored'
            requirement.asset_id = None
            requirement.resolved_by = user_id
            requirement.resolved_time = now
            requirement.resolution_reason = command.reason
            requirement.update_by = actor_name
            requirement.update_time = now
            await db.flush()
            result = ShotGridAssetRequirementActionResultModel(
                requirementId=requirement_id,
                resolutionStatus='ignored',
            )
            await cls._audit(
                db,
                actor_name,
                dept_name,
                'ignore',
                f'/shot-grid/projects/{project_id}/asset-requirements/{requirement_id}/ignore',
                {'projectId': project_id, 'requirementId': requirement_id, **command.model_dump(by_alias=True)},
                result.model_dump(by_alias=True),
            )
            await db.commit()
            return result
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def rematch(
        cls,
        db: AsyncSession,
        project_id: int,
        current_user: CurrentUserModel,
    ) -> ShotGridAssetRequirementRematchResultModel:
        _, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        try:
            await cls._lock_writable_project(db, project_id)
            requirements = await ShotGridAssetRequirementDao.get_unresolved(db, project_id)
            keys = sorted({(item.asset_type, item.normalized_name) for item in requirements})
            assets = await ShotGridAssetRequirementDao.get_candidate_assets(db, project_id, keys)
            candidates: dict[tuple[str, str], list[ShotGridAsset]] = defaultdict(list)
            for asset in assets:
                candidates[(asset.asset_type, asset.asset_name_key)].append(asset)

            now = datetime.now().replace(microsecond=0)
            matched_count = 0
            for requirement in requirements:
                matches = candidates[(requirement.asset_type, requirement.normalized_name)]
                if len(matches) == 1:
                    asset = matches[0]
                    await ShotGridAssetRequirementDao.ensure_relation(
                        db,
                        project_id=project_id,
                        shot_id=requirement.shot_id,
                        asset_id=asset.asset_id,
                        actor_name=actor_name,
                        now=now,
                    )
                    cls._mark_matched(
                        requirement,
                        asset,
                        None,
                        actor_name,
                        now,
                        '项目范围按类型和规范化名称重新匹配',
                    )
                    matched_count += 1
                elif len(matches) > 1:
                    requirement.resolution_status = 'conflict'
                    requirement.asset_id = None
                    requirement.resolved_by = None
                    requirement.resolved_time = None
                    requirement.resolution_reason = '存在多个同类型同名正式资产，请人工选择'
                    requirement.update_by = actor_name
                    requirement.update_time = now
                elif requirement.resolution_status == 'conflict':
                    requirement.resolution_status = 'pending'
                    requirement.resolution_reason = None
                    requirement.update_by = actor_name
                    requirement.update_time = now

            pending_count = sum(item.resolution_status == 'pending' for item in requirements)
            conflict_count = sum(item.resolution_status == 'conflict' for item in requirements)
            result = ShotGridAssetRequirementRematchResultModel(
                matchedCount=matched_count,
                pendingCount=pending_count,
                conflictCount=conflict_count,
            )
            await cls._audit(
                db,
                actor_name,
                dept_name,
                'rematch',
                f'/shot-grid/projects/{project_id}/asset-requirements/rematch',
                {'projectId': project_id},
                result.model_dump(by_alias=True),
            )
            await db.commit()
            return result
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def _lock_writable_project(db: AsyncSession, project_id: int) -> None:
        project = await ShotGridProjectDao.get_project_by_id(db, project_id, for_update=True)
        if project is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
        if project.project_status in {'completed', 'archived'}:
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '已完成或归档项目不允许处理资产需求')

    @staticmethod
    async def _require_requirement(
        db: AsyncSession,
        project_id: int,
        requirement_id: int,
    ) -> ShotGridShotAssetRequirement:
        requirement = await ShotGridAssetRequirementDao.get_requirement(
            db,
            project_id,
            requirement_id,
            for_update=True,
        )
        if requirement is None:
            raise shot_grid_error(404, 'SG_ASSET_REQUIREMENT_NOT_FOUND', '待匹配资产需求不存在或不可见')
        return requirement

    @staticmethod
    def _require_unresolved(requirement: ShotGridShotAssetRequirement) -> None:
        if requirement.resolution_status not in {'pending', 'conflict'}:
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '该资产需求已完成处理，请刷新后重试')

    @staticmethod
    def _mark_matched(
        requirement: ShotGridShotAssetRequirement,
        asset: ShotGridAsset,
        resolved_by: int | None,
        actor_name: str,
        now: datetime,
        reason: str,
    ) -> None:
        requirement.resolution_status = 'matched'
        requirement.asset_id = asset.asset_id
        requirement.resolved_by = resolved_by
        requirement.resolved_time = now
        requirement.resolution_reason = reason
        requirement.update_by = actor_name
        requirement.update_time = now

    @staticmethod
    def _require_idempotency_key(value: str | None) -> str:
        normalized = value.strip() if isinstance(value, str) else ''
        if not normalized or len(normalized) > MAX_IDEMPOTENCY_KEY_LENGTH:
            raise shot_grid_error(422, 'SG_IDEMPOTENCY_KEY_INVALID', 'X-Idempotency-Key 长度必须为 1—100 个字符')
        return normalized

    @staticmethod
    async def _audit(
        db: AsyncSession,
        actor_name: str,
        dept_name: str | None,
        action: str,
        url: str,
        payload: dict,
        result: dict,
    ) -> None:
        await ShotGridProjectAuditDao.add_success_log(
            db,
            title='Shot Grid 资产需求处理',
            business_type=BusinessType.UPDATE.value,
            method=(f'module_shot_grid.service.asset_requirement_service.ShotGridAssetRequirementService.{action}()'),
            request_method='POST',
            oper_name=actor_name,
            dept_name=dept_name,
            oper_url=url,
            oper_param=payload,
            result=result,
        )

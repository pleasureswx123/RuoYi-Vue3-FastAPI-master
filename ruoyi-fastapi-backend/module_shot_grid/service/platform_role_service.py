from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from module_shot_grid.dao.platform_role_dao import ShotGridPlatformRoleDao
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.entity.vo.project_option_vo import (
    ShotGridPlatformRoleOptionModel,
    ShotGridPlatformRoleReconcileResultModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from module_admin.entity.do.role_do import SysRole
    from module_admin.entity.vo.user_vo import CurrentUserModel
    from module_shot_grid.entity.vo.project_member_vo import ProjectRole

PlatformRoleKey = Literal['shotgrid_admin', 'shotgrid_creator']


@dataclass(frozen=True)
class ShotGridPlatformRoleDefinition:
    """已通过安全校验的项目角色与平台角色映射。"""

    project_role: ProjectRole
    role_id: int
    role_key: PlatformRoleKey
    role_name: str


class ShotGridPlatformRoleService:
    """维护 Shot Grid 项目成员所需的最小平台角色授权。"""

    ROLE_KEY_BY_PROJECT_ROLE: dict[ProjectRole, PlatformRoleKey] = {
        'director': 'shotgrid_admin',
        'creator': 'shotgrid_creator',
    }
    REQUIRED_ROLE_KEYS = ('shotgrid_admin', 'shotgrid_creator')
    REQUIRED_NAVIGATION_PERMISSION = 'shotgrid:navigation:list'
    BUSINESS_NAVIGATION_PERMISSIONS = {
        'shotgrid:project:overview',
        'shotgrid:project:list',
        'shotgrid:shot:list',
        'shotgrid:asset:list',
        'shotgrid:reviewList:list',
        'shotgrid:storage:path',
    }
    FORBIDDEN_PERMISSIONS = {'*:*:*', 'shotgrid:project:all'}
    STORAGE_ROOT_READ_PERMISSIONS = {'shotgrid:storageRoot:list', 'shotgrid:storageRoot:query'}
    PROJECT_ROLE_LABELS: dict[ProjectRole, str] = {
        'director': '项目管理人',
        'creator': '制作人员',
    }

    @classmethod
    async def get_role_options(cls, db: AsyncSession) -> list[ShotGridPlatformRoleOptionModel]:
        definitions = await cls.resolve_role_definitions(db)
        return [
            ShotGridPlatformRoleOptionModel(
                projectRole=project_role,
                projectRoleLabel=cls.PROJECT_ROLE_LABELS[project_role],
                systemRoleId=definitions[project_role].role_id,
                systemRoleKey=definitions[project_role].role_key,
                systemRoleName=definitions[project_role].role_name,
            )
            for project_role in ('director', 'creator')
        ]

    @classmethod
    async def resolve_role_definitions(
        cls,
        db: AsyncSession,
    ) -> dict[ProjectRole, ShotGridPlatformRoleDefinition]:
        """解析并验证专用角色；任何配置漂移都以稳定领域错误失败关闭。"""

        rows = await ShotGridPlatformRoleDao.list_roles_by_keys(db, cls.REQUIRED_ROLE_KEYS)
        rows_by_key: dict[str, list[SysRole]] = {role_key: [] for role_key in cls.REQUIRED_ROLE_KEYS}
        for role in rows:
            rows_by_key.setdefault(str(role.role_key), []).append(role)

        missing = [role_key for role_key in cls.REQUIRED_ROLE_KEYS if not rows_by_key[role_key]]
        if missing:
            raise shot_grid_error(
                503,
                'SG_PLATFORM_ROLE_MISSING',
                'Shot Grid 专用平台角色尚未配置',
                details={'roleKeys': missing},
            )

        duplicate = {role_key: len(role_rows) for role_key, role_rows in rows_by_key.items() if len(role_rows) != 1}
        if duplicate:
            raise shot_grid_error(
                503,
                'SG_PLATFORM_ROLE_DUPLICATE',
                'Shot Grid 专用平台角色配置不唯一',
                details={'roleCounts': duplicate},
            )

        role_by_key = {role_key: role_rows[0] for role_key, role_rows in rows_by_key.items()}
        unavailable = [role_key for role_key, role in role_by_key.items() if role.status != '0' or role.del_flag != '0']
        if unavailable:
            raise shot_grid_error(
                503,
                'SG_PLATFORM_ROLE_DISABLED',
                'Shot Grid 专用平台角色已停用或删除',
                details={'roleKeys': unavailable},
            )

        blank_name_keys = [
            role_key
            for role_key, role in role_by_key.items()
            if not isinstance(role.role_name, str) or not role.role_name.strip()
        ]
        if blank_name_keys:
            raise shot_grid_error(
                503,
                'SG_PLATFORM_ROLE_UNSAFE',
                'Shot Grid 专用平台角色名称不能为空',
                details={'roleKeys': blank_name_keys, 'violations': ['blank_role_name']},
            )

        super_admin_keys = [role_key for role_key, role in role_by_key.items() if int(role.role_id) == 1]
        if super_admin_keys:
            raise shot_grid_error(
                503,
                'SG_PLATFORM_ROLE_UNSAFE',
                'Shot Grid 专用角色不能复用平台超级管理员角色',
                details={'roleKeys': super_admin_keys, 'violations': ['super_admin_role']},
            )

        permissions_by_role_id = await cls._load_permissions_by_role_id(
            db,
            {int(role.role_id) for role in role_by_key.values()},
        )

        for role_key in cls.REQUIRED_ROLE_KEYS:
            role = role_by_key[role_key]
            cls._validate_permission_package(role_key, permissions_by_role_id[int(role.role_id)])

        return {
            project_role: ShotGridPlatformRoleDefinition(
                project_role=project_role,
                role_id=int(role_by_key[role_key].role_id),
                role_key=role_key,
                role_name=role_by_key[role_key].role_name.strip(),
            )
            for project_role, role_key in cls.ROLE_KEY_BY_PROJECT_ROLE.items()
        }

    @classmethod
    async def _load_permissions_by_role_id(
        cls,
        db: AsyncSession,
        role_ids: set[int],
    ) -> dict[int, list[tuple[str, str | None]]]:
        permissions = await ShotGridPlatformRoleDao.list_role_permissions(db, role_ids)
        permissions_by_role_id: dict[int, list[tuple[str, str | None]]] = {role_id: [] for role_id in role_ids}
        for permission in permissions:
            raw_code = permission['perms']
            if raw_code is not None and str(raw_code) != '':
                permissions_by_role_id[int(permission['role_id'])].append((str(raw_code), permission['menu_status']))
        return permissions_by_role_id

    @classmethod
    async def validate_platform_role_mutation(
        cls,
        db: AsyncSession,
        role_id: int,
        *,
        previous_role_key: str | None = None,
        deleting: bool = False,
    ) -> None:
        """在平台角色事务提交前保护专用角色键和启用状态下的权限包。"""

        role = await ShotGridPlatformRoleDao.get_role_by_id_including_deleted(db, role_id)
        current_role_key = str(role.role_key) if role is not None and role.role_key is not None else None
        was_reserved = previous_role_key in cls.REQUIRED_ROLE_KEYS
        is_reserved = current_role_key in cls.REQUIRED_ROLE_KEYS
        if not was_reserved and not is_reserved:
            return
        await ShotGridPlatformRoleDao.lock_role_configuration(db)

        if deleting:
            if was_reserved or is_reserved:
                raise cls._reserved_role_contract_error(
                    role_id,
                    previous_role_key or current_role_key,
                    'delete',
                )
            return

        if was_reserved and current_role_key != previous_role_key:
            raise cls._reserved_role_contract_error(role_id, previous_role_key, 'change_role_key')

        if role is None or not is_reserved:
            return
        # 停用是允许的紧急撤权动作；再次启用时必须重新通过完整安全校验。
        if role.status != '0' or role.del_flag != '0':
            return

        rows = await ShotGridPlatformRoleDao.list_roles_by_keys(db, (current_role_key,))
        if len(rows) != 1 or int(rows[0].role_id) != role_id:
            raise shot_grid_error(
                503,
                'SG_PLATFORM_ROLE_DUPLICATE',
                'Shot Grid 专用平台角色配置不唯一',
                details={'roleCounts': {current_role_key: len(rows)}},
            )
        if not isinstance(role.role_name, str) or not role.role_name.strip():
            raise shot_grid_error(
                503,
                'SG_PLATFORM_ROLE_UNSAFE',
                'Shot Grid 专用平台角色名称不能为空',
                details={'roleKeys': [current_role_key], 'violations': ['blank_role_name']},
            )
        if int(role.role_id) == 1:
            raise shot_grid_error(
                503,
                'SG_PLATFORM_ROLE_UNSAFE',
                'Shot Grid 专用角色不能复用平台超级管理员角色',
                details={'roleKeys': [current_role_key], 'violations': ['super_admin_role']},
            )
        permissions_by_role_id = await cls._load_permissions_by_role_id(db, {role_id})
        cls._validate_permission_package(current_role_key, permissions_by_role_id[role_id])

    @classmethod
    async def validate_menu_mutation(cls, db: AsyncSession, menu_id: int) -> None:
        """菜单权限码或状态变化后，重验受影响的启用专用角色。"""

        role_ids = await ShotGridPlatformRoleDao.list_dedicated_role_ids_for_menu(
            db,
            menu_id,
            cls.REQUIRED_ROLE_KEYS,
        )
        for role_id in role_ids:
            await cls.validate_platform_role_mutation(db, role_id)

    @classmethod
    async def ensure_user_role_replacement_safe(
        cls,
        db: AsyncSession,
        user_id: int,
        retained_role_ids: set[int],
    ) -> set[int]:
        """全量替换平台用户角色时保留活动成员所需和 Shot Grid 受管关系。"""

        protected_by_user = await cls._get_protected_role_ids_by_user(db, {user_id})
        protected_role_ids = protected_by_user[user_id]
        removed_role_ids = sorted(protected_role_ids - retained_role_ids)
        if removed_role_ids:
            raise cls._project_role_protected_error([user_id], removed_role_ids)
        existing = await ShotGridPlatformRoleDao.list_user_roles(db, {user_id}, protected_role_ids)
        return {role_id for existing_user_id, role_id in existing if existing_user_id == user_id}

    @classmethod
    async def ensure_user_role_deletion_safe(
        cls,
        db: AsyncSession,
        user_ids: set[int],
        role_id: int,
    ) -> None:
        protected_by_user = await cls._get_protected_role_ids_by_user(db, user_ids)
        blocked_user_ids = sorted(user_id for user_id in user_ids if role_id in protected_by_user[user_id])
        if blocked_user_ids:
            raise cls._project_role_protected_error(blocked_user_ids, [role_id])

    @classmethod
    async def _get_protected_role_ids_by_user(
        cls,
        db: AsyncSession,
        user_ids: set[int],
    ) -> dict[int, set[int]]:
        await cls.lock_target_users(db, user_ids)
        protected_by_user = {user_id: set() for user_id in user_ids}
        managed = await ShotGridPlatformRoleDao.list_managed_user_roles(db, user_ids)
        for user_id, role_id in managed:
            protected_by_user[user_id].add(role_id)

        active_memberships = await ShotGridPlatformRoleDao.list_active_membership_roles(db, user_ids)
        needed_project_roles = {project_role for _, project_role in active_memberships}
        if not needed_project_roles:
            return protected_by_user

        needed_role_keys = tuple(
            role_key
            for project_role, role_key in cls.ROLE_KEY_BY_PROJECT_ROLE.items()
            if project_role in needed_project_roles
        )
        rows = await ShotGridPlatformRoleDao.list_roles_by_keys(db, needed_role_keys)
        rows_by_key: dict[str, list[SysRole]] = {role_key: [] for role_key in needed_role_keys}
        for role in rows:
            rows_by_key.setdefault(str(role.role_key), []).append(role)
        missing = [role_key for role_key, role_rows in rows_by_key.items() if not role_rows]
        if missing:
            raise shot_grid_error(
                503,
                'SG_PLATFORM_ROLE_MISSING',
                'Shot Grid 专用平台角色尚未配置',
                details={'roleKeys': missing},
            )
        duplicate = {role_key: len(role_rows) for role_key, role_rows in rows_by_key.items() if len(role_rows) != 1}
        if duplicate:
            raise shot_grid_error(
                503,
                'SG_PLATFORM_ROLE_DUPLICATE',
                'Shot Grid 专用平台角色配置不唯一',
                details={'roleCounts': duplicate},
            )
        role_id_by_project_role = {
            project_role: int(rows_by_key[role_key][0].role_id)
            for project_role, role_key in cls.ROLE_KEY_BY_PROJECT_ROLE.items()
            if project_role in needed_project_roles
        }
        for user_id, project_role in active_memberships:
            if project_role in role_id_by_project_role:
                protected_by_user[user_id].add(role_id_by_project_role[project_role])
        return protected_by_user

    @classmethod
    async def ensure_user_deletion_safe(cls, db: AsyncSession, user_ids: set[int]) -> None:
        await cls.lock_target_users(db, user_ids)
        active_memberships = await ShotGridPlatformRoleDao.list_active_membership_roles(db, user_ids)
        active_user_ids = {user_id for user_id, _ in active_memberships}
        managed = await ShotGridPlatformRoleDao.list_managed_user_roles(db, user_ids)
        managed_user_ids = {user_id for user_id, _ in managed}
        blocked_user_ids = sorted(active_user_ids | managed_user_ids)
        if blocked_user_ids:
            raise shot_grid_error(
                409,
                'SG_ACTIVE_PROJECT_MEMBER_USER_PROTECTED',
                '用户仍有活动项目成员关系或 Shot Grid 受管授权，请先完成成员治理和角色对账',
                details={
                    'userIds': blocked_user_ids,
                    'activeMemberUserIds': sorted(active_user_ids),
                    'managedRoleUserIds': sorted(managed_user_ids),
                },
            )

    @staticmethod
    def _reserved_role_contract_error(
        role_id: int,
        role_key: str | None,
        operation: str,
    ) -> ShotGridDomainException:
        return shot_grid_error(
            409,
            'SG_PLATFORM_ROLE_CONTRACT_PROTECTED',
            'Shot Grid 专用平台角色键为固定契约，不能改键或删除',
            details={'roleId': role_id, 'roleKey': role_key, 'operation': operation},
        )

    @staticmethod
    def _project_role_protected_error(
        user_ids: list[int],
        role_ids: list[int],
    ) -> ShotGridDomainException:
        return shot_grid_error(
            409,
            'SG_PROJECT_ROLE_BINDING_PROTECTED',
            '活动项目成员所需或 Shot Grid 受管的平台角色必须通过项目成员管理修改',
            details={'userIds': user_ids, 'roleIds': role_ids},
        )

    @classmethod
    def _validate_permission_package(
        cls,
        role_key: str,
        permissions: list[tuple[str, str | None]],
    ) -> None:
        all_codes = {code for code, _ in permissions}
        active_codes = {code for code, menu_status in permissions if menu_status == '0'}
        violations: list[str] = []

        if any(code != code.strip() for code in all_codes):
            violations.append('permission_code_whitespace')
        if any(not code.startswith('shotgrid:') for code in all_codes):
            violations.append('non_shot_grid_permission')
        if all_codes.intersection(cls.FORBIDDEN_PERMISSIONS):
            violations.append('forbidden_global_permission')
        if any(
            code.startswith('shotgrid:storageRoot:') and code not in cls.STORAGE_ROOT_READ_PERMISSIONS
            for code in all_codes
        ):
            violations.append('storage_root_write_permission')
        if cls.REQUIRED_NAVIGATION_PERMISSION not in active_codes:
            violations.append('navigation_permission_missing_or_disabled')
        if not active_codes.intersection(cls.BUSINESS_NAVIGATION_PERMISSIONS):
            violations.append('business_navigation_permission_missing_or_disabled')

        if violations:
            raise shot_grid_error(
                503,
                'SG_PLATFORM_ROLE_UNSAFE',
                'Shot Grid 专用平台角色权限包不符合最小授权约束',
                details={'roleKey': role_key, 'violations': violations},
            )

    @classmethod
    async def lock_target_users(cls, db: AsyncSession, user_ids: set[int]) -> None:
        locked_users = await ShotGridPlatformRoleDao.lock_users(db, user_ids)
        locked_user_ids = {int(user.user_id) for user in locked_users}
        missing_user_ids = sorted(user_ids - locked_user_ids)
        if missing_user_ids:
            raise shot_grid_error(
                422,
                'SG_MEMBER_USER_INVALID',
                '项目成员账号不存在、已停用或已删除',
                details={'userIds': missing_user_ids},
            )

    @classmethod
    async def synchronize_user_roles(
        cls,
        db: AsyncSession,
        user_ids: set[int],
        actor_name: str,
    ) -> list[dict[str, object]]:
        """按活动成员关系增量授权，并只回收 Shot Grid 自己创建的关系。"""

        if not user_ids:
            return []
        await cls.lock_target_users(db, user_ids)
        definitions = await cls.resolve_role_definitions(db)
        role_ids = {definition.role_id for definition in definitions.values()}
        active_memberships = await ShotGridPlatformRoleDao.list_active_membership_roles(db, user_ids)
        required_project_roles: dict[int, set[str]] = {user_id: set() for user_id in user_ids}
        for user_id, project_role in active_memberships:
            required_project_roles.setdefault(user_id, set()).add(project_role)

        existing = await ShotGridPlatformRoleDao.list_user_roles(db, user_ids, role_ids)
        managed_role_keys = await ShotGridPlatformRoleDao.list_managed_user_roles(db, user_ids)
        managed = set(managed_role_keys)
        now = datetime.now()
        granted_by_user: dict[int, list[str]] = {user_id: [] for user_id in user_ids}
        revoked_by_user: dict[int, list[str]] = {user_id: [] for user_id in user_ids}
        required_preserved_by_user: dict[int, list[str]] = {user_id: [] for user_id in user_ids}
        external_preserved_by_user: dict[int, list[str]] = {user_id: [] for user_id in user_ids}

        # 先补齐全部必需授权，再回收不再需要的受管授权，避免角色切换期间先减后加。
        for user_id in sorted(user_ids):
            for project_role in ('director', 'creator'):
                definition = definitions[project_role]
                relation = (user_id, definition.role_id)
                is_required = project_role in required_project_roles.get(user_id, set())
                if not is_required:
                    continue
                if relation not in existing:
                    await ShotGridPlatformRoleDao.add_managed_user_role(
                        db,
                        user_id=user_id,
                        role_id=definition.role_id,
                        actor_name=actor_name,
                        create_time=now,
                    )
                    existing.add(relation)
                    managed.add(relation)
                    managed_role_keys[relation] = definition.role_key
                    granted_by_user[user_id].append(definition.role_key)
                else:
                    required_preserved_by_user[user_id].append(definition.role_key)

        for user_id in sorted(user_ids):
            required_role_ids = {
                definitions[project_role].role_id
                for project_role in required_project_roles.get(user_id, set())
                if project_role in definitions
            }
            stale_managed_relations = sorted(
                relation for relation in managed if relation[0] == user_id and relation[1] not in required_role_ids
            )
            for relation in stale_managed_relations:
                await ShotGridPlatformRoleDao.remove_managed_user_role(
                    db,
                    user_id=relation[0],
                    role_id=relation[1],
                )
                existing.discard(relation)
                managed.discard(relation)
                revoked_by_user[user_id].append(managed_role_keys[relation])

            for project_role in ('director', 'creator'):
                definition = definitions[project_role]
                relation = (user_id, definition.role_id)
                is_required = project_role in required_project_roles.get(user_id, set())
                if is_required:
                    continue
                if relation in existing:
                    external_preserved_by_user[user_id].append(definition.role_key)

        return [
            {
                'userId': user_id,
                'grantedRoleKeys': granted_by_user[user_id],
                'revokedRoleKeys': revoked_by_user[user_id],
                'requiredPreservedRoleKeys': required_preserved_by_user[user_id],
                'externalPreservedRoleKeys': external_preserved_by_user[user_id],
            }
            for user_id in sorted(user_ids)
        ]

    @classmethod
    async def reconcile_user_roles(
        cls,
        db: AsyncSession,
        current_user: CurrentUserModel,
    ) -> ShotGridPlatformRoleReconcileResultModel:
        """对全部活动成员和存量来源标记执行一次事务内授权对账。"""

        user = current_user.user
        if user is None or user.user_id is None or not user.user_name:
            raise shot_grid_error(401, 'SG_CURRENT_USER_INVALID', '无法识别当前用户')
        actor_name = user.user_name
        dept_name = user.dept.dept_name if user.dept is not None else None

        try:
            user_ids = set(await ShotGridPlatformRoleDao.list_reconciliation_user_ids(db))
            if user_ids:
                changes = await cls.synchronize_user_roles(db, user_ids, actor_name)
            else:
                # 即使当前没有待处理用户，也校验配置，避免把缺失权限包误报为对账成功。
                await cls.resolve_role_definitions(db)
                changes = []

            result = cls._build_reconcile_result(changes)
            result_payload = result.model_dump(by_alias=True)
            await ShotGridProjectAuditDao.add_success_log(
                db,
                title='Shot Grid 平台角色绑定对账',
                business_type=2,
                method=(
                    'module_shot_grid.service.platform_role_service.ShotGridPlatformRoleService.reconcile_user_roles()'
                ),
                request_method='POST',
                oper_name=actor_name,
                dept_name=dept_name,
                oper_url='/shot-grid/platform-role-bindings/reconcile',
                oper_param={'operatorUserId': int(user.user_id)},
                result=result_payload,
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
    def _build_reconcile_result(
        cls,
        changes: list[dict[str, object]],
    ) -> ShotGridPlatformRoleReconcileResultModel:
        def binding_count(field: str) -> int:
            return sum(len(change[field]) for change in changes if isinstance(change[field], list))

        return ShotGridPlatformRoleReconcileResultModel(
            processedUserCount=len(changes),
            changedUserCount=sum(bool(change['grantedRoleKeys'] or change['revokedRoleKeys']) for change in changes),
            grantedBindingCount=binding_count('grantedRoleKeys'),
            revokedBindingCount=binding_count('revokedRoleKeys'),
            requiredPreservedBindingCount=binding_count('requiredPreservedRoleKeys'),
            externalPreservedBindingCount=binding_count('externalPreservedRoleKeys'),
        )

import asyncio
import os
import secrets
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.storage_root_dao import ShotGridStorageRootDao
from module_shot_grid.entity.do.storage_do import ShotGridStorageRoot
from module_shot_grid.entity.vo.storage_root_vo import (
    ShotGridStorageRootCreateModel,
    ShotGridStorageRootModel,
    ShotGridStorageRootProbeModel,
    ShotGridStorageRootQueryModel,
    ShotGridStorageRootUpdateModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.project_path_service import ShotGridProjectPathService


@dataclass(frozen=True)
class _ProbeResult:
    status: str
    error_key: str | None = None
    error_message: str | None = None


class ShotGridStorageRootService:
    """平台管理员维护和探测 NAS 根目录。"""

    @classmethod
    async def get_page(
        cls,
        db: AsyncSession,
        query: ShotGridStorageRootQueryModel,
    ) -> PageModel[ShotGridStorageRootModel]:
        rows, total = await ShotGridStorageRootDao.get_page(db, query)
        return PageModel[ShotGridStorageRootModel](
            rows=[ShotGridStorageRootModel.model_validate(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def get_detail(cls, db: AsyncSession, storage_root_id: int) -> ShotGridStorageRootModel:
        root = await ShotGridStorageRootDao.get_by_id(db, storage_root_id)
        if root is None:
            raise shot_grid_error(404, 'SG_STORAGE_ROOT_NOT_FOUND', 'NAS 根目录配置不存在')
        return ShotGridStorageRootModel.model_validate(root)

    @classmethod
    async def create(
        cls,
        db: AsyncSession,
        command: ShotGridStorageRootCreateModel,
        current_user: CurrentUserModel,
    ) -> ShotGridStorageRootModel:
        actor_name, dept_name = cls._actor(current_user)
        now = cls._now()
        normalized_path = ShotGridProjectPathService.normalize_root_path(command.unc_root_path)
        root = ShotGridStorageRoot(
            root_code=command.root_code,
            root_name=command.root_name,
            protocol='smb_unc',
            unc_root_path=normalized_path,
            root_path_key=normalized_path.casefold(),
            credential_ref=None,
            root_status=command.root_status,
            last_probe_status='unknown',
            create_by=actor_name,
            create_time=now,
            update_by=actor_name,
            update_time=now,
            remark=command.remark,
            lock_version=0,
            del_flag='0',
        )
        try:
            await ShotGridStorageRootDao.add(db, root)
            await cls._audit(
                db,
                action='create',
                business_type=1,
                actor_name=actor_name,
                dept_name=dept_name,
                storage_root_id=root.storage_root_id,
                payload={'rootCode': root.root_code, 'rootName': root.root_name, 'rootStatus': root.root_status},
            )
            result = ShotGridStorageRootModel.model_validate(root)
            await db.commit()
            return result
        except IntegrityError as exc:
            await db.rollback()
            raise cls._duplicate_error(exc) from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def update(
        cls,
        db: AsyncSession,
        storage_root_id: int,
        command: ShotGridStorageRootUpdateModel,
        current_user: CurrentUserModel,
    ) -> ShotGridStorageRootModel:
        existing = await ShotGridStorageRootDao.get_by_id(db, storage_root_id)
        if existing is None:
            raise shot_grid_error(404, 'SG_STORAGE_ROOT_NOT_FOUND', 'NAS 根目录配置不存在')
        normalized_path = ShotGridProjectPathService.normalize_root_path(command.unc_root_path)
        path_changed = existing.root_path_key != normalized_path.casefold()
        re_enabled = existing.root_status == 'disabled' and command.root_status == 'enabled'
        actor_name, dept_name = cls._actor(current_user)
        now = cls._now()
        values = {
            'root_code': command.root_code,
            'root_name': command.root_name,
            'unc_root_path': normalized_path,
            'root_path_key': normalized_path.casefold(),
            'root_status': command.root_status,
            'update_by': actor_name,
            'update_time': now,
            'remark': command.remark,
        }
        if path_changed or re_enabled:
            values.update(
                last_probe_status='unknown',
                last_probe_time=None,
                last_error_key=None,
                last_error_message=None,
            )
        try:
            updated = await ShotGridStorageRootDao.update_fields(
                db,
                storage_root_id,
                command.lock_version,
                values,
            )
            if not updated:
                raise shot_grid_error(409, 'SG_CONCURRENT_MODIFICATION', 'NAS 根目录已被其他操作修改，请刷新后重试')
            await cls._audit(
                db,
                action='update',
                business_type=2,
                actor_name=actor_name,
                dept_name=dept_name,
                storage_root_id=storage_root_id,
                payload={
                    'rootCode': command.root_code,
                    'rootName': command.root_name,
                    'rootStatus': command.root_status,
                    'pathChanged': path_changed,
                },
            )
            await db.commit()
            return await cls.get_detail(db, storage_root_id)
        except IntegrityError as exc:
            await db.rollback()
            raise cls._duplicate_error(exc) from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def probe(
        cls,
        db: AsyncSession,
        storage_root_id: int,
        current_user: CurrentUserModel,
    ) -> ShotGridStorageRootProbeModel:
        root = await ShotGridStorageRootDao.get_by_id(db, storage_root_id)
        if root is None:
            raise shot_grid_error(404, 'SG_STORAGE_ROOT_NOT_FOUND', 'NAS 根目录配置不存在')
        root_path = root.unc_root_path
        expected_lock_version = root.lock_version
        actor_name, dept_name = cls._actor(current_user)

        # 结束只读事务后再进行 SMB I/O，避免探测期间占用数据库事务和连接锁。
        await db.rollback()
        try:
            probe_result = await asyncio.wait_for(asyncio.to_thread(cls._probe_path, root_path), timeout=15.0)
        except TimeoutError:
            # 线程中的 SMB 系统调用无法硬取消；随机文件名和 finally 清理保证其迟到完成仍是安全的。
            probe_result = _ProbeResult(
                'unreachable',
                'SG_STORAGE_ROOT_PROBE_TIMEOUT',
                '后端服务探测 UNC 根目录超时',
            )
        probe_time = cls._now()
        updated = await ShotGridStorageRootDao.update_fields(
            db,
            storage_root_id,
            expected_lock_version,
            {
                'last_probe_status': probe_result.status,
                'last_probe_time': probe_time,
                'last_error_key': probe_result.error_key,
                'last_error_message': probe_result.error_message,
                'update_by': actor_name,
                'update_time': probe_time,
            },
        )
        if not updated:
            await db.rollback()
            raise shot_grid_error(409, 'SG_CONCURRENT_MODIFICATION', '探测期间配置已被修改，结果未写入，请重新探测')
        await cls._audit(
            db,
            action='probe',
            business_type=0,
            actor_name=actor_name,
            dept_name=dept_name,
            storage_root_id=storage_root_id,
            payload={'probeStatus': probe_result.status},
        )
        await db.commit()
        return ShotGridStorageRootProbeModel(
            storageRootId=storage_root_id,
            lastProbeStatus=probe_result.status,
            lastProbeTime=probe_time,
            lastErrorKey=probe_result.error_key,
            lastErrorMessage=probe_result.error_message,
            lockVersion=expected_lock_version + 1,
        )

    @staticmethod
    def _probe_path(root_path: str) -> _ProbeResult:
        """在根目录创建、回读并删除随机临时文件，验证真实读写权限。"""

        if not os.path.isdir(root_path):
            return _ProbeResult('unreachable', 'SG_STORAGE_ROOT_UNREACHABLE', '后端服务无法访问该 UNC 根目录')

        probe_name = f'.shotgrid-probe-{secrets.token_hex(12)}.tmp'
        probe_path = os.path.join(root_path, probe_name)
        payload = secrets.token_bytes(32)
        created = False
        try:
            descriptor = os.open(probe_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            created = True
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            with open(probe_path, 'rb') as stream:
                if stream.read() != payload:
                    return _ProbeResult('unwritable', 'SG_STORAGE_ROOT_VERIFY_FAILED', '临时探测文件回读校验失败')
            os.remove(probe_path)
            created = False
            return _ProbeResult('healthy')
        except PermissionError:
            return _ProbeResult('unwritable', 'SG_STORAGE_ROOT_UNWRITABLE', '后端服务账号没有该目录的读写删除权限')
        except FileNotFoundError:
            return _ProbeResult('unreachable', 'SG_STORAGE_ROOT_UNREACHABLE', '探测期间 UNC 根目录不可达')
        except OSError as exc:
            if getattr(exc, 'winerror', None) in {5, 13}:
                return _ProbeResult('unwritable', 'SG_STORAGE_ROOT_UNWRITABLE', '后端服务账号没有该目录的读写删除权限')
            return _ProbeResult('unreachable', 'SG_STORAGE_ROOT_UNREACHABLE', '后端服务访问 UNC 根目录失败')
        finally:
            if created:
                try:
                    os.remove(probe_path)
                except OSError:
                    pass

    @staticmethod
    def _actor(current_user: CurrentUserModel) -> tuple[str, str | None]:
        user = current_user.user
        if user is None or user.user_id is None:
            raise shot_grid_error(401, 'SG_AUTH_REQUIRED', '当前登录信息无效')
        actor_name = user.user_name or str(user.user_id)
        dept_name = user.dept.dept_name if user.dept is not None else None
        return actor_name, dept_name

    @staticmethod
    def _now() -> datetime:
        return datetime.now().replace(microsecond=0)

    @staticmethod
    def _duplicate_error(exc: IntegrityError) -> ShotGridDomainException:
        message = str(getattr(exc, 'orig', exc)).lower()
        if 'uk_sg_storage_root_path_active' in message:
            return shot_grid_error(409, 'SG_STORAGE_ROOT_PATH_DUPLICATE', '该 UNC 根目录已经配置')
        return shot_grid_error(409, 'SG_STORAGE_ROOT_CODE_DUPLICATE', 'NAS 根目录编码已经存在')

    @staticmethod
    async def _audit(
        db: AsyncSession,
        *,
        action: str,
        business_type: int,
        actor_name: str,
        dept_name: str | None,
        storage_root_id: int,
        payload: dict,
    ) -> None:
        await ShotGridProjectAuditDao.add_success_log(
            db,
            title='Shot Grid NAS 根目录管理',
            business_type=business_type,
            method=f'module_shot_grid.service.storage_root_service.ShotGridStorageRootService.{action}()',
            request_method={'create': 'POST', 'update': 'PUT', 'probe': 'POST'}[action],
            oper_name=actor_name,
            dept_name=dept_name,
            oper_url=(
                f'/shot-grid/admin/storage-roots/{storage_root_id}'
                if action != 'create'
                else '/shot-grid/admin/storage-roots'
            ),
            oper_param={'storageRootId': storage_root_id, **payload},
            result={'storageRootId': storage_root_id, 'success': True},
        )

import hashlib
import uuid

from fastapi import Request
from redis import asyncio as aioredis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import RedisInitKeyConfig
from config.env import AppConfig
from module_admin.dao.user_dao import UserDao
from module_admin.entity.vo.user_vo import CurrentUserInfoModel, CurrentUserModel
from module_shot_grid.config import SHOT_GRID_PLAYBACK_CONFIG, ShotGridPlaybackConfig
from module_shot_grid.entity.vo.version_submission_vo import ShotGridPlaybackTicketPayloadModel
from module_shot_grid.exceptions import shot_grid_error
from utils.common_util import CamelCaseUtil
from utils.jwt_util import JwtUtil


class ShotGridPlaybackTicketService:
    """Redis 短期播放票据；Redis 不可用时失败关闭。"""

    @staticmethod
    def new_token() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    @classmethod
    async def create(
        cls,
        redis: aioredis.Redis,
        request: Request,
        *,
        version_id: int,
        file_id: str,
        current_user: CurrentUserModel,
        config: ShotGridPlaybackConfig = SHOT_GRID_PLAYBACK_CONFIG,
    ) -> str:
        user = current_user.user
        if user is None or user.user_id is None:
            raise shot_grid_error(403, 'SG_FILE_ACCESS_DENIED', '文件不存在或无权访问')
        authorization = request.headers.get('Authorization', '')
        access_token = authorization.removeprefix('Bearer ').strip()
        session_id = str(JwtUtil.decode(access_token).get('session_id') or '')
        if not access_token or not session_id:
            raise shot_grid_error(401, 'SG_PLAYBACK_SESSION_INVALID', '当前登录会话无效，请重新登录')
        token = cls.new_token()
        payload = ShotGridPlaybackTicketPayloadModel(
            versionId=version_id,
            fileId=file_id,
            userId=user.user_id,
            sessionId=session_id,
            accessTokenHash=cls.token_hash(access_token),
        )
        try:
            saved = await redis.set(
                cls._key(token, config),
                payload.model_dump_json(by_alias=True),
                ex=config.ticket_ttl_seconds,
                nx=True,
            )
        except RedisError as exc:
            raise shot_grid_error(503, 'SG_PLAYBACK_TICKET_STORE_UNAVAILABLE', '媒体播放票据服务暂不可用') from exc
        if not saved:
            raise shot_grid_error(409, 'SG_PLAYBACK_TICKET_CONFLICT', '媒体播放票据冲突，请重试')
        return token

    @classmethod
    async def get(
        cls,
        redis: aioredis.Redis,
        token: str,
        *,
        version_id: int,
        file_id: str,
        config: ShotGridPlaybackConfig = SHOT_GRID_PLAYBACK_CONFIG,
    ) -> ShotGridPlaybackTicketPayloadModel:
        try:
            value = await redis.get(cls._key(token, config))
        except RedisError as exc:
            raise shot_grid_error(503, 'SG_PLAYBACK_TICKET_STORE_UNAVAILABLE', '媒体播放票据服务暂不可用') from exc
        if value is None:
            raise shot_grid_error(403, 'SG_PLAYBACK_TICKET_INVALID', '媒体播放票据无效或已过期')
        try:
            payload = ShotGridPlaybackTicketPayloadModel.model_validate_json(value)
        except ValueError as exc:
            raise shot_grid_error(403, 'SG_PLAYBACK_TICKET_INVALID', '媒体播放票据无效或已过期') from exc
        if payload.version_id != version_id or payload.file_id != file_id:
            raise shot_grid_error(403, 'SG_PLAYBACK_TICKET_INVALID', '媒体播放票据与目标文件不匹配')
        try:
            session_key = (
                f'{RedisInitKeyConfig.ACCESS_TOKEN.key}:{payload.session_id}'
                if AppConfig.app_same_time_login
                else f'{RedisInitKeyConfig.ACCESS_TOKEN.key}:{payload.user_id}'
            )
            current_access_token = await redis.get(session_key)
        except RedisError as exc:
            raise shot_grid_error(503, 'SG_PLAYBACK_TICKET_STORE_UNAVAILABLE', '媒体播放票据服务暂不可用') from exc
        if not current_access_token or cls.token_hash(current_access_token) != payload.access_token_hash:
            raise shot_grid_error(403, 'SG_PLAYBACK_SESSION_INVALID', '当前登录会话已失效，请重新登录')
        return payload

    @classmethod
    async def load_current_user(cls, db: AsyncSession, user_id: int) -> CurrentUserModel:
        """每个 Range 请求从数据库重建用户权限，避免票据固化已撤销权限。"""

        query_user = await UserDao.get_user_by_id(db, user_id=user_id)
        basic = query_user.get('user_basic_info')
        if basic is None:
            raise shot_grid_error(403, 'SG_PLAYBACK_TICKET_INVALID', '媒体播放用户已不可用')
        role_rows = query_user.get('user_role_info') or []
        role_ids = [row.role_id for row in role_rows]
        permissions = (
            ['*:*:*'] if 1 in role_ids else [row.perms for row in (query_user.get('user_menu_info') or []) if row.perms]
        )
        if '*:*:*' not in permissions and 'shotgrid:file:download' not in permissions:
            raise shot_grid_error(403, 'SG_FILE_ACCESS_DENIED', '文件不存在或无权访问')
        return CurrentUserModel(
            permissions=permissions,
            roles=[row.role_key for row in role_rows],
            user=CurrentUserInfoModel(
                **CamelCaseUtil.transform_result(basic),
                postIds=','.join(str(row.post_id) for row in (query_user.get('user_post_info') or [])),
                roleIds=','.join(str(role_id) for role_id in role_ids),
                dept=CamelCaseUtil.transform_result(query_user.get('user_dept_info')),
                role=CamelCaseUtil.transform_result(role_rows),
            ),
        )

    @classmethod
    def _key(cls, token: str, config: ShotGridPlaybackConfig) -> str:
        return f'{config.redis_key_prefix}:{cls.token_hash(token)}'

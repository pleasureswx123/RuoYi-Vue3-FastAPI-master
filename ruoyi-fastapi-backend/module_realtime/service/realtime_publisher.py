import asyncio
import json
from uuid import uuid4

from redis.exceptions import RedisError

from config.get_redis import RedisUtil
from utils.log_util import logger

TOPIC = 'shot-grid.version'
CHANNEL_PREFIX = 'realtime:v1:'


async def _publish(version_id: int, reason: str) -> None:
    redis = await RedisUtil.create_redis_pool(log_enabled=False)
    try:
        await redis.publish(
            f'{CHANNEL_PREFIX}{TOPIC}:{version_id}',
            json.dumps(
                {
                    'type': 'event',
                    'eventId': str(uuid4()),
                    'topic': TOPIC,
                    'resourceId': version_id,
                    'event': 'version.changed',
                    'reason': reason,
                }
            ),
        )
    finally:
        await redis.aclose()


async def publish_version_changed(version_id: int, reason: str) -> None:
    """提交后发送失效提示；失败不反转业务成功，客户端定期补查。"""
    try:
        await asyncio.wait_for(_publish(version_id, reason), timeout=2)
    except (RedisError, TimeoutError, OSError):
        logger.warning('实时通知暂不可用，客户端将通过状态校验恢复')

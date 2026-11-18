import asyncio
import json
from uuid import uuid4

from redis.exceptions import RedisError

from config.get_redis import RedisUtil
from utils.log_util import logger

TOPIC = 'shot-grid.version'
INBOX_TOPIC = 'shot-grid.inbox'
CHANNEL_PREFIX = 'realtime:v1:'


async def _publish(version_id: int, reason: str, topic: str = TOPIC) -> None:
    redis = await RedisUtil.create_redis_pool(log_enabled=False)
    try:
        await redis.publish(
            f'{CHANNEL_PREFIX}{topic}:{version_id}',
            json.dumps(
                {
                    'type': 'event',
                    'eventId': str(uuid4()),
                    'topic': topic,
                    'resourceId': version_id,
                    'event': 'inbox.changed' if topic == INBOX_TOPIC else 'version.changed',
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


async def publish_inbox_changed(user_id: int) -> None:
    try:
        await asyncio.wait_for(_publish(user_id, 'inbox.changed', INBOX_TOPIC), timeout=2)
    except (RedisError, TimeoutError, OSError):
        logger.warning('个人消息唤醒失败，客户端将补查未读')
